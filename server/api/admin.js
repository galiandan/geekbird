'use strict';
const $ = selector => document.querySelector(selector);
const apiBase = new URL('api/', location.href).pathname;
const states = {
  bookings: { new: '待联系', contacted: '已联系', scheduled: '已安排', in_progress: '处理中', completed: '已结案', cancelled: '已取消' },
  feedback: { pending: '待核实', reviewed: '已核实', invalid: '无效' },
};
const labels = { id: '内部 ID', reference: '编号', createdAt: '提交时间', updatedAt: '更新时间', name: '姓名', gradeMajor: '年级与专业', phone: '手机', qq: 'QQ', email: '邮箱', device: '设备', os: '系统', issue: '故障描述', preferredContactTime: '方便联系时间', nameMajor: '姓名与专业', contactType: '联系类型', contact: '联系方式', bookingReference: '用户填写的预约编号', bookingId: '核实关联的预约 ID', serviceTypes: '服务内容', summary: '故障或咨询简述', volunteerNames: '志愿者姓名', reportedHours: '填报时长（小时）', confirmedHours: '确认时长（小时）', requestedOn: '预约或咨询日期', attitudeRating: '态度评分', skillRating: '技术评分', overallRating: '综合评分', comment: '评语', consentVersion: '信息说明版本' };
let page = 1, current, currentKind, settings, listRequest = 0;
function message(text, isError = false) { $('#message').textContent = text; $('#message').dataset.error = String(isError); }
function timestamp(value) { return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }); }
async function api(path, options = {}) {
  const response = await fetch(apiBase + path, { ...options, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(20000),
    headers: { 'Content-Type': 'application/json', 'X-GB-Request': 'records', ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || '操作未完成，请稍后重试。');
  return data;
}
function options(select, kind, all = false) {
  select.replaceChildren();
  for (const [key, label] of Object.entries({ ...(all ? { '': '全部状态' } : {}), ...states[kind] })) {
    select.add(new Option(label, key));
  }
}
function query() {
  const params = new URLSearchParams();
  for (const [key, value] of [['status', $('#filter-status').value], ['start', $('#start').value], ['end', $('#end').value]]) {
    if (value) params.set(key, value);
  }
  return params;
}
async function load() {
  const requestId = ++listRequest;
  const kind = $('#kind').value, params = query(); params.set('page', page);
  $('#record-total').textContent = '—';
  message('正在读取…'); $('#rows').replaceChildren(); $('#previous').disabled = $('#next').disabled = true;
  try {
    const result = await api(kind + '?' + params);
    if (requestId !== listRequest) return;
    for (const row of result.items) {
      const tr = document.createElement('tr');
      for (const [index, value] of [row.reference + '\n' + timestamp(row.createdAt), row.name || row.nameMajor, states[kind][row.status], row.device || row.volunteerNames].entries()) {
        const td = document.createElement('td');
        if (index === 2) { const badge = document.createElement('span'); badge.className = 'badge'; badge.dataset.state = row.status; badge.textContent = value; td.append(badge); }
        else td.textContent = value || '—';
        tr.append(td);
      }
      const cell = document.createElement('td'), button = document.createElement('button');
      button.type = 'button'; button.className = 'row-action'; button.textContent = '查看 / 处理'; button.addEventListener('click', () => open(kind, row.id)); cell.append(button); tr.append(cell); $('#rows').append(tr);
    }
    $('#record-total').textContent = result.total.toLocaleString('zh-CN');
    if (!result.items.length) {
      const tr = document.createElement('tr'), td = document.createElement('td'); td.colSpan = 5; td.className = 'empty';
      const title = document.createElement('strong'); title.textContent = '暂无匹配的记录';
      td.append(title, '新提交的记录会显示在这里，也可以调整筛选条件。'); tr.append(td); $('#rows').append(tr);
    }
    $('#count').textContent = `共 ${result.total} 条 · 第 ${page} 页`;
    $('#previous').disabled = page <= 1; $('#next').disabled = page * result.limit >= result.total;
    message(result.total ? '已读取当前记录。' : '当前筛选条件下没有记录。');
  } catch (error) { if (requestId === listRequest) message(error.message, true); }
}
async function open(kind, id) {
  try {
    const row = await api(kind + '/' + id); current = row; currentKind = kind;
    $('#detail-title').textContent = row.reference; $('#record-data').replaceChildren();
    for (const [key, label] of Object.entries(labels)) {
      if (!(key in row)) continue;
      const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = label;
      const value = row[key]; dd.textContent = key.endsWith('At') ? timestamp(value) : Array.isArray(value) ? value.map(item => ({ repair: '日常预约', purchase_advice: '产品导购' })[item] || item).join('、') : value ?? '未填写';
      $('#record-data').append(dt, dd);
    }
    options($('#record-status'), kind); $('#record-status').value = row.status;
    $('#notes').value = row.notes; $('#reason').value = ''; $('#hours').value = row.confirmedHours ?? ''; $('#association').value = row.bookingId || '';
    $('#hours-label').hidden = $('#association-label').hidden = kind !== 'feedback';
    $('#detail-message').textContent = ''; $('#events').replaceChildren();
    for (const event of row.events) {
      const pre = document.createElement('pre'); pre.textContent = `${timestamp(event.createdAt)} · ${event.actor}\n${event.changes}\n${event.reason}`; $('#events').append(pre);
    }
    if (!$('#detail').open) $('#detail').showModal();
  } catch (error) { message(error.message, true); $('#detail-message').textContent = error.message; }
}
function changeKind() {
  const kind = $('#kind').value, feedback = kind === 'feedback';
  $('#page-title').textContent = $('#breadcrumb').textContent = feedback ? '服务反馈' : '维修预约';
  $('#list-title').textContent = feedback ? '反馈记录' : '预约记录';
  $('#page-description').textContent = feedback ? '让每一份反馈，帮助服务变得更好。核实评价，确认志愿服务时长。' : '把每一次求助，变成有回应的服务。查看预约，跟进处理进度。';
  document.querySelectorAll('[data-kind]').forEach(button => {
    if (button.dataset.kind === kind) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  options($('#filter-status'), kind, true); page = 1; load();
}
$('#kind').addEventListener('change', changeKind);
document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
  $('#kind').value = button.dataset.kind; changeKind();
}));
$('#filters').addEventListener('submit', event => { event.preventDefault(); page = 1; load(); });
$('#previous').addEventListener('click', () => { page--; load(); });
$('#next').addEventListener('click', () => { page++; load(); });
$('#close-detail').addEventListener('click', () => $('#detail').close());
$('#reload-detail').addEventListener('click', () => open(currentKind, current.id));
$('#update').addEventListener('submit', async event => {
  event.preventDefault();
  const value = { version: current.version, status: $('#record-status').value, notes: $('#notes').value, reason: $('#reason').value };
  if (currentKind === 'feedback') Object.assign(value, { confirmedHours: $('#hours').value || null, bookingId: $('#association').value || null });
  $('#update-fields').disabled = true;
  try { await api(currentKind + '/' + current.id, { method: 'PATCH', body: JSON.stringify(value) }); await open(currentKind, current.id); $('#detail-message').textContent = '已保存。'; await load(); }
  catch (error) { $('#detail-message').textContent = error.message; }
  finally { $('#update-fields').disabled = false; }
});
function showReceiving() {
  $('#booking-state').textContent = settings.acceptingBookings ? '开放接收' : '暂停接收';
  $('#feedback-state').textContent = settings.acceptingFeedback ? '开放接收' : '暂停接收';
}
async function loadSettings() {
  try {
    settings = await api('settings'); $('#accept-booking').checked = settings.acceptingBookings; $('#accept-feedback').checked = settings.acceptingFeedback;
    showReceiving(); $('#closed-message').value = settings.closedMessage; $('#settings-fields').disabled = false;
  } catch (error) { message(error.message, true); }
}
$('#reload-settings').addEventListener('click', loadSettings);
$('#settings').addEventListener('submit', async event => {
  event.preventDefault(); const value = { version: settings.version, acceptingBookings: $('#accept-booking').checked, acceptingFeedback: $('#accept-feedback').checked, closedMessage: $('#closed-message').value };
  $('#settings-fields').disabled = true;
  try { settings = await api('settings', { method: 'PATCH', body: JSON.stringify(value) }); showReceiving(); message('接收设置已保存。'); }
  catch (error) { message(error.message, true); }
  finally { $('#settings-fields').disabled = false; }
});
$('#export').addEventListener('click', async () => {
  $('#export').disabled = true;
  try {
    const response = await fetch(apiBase + 'export/' + $('#kind').value + '?' + query(), { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error((await response.json()).error?.message || '导出失败。');
    const url = URL.createObjectURL(await response.blob()), link = document.createElement('a'); link.href = url; link.download = `geekbird-${$('#kind').value}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); message('导出已生成，请妥善保存。');
  } catch (error) { message(error.message, true); }
  finally { $('#export').disabled = false; }
});
options($('#filter-status'), 'bookings', true); load(); loadSettings();
