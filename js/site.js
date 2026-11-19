/* ZeroPoint Geospatial: small behaviours shared by every page. */
(function () {
  'use strict';

  /* ---- mobile navigation ---- */
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  function setNav(open) {
    if (!toggle || !nav) return;
    nav.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      setNav(toggle.getAttribute('aria-expanded') !== 'true');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a')) setNav(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setNav(false);
    });
    document.addEventListener('click', function (e) {
      if (!nav.contains(e.target) && !toggle.contains(e.target)) setNav(false);
    });
    window.matchMedia('(min-width: 1041px)').addEventListener('change', function () { setNav(false); });
  }

  /* ---- quote form: post to Formspree without leaving the page ---- */
  var form = document.getElementById('quote-form');
  if (form) {
    var status = form.querySelector('.form__status');
    var button = form.querySelector('button[type="submit"]');
    var idle = button ? button.textContent : '';
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (form.website && form.website.value) return;          /* honeypot */
      button.disabled = true;
      button.textContent = 'Sending';
      status.textContent = '';
      status.removeAttribute('data-state');
      fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } })
        .then(function (res) {
          if (!res.ok) throw new Error('send failed');
          form.reset();
          status.dataset.state = 'ok';
          status.textContent = 'Thank you. We have your request and will reply within two hours on business days.';
        })
        .catch(function () {
          status.dataset.state = 'error';
          status.textContent = 'That did not send. Please email or WhatsApp us directly.';
        })
        .then(function () {
          button.disabled = false;
          button.textContent = idle;
        });
    });
  }

  /* ---- prints catalogue: filter by series ---- */
  var filters = document.querySelectorAll('.filter');
  if (filters.length) {
    var cards = document.querySelectorAll('.print-card');
    filters.forEach(function (f) {
      f.addEventListener('click', function () {
        var series = f.dataset.series;
        filters.forEach(function (o) { o.setAttribute('aria-pressed', o === f ? 'true' : 'false'); });
        cards.forEach(function (c) { c.hidden = series !== 'all' && c.dataset.series !== series; });
      });
    });
  }

  /* ---- single print: frame preview, order message, zoom ---- */
  var order = document.getElementById('print-order');
  if (order) {
    var frame = document.querySelector('.print__stage .frame');
    var waLink = document.getElementById('order-wa');
    var mailLink = document.getElementById('order-mail');
    var name = order.dataset.print;
    function picked(group) {
      var el = order.querySelector('input[name="' + group + '"]:checked');
      return el ? el : null;
    }
    function update() {
      var size = picked('size'), fr = picked('frame');
      if (fr && frame) frame.dataset.frame = fr.value;
      var line = 'Hello ZeroPoint, I would like to order the print "' + name + '"' +
        (size ? ', size ' + size.dataset.label : '') +
        (fr ? ', ' + fr.dataset.label.toLowerCase() : '') + '.';
      if (waLink) waLink.href = 'https://wa.me/' + waLink.dataset.number + '?text=' + encodeURIComponent(line);
      if (mailLink) mailLink.href = 'mailto:' + mailLink.dataset.email + '?subject=' +
        encodeURIComponent('Print order: ' + name) + '&body=' + encodeURIComponent(line);
    }
    order.addEventListener('change', update);
    update();

    var zoom = document.getElementById('zoom');
    if (zoom && frame && zoom.showModal) {
      frame.addEventListener('click', function () {
        var img = zoom.querySelector('img');
        if (!img.src) img.src = img.dataset.src;
        zoom.showModal();
      });
      zoom.addEventListener('click', function () { zoom.close(); });
    }
  }
})();
