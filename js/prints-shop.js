/* ZeroPoint Geospatial — Prints Shop page-specific polish */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.id = 'prints-page-polish';
  style.textContent = `
    /* The Prints shop uses ONE header: logo + category navigation together. */
    body.prints-shop-page > nav:first-of-type {
      display: none !important;
    }

    body.prints-shop-page .prints-sticky-nav {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      z-index: 1000 !important;
      height: 74px !important;
      background: rgba(11,13,12,.96) !important;
      border-bottom: 1px solid rgba(255,255,255,.11) !important;
      box-shadow: none !important;
      backdrop-filter: blur(16px) !important;
      -webkit-backdrop-filter: blur(16px) !important;
    }

    body.prints-shop-page .prints-sticky-nav-inner {
      height: 74px !important;
      display: flex !important;
      align-items: center !important;
      gap: 1.4rem !important;
      max-width: none !important;
      width: 100% !important;
      padding: 0 5.2% !important;
    }

    /* Logo is inserted into the same bar as Categories / Thematic. */
    body.prints-shop-page .prints-shop-logo {
      display: inline-flex !important;
      align-items: center !important;
      gap: .65rem !important;
      flex: 0 0 auto !important;
      margin-right: auto !important;
      color: #fff !important;
      text-decoration: none !important;
    }
    body.prints-shop-page .prints-shop-logo img {
      width: 40px !important;
      height: 40px !important;
      object-fit: cover !important;
      border-radius: 0 !important;
    }
    body.prints-shop-page .prints-shop-logo-text {
      display: flex !important;
      flex-direction: column !important;
      line-height: 1.05 !important;
      white-space: nowrap !important;
    }
    body.prints-shop-page .prints-shop-logo-name {
      color: #fff !important;
      font-size: .84rem !important;
      font-weight: 700 !important;
      letter-spacing: 1.35px !important;
    }
    body.prints-shop-page .prints-shop-logo-tagline {
      margin-top: 3px !important;
      color: rgba(255,255,255,.43) !important;
      font-size: .5rem !important;
      letter-spacing: 1.3px !important;
      text-transform: uppercase !important;
    }

    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo) {
      color: rgba(255,255,255,.66) !important;
      font-size: .61rem !important;
      font-weight: 500 !important;
      letter-spacing: 1px !important;
      text-transform: uppercase !important;
      text-decoration: none !important;
      white-space: nowrap !important;
    }
    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo):hover,
    body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo):focus {
      color: #fff !important;
    }

    /* Keep the page content from hiding underneath the fixed shop header. */
    body.prints-shop-page main { padding-top: 74px !important; }

    /* Floating WhatsApp: green, circular and clean. */
    body.prints-shop-page .whatsapp-btn {
      position: fixed !important;
      right: 24px !important;
      bottom: 24px !important;
      z-index: 1100 !important;
      width: 56px !important;
      height: 56px !important;
      min-width: 56px !important;
      min-height: 56px !important;
      padding: 0 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      background: #25D366 !important;
      color: #fff !important;
      border: 0 !important;
      border-radius: 50% !important;
      box-shadow: 0 8px 22px rgba(0,0,0,.18) !important;
    }
    body.prints-shop-page .whatsapp-btn svg {
      width: 27px !important;
      height: 27px !important;
      fill: currentColor !important;
    }

    @media (max-width: 1050px) {
      body.prints-shop-page .prints-sticky-nav-inner > a:not(.prints-shop-logo) {
        display: none !important;
      }
      body.prints-shop-page .prints-sticky-nav-inner {
        justify-content: flex-start !important;
      }
      body.prints-shop-page .prints-shop-logo {
        margin-right: 0 !important;
      }
    }

    @media (max-width: 600px) {
      body.prints-shop-page .prints-sticky-nav-inner {
        padding: 0 5% !important;
      }
      body.prints-shop-page .prints-shop-logo img {
        width: 36px !important;
        height: 36px !important;
      }
      body.prints-shop-page .prints-shop-logo-name {
        font-size: .75rem !important;
      }
      body.prints-shop-page .prints-shop-logo-tagline {
        display: none !important;
      }
      body.prints-shop-page .whatsapp-btn {
        right: 16px !important;
        bottom: 76px !important;
      }
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
