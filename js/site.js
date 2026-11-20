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

  /* ---- forms (quote, proof request): post to Formspree without leaving the page ---- */
  function send(action, data) {
    return fetch(action, { method: 'POST', body: data, headers: { Accept: 'application/json' } })
      .then(function (res) { if (!res.ok) throw new Error('send failed'); return res; });
  }
  document.querySelectorAll('#quote-form, form[data-ajax]').forEach(function (form) {
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
      send(form.action, new FormData(form))
        .then(function () {
          form.reset();
          status.dataset.state = 'ok';
          status.textContent = form.dataset.ok ||
            'Thank you. We have your request and will reply within two hours on business days.';
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
  });

  /* ---- field notes: filter by topic ---- */
  var topics = document.querySelectorAll('.topic-filter');
  if (topics.length) {
    var notes = document.querySelectorAll('.notes > li[data-topic]');
    topics.forEach(function (f) {
      f.addEventListener('click', function () {
        var t = f.dataset.topic;
        topics.forEach(function (o) { o.setAttribute('aria-pressed', o === f ? 'true' : 'false'); });
        notes.forEach(function (n) { n.hidden = t !== 'all' && n.dataset.topic !== t; });
      });
    });
  }

  /* ---- prints catalogue: filter by series ---- */
  var filters = document.querySelectorAll('.filter[data-series]');
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

  /* ---- county list: find a county by name ---- */
  var countyQ = document.getElementById('county-q');
  if (countyQ) {
    var countyCards = document.querySelectorAll('.catalogue--counties .print-card');
    var none = document.querySelector('.county-none');
    countyQ.addEventListener('input', function () {
      var q = countyQ.value.trim().toLowerCase();
      var shown = 0;
      countyCards.forEach(function (c) {
        var hit = !q || c.querySelector('h3').textContent.toLowerCase().indexOf(q) !== -1;
        c.hidden = !hit;
        if (hit) shown++;
      });
      if (none) none.hidden = shown > 0;
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
    var prices = {};
    try { prices = JSON.parse(order.dataset.prices || '{}'); } catch (err) { prices = {}; }
    var priceEl = document.querySelector('[data-price]');
    var noteEl = document.querySelector('[data-price-note]');
    var payBtn = document.getElementById('pay-now');
    var payNote = document.querySelector('[data-pay-note]');
    var paperNote = document.querySelector('[data-paper-note]');
    var paid = false;                       /* once paid, the Pay button does not come back */
    function ksh(n) { return 'KSh ' + n.toLocaleString('en-KE'); }
    /* the price of the current size and frame in KSh, or null when it is quoted by hand */
    function price() {
      var size = picked('size'), fr = picked('frame');
      var row = size && prices[size.value];
      var v = row && fr ? row[fr.value] : null;
      return typeof v === 'number' && v > 0 ? v : null;
    }
    /* "A2, black frame, matte paper" */
    function chosen() {
      var size = picked('size'), fr = picked('frame'), pa = picked('paper');
      return [size && size.dataset.label, fr && fr.dataset.label.toLowerCase(),
              pa && pa.dataset.label.toLowerCase() + ' paper'].filter(Boolean).join(', ');
    }
    order.price = price;
    function update() {
      var size = picked('size'), fr = picked('frame');
      if (fr && frame) frame.dataset.frame = fr.value;
      var amount = price();
      if (priceEl) priceEl.textContent = amount ? ksh(amount) : order.dataset.range;
      if (noteEl) noteEl.textContent = amount ? chosen().charAt(0).toUpperCase() + chosen().slice(1) + '.'
        : (size && size.value === 'custom' ? order.dataset.customNote : order.dataset.note);
      var pa = picked('paper');
      if (paperNote && pa) paperNote.textContent = pa.parentNode.title.charAt(0).toUpperCase() + pa.parentNode.title.slice(1) + '.';
      if (payBtn) {
        payBtn.hidden = paid || !amount;
        payBtn.querySelector('[data-pay-amount]').textContent = amount ? ksh(amount) : '';
      }
      if (payNote) payNote.hidden = paid || !amount;
      var pap = picked('paper');
      var line = 'Hello ZeroPoint, I would like to order the print "' + name + '"' +
        (size ? ', size ' + size.dataset.label : '') +
        (fr ? ', ' + fr.dataset.label.toLowerCase() : '') +
        (pap ? ', ' + pap.dataset.label.toLowerCase() + ' paper' : '') +
        (amount ? ' (' + ksh(amount) + ')' : '') + '.';
      if (waLink) waLink.href = 'https://wa.me/' + waLink.dataset.number + '?text=' + encodeURIComponent(line);
      if (mailLink) mailLink.href = 'mailto:' + mailLink.dataset.email + '?subject=' +
        encodeURIComponent('Print order: ' + name) + '&body=' + encodeURIComponent(line);
    }
    order.addEventListener('change', update);
    order.addEventListener('submit', function (e) { e.preventDefault(); });
    update();

    /* ---- checkout: customer details, then Paystack (M-Pesa or card) ---- */
    var checkout = document.getElementById('checkout');
    if (checkout && payBtn && checkout.showModal) {
      var cform = checkout.querySelector('form');
      var cstatus = cform.querySelector('.form__status');
      var summary = checkout.querySelector('[data-checkout-summary]');
      var payStatus = document.createElement('p');
      payStatus.className = 'form__status print__paid';
      payStatus.setAttribute('role', 'status');
      payBtn.parentNode.insertAdjacentElement('afterend', payStatus);
      function loadPaystack() {
        return new Promise(function (resolve, reject) {
          if (window.PaystackPop) return resolve();
          var s = document.createElement('script');
          s.src = 'https://js.paystack.co/v2/inline.js';
          s.onload = function () { resolve(); };
          s.onerror = function () { reject(new Error('Paystack did not load')); };
          document.head.appendChild(s);
        });
      }
      function selection() {
        var size = picked('size'), fr = picked('frame'), pa = picked('paper');
        return { size: size.dataset.label, frame: fr.dataset.label, paper: pa ? pa.dataset.label + ' paper' : '',
                 amount: price() };
      }
      payBtn.addEventListener('click', function () {
        var sel = selection();
        if (!sel.amount) return;
        summary.textContent = chosen() + ', ' + ksh(sel.amount);
        cstatus.textContent = '';
        checkout.showModal();
      });
      checkout.querySelector('[data-checkout-close]').addEventListener('click', function () { checkout.close(); });
      cform.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!cform.checkValidity()) { cform.reportValidity(); return; }
        var sel = selection();
        var d = Object.fromEntries(new FormData(cform).entries());
        var parts = d.name.trim().split(/\s+/);
        var fields = [
          ['Print', name], ['Size', sel.size], ['Frame', sel.frame], ['Paper', sel.paper],
          ['Name', d.name], ['Phone', d.phone], ['Delivery', d.delivery], ['Notes', d.notes || '']
        ];
        cstatus.textContent = 'Opening the payment window';
        loadPaystack().then(function () {
          checkout.close();                     /* the Paystack window cannot sit above a modal */
          new window.PaystackPop().newTransaction({
            key: checkout.dataset.key,
            email: d.email,
            amount: Math.round(sel.amount * 100),   /* in cents */
            currency: 'KES',
            firstName: parts[0],
            lastName: parts.slice(1).join(' '),
            phone: d.phone,
            metadata: {
              print: order.dataset.slug,
              custom_fields: fields.map(function (f) {
                return { display_name: f[0], variable_name: f[0].toLowerCase(), value: f[1] };
              })
            },
            onSuccess: function (t) {
              paid = true;
              payBtn.hidden = true;
              if (payNote) payNote.hidden = true;
              payStatus.dataset.state = 'ok';
              payStatus.textContent = 'Paid. Thank you. Your reference is ' + t.reference +
                '. We will call ' + d.phone + ' to arrange delivery.';
              var data = new FormData();
              data.append('_subject', 'Paid print order: ' + name + ' (' + t.reference + ')');
              fields.forEach(function (f) { data.append(f[0].toLowerCase(), f[1]); });
              data.append('email', d.email);
              data.append('amount', ksh(sel.amount));
              data.append('paystack_reference', t.reference);
              send(checkout.dataset.form, data).catch(function () {});   /* the payment is in Paystack either way */
              cform.reset();
              payStatus.scrollIntoView({ behavior: 'smooth', block: 'center' });
            },
            onCancel: function () {
              payStatus.dataset.state = 'error';
              payStatus.textContent = 'The payment window was closed before payment finished. You can try again, or order on WhatsApp.';
            },
            onError: function (err) {
              payStatus.dataset.state = 'error';
              payStatus.textContent = 'Payment could not start (' + (err && err.message || 'unknown error') + '). Please order on WhatsApp.';
            }
          });
        }).catch(function () {
          cstatus.dataset.state = 'error';
          cstatus.textContent = 'The payment service did not load. Check your connection, or order on WhatsApp.';
        });
      });
    }

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
