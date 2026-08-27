/* ZeroPoint Geospatial — Prints Shop page-specific polish */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.id = 'prints-page-polish';
  style.textContent = `
    body.prints-shop-page > nav:first-of-type { display: none !important; }
    body.prints-shop-page .prints-sticky-nav {
      position: fixed !important; top: 0 !important; left: 0 !important; right: 0 !important;
      z-index: 1000 !important; height: 74px !important; background: rgba(11,13,12,.96) !important;
      border-bottom: 1px solid rgba(255,255,255,.11) !important; box-shadow: none !important;
      backdrop-filter: blur(16px) !important; -webkit-backdrop-filter: blur(16px) !important;
    }
    body.prints-shop-page .prints-sticky-nav-inner {
      height: 74px !important; display: flex !important; align-items: center !important;
      gap: 1.4rem !important; max-width: none !important; width: 100% !important; padding: 0 5.2% !important;
    }
    body.prints-shop-page .prints-shop-logo {
      display: inline-flex !important; align-items: center !important; gap: .65rem !important;
      flex: 0 0 auto !important; margin-right: auto !important; color: #fff !important; text-decoration: none !important;
    }
    body.prints-shop-page .prints-shop-logo img { width: 40px !important; height: 40px !important; object-fit: cover !important; border-radius: 0 !important; }
    body.prints-shop-page .prints-shop-logo-text { display: flex !important; flex-direction: column !important; line-height: 1.05 !important; white-space: nowrap !important; }
    body.prints-shop-page .prints-shop-logo-name { color: #fff !important; font-size: .84rem !important; font-weight: 700 !important; letter-spacing: 1.35px !important; }
    body.prints-shop-page .prints-shop-logo-tagline { margin-top: 3px !important; color: rgba(255,255,255,.43) !important; font-size: .5rem !important; letter-spacing: 1.3px !important; text-transform: uppercase !important; }
    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo) { color: rgba(255,255,255,.66) !important; font-size: .61rem !important; font-weight: 500 !important; letter-spacing: 1px !important; text-transform: uppercase !important; text-decoration: none !important; white-space: nowrap !important; }
    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo):hover,
    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo):focus { color: #fff !important; }
    body.prints-shop-page main { padding-top: 74px !important; }

    /* Balanced print grids: two cards use two columns; three cards use three columns. */
    body.prints-shop-page .print-grid:has(> .print-card:nth-child(2):last-child),
    body.prints-shop-page .print-grid-compact:has(> .print-card:nth-child(2):last-child) {
      grid-template-columns: repeat(2, minmax(0,1fr)) !important;
    }
    body.prints-shop-page .print-grid:has(> .print-card:nth-child(3):last-child),
    body.prints-shop-page .print-grid-compact:has(> .print-card:nth-child(3):last-child) {
      grid-template-columns: repeat(3, minmax(0,1fr)) !important;
    }
    body.prints-shop-page .print-grid > .print-card,
    body.prints-shop-page .print-grid-compact > .print-card { min-width: 0 !important; }

    body.prints-shop-page .prints-custom-btns {
      position: relative !important; display: flex !important; align-items: center !important;
      flex-wrap: wrap !important; gap: .75rem !important; width: 100% !important;
      margin-top: 2rem !important; padding-top: 0 !important; clear: both !important;
    }
    body.prints-shop-page .prints-custom-btns .btn-primary,
    body.prints-shop-page .prints-custom-btns .btn-wa {
      position: static !important; float: none !important; transform: none !important; margin: 0 !important;
      min-height: 46px !important; display: inline-flex !important; align-items: center !important;
      justify-content: center !important; gap: .5rem !important; box-sizing: border-box !important;
      text-decoration: none !important; white-space: nowrap !important;
    }
    body.prints-shop-page .prints-custom-btns .btn-primary { background: #151817 !important; color: #fff !important; border: 1px solid #151817 !important; padding: .78rem 1.15rem !important; }
    body.prints-shop-page .prints-custom-btns .btn-primary:hover { background: #8fa36f !important; border-color: #8fa36f !important; color: #111 !important; }
    body.prints-shop-page .prints-custom-btns .btn-wa { background: #25D366 !important; color: #fff !important; border: 1px solid #25D366 !important; padding: .78rem 1.15rem !important; opacity: 1 !important; }
    body.prints-shop-page .prints-custom-btns .btn-wa:hover { background: #1fb957 !important; border-color: #1fb957 !important; color: #fff !important; }
    body.prints-shop-page .prints-custom-btns .btn-wa svg { width: 18px !important; height: 18px !important; flex: 0 0 18px !important; display: block !important; fill: currentColor !important; }

    body.prints-shop-page .whatsapp-btn {
      position: fixed !important; right: 24px !important; bottom: 24px !important; z-index: 1100 !important;
      width: 56px !important; height: 56px !important; min-width: 56px !important; min-height: 56px !important;
      padding: 0 !important; display: flex !important; align-items: center !important; justify-content: center !important;
      background: #25D366 !important; color: #fff !important; border: 2px solid #fff !important;
      border-radius: 50% !important; box-shadow: 0 8px 22px rgba(0,0,0,.22) !important; overflow: hidden !important;
    }
    body.prints-shop-page .whatsapp-btn svg { width: 27px !important; height: 27px !important; display: block !important; flex: 0 0 27px !important; fill: currentColor !important; }

    body.prints-shop-page .mobile-bar {
      position: fixed !important; left: 0 !important; right: 0 !important; bottom: 0 !important; z-index: 1090 !important;
      display: none !important; grid-template-columns: 1fr 1fr !important; gap: 8px !important; padding: 10px !important;
      background: rgba(11,13,12,.97) !important; border-top: 1px solid rgba(255,255,255,.14) !important;
      box-shadow: 0 -10px 30px rgba(0,0,0,.18) !important;
    }
    body.prints-shop-page .mobile-bar a { min-height: 44px !important; display: flex !important; align-items: center !important; justify-content: center !important; text-decoration: none !important; font-size: .65rem !important; font-weight: 600 !important; letter-spacing: 1px !important; text-transform: uppercase !important; }
    body.prints-shop-page .mobile-bar .call { background: #fff !important; color: #111 !important; }
    body.prints-shop-page .mobile-bar .wa { background: #25D366 !important; color: #fff !important; border: 1px solid #25D366 !important; }

    @media (max-width: 1050px) {
      body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo) { display: none !important; }
      body.prints-shop-page .prints-sticky-nav-inner { justify-content: flex-start !important; }
      body.prints-shop-page .prints-shop-logo { margin-right: 0 !important; }
    }
    @media (max-width: 1000px) {
      body.prints-shop-page .print-grid:has(> .print-card:nth-child(3):last-child),
      body.prints-shop-page .print-grid-compact:has(> .print-card:nth-child(3):last-child) { grid-template-columns: repeat(2, minmax(0,1fr)) !important; }
    }
    @media (max-width: 800px) {
      body.prints-shop-page .mobile-bar { display: grid !important; }
      body.prints-shop-page main { padding-bottom: 76px !important; }
      body.prints-shop-page .whatsapp-btn { right: 16px !important; bottom: 86px !important; }
      body.prints-shop-page .print-grid:has(> .print-card:nth-child(3):last-child),
      body.prints-shop-page .print-grid:has(> .print-card:nth-child(2):last-child),
      body.prints-shop-page .print-grid-compact:has(> .print-card:nth-child(3):last-child),
      body.prints-shop-page .print-grid-compact:has(> .print-card:nth-child(2):last-child) { grid-template-columns: 1fr !important; }
      body.prints-shop-page .prints-custom-btns { flex-direction: column !important; align-items: stretch !important; }
      body.prints-shop-page .prints-custom-btns .btn-primary,
      body.prints-shop-page .prints-custom-btns .btn-wa { width: 100% !important; }
    }
    @media (max-width: 600px) {
      body.prints-shop-page .prints-sticky-nav-inner { padding: 0 5% !important; }
      body.prints-shop-page .prints-shop-logo img { width: 36px !important; height: 36px !important; }
      body.prints-shop-page .prints-shop-logo-name { font-size: .75rem !important; }
      body.prints-shop-page .prints-shop-logo-tagline { display: none !important; }
    }
  `;
  document.head.appendChild(style);

  function setupPrintsHeader() {
    var mainNav = document.querySelector('body.prints-shop-page > nav:first-of-type');
    var categoryNav = document.querySelector('body.prints-shop-page .prints-sticky-nav');
    var inner = categoryNav && categoryNav.querySelector('.prints-sticky-nav-inner');
    var logo = mainNav && mainNav.querySelector('.nav-logo');

    if (!categoryNav || !inner || !logo) return;

    if (!inner.querySelector('.prints-shop-logo')) {
      var shopLogo = document.createElement('a');
      shopLogo.className = 'prints-shop-logo';
      shopLogo.href = 'index.html';
      shopLogo.setAttribute('aria-label', 'Return to ZeroPoint Geospatial main site');
      shopLogo.innerHTML = `
        <img src="assets/zeropoint-logo.jpg" alt="ZeroPoint Geospatial" width="40" height="40">
        <span class="prints-shop-logo-text">
          <span class="prints-shop-logo-name">ZEROPOINT GEOSPATIAL</span>
          <span class="prints-shop-logo-tagline">Precision Data. Smarter Decisions.</span>
        </span>`;
      inner.insertBefore(shopLogo, inner.firstChild);
    }
  }

  function closePrintsMenu() {
    var menu = document.getElementById('mobileMenu');
    var button = document.querySelector('body.prints-shop-page > nav .hamburger');
    if (menu) menu.classList.remove('open');
    if (button) {
      button.classList.remove('open');
      button.setAttribute('aria-expanded', 'false');
    }
  }

  setupPrintsHeader();
  closePrintsMenu();
})();
