(function () {
  function cleanUnbuiltJekyllText() {
    const bodyText = document.body?.innerText || '';
    const looksUnbuilt = bodyText.includes('{%') || bodyText.includes('{{') || bodyText.trim().startsWith('---');

    if (!looksUnbuilt) return;

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const remove = [];
    let node;

    while ((node = walker.nextNode())) {
      const text = node.nodeValue || '';
      if (text.includes('{%') || text.includes('{{') || text.trim().startsWith('---')) {
        remove.push(node);
      }
    }

    remove.forEach((textNode) => textNode.parentNode?.removeChild(textNode));
    document.querySelectorAll('.jekyll-source').forEach((el) => el.remove());
    document.body.classList.remove('jekyll-ready');
  }

  cleanUnbuiltJekyllText();

  const mobileMenu = document.getElementById('mobileMenu');
  const hamburger = document.querySelector('.hamburger');
  const nav = document.querySelector('nav');

  function setMenuOpen(open) {
    mobileMenu?.classList.toggle('open', open);
    hamburger?.classList.toggle('open', open);
    hamburger?.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  window.toggleMenu = function () {
    setMenuOpen(!mobileMenu?.classList.contains('open'));
  };

  mobileMenu?.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => setMenuOpen(false));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setMenuOpen(false);
  });

  window.addEventListener('scroll', () => {
    nav?.classList.toggle('scrolled', window.scrollY > 8);
  }, { passive: true });

  window.handleSubmit = async function (event) {
    event.preventDefault();
    const form = event.target;
    const btn = document.getElementById('submitBtn');
    const success = document.getElementById('formSuccess');
    const originalText = btn?.textContent || 'Request Quote';

    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Sending...';
    }
    success?.classList.remove('show');

    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error('submit failed');
      form.reset();
      if (success) {
        success.textContent = "Thank you - we've received your request. Our team will respond within 2 hours on business days.";
        success.style.borderColor = '';
        success.style.color = '';
        success.style.background = '';
        success.classList.add('show');
        setTimeout(() => success.classList.remove('show'), 8000);
      }
    } catch {
      if (success) {
        success.textContent = 'Could not send. Please email or WhatsApp us directly.';
        success.style.borderColor = '#c0392b';
        success.style.color = '#c0392b';
        success.style.background = 'rgba(192,57,43,.08)';
        success.classList.add('show');
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    }
  };
})();
