(() => {
  'use strict';
  const form = document.querySelector('[data-service-form]');
  if (!form) return;
  const kind = form.dataset.serviceForm;
  const fields = form.querySelector('fieldset');
  const status = document.querySelector('#form-status');
  const receipt = document.querySelector('#receipt');
  const retry = document.querySelector('#retry-connection');
  const another = document.querySelector('#new-request');
  const storageKey = 'geekbird-submission-' + kind;
  if (window.GEEKBIRD_CONFIG?.isPreview) {
    const notice = document.createElement('p'); notice.className = 'preview-notice';
    notice.textContent = '测试预览：请使用虚构信息，提交仅供功能验收。'; form.before(notice);
  }
  let ready = false, busy = false, key, base = '';
  try {
    const value = window.GEEKBIRD_CONFIG?.apiBaseUrl;
    const url = new URL(value);
    if ((url.protocol === 'https:' || (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) && !url.username && !url.password && !url.search && !url.hash) base = value.replace(/\/$/, '');
  } catch { /* A disabled preview or missing configuration never submits elsewhere. */ }
  function message(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function submissionKey() {
    if (!key) {
      try { key = sessionStorage.getItem(storageKey); } catch {}
      if (!key || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key)) key = crypto.randomUUID();
      try { sessionStorage.setItem(storageKey, key); } catch {}
    }
    return key;
  }
  async function request(path, options = {}) {
    const response = await fetch(base + path, { ...options, mode: 'cors', credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(20000) });
    let data;
    try { data = await response.json(); } catch { throw new Error('服务暂时不可用，已填写的内容会保留，请稍后重试。'); }
    if (!response.ok) {
      const error = new Error(data.error?.message || '提交未完成，请稍后重试。');
      error.code = data.error?.code; error.fields = data.error?.fields; throw error;
    }
    return data;
  }
  async function connect() {
    ready = false; fields.disabled = true; retry.hidden = true;
    if (!base) { message('当前页面暂未开放提交，可以先通过 QQ 联系我们。', true); return; }
    message('正在确认服务是否开放…');
    try {
      const meta = await request('/meta');
      if (meta.consentVersion !== form.dataset.consentVersion) throw new Error('信息使用说明已更新，请刷新页面后重新阅读。');
      ready = kind === 'bookings' ? meta.acceptingBookings : meta.acceptingFeedback;
      fields.disabled = !ready;
      message(ready ? '带 * 的项目为必填，请按实际情况填写。' : meta.closedMessage);
      retry.hidden = ready;
    } catch (error) { message(error.name === 'TimeoutError' || error instanceof TypeError ? '暂时无法连接服务，请稍后重试，或通过 QQ 联系我们。' : error.message, true); retry.hidden = false; }
  }
  function localValidation() {
    if (kind === 'bookings') {
      const phone = form.elements.phone, qq = form.elements.qq;
      phone.setCustomValidity(phone.value.trim() || qq.value.trim() ? '' : '手机与 QQ 请至少填写一个。');
    } else {
      const first = form.querySelector('[name="serviceTypes"]');
      first.setCustomValidity(form.querySelector('[name="serviceTypes"]:checked') ? '' : '请选择服务内容。');
    }
  }
  form.addEventListener('input', localValidation);
  form.addEventListener('change', localValidation);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!ready || busy) return;
    localValidation(); if (!form.reportValidity()) return;
    const entries = new FormData(form), value = Object.fromEntries(entries);
    value.consent = form.elements.consent.checked; value.consentVersion = form.dataset.consentVersion;
    if (kind === 'feedback') {
      value.serviceTypes = entries.getAll('serviceTypes');
      for (const field of ['attitudeRating', 'skillRating', 'overallRating']) value[field] = Number(value[field]);
    }
    busy = true; fields.disabled = true; another.hidden = true; retry.hidden = true; message('正在提交，请稍候…');
    try {
      const data = await request('/' + kind, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': submissionKey() }, body: JSON.stringify(value) });
      ready = false; receipt.hidden = false; receipt.querySelector('strong').textContent = data.reference;
      receipt.querySelector('p').textContent = data.message; receipt.focus(); message('请保存编号，后续联系时可以提供。');
      another.textContent = kind === 'bookings' ? '开始另一份预约' : '填写另一份反馈'; another.hidden = false;
    } catch (error) {
      message(error.name === 'TimeoutError' || error instanceof TypeError ? '暂时未收到确认，内容已保留。请用原内容再次提交，我们会核对这次请求，避免重复记录。' : error.message, true);
      if (['IDEMPOTENCY_CONFLICT', 'SUBMISSION_EXPIRED'].includes(error.code)) { another.textContent = '已核对，需要开始新的提交'; another.hidden = false; }
      if (error.code === 'SUBMISSIONS_CLOSED') { ready = false; retry.hidden = false; }
      if (error.code === 'CONSENT_VERSION_CHANGED') ready = false;
      if (error.fields?.length) form.elements.namedItem(error.fields[0])?.focus?.();
    } finally { busy = false; fields.disabled = !ready; }
  });
  retry.addEventListener('click', connect);
  another.addEventListener('click', () => {
    key = undefined; try { sessionStorage.removeItem(storageKey); } catch {}
    form.reset(); receipt.hidden = true; another.hidden = true; connect();
  });
  connect();
})();
