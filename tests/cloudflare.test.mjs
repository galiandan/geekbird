import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../dist/cloudflare/_worker.js', import.meta.url), 'utf8');
const { default: worker } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const initial = await readFile(new URL('../dist/cloudflare/config.js', import.meta.url), 'utf8');
const defaults = JSON.parse(initial.match(/Object.freeze\((.*)\);/)[1]);
const password = 'test-only-long-password-123';
const origin = 'https://example.pages.dev';
const authorization = 'Basic ' + Buffer.from('admin:' + password).toString('base64');
function environment() {
  const values = new Map();
  return { ADMIN_PASSWORD: password,
    SITE_CONFIG: { get: async key => values.has(key) ? JSON.parse(values.get(key)) : null, put: async (key, value) => values.set(key, value) },
    ASSETS: { fetch: async request => new Response(new URL(request.url).pathname === '/config.js' ? initial : 'static page') } };
}
function request(path, { auth = true, method = 'GET', body, headers = {} } = {}) {
  return new Request(origin + path, { method, headers: { ...(auth ? { Authorization: authorization } : {}), ...headers }, body });
}
function save(env, value, headers = {}) {
  return worker.fetch(request('/_gb-settings/api', { method: 'PUT', body: JSON.stringify(value),
    headers: { Origin: origin, 'Content-Type': 'application/json', 'X-GB-Request': 'settings', ...headers } }), env);
}
const value = { schemaVersion: 2, emergencyQQ: '123456789' };
test('private routes require authentication and built HTML has only current settings', async () => {
  const env = environment();
  for (const route of ['/_gb-settings', '/_gb-settings/', '/_gb-settings/api', '/_gb-settings/other']) {
    assert.equal((await worker.fetch(request(route, { auth: false }), env)).status, 401);
  }
  const response = await worker.fetch(request('/_gb-settings/'), env);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  const html = await response.text(); assert.match(html, /服务工作台/); assert.ok(!html.includes('name="bookingUrl"'));
  env.ADMIN_PASSWORD = 'short'; assert.equal((await worker.fetch(request('/_gb-settings/'), env)).status, 503);
});
test('legacy stored URLs cannot override site paths, API or public whitelist', async () => {
  const env = environment();
  await env.SITE_CONFIG.put('site-config', JSON.stringify({ emergencyQQ: '987654321', bookingUrl: 'https://www.wjx.top/old', feedbackUrl: '', apiBaseUrl: 'https://evil.example', privateNote: 'private-marker' }));
  const data = await (await worker.fetch(request('/_gb-settings/api'), env)).json();
  assert.deepEqual(data, { ...defaults, emergencyQQ: '987654321' });
  assert.equal(data.bookingUrl, '/booking/'); assert.equal(data.feedbackUrl, '/feedback/');
  const publicConfig = await worker.fetch(request('/config.js', { auth: false }), env);
  const text = await publicConfig.text(); assert.ok(!text.includes('private-marker')); assert.ok(!text.includes('wjx.top')); assert.ok(!text.includes('evil.example'));
});
test('v2 saves QQ, rejects stale pages and malformed values without changing state', async () => {
  const env = environment();
  assert.deepEqual(await (await worker.fetch(request('/_gb-settings/api'), env)).json(), defaults);
  assert.equal((await save(env, value)).status, 200);
  for (const invalid of [{ ...value, emergencyQQ: '01234' }, { emergencyQQ: '12345678', bookingUrl: '' }, { ...value, apiBaseUrl: 'https://evil.example' }, { ...value, schemaVersion: 3 }]) {
    assert.equal((await save(env, invalid)).status, 400);
  }
  assert.equal((await save(env, value, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await save(env, value, { 'X-GB-Request': '' })).status, 403);
  assert.equal((await save(env, value, { 'Content-Type': 'text/plain' })).status, 415);
  assert.equal((await save(env, { ...value, emergencyQQ: 'x'.repeat(17000) })).status, 413);
  assert.equal((await (await worker.fetch(request('/_gb-settings/api'), env)).json()).emergencyQQ, value.emergencyQQ);
  assert.equal((await save(env, { ...value, emergencyQQ: '' })).status, 200);
});
test('HEAD, infrastructure failures and missing KV have explicit behavior', async () => {
  const env = environment();
  const head = await worker.fetch(request('/config.js', { method: 'HEAD', auth: false }), env);
  assert.equal(head.status, 200); assert.equal(await head.text(), '');
  assert.equal((await worker.fetch(request('/config.js', { method: 'POST', auth: false }), env)).status, 405);
  env.SITE_CONFIG.get = async () => ({ emergencyQQ: 'bad' });
  assert.equal((await worker.fetch(request('/config.js', { auth: false }), env)).status, 503);
  delete env.SITE_CONFIG;
  assert.equal(await (await worker.fetch(request('/config.js', { auth: false }), env)).text(), initial);
  assert.equal((await worker.fetch(request('/_gb-settings/'), env)).status, 503);
  for (const route of ['/_worker.js', '/_routes.json', '/_headers', '/_worker.js/extra']) assert.equal((await worker.fetch(request(route, { auth: false }), env)).status, 404);
});
