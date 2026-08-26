(function () {
  'use strict';

  const mobileMenu = document.getElementById('mobileMenu');
  const hamburger = document.querySelector('.hamburger');
  const nav = document.querySelector('nav');

  /* Keep the mobile menu CLOSED unless the user explicitly opens it. */
  function setMenuOpen(open) {
    const isMobile = window.innerWidth <= 900;
    const shouldOpen = Boolean(open) && isMobile;

    if (mobileMenu) {
      mobileMenu.classList.toggle('open', shouldOpen);
      mobileMenu.hidden = !shouldOpen;
      mobileMenu.style.display = shouldOpen ? 'flex' : 'none';
    }
    if (hamburger) {
      hamburger.classList.toggle('open', shouldOpen);
      hamburger.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
    }
    document.body.classList.toggle('menu-open', shouldOpen);
  }

  /* Force a clean initial state before anything else can display the menu. */
  setMenuOpen(false);

  window.toggleMenu = function () {
    const open = mobileMenu && mobileMenu.classList.contains('open');
    setMenuOpen(!open);
  };

  mobileMenu?.querySelectorAll('a').forEach(function (link) {
    link.addEventListener('click', function () {
      setMenuOpen(false);
    });
  });

  document.addEventListener('click', function (event) {
    if (!mobileMenu?.classList.contains('open')) return;
    if (mobileMenu.contains(event.target) || hamburger?.contains(event.target)) return;
    setMenuOpen(false);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') setMenuOpen(false);
  });

  window.addEventListener('resize', function () {
    setMenuOpen(false);
    syncFloatingControls();
  });

  /* Keep the floating contact controls working on every page. */
  function syncFloatingControls() {
    const mobile = window.innerWidth <= 800;
    const mobileBar = document.querySelector('.mobile-bar');
    const whatsapp = document.querySelector('.whatsapp-btn');

    if (mobileBar) mobileBar.style.display = mobile ? 'flex' : 'none';

    if (whatsapp) {
      whatsapp.style.width = '56px';
      whatsapp.style.height = '56px';
      whatsapp.style.display = 'flex';
      whatsapp.style.alignItems = 'center';
      whatsapp.style.justifyContent = 'center';
      whatsapp.style.position = 'fixed';
      whatsapp.style.right = '20px';
      whatsapp.style.bottom = mobile ? '76px' : '20px';
      whatsapp.style.zIndex = '90';
      whatsapp.style.borderRadius = '50%';
      whatsapp.style.padding = '0';
      whatsapp.style.overflow = 'hidden';
      const icon = whatsapp.querySelector('svg');
      if (icon) {
        icon.style.width = '27px';
        icon.style.height = '27px';
        icon.style.display = 'block';
        icon.style.flex = '0 0 27px';
      }
    }
  }
  syncFloatingControls();

  /* Do not let scrolling turn the Projects-style navbar into a different navbar. */
  window.addEventListener('scroll', function () {
    nav?.classList.remove('scrolled');
  }, { passive: true });
  nav?.classList.remove('scrolled');

  /* Shared navbar: intentionally matches the clean Projects page navbar. */
  const navStyle = document.createElement('style');
  navStyle.id = 'zp-unified-navbar';
  navStyle.textContent = `
    nav {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      z-index: 1000 !important;
      min-height: 74px !important;
      padding: .75rem 5.2% !important;
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      background: rgba(11,13,12,.94) !important;
      border-bottom: 1px solid rgba(255,255,255,.12) !important;
      box-shadow: none !important;
      backdrop-filter: blur(14px) !important;
      -webkit-backdrop-filter: blur(14px) !important;
    }
    nav.scrolled {
      background: rgba(11,13,12,.94) !important;
      border-bottom-color: rgba(255,255,255,.12) !important;
      box-shadow: none !important;
    }
    nav .nav-logo {
      display: flex !important;
      align-items: center !important;
      gap: .7rem !important;
      flex-shrink: 0 !important;
      text-decoration: none !important;
    }
    nav .nav-logo img {
      width: auto !important;
      height: 42px !important;
      display: block !important;
      border-radius: 0 !important;
    }
    nav .nav-brand-text {
      display: flex !important;
      flex-direction: column !important;
      line-height: 1.1 !important;
    }
    nav .nav-brand-text .name {
      font-size: .92rem !important;
      font-weight: 700 !important;
      letter-spacing: 1.5px !important;
    }
    nav .nav-brand-text .blue { color: #fff !important; }
    nav .nav-brand-text .green { color: #aab590 !important; }
    nav .nav-brand-text .tagline {
      margin-top: 3px !important;
      color: rgba(255,255,255,.46) !important;
      font-size: .57rem !important;
      letter-spacing: 1.4px !important;
      text-transform: uppercase !important;
    }
    nav .nav-links {
      display: flex !important;
      align-items: center !important;
      gap: 1.45rem !important;
      list-style: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    nav .nav-links li {
      list-style: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    nav .nav-links a {
      color: rgba(255,255,255,.70) !important;
      text-decoration: none !important;
      font-size: .68rem !important;
      font-weight: 500 !important;
      letter-spacing: 1.1px !important;
      text-transform: uppercase !important;
      white-space: nowrap !important;
    }
    nav .nav-links a:hover { color: #fff !important; }
    nav .nav-cta {
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      background: #fff !important;
      color: #111 !important;
      border: 0 !important;
      border-radius: 0 !important;
      padding: .68rem 1rem !important;
      font-size: .66rem !important;
      font-weight: 600 !important;
      letter-spacing: 1.2px !important;
      text-transform: uppercase !important;
      text-decoration: none !important;
      white-space: nowrap !important;
    }
    nav .nav-cta:hover { background: #aab590 !important; color: #111 !important; }
    nav .hamburger { display: none !important; }
    .mobile-menu { display: none !important; }
    .mobile-menu.open { display: flex !important; flex-direction: column !important; }

    @media (max-width: 900px) {
      nav {
        min-height: 74px !important;
        padding: .75rem 5% !important;
      }
      nav .nav-links,
      nav > .nav-cta { display: none !important; }
      nav .hamburger {
        display: flex !important;
        flex-direction: column !important;
        gap: 5px !important;
        padding: 6px !important;
        border: 0 !important;
        background: transparent !important;
        cursor: pointer !important;
      }
      nav .hamburger span {
        display: block !important;
        width: 24px !important;
        height: 2px !important;
        background: #fff !important;
        transition: .2s !important;
      }
      nav .nav-logo img { height: 42px !important; }
      .mobile-menu {
        position: fixed !important;
        top: 74px !important;
        left: 0 !important;
        right: 0 !important;
        z-index: 9999 !important;
        max-height: calc(100vh - 74px) !important;
        overflow: auto !important;
        background: #0b0d0c !important;
        padding: 1rem 5% !important;
        border-bottom: 1px solid rgba(255,255,255,.12) !important;
        box-shadow: 0 18px 40px rgba(0,0,0,.24) !important;
      }
      .mobile-menu.open { display: flex !important; }
      .mobile-menu a {
        display: block !important;
        padding: .8rem 0 !important;
        color: rgba(255,255,255,.82) !important;
        border-bottom: 1px solid rgba(255,255,255,.10) !important;
        font-size: .8rem !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
        text-decoration: none !important;
      }
    }
    @media (max-width: 560px) {
      nav .nav-brand-text .tagline { display: none !important; }
      nav .nav-logo img { height: 39px !important; }
    }
    @media (min-width: 901px) {
      .mobile-menu,
      nav .hamburger { display: none !important; }
    }
  `;
  document.head.appendChild(navStyle);

  /* Contact section polish: keep the existing form and Calendly functionality, only fix presentation. */
  const contactStyle = document.createElement('style');
  contactStyle.id = 'zp-contact-polish';
  contactStyle.textContent = `
    #contact .contact-wrap {
      align-items: start !important;
    }
    #contact .calendly-wrap {
      width: 100% !important;
      min-width: 0 !important;
    }
    #contact .calendly-inline-widget {
      width: 100% !important;
      min-width: 0 !important;
      height: 680px !important;
      min-height: 680px !important;
      overflow: hidden !important;
      background: #fff !important;
    }
    #contact .calendly-inline-widget iframe {
      width: 100% !important;
      min-width: 0 !important;
      height: 680px !important;
      min-height: 680px !important;
      border: 0 !important;
    }
    #contact .contact-form-wrap {
      width: 100% !important;
      overflow: hidden !important;
      background: #f4f3ee !important;
      border: 1px solid #d5d5ce !important;
    }
    #contact .form-img {
      display: block !important;
      width: 100% !important;
      height: 190px !important;
      object-fit: cover !important;
      object-position: center !important;
      filter: grayscale(.35) saturate(.55) !important;
    }
    #contact .contact-form {
      display: block !important;
      padding: 1.75rem !important;
    }
    #contact .form-row {
      display: grid !important;
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      gap: 1rem !important;
      margin: 0 0 1rem !important;
    }
    #contact .form-group {
      display: flex !important;
      flex-direction: column !important;
      min-width: 0 !important;
      width: 100% !important;
      gap: .4rem !important;
    }
    #contact .form-group label {
      display: block !important;
      margin: 0 !important;
      line-height: 1.2 !important;
    }
    #contact .form-group input,
    #contact .form-group select,
    #contact .form-group textarea {
      display: block !important;
      width: 100% !important;
      min-width: 0 !important;
      min-height: 42px !important;
      padding: .7rem .75rem !important;
      font: inherit !important;
      font-size: .82rem !important;
      line-height: 1.3 !important;
    }
    #contact .form-group select {
      appearance: auto !important;
      -webkit-appearance: auto !important;
    }
    #contact .hidden-field {
      display: none !important;
      visibility: hidden !important;
    }
    #contact .submit-btn {
      display: block !important;
      width: 100% !important;
      min-height: 48px !important;
      margin-top: .25rem !important;
    }
    #contact .form-success {
      margin-top: .8rem !important;
      line-height: 1.55 !important;
    }
    .whatsapp-btn {
      width: 56px !important;
      height: 56px !important;
      min-width: 56px !important;
      min-height: 56px !important;
      padding: 0 !important;
      border-radius: 50% !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      background: #0b0d0c !important;
      color: #fff !important;
      border: 1px solid rgba(255,255,255,.16) !important;
      box-shadow: 0 8px 24px rgba(0,0,0,.16) !important;
      overflow: hidden !important;
    }
    .whatsapp-btn svg {
      width: 27px !important;
      height: 27px !important;
      display: block !important;
      flex: 0 0 27px !important;
    }
    @media (max-width: 900px) {
      #contact .form-row {
        grid-template-columns: 1fr !important;
        gap: .85rem !important;
      }
      #contact .calendly-inline-widget,
      #contact .calendly-inline-widget iframe {
        height: 650px !important;
        min-height: 650px !important;
      }
    }
  `;
  document.head.appendChild(contactStyle);

  /* Existing Jekyll fallback cleanup. */
  function cleanUnbuiltJekyllText() {
    const bodyText = document.body?.innerText || '';
    const looksUnbuilt = bodyText.includes('{%') || bodyText.includes('{{') || bodyText.trim().startsWith('---');
    if (!looksUnbuilt) return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const remove = [];
    let node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue || '';
      if (text.includes('{%') || text.includes('{{') || text.trim().startsWith('---')) remove.push(node);
    }
    remove.forEach(function (textNode) { textNode.parentNode?.removeChild(textNode); });
    document.querySelectorAll('.jekyll-source').forEach(function (el) { el.remove(); });
    document.body.classList.remove('jekyll-ready');
  }
  cleanUnbuiltJekyllText();

  /* Existing quote form submission. */
  window.handleSubmit = async function (event) {
    event.preventDefault();
    const form = event.target;
    const btn = document.getElementById('submitBtn');
    const success = document.getElementById('formSuccess');
    const originalText = btn?.textContent || 'Request Quote';
    if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
    success?.classList.remove('show');

    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' }
      });
      if (!res.ok) throw new Error('submit failed');
      form.reset();
      if (success) {
        success.textContent = "Thank you - we've received your request. Our team will respond within 2 hours on business days.";
        success.style.borderColor = '';
        success.style.color = '';
        success.style.background = '';
        success.classList.add('show');
        setTimeout(function () { success.classList.remove('show'); }, 8000);
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
      if (btn) { btn.disabled = false; btn.textContent = originalText; }
    }
  };
})();
