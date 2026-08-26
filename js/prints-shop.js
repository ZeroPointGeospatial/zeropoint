/* ZeroPoint Geospatial — Prints Shop page-specific fixes.
   Keep the main site navbar and category sticky nav separate. */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.id = 'prints-page-fixes';
  style.textContent = `
    /* MAIN SITE NAV ONLY */
    body.prints-shop-page > nav:not(.prints-sticky-nav) {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      z-index: 1000 !important;
      min-height: 74px !important;
      height: 74px !important;
      padding: .75rem 5.2% !important;
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      background: rgba(11,13,12,.94) !important;
      border-bottom: 1px solid rgba(255,255,255,.12) !important;
      color: #fff !important;
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
    }

    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-logo {
      display: flex !important;
      align-items: center !important;
      gap: .7rem !important;
      flex-shrink: 0 !important;
      width: auto !important;
      height: auto !important;
      padding: 0 !important;
      border: 0 !important;
      background: transparent !important;
      text-decoration: none !important;
      visibility: visible !important;
      opacity: 1 !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-logo img {
      width: 42px !important;
      height: 42px !important;
      object-fit: cover !important;
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-brand-text {
      display: flex !important;
      flex-direction: column !important;
      line-height: 1.1 !important;
      visibility: visible !important;
      opacity: 1 !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-brand-text .name {
      color: #fff !important;
      font-size: .92rem !important;
      font-weight: 700 !important;
      letter-spacing: 1.5px !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-brand-text .blue { color: #fff !important; }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-brand-text .green { color: #aab590 !important; }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-brand-text .tagline {
      margin-top: 3px !important;
      color: rgba(255,255,255,.46) !important;
      font-size: .57rem !important;
      letter-spacing: 1.4px !important;
      text-transform: uppercase !important;
    }

    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links {
      display: flex !important;
      align-items: center !important;
      gap: 1.45rem !important;
      list-style: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links li { list-style: none !important; margin: 0 !important; padding: 0 !important; }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links a {
      color: rgba(255,255,255,.70) !important;
      font-size: .68rem !important;
      font-weight: 500 !important;
      letter-spacing: 1.1px !important;
      text-transform: uppercase !important;
      text-decoration: none !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links a:hover { color: #fff !important; }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links .nav-active {
      color: #fff !important;
      font-weight: 700 !important;
      border-bottom: 1px solid #aab590 !important;
      padding-bottom: 3px !important;
    }

    body.prints-shop-page > nav:not(.prints-sticky-nav) > .nav-cta {
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
    }

    body.prints-shop-page > nav:not(.prints-sticky-nav) .hamburger {
      display: none !important;
      flex-direction: column !important;
      gap: 5px !important;
      padding: 6px !important;
      border: 0 !important;
      background: transparent !important;
      cursor: pointer !important;
    }
    body.prints-shop-page > nav:not(.prints-sticky-nav) .hamburger span {
      display: block !important;
      width: 24px !important;
      height: 2px !important;
      background: #fff !important;
    }

    /* Category navigation belongs BELOW the main navbar. */
    body.prints-shop-page > nav.prints-sticky-nav {
      position: sticky !important;
      top: 74px !important;
      z-index: 50 !important;
      display: block !important;
      min-height: 0 !important;
      height: auto !important;
      padding: 0 !important;
      background: rgba(244,243,239,.96) !important;
      color: #161a18 !important;
    }

    body.prints-shop-page > #mobileMenu {
      display: none !important;
      position: fixed !important;
      top: 74px !important;
      left: 0 !important;
      right: 0 !important;
      z-index: 999 !important;
      background: #0b0d0c !important;
      padding: 1rem 5% !important;
      border-bottom: 1px solid rgba(255,255,255,.12) !important;
    }
    body.prints-shop-page > #mobileMenu.open { display: flex !important; flex-direction: column !important; }
    body.prints-shop-page > #mobileMenu a {
      display: block !important;
      padding: .8rem 0 !important;
      color: rgba(255,255,255,.82) !important;
      border-bottom: 1px solid rgba(255,255,255,.10) !important;
      text-decoration: none !important;
      font-size: .8rem !important;
      letter-spacing: 1px !important;
      text-transform: uppercase !important;
    }

    /* Floating WhatsApp: unmistakably WhatsApp green, circular, compact. */
    body.prints-shop-page > .whatsapp-btn {
      position: fixed !important;
      right: 24px !important;
      bottom: 24px !important;
      z-index: 1200 !important;
      width: 56px !important;
      height: 56px !important;
      min-width: 56px !important;
      min-height: 56px !important;
      padding: 0 !important;
      margin: 0 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      border-radius: 50% !important;
      border: 0 !important;
      background: #25D366 !important;
      color: #fff !important;
      box-shadow: 0 8px 24px rgba(0,0,0,.22) !important;
      text-decoration: none !important;
      line-height: 1 !important;
    }
    body.prints-shop-page > .whatsapp-btn svg {
      display: block !important;
      width: 29px !important;
      height: 29px !important;
      margin: 0 !important;
      fill: currentColor !important;
    }
    body.prints-shop-page > .whatsapp-btn:hover { background: #20bd5a !important; color: #fff !important; transform: translateY(-2px) !important; }

    @media (max-width: 900px) {
      body.prints-shop-page > nav:not(.prints-sticky-nav) .nav-links,
      body.prints-shop-page > nav:not(.prints-sticky-nav) > .nav-cta { display: none !important; }
      body.prints-shop-page > nav:not(.prints-sticky-nav) .hamburger { display: flex !important; }
      body.prints-shop-page > .whatsapp-btn { right: 16px !important; bottom: 82px !important; }
    }
  `;
  document.head.appendChild(style);

  function closePrintsMenu() {
    var menu = document.getElementById('mobileMenu');
    var button = document.querySelector('body.prints-shop-page > nav:not(.prints-sticky-nav) .hamburger');
    if (menu) menu.classList.remove('open');
    if (button) {
      button.classList.remove('open');
      button.setAttribute('aria-expanded', 'false');
    }
  }

  closePrintsMenu();

  document.querySelectorAll('body.prints-shop-page > #mobileMenu a').forEach(function (link) {
    link.addEventListener('click', closePrintsMenu);
  });
})();
