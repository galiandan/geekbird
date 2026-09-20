import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const booking = 'https://www.wjx.top/m/93277562.aspx';
const feedback = 'https://www.wjx.top/m/93298004.aspx';
const source = readFileSync(new URL('../assets/app.js', import.meta.url), 'utf8');
const configSource = readFileSync(new URL('../config.js', import.meta.url), 'utf8');

test('default reservation goes straight to the booking form', () => {
  const context = { window: {} };
  vm.runInNewContext(configSource, context);
  assert.equal(context.window.GEEKBIRD_CONFIG.bookingUrl, booking);
  assert.equal(context.window.GEEKBIRD_CONFIG.feedbackUrl, feedback);
});

for (const file of ['index.html', 'service/index.html', 'disclaimer/index.html', 'booking/index.html']) {
  test(`${file} exposes direct booking and feedback links without an intermediate page`, () => {
    const html = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
    const anchors = html.match(/<a\b[^>]*>/g);
    assert.ok(!anchors.some(tag => tag.includes('href="/booking/"')));
    const reservations = anchors.filter(tag => tag.includes('data-config-link="bookingUrl"'));
    assert.ok(reservations.length >= 3);
    assert.ok(!html.includes(booking) && !html.includes(feedback));
    assert.ok(reservations.every(tag => !tag.includes('href=')));
    assert.ok(anchors.some(tag => tag.includes('data-config-link="feedbackUrl"') && tag.includes('button')));
    assert.match(html, /id="booking-status"/);
  });
}

function render(bookingUrl, withStatus = true, feedbackUrl) {
  const links = Array.from({ length: 4 }, () => ({
    attributes: { 'aria-disabled': 'true' },
    removeAttribute(name) { delete this[name]; delete this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = value; },
  }));
  const feedbackLinks = links.map(link => ({ ...link, attributes: { 'aria-disabled': 'true' } }));
  const status = { hidden: true, textContent: '' };
  const feedbackStatus = { hidden: true, textContent: '' };
  const copy = { addEventListener() {} };
  const document = {
    querySelectorAll(selector) { return ({ '[data-config-link="bookingUrl"]': links, '[data-config-link="feedbackUrl"]': feedbackLinks })[selector] || []; },
    querySelector(selector) {
      return ({ '#feedback-status': withStatus ? feedbackStatus : null, '#booking-status': withStatus ? status : null,
        '[data-qq]': {}, '[data-copy-qq]': copy, '.contact': {} })[selector] || null;
    },
    addEventListener() {},
  };
  if (arguments.length < 3) feedbackUrl = feedback;
  vm.runInNewContext(source, { window: { GEEKBIRD_CONFIG: { bookingUrl, feedbackUrl } }, document,
    URL, location: { origin: 'http://localhost:8080' }, matchMedia: () => ({ matches: true }) });
  return { links, status, feedbackLinks, feedbackStatus };
}

test('configuration updates every booking entry, not just the first', () => {
  const url = 'https://booking.example/new-form';
  assert.ok(render(url).links.every(link => link.href === url));
});

for (const value of ['', undefined, 'not a url', 'javascript:alert(1)', 'http://localhost:8080/booking/']) {
  test(`invalid or disabled booking (${value}) disables every entry and shows status`, () => {
    const { links, status } = render(value);
    assert.ok(links.every(link => !link.href && link.attributes['aria-disabled'] === 'true'));
    assert.equal(status.hidden, false);
    assert.match(status.textContent, /预约入口暂未开放/);
  });
}

test('missing optional status does not break contact initialization', () => {
  assert.doesNotThrow(() => render('', false));
});

test('feedback uses its own configured address and does not depend on booking', () => {
  const url = 'https://feedback.example/new-form';
  const result = render('', true, url);
  assert.ok(result.feedbackLinks.every(link => link.href === url && !link.attributes['aria-disabled']));
  assert.equal(result.feedbackStatus.hidden, true);
});
for (const value of ['', undefined, 'not a url', 'javascript:alert(1)', 'https://user:pass@example.org/', 'http://localhost:8080/feedback/']) {
  test(`invalid feedback (${value}) does not disable booking`, () => {
    const result = render(booking, true, value);
    assert.ok(result.feedbackLinks.every(link => !link.href && link.attributes['aria-disabled'] === 'true'));
    assert.equal(result.feedbackStatus.hidden, false);
    assert.ok(result.links.every(link => link.href === booking));
  });
}
