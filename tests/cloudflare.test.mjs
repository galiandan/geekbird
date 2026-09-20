import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../dist/cloudflare/_worker.js', import.meta.url), 'utf8');
const { default: worker } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const initial = await readFile(new URL('../config.js', import.meta.url), 'utf8');
const password = 'test-only-long-password-123';
const origin = 'https://example.pages.dev';
const authorization = 'Basic ' + Buffer.from('admin:' + password).toString('base64');
function environment() {
  const values = new Map();
  return {
    ADMIN_PASSWORD: password,
    SITE_CONFIG: {
      get: async key => values.has(key) ? JSON.parse(values.get(key)) : null,
      put: async (key, value) => values.set(key, value),
    },
    ASSETS: { fetch: async request => new Response(new URL(request.url).pathname === '/config.js' ? initial : 'static page') },
  };
}
function request(path, { auth = true, method = 'GET', body, headers = {} } = {}) {
  return new Request(origin + path, { method,
    headers: { ...(auth ? { Authorization: authorization } : {}), ...headers }, body });
}
function save(env, config, headers = {}) {
  return worker.fetch(request('/_gb-settings/api', { method: 'PUT', body: JSON.stringify(config),
    headers: { Origin: origin, 'Content-Type': 'application/json', 'X-GB-Request': 'settings', ...headers } }), env);
}
const config = { emergencyQQ: '123456789', bookingUrl: 'https://booking.example/form?a=1&b=2#go', feedbackUrl: 'https://feedback.example/form' };

test('Pages control files are never served as public assets', async () => {
  for (const path of ['/_worker.js', '/_worker.js/anything', '/_routes.json', '/_headers']) {
    assert.equal((await worker.fetch(request(path, { auth: false }), environment())).status, 404);
  }
});

test('all management paths and writes require authentication; no secret leaks', async () => {
  const env = environment();
  for (const path of ['/_gb-settings', '/_gb-settings/', '/_gb-settings/api', '/_gb-settings/anything']) {
    for (const method of ['GET', 'PUT']) {
      const result = await worker.fetch(request(path, { auth: false, method }), env);
      assert.equal(result.status, 401);
      assert.match(result.headers.get('WWW-Authenticate'), /Basic/);
      assert.ok(!(await result.text()).includes('<form'));
    }
  }
  env.ADMIN_PASSWORD = 'short';
  assert.equal((await worker.fetch(request('/_gb-settings/'), env)).status, 503);
  env.ADMIN_PASSWORD = undefined;
  assert.equal((await worker.fetch(request('/_gb-settings/'), env)).status, 503);
});

test('authenticated admin is private and contains built HTML', async () => {
  const result = await worker.fetch(request('/_gb-settings/'), environment());
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('Cache-Control'), 'no-store');
  assert.match(result.headers.get('X-Robots-Tag'), /noindex/);
  const html = await result.text();
  assert.match(html, /<form id="settings">/);
  assert.match(html, /name="feedbackUrl"/);
});

test('initial settings load from existing config, then save reaches public config', async () => {
  const env = environment();
  const before = await worker.fetch(request('/_gb-settings/api'), env);
  assert.equal((await before.json()).emergencyQQ, '2657698039');
  assert.equal((await save(env, config)).status, 200);
  assert.deepEqual(await (await worker.fetch(request('/_gb-settings/api'), env)).json(), config);
  const publicConfig = await worker.fetch(request('/config.js', { auth: false }), env);
  assert.equal(publicConfig.status, 200);
  const text = await publicConfig.text();
  assert.match(text, /123456789/);
  assert.ok(!text.includes(password));
  assert.ok(text.includes(JSON.stringify(config)));
  assert.equal(publicConfig.headers.get('Cache-Control'), 'no-store');
});

test('blank settings intentionally disable contact and booking', async () => {
  const env = environment();
  const result = await save(env, { emergencyQQ: ' ', bookingUrl: '', feedbackUrl: '' });
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { emergencyQQ: '', bookingUrl: '', feedbackUrl: '' });
});

test('invalid input and cross-origin writes do not change saved configuration', async () => {
  const env = environment();
  await save(env, config);
  for (const change of [{ emergencyQQ: '01234' }, { emergencyQQ: 12345 }, { bookingUrl: 'javascript:alert(1)' },
    { bookingUrl: origin + '/booking/' }, { bookingUrl: 'http://example.pages.dev/booking/' },
    { bookingUrl: 'https://geekbird.org/booking/' }, { bookingUrl: 'https://www.geekbird.org/booking/' },
    { bookingUrl: 'https://user:pass@example.org/' }]) {
    assert.equal((await save(env, { ...config, ...change })).status, 400);
  }
  assert.equal((await save(env, config, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await save(env, config, { 'X-GB-Request': '' })).status, 403);
  assert.equal((await save(env, config, { 'Content-Type': 'text/plain' })).status, 415);
  assert.equal((await save(env, { ...config, bookingUrl: 'x'.repeat(17000) })).status, 413);
  assert.deepEqual(await (await worker.fetch(request('/_gb-settings/api'), env)).json(), config);
});

test('invalid persisted configuration fails without leaking arbitrary KV values', async () => {
  const env = environment();
  env.SITE_CONFIG.get = async () => ({ emergencyQQ: 'bad', bookingUrl: 'javascript:alert(1)', privateNote: 'do-not-publish' });
  const result = await worker.fetch(request('/config.js', { auth: false }), env);
  assert.equal(result.status, 503);
  assert.ok(!(await result.text()).includes('do-not-publish'));
  env.SITE_CONFIG.get = async () => ({ ...config, privateNote: 'do-not-publish' });
  assert.ok(!(await (await worker.fetch(request('/config.js', { auth: false }), env)).text()).includes('do-not-publish'));
});

test('public configuration methods, HEAD response and malformed JSON are handled', async () => {
  const env = environment();
  const head = await worker.fetch(request('/config.js', { method: 'HEAD', auth: false }), env);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal((await worker.fetch(request('/config.js', { method: 'POST', auth: false }), env)).status, 405);
  assert.equal((await worker.fetch(request('/_gb-settings/api', { method: 'PUT', body: '{',
    headers: { Origin: origin, 'X-GB-Request': 'settings', 'Content-Type': 'application/json' } }), env)).status, 400);
  delete env.SITE_CONFIG;
  assert.equal((await worker.fetch(request('/config.js', { method: 'POST', auth: false }), env)).status, 405);
});

test('KV failure reports failure, missing binding keeps static public website available', async () => {
  const env = environment();
  env.SITE_CONFIG.put = async () => { throw new Error('KV unavailable'); };
  assert.equal((await save(env, config)).status, 503);
  delete env.SITE_CONFIG;
  assert.equal((await worker.fetch(request('/_gb-settings/'), env)).status, 503);
  assert.equal(await (await worker.fetch(request('/config.js', { auth: false }), env)).text(), initial);
  assert.equal(await (await worker.fetch(request('/', { auth: false }), env)).text(), 'static page');
});

test('legacy records inherit feedback default, explicit blank remains disabled', async () => {
  const env = environment();
  const { feedbackUrl, ...legacy } = config;
  await env.SITE_CONFIG.put('site-config', JSON.stringify(legacy));
  const value = await (await worker.fetch(request('/_gb-settings/api'), env)).json();
  assert.equal(value.feedbackUrl, 'https://www.wjx.top/m/93298004.aspx');
  assert.equal((await save(env, legacy)).status, 400);
  assert.equal((await save(env, { ...config, feedbackUrl: '' })).status, 200);
  assert.equal((await (await worker.fetch(request('/_gb-settings/api'), env)).json()).feedbackUrl, '');
});
test('feedback validation rejects unsafe values without changing saved configuration', async () => {
  const env = environment();
  await save(env, config);
  for (const feedbackUrl of [null, 123, 'javascript:alert(1)', origin + '/feedback/', 'https://user:pass@example.org/', 'https://example.org:bad/', 'https://example.org/with space']) {
    assert.equal((await save(env, { ...config, feedbackUrl })).status, 400);
  }
  assert.deepEqual(await (await worker.fetch(request('/_gb-settings/api'), env)).json(), config);
});
