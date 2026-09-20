(() => {
  'use strict';
  const config = window.GEEKBIRD_CONFIG || {};
  function bindLinks(key, label, statusSelector) {
    let href = '';
    const route = key === 'bookingUrl' ? '/booking/' : '/feedback/';
    if (config[key] === route) href = route;
    const message = `${label}入口暂未开放，可以先通过 QQ 联系我们。`;
    document.querySelectorAll(`[data-config-link="${key}"]`).forEach(link => {
      if (href) {
        link.href = href;
        link.removeAttribute('aria-disabled');
        link.removeAttribute('title');
      } else {
        link.removeAttribute('href');
        link.setAttribute('aria-disabled', 'true');
        link.setAttribute('title', message);
      }
    });
    const status = document.querySelector(statusSelector);
    if (status) {
      status.hidden = Boolean(href);
      status.textContent = href ? '' : message;
    }
  }
  bindLinks('bookingUrl', '预约', '#booking-status');
  bindLinks('feedbackUrl', '反馈', '#feedback-status');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const qq = String(config.emergencyQQ || '');
  const contact = document.querySelector('.contact');
  document.querySelector('[data-qq]').textContent = /^[1-9]\d{4,14}$/.test(qq) ? qq : 'QQ 号暂未公布';
  const copyQQ = document.querySelector('[data-copy-qq]');
  copyQQ.disabled = !/^[1-9]\d{4,14}$/.test(qq);
  copyQQ.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(qq); document.querySelector('.contact-status').textContent = 'QQ 号已复制，添加好友后说说设备的情况吧。'; }
    catch { document.querySelector('.contact-status').textContent = '请长按或选中上方 QQ 号手动复制。'; }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && contact.open) { contact.open = false; contact.querySelector('summary').focus(); } });
  document.addEventListener('click', e => { if (!contact.contains(e.target)) contact.open = false; });
  if ('IntersectionObserver' in window && !reduced.matches) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.remove('pending'); observer.unobserve(entry.target); }
    }), {threshold: .08});
    document.querySelectorAll('.reveal').forEach(el => { el.classList.add('pending'); observer.observe(el); });
    reduced.addEventListener('change', () => { if (reduced.matches) { document.querySelectorAll('.pending').forEach(el => el.classList.remove('pending')); observer.disconnect(); } });
  }
  const home = document.querySelector('.hero-home');
  if (home) {
    const title = home.querySelector('h1');
    let index = 0;
    [...title.childNodes].forEach(node => {
      if (node.nodeType !== Node.TEXT_NODE) return;
      const fragment = document.createDocumentFragment();
      for (const char of node.textContent) { const span = document.createElement('span'); span.className = 'char'; span.style.setProperty('--i', index++); span.textContent = char; fragment.append(span); }
      node.replaceWith(fragment);
    });
    home.addEventListener('pointermove', e => {
      if (reduced.matches || e.pointerType !== 'mouse') return;
      home.style.setProperty('--mx', `${(e.clientX / innerWidth - .5) * 9}px`);
      home.style.setProperty('--my', `${(e.clientY / innerHeight - .5) * 7}px`);
    });
    home.addEventListener('pointerleave', () => { home.style.setProperty('--mx','0px'); home.style.setProperty('--my','0px'); });
    let scheduled = false;
    window.addEventListener('scroll', () => {
      if (scheduled || reduced.matches) return;
      scheduled = true;
      requestAnimationFrame(() => { home.style.setProperty('--zoom', 1.015 + Math.min(scrollY / home.offsetHeight,1) * .065); scheduled = false; });
    }, {passive:true});
  }
})();
