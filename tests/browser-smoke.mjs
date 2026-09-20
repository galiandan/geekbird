// Start the local API and built static site as documented in docs/backend.md.
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
const { chromium } = await import(process.env.GEEKBIRD_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GB_BROWSER_BASE || 'http://127.0.0.1:8800';
const api = process.env.GB_BROWSER_API || 'http://127.0.0.1:8790';
const apiPrefix = process.env.GB_BROWSER_PREFIX || '';
if (!base.startsWith('http://127.0.0.1:') && !(base.endsWith('.geekbird.pages.dev') && apiPrefix === '/_gb-preview')) throw new Error('Use a local or isolated preview environment only.');
const password = process.env.GB_BROWSER_PASSWORD_FILE ? (await readFile(process.env.GB_BROWSER_PASSWORD_FILE, 'utf8')).trim() : 'local-browser-password-only';
const auth = 'Basic ' + Buffer.from('admin:' + password).toString('base64');
const adminBase = api + apiPrefix + '/_gb-data';
const browser = await chromium.launch({ headless: true, executablePath: process.env.GB_BROWSER_EXECUTABLE, args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
// Optional: serve the built assets under an allowed preview origin while testing
// the real remote HTTPS API. This does not publish a Cloudflare deployment.
if (process.env.GB_BROWSER_ASSETS) {
  const root = path.resolve(process.env.GB_BROWSER_ASSETS);
  await context.route(base + '/**', async route => {
    const url = new URL(route.request().url());
    let name = decodeURIComponent(url.pathname); if (name.endsWith('/')) name += 'index.html';
    const file = path.resolve(root, '.' + name);
    if (!file.startsWith(root + path.sep) || name.startsWith('/_')) return route.fulfill({ status: 404 });
    const type = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.webp': 'image/webp' }[path.extname(file)];
    try { await route.fulfill({ body: await readFile(file), contentType: type || 'application/octet-stream' }); }
    catch { await route.fulfill({ status: 404 }); }
  });
}
const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
const stamp = Date.now().toString(); const person = '验收测试' + stamp;
const output = process.env.GB_BROWSER_OUTPUT || '/tmp/geekbird-browser-results'; await mkdir(output, { recursive: true });
async function admin(path, method = 'GET', data) {
  let response;
  try { response = await context.request.fetch(adminBase + '/api/' + path, { method, data,
    headers: { Authorization: auth, Origin: api, 'X-GB-Request': 'records' } }); }
  catch { throw new Error('Unable to reach the test administration API.'); }
  assert.equal(response.status(), 200, await response.text()); return response.json();
}
async function ready() { await page.locator('form[data-service-form] > fieldset').waitFor(); await page.waitForFunction(() => !document.querySelector('form[data-service-form] > fieldset').disabled); }
try {
  const before = (await admin('bookings')).total;
  await page.goto(base + '/booking/'); await ready();
  await page.locator('[name=name]').fill(person); await page.locator('[name=gradeMajor]').fill('测试专业');
  await page.locator('[name=qq]').fill('12345678'); await page.locator('[name=device]').fill('测试设备');
  await page.locator('[name=os]').fill('测试系统'); await page.locator('[name=issue]').fill('功能验收使用的虚构故障描述');
  await page.locator('[name=consent]').check();
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0); });
  await page.screenshot({ path: output + '/booking-desktop.png', fullPage: true });
  // Commit on the server, then lose the reply. A retry must return the same record.
  let lost = false;
  await page.route('**/api/v1/bookings', async route => {
    if (route.request().method() !== 'POST' || lost) return route.continue();
    lost = true; await route.fetch(); await route.abort('failed');
  });
  await page.getByRole('button', { name: '提交预约' }).click();
  await page.waitForFunction(() => document.querySelector('#form-status').textContent.includes('暂时未收到确认'));
  assert.equal(await page.locator('[name=issue]').inputValue(), '功能验收使用的虚构故障描述');
  await page.getByRole('button', { name: '提交预约' }).click();
  await page.locator('#receipt').waitFor({ state: 'visible' });
  const reference = await page.locator('#receipt strong').textContent(); assert.match(reference, /^GB-B-/);
  const bookings = await admin('bookings'); assert.equal(bookings.total, before + 1);
  const booking = bookings.items.find(row => row.reference === reference); assert.ok(booking);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + '/feedback/'); await ready();
  await page.locator('[name=nameMajor]').fill(person + ' 测试专业'); await page.locator('[name=contact]').fill('12345678');
  await page.locator('[name=bookingReference]').fill(reference); await page.locator('[name=serviceTypes][value=repair]').check();
  await page.locator('[name=summary]').fill('功能验收测试'); await page.locator('[name=volunteerNames]').fill('测试志愿者');
  await page.locator('[name=reportedHours]').fill('2.5'); await page.locator('[name=requestedOn]').fill('2026-09-01');
  for (const name of ['attitudeRating', 'skillRating', 'overallRating']) await page.locator(`[name=${name}]`).selectOption('5');
  await page.locator('[name=consent]').check();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile horizontal overflow');
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0); });
  await page.screenshot({ path: output + '/feedback-mobile.png', fullPage: true });
  await page.getByRole('button', { name: '提交反馈' }).click(); await page.locator('#receipt').waitFor({ state: 'visible' });
  const feedbackRef = await page.locator('#receipt strong').textContent(); assert.match(feedbackRef, /^GB-F-/);
  const staff = await browser.newContext({ httpCredentials: { username: 'admin', password, origin: api }, viewport: { width: 1360, height: 900 } });
  const dashboard = await staff.newPage(); dashboard.on('pageerror', error => errors.push(error.message));
  await dashboard.goto(adminBase + '/');
  await dashboard.getByRole('row').filter({ hasText: reference }).getByRole('button').click();
  await dashboard.locator('#record-status').selectOption('contacted'); await dashboard.locator('#notes').fill('浏览器验收：已联系');
  await dashboard.getByRole('button', { name: '保存处理结果' }).click();
  await dashboard.waitForFunction(() => document.querySelector('#detail-message').textContent === '已保存。');
  assert.equal((await admin('bookings/' + booking.id)).status, 'contacted');
  await dashboard.locator('#close-detail').click(); await dashboard.locator('#kind').selectOption('feedback');
  await dashboard.getByRole('row').filter({ hasText: feedbackRef }).getByRole('button').click();
  await dashboard.locator('#record-status').selectOption('reviewed'); await dashboard.locator('#hours').fill('2');
  await dashboard.locator('#association').fill(booking.id); await dashboard.getByRole('button', { name: '保存处理结果' }).click();
  await dashboard.waitForFunction(() => document.querySelector('#detail-message').textContent === '已保存。');
  await dashboard.screenshot({ path: output + '/admin-feedback.png', fullPage: true });
  await dashboard.locator('#close-detail').click();
  const downloadPromise = dashboard.waitForEvent('download'); await dashboard.locator('#export').click(); const download = await downloadPromise;
  assert.equal(await download.failure(), null);
  const current = await admin('settings');
  try {
    await admin('settings', 'PATCH', { ...current, acceptingBookings: false });
    await page.goto(base + '/booking/');
    await page.waitForFunction(() => !document.querySelector('#retry-connection').hidden);
    assert.ok(await page.getByRole('button', { name: '提交预约' }).isDisabled());
  } finally {
    const latest = await admin('settings'); await admin('settings', 'PATCH', { ...current, version: latest.version });
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ result: 'passed', booking: reference, feedback: feedbackRef, checks: 'desktop, mobile, lost reply retry, admin workflow, confirmed hours, CSV, closed state', screenshots: output }));
  await staff.close();
} finally { await context.close(); await browser.close(); }
