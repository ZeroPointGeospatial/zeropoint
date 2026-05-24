(function () {
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

    btn.disabled = true;
    success.classList.remove('show');

    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error('submit failed');
      form.reset();
      success.classList.add('show');
    } catch {
      success.textContent = 'Could not send. Please email or WhatsApp us directly.';
      success.style.borderColor = '#c0392b';
      success.style.color = '#c0392b';
      success.style.background = 'rgba(192,57,43,.08)';
      success.classList.add('show');
    } finally {
      btn.disabled = false;
    }
  };
})();
