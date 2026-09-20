// Cloudflare Pages advanced-mode Worker. HTML is embedded by scripts/cloudflare.py.
const ADMIN_HTML = "__ADMIN_HTML__";
const ADMIN_PATH = '/_gb-settings';
const KEY = 'site-config';

function response(body, status = 200, extra = {}) {
  return new Response(body, { status, headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'X-Robots-Tag': 'noindex, nofollow, noarchive',
    ...extra,
  }});
}

async function authenticated(request, password) {
  if (typeof password !== 'string' || password.length < 16) return false;
  let supplied;
  try {
    const header = request.headers.get('Authorization') || '';
    if (!header.startsWith('Basic ')) return false;
    supplied = new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(atob(header.slice(6)), char => char.charCodeAt(0)));
  } catch { return false; }
  const encode = new TextEncoder();
  const [actual, expected] = await Promise.all([
    crypto.subtle.digest('SHA-256', encode.encode(supplied)),
    crypto.subtle.digest('SHA-256', encode.encode(`admin:${password}`)),
  ]);
  const a = new Uint8Array(actual), b = new Uint8Array(expected);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}

function validate(value, origin) {
  const keys = ['emergencyQQ', 'bookingUrl', 'feedbackUrl'];
  if (!value || keys.some(key => typeof value[key] !== 'string')) {
    throw new Error('请填写 QQ 号、预约和反馈链接。');
  }
  const config = Object.fromEntries(keys.map(key => [key, value[key].trim()]));
  if (config.emergencyQQ && !/^[1-9]\d{4,14}$/.test(config.emergencyQQ)) throw new Error('QQ 号应为 5–15 位数字，且不能以 0 开头。');
  for (const key of ['bookingUrl', 'feedbackUrl']) {
    const link = config[key];
    if (!link) continue;
    let url;
    try { url = new URL(link); } catch { throw new Error('请填写完整的 http:// 或 https:// 链接。'); }
    if (!['http:', 'https:'].includes(url.protocol) || [new URL(origin).hostname, 'geekbird.org', 'www.geekbird.org'].includes(url.hostname) || url.username || url.password || link.length > 4096 || /\s/.test(link)) {
      throw new Error('请使用外部平台的 HTTP(S) 链接，不要包含账号密码。');
    }
  }
  return config;
}

async function readConfig(request, env) {
  const saved = await env.SITE_CONFIG.get(KEY, 'json');
  if (saved !== null && Object.hasOwn(saved, 'feedbackUrl')) return validate(saved, new URL(request.url).origin);
  // Keep the existing configuration until the first successful save.
  const asset = await env.ASSETS.fetch(new Request(new URL('/config.js', request.url)));
  if (!asset.ok) throw new Error('Initial configuration is unavailable');
  const source = await asset.text();
  const read = key => {
    const match = source.match(new RegExp(key + '\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")'));
    if (!match) throw new Error('Initial configuration is invalid');
    return JSON.parse(match[1]);
  };
  // Only missing legacy fields inherit defaults; an explicit blank stays disabled.
  const config = saved === null
    ? { emergencyQQ: read('emergencyQQ'), bookingUrl: read('bookingUrl'), feedbackUrl: read('feedbackUrl') }
    : { ...saved, feedbackUrl: read('feedbackUrl') };
  return validate(config, new URL(request.url).origin);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const admin = url.pathname === ADMIN_PATH || url.pathname.startsWith(ADMIN_PATH + '/');
    if (url.pathname.startsWith('/_') && !admin) return response('{}', 404);
    if (!admin && url.pathname !== '/config.js') return env.ASSETS.fetch(request);
    if (admin) {
      if (url.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(url.hostname)) return response('{}', 403);
      if (typeof env.ADMIN_PASSWORD !== 'string' || env.ADMIN_PASSWORD.length < 16) {
        return response('{"error":"请先在 Cloudflare 设置至少 16 位的 ADMIN_PASSWORD Secret，并重新部署。"}', 503);
      }
      if (!await authenticated(request, env.ADMIN_PASSWORD)) {
        return response('{"error":"需要管理员身份验证。"}', 401, { 'WWW-Authenticate': 'Basic realm="Private", charset="UTF-8"' });
      }
    }
    if (url.pathname === '/config.js' && !['GET', 'HEAD'].includes(request.method)) return response('{}', 405, { Allow: 'GET, HEAD' });
    if (!env.SITE_CONFIG) {
      if (!admin) return env.ASSETS.fetch(request);
      return response('{"error":"请先在 Cloudflare 绑定 SITE_CONFIG KV 命名空间。"}', 503);
    }
    try {
      if (url.pathname === '/config.js') {
        const config = await readConfig(request, env);
        return response(request.method === 'HEAD' ? null : `window.GEEKBIRD_CONFIG = Object.freeze(${JSON.stringify(config)});\n`, 200,
          { 'Content-Type': 'application/javascript; charset=utf-8' });
      }
      if ([ADMIN_PATH, ADMIN_PATH + '/'].includes(url.pathname)) {
        if (!['GET', 'HEAD'].includes(request.method)) return response('{}', 405, { Allow: 'GET, HEAD' });
        return response(request.method === 'HEAD' ? null : ADMIN_HTML, 200, { 'Content-Type': 'text/html; charset=utf-8' });
      }
      if (url.pathname !== ADMIN_PATH + '/api') return response('{}', 404);
      if (request.method === 'GET') return response(JSON.stringify(await readConfig(request, env)));
      if (request.method !== 'PUT') return response('{}', 405, { Allow: 'GET, PUT' });
      if (request.headers.get('Origin') !== url.origin || request.headers.get('X-GB-Request') !== 'settings') return response('{}', 403);
      if (!request.headers.get('Content-Type')?.startsWith('application/json')) return response('{}', 415);
      // Bound the streamed body even when Content-Length is absent or incorrect.
      const reader = request.body?.getReader();
      if (!reader) return response('{}', 400);
      const chunks = []; let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 16384) { await reader.cancel(); return response('{}', 413); }
        chunks.push(value);
      }
      let config;
      try {
        const body = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
        config = validate(JSON.parse(new TextDecoder().decode(body)), url.origin);
      } catch (error) { return response(JSON.stringify({ error: error instanceof SyntaxError ? '提交内容格式不正确。' : error.message }), 400); }
      await env.SITE_CONFIG.put(KEY, JSON.stringify(config));
      return response(JSON.stringify(config));
    } catch {
      return response('{"error":"配置暂时无法读取或保存，请稍后重试。"}', 503);
    }
  },
};
