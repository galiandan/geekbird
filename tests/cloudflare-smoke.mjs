// Run against `wrangler pages dev` only; exercises actual routing, assets and local KV.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const base = 'http://127.0.0.1:8788';
const auth = 'Basic ' + Buffer.from('admin:local-test-password-only').toString('base64');
const hash = data => createHash('sha256').update(data).digest('hex');
for (const [route, name] of [['/', 'index.html'], ['/service/', 'service/index.html'], ['/disclaimer/', 'disclaimer/index.html'], ['/booking/', 'booking/index.html'], ['/assets/app.js', 'assets/app.js']]) {
  const result = await fetch(base + route);
  assert.equal(result.status, 200, route);
  assert.equal(hash(Buffer.from(await result.arrayBuffer())), hash(await readFile(new URL('../dist/cloudflare/' + name, import.meta.url))), route);
  assert.equal(result.headers.get('Cache-Control'), 'no-cache');
}
for (const route of ['/unknown-page', '/README.md', '/server/admin.py', '/cloudflare/admin.html', '/_worker.js', '/_headers', '/_routes.json']) {
  assert.equal((await fetch(base + route)).status, 404, route);
}
for (const route of ['/_gb-settings', '/_gb-settings/', '/_gb-settings/api']) {
  const result = await fetch(base + route);
  assert.equal(result.status, 401, route);
  assert.match(result.headers.get('WWW-Authenticate'), /Basic/);
}
const html = await fetch(base + '/_gb-settings/', { headers: { Authorization: auth } });
assert.equal(html.status, 200);
assert.match(await html.text(), /<form id="settings">/);
assert.equal(html.headers.get('Cache-Control'), 'no-store');
assert.match(html.headers.get('X-Robots-Tag'), /noindex/);
const api = '/_gb-settings/api';
const original = await (await fetch(base + api, { headers: { Authorization: auth } })).json();
async function save(config, origin = base) {
  return fetch(base + api, { method: 'PUT', headers: {
    Authorization: auth, Origin: origin, 'X-GB-Request': 'settings', 'Content-Type': 'application/json',
  }, body: JSON.stringify(config) });
}
try {
  const changed = { emergencyQQ: '123456789', bookingUrl: 'https://booking.example/form?from=smoke', feedbackUrl: 'https://feedback.example/form?from=smoke' };
  assert.equal((await save(changed)).status, 200);
  const publicConfig = await fetch(base + '/config.js');
  assert.equal(publicConfig.status, 200);
  assert.equal(publicConfig.headers.get('Cache-Control'), 'no-store');
  assert.ok((await publicConfig.text()).includes(JSON.stringify(changed)));
  assert.equal((await save(original, 'https://evil.example')).status, 403);
  assert.equal((await save({ ...changed, bookingUrl: 'javascript:alert(1)' })).status, 400);
} finally {
  assert.equal((await save(original)).status, 200, 'Restore local test configuration');
}
assert.match(await (await fetch(base + '/sitemap.xml')).text(), /https:\/\/geekbird\.org\/disclaimer\//);
assert.ok(!(await (await fetch(base + '/robots.txt')).text()).includes('_gb-settings'));
console.log('Cloudflare runtime verified: static assets, 404, private routes, headers, local KV writes and public configuration.');
