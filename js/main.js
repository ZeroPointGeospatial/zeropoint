(function () {
  // Hide the mobile menu immediately, before any other page logic runs.
  // This prevents the menu from ever appearing as a permanent open panel.
  const mobileMenu = document.getElementById('mobileMenu');
  const hamburger = document.querySelector('.hamburger');
  const nav = document.querySelector('nav');
  if (mobileMenu) {
    mobileMenu.classList.remove('open');
    mobileMenu.hidden = true;
    mobileMenu.style.display = 'none';
  }
  if (hamburger) hamburger.setAttribute('aria-expanded', 'false');

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
    remove.forEach((textNode) => textNode.parentNode?.removeChild(textNode));
    document.querySelectorAll('.jekyll-source').forEach((el) => el.remove());
    document.body.classList.remove('jekyll-ready');
  }

  cleanUnbuiltJekyllText();

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
    }
  }

  function setMenuOpen(open) {
    const shouldOpen = Boolean(open) && window.innerWidth <= 800;
    mobileMenu?.classList.toggle('open', shouldOpen);
    hamburger?.classList.toggle('open', shouldOpen);
    hamburger?.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
    document.body.classList.toggle('menu-open', shouldOpen);
    if (mobileMenu) {
      mobileMenu.hidden = !shouldOpen;
      mobileMenu.style.display = shouldOpen ? 'flex' : 'none';
    }
  }

  // Always start closed. Desktop should never show the mobile menu.
  setMenuOpen(false);
  syncFloatingControls();

  window.toggleMenu = function () {
    setMenuOpen(!mobileMenu?.classList.contains('open'));
  };

  mobileMenu?.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => setMenuOpen(false));
  });

  document.addEventListener('click', (e) => {
    if (!mobileMenu?.classList.contains('open')) return;
    if (mobileMenu.contains(e.target) || hamburger?.contains(e.target)) return;
    setMenuOpen(false);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setMenuOpen(false);
  });

  window.addEventListener('resize', () => {
    setMenuOpen(false);
    syncFloatingControls();
  }, { passive: true });

  window.addEventListener('scroll', () => {
    nav?.classList.toggle('scrolled', window.scrollY > 8);
  }, { passive: true });

  window.handleSubmit = async function (event) {
    event.preventDefault();
    const form = event.target;
    const btn = document.getElementById('submitBtn');
    const success = document.getElementById('formSuccess');
    const originalText = btn?.textContent || 'Request Quote';
    if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
    success?.classList.remove('show');
    try {
      const res = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error('submit failed');
      form.reset();
      if (success) {
        success.textContent = "Thank you - we've received your request. Our team will respond within 2 hours on business days.";
        success.style.borderColor = ''; success.style.color = ''; success.style.background = '';
        success.classList.add('show');
        setTimeout(() => success.classList.remove('show'), 8000);
      }
    } catch {
      if (success) {
        success.textContent = 'Could not send. Please email or WhatsApp us directly.';
        success.style.borderColor = '#c0392b'; success.style.color = '#c0392b'; success.style.background = 'rgba(192,57,43,.08)';
        success.classList.add('show');
      }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = originalText; }
    }
  };

  const polish = document.createElement('style');
  polish.id = 'zp-small-polish';
  polish.textContent = `
    /* Shared navbar: intentionally matches the clean Projects page navbar. */
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
    nav .nav-logo { display:flex !important; align-items:center !important; gap:.7rem !important; flex-shrink:0 !important; text-decoration:none !important; }
    nav .nav-logo img { width:auto !important; height:42px !important; display:block !important; border-radius:0 !important; }
    nav .nav-brand-text { display:flex !important; flex-direction:column !important; line-height:1.1 !important; }
    nav .nav-brand-text .name { font-size:.92rem !important; font-weight:700 !important; letter-spacing:1.5px !important; }
    nav .nav-brand-text .blue { color:#fff !important; }
    nav .nav-brand-text .green { color:#aab590 !important; }
    nav .nav-brand-text .tagline { margin-top:3px !important; color:rgba(255,255,255,.46) !important; font-size:.57rem !important; letter-spacing:1.4px !important; text-transform:uppercase !important; }
    nav.scrolled .nav-brand-text .name .blue,
    nav.scrolled .nav-brand-text .name .green,
    nav.scrolled .nav-brand-text .tagline { color:inherit !important; }
    nav.scrolled .nav-brand-text .name .blue { color:#fff !important; }
    nav.scrolled .nav-brand-text .name .green { color:#aab590 !important; }
    nav.scrolled .nav-brand-text .tagline { color:rgba(255,255,255,.46) !important; }
    nav .nav-links { display:flex !important; align-items:center !important; gap:1.45rem !important; list-style:none !important; margin:0 !important; padding:0 !important; }
    nav .nav-links li { list-style:none !important; margin:0 !important; padding:0 !important; }
    nav .nav-links a { color:rgba(255,255,255,.70) !important; text-decoration:none !important; font-size:.68rem !important; font-weight:500 !important; letter-spacing:1.1px !important; text-transform:uppercase !important; white-space:nowrap !important; }
    nav .nav-links a:hover { color:#fff !important; }
    nav .nav-cta { display:inline-flex !important; align-items:center !important; justify-content:center !important; background:#fff !important; color:#111 !important; border:0 !important; border-radius:0 !important; padding:.68rem 1rem !important; font-size:.66rem !important; font-weight:600 !important; letter-spacing:1.2px !important; text-transform:uppercase !important; text-decoration:none !important; white-space:nowrap !important; }
    nav .nav-cta:hover { background:#aab590 !important; color:#111 !important; }
    nav .hamburger { display:none !important; }
    .mobile-menu { display:none !important; }
    .mobile-menu.open { display:flex !important; flex-direction:column !important; }
    @media (max-width: 900px) {
      nav { min-height:64px !important; padding:.65rem 5% !important; }
      nav .nav-links, nav > .nav-cta { display:none !important; }
      nav .hamburger { display:flex !important; flex-direction:column !important; gap:5px !important; padding:6px !important; border:0 !important; background:transparent !important; cursor:pointer !important; }
      nav .hamburger span { display:block !important; width:24px !important; height:2px !important; background:#fff !important; transition:.2s !important; }
      nav .nav-logo img { height:42px !important; }
      nav .nav-brand-text .tagline { display:block !important; }
      .mobile-menu { top:64px !important; left:0 !important; right:0 !important; z-index:9999 !important; background:#0b0d0c !important; padding:1rem 5% !important; border-bottom:1px solid rgba(255,255,255,.12) !important; box-shadow:0 18px 40px rgba(0,0,0,.24) !important; }
      .mobile-menu.open { display:flex !important; }
      .mobile-menu a { display:block !important; padding:.8rem 0 !important; color:rgba(255,255,255,.82) !important; border-bottom:1px solid rgba(255,255,255,.1) !important; font-size:.8rem !important; letter-spacing:1px !important; text-transform:uppercase !important; text-decoration:none !important; }
    }
    @media (max-width: 560px) {
      nav .nav-brand-text .tagline { display:none !important; }
      nav .nav-logo img { height:39px !important; }
    }

    .mobile-menu { display:none !important; }
    .mobile-menu.open { display:flex !important; }
    @media (min-width:901px) { .mobile-menu { display:none !important; } .hamburger { display:none !important; } }
    @media (max-width:900px) { .mobile-menu { position:fixed; max-height:calc(100vh - 64px); overflow:auto; } .mobile-menu.open { display:flex !important; } }

    #contact { background:#f1f0eb !important; }
    #contact form { max-width:760px; margin:0 auto; padding:2.25rem; background:#fafaf7; border:1px solid #d3d3cc; box-shadow:0 18px 45px rgba(11,13,12,.07); font-family:'Barlow',Arial,sans-serif; }
    #contact form input,#contact form textarea,#contact form select { width:100%; min-height:46px; border:1px solid #c9cbc5 !important; border-radius:0 !important; background:#fff !important; color:#171a18 !important; padding:.72rem .8rem !important; box-shadow:none !important; }
    #contact form textarea { min-height:130px; resize:vertical; }
    #contact form input:focus,#contact form textarea:focus,#contact form select:focus { outline:none !important; border-color:#788653 !important; box-shadow:0 0 0 1px #788653 !important; }
    #contact form button,#contact form .btn,#contact form input[type='submit'] { width:100%; min-height:48px; border:0 !important; border-radius:0 !important; background:#0b0d0c !important; color:#fff !important; font:600 .68rem 'Barlow',Arial,sans-serif !important; letter-spacing:1.4px; text-transform:uppercase; cursor:pointer; }
    #contact form button:hover,#contact form .btn:hover,#contact form input[type='submit']:hover { background:#788653 !important; }

    body:has(.project-grid) { background:#f1f0eb; }
    .page-hero { min-height:520px !important; padding:11rem 5.2% 5rem !important; display:flex; align-items:flex-end; background:#0b0d0c !important; color:#fff !important; position:relative; overflow:hidden; }
    .page-hero::after { content:''; position:absolute; inset:0; background:linear-gradient(90deg,rgba(11,13,12,.96),rgba(11,13,12,.65) 55%,rgba(11,13,12,.25)); pointer-events:none; }
    .page-hero .container { position:relative; z-index:2; width:100%; max-width:1180px; margin:0 auto; }
    .page-hero h1 { max-width:900px; margin:.5rem 0 1.1rem !important; font-size:clamp(3.4rem,7vw,7rem) !important; line-height:.9 !important; font-weight:300 !important; letter-spacing:-3px !important; text-transform:uppercase; }
    .page-hero p { max-width:650px; color:rgba(255,255,255,.62) !important; font-size:.95rem !important; line-height:1.7; }
    .page-hero-stats { display:flex; flex-wrap:wrap; gap:0 !important; margin-top:2.2rem !important; border-top:1px solid rgba(255,255,255,.15); }
    .page-hero-stats span { padding:1rem 1.4rem 0 0 !important; margin-right:1.4rem; color:rgba(255,255,255,.52) !important; font-size:.59rem !important; letter-spacing:1.2px; text-transform:uppercase; border:0 !important; }
    .project-grid { max-width:1180px; margin:0 auto; display:grid !important; grid-template-columns:repeat(12,1fr) !important; gap:1px !important; background:#d3d3cc; border:1px solid #d3d3cc; }
    .project-card { grid-column:span 6; display:flex; flex-direction:column; min-width:0; background:#fafaf7 !important; border:0 !important; border-radius:0 !important; box-shadow:none !important; overflow:hidden; transition:background .2s ease; }
    .project-card:nth-child(1),.project-card:nth-child(4) { grid-column:span 7; }
    .project-card:nth-child(2),.project-card:nth-child(3) { grid-column:span 5; }
    .project-card:hover { transform:none !important; background:#fff !important; box-shadow:none !important; }
    .project-card img { width:100%; height:310px !important; object-fit:cover; filter:grayscale(.12) saturate(.72); transition:filter .3s ease,transform .45s ease; }
    .project-card:hover img { filter:grayscale(0) saturate(.9); transform:scale(1.015); }
    .project-card-body { padding:1.65rem 1.7rem 1.8rem !important; flex:1; }
    .project-card-body h3 { margin:0 0 .65rem !important; color:#171a18 !important; font-size:1.35rem !important; font-weight:400 !important; line-height:1.05; }
    .project-card-body p { margin:0; color:#6e746f !important; font-size:.82rem !important; line-height:1.7; max-width:560px; }
    .project-tags { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:1.25rem !important; }
    .project-tags .chip { padding:.3rem .5rem !important; border:1px solid #d3d3cc !important; border-radius:0 !important; background:transparent !important; color:#5e655f !important; font-size:.56rem !important; letter-spacing:.8px; text-transform:uppercase; }
    .project-tags .chip-green { border-color:#aab590 !important; color:#647043 !important; background:transparent !important; }
    .coming-soon-panel { max-width:900px; margin:0 auto; padding:3rem !important; border:1px solid #d3d3cc; border-radius:0 !important; background:#fafaf7 !important; box-shadow:none !important; }
    .coming-soon-panel h2 { font-size:2.5rem !important; font-weight:300 !important; letter-spacing:-1px; color:#171a18 !important; }
    .coming-soon-panel p { max-width:650px; color:#6e746f !important; }
    .coming-soon-panel .checklist { display:grid; grid-template-columns:repeat(2,1fr); gap:.6rem 2rem; margin:1.6rem 0 2rem !important; padding:0 !important; }
    .coming-soon-panel .checklist li { color:#4f5651; font-size:.78rem; border-bottom:1px solid #deded8; padding:.65rem 0; }
    @media(max-width:768px) { #contact form { padding:1.35rem; } .page-hero { min-height:470px !important; padding:8rem 5% 3.5rem !important; } .page-hero h1 { font-size:clamp(3rem,14vw,5rem) !important; letter-spacing:-2px !important; } .project-grid { display:grid !important; grid-template-columns:1fr !important; } .project-card,.project-card:nth-child(1),.project-card:nth-child(2),.project-card:nth-child(3),.project-card:nth-child(4) { grid-column:1 !important; } .project-card img { height:240px !important; } .coming-soon-panel { padding:2rem 1.35rem !important; } .coming-soon-panel .checklist { grid-template-columns:1fr; } }
  `;
  document.head.appendChild(polish);
})();