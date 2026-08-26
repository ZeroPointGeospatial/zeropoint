/* Prints page navigation safety layer.
   The Projects page has a small page-specific navigation treatment; keep Prints
   consistent without touching the shop layout or shared homepage styles. */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.id = 'prints-nav-safety';
  style.textContent = `
    body.prints-shop-page > nav {
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
      color: #fff !important;
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
    }

    body.prints-shop-page > nav .nav-logo {
      display: flex !important;
      align-items: center !important;
      gap: .7rem !important;
      flex-shrink: 0 !important;
      text-decoration: none !important;
    }
    body.prints-shop-page > nav .nav-logo img {
      width: auto !important;
      height: 42px !important;
      display: block !important;
    }
    body.prints-shop-page > nav .nav-brand-text {
      display: flex !important;
      flex-direction: column !important;
      line-height: 1.1 !important;
    }
    body.prints-shop-page > nav .nav-brand-text .name {
      color: #fff !important;
      font-size: .92rem !important;
      font-weight: 700 !important;
      letter-spacing: 1.5px !important;
    }
    body.prints-shop-page > nav .nav-brand-text .blue { color: #fff !important; }
    body.prints-shop-page > nav .nav-brand-text .green { color: #aab590 !important; }
    body.prints-shop-page > nav .nav-brand-text .tagline {
      margin-top: 3px !important;
      color: rgba(255,255,255,.46) !important;
      font-size: .57rem !important;
      letter-spacing: 1.4px !important;
      text-transform: uppercase !important;
    }

    body.prints-shop-page > nav .nav-links {
      display: flex !important;
      align-items: center !important;
      gap: 1.45rem !important;
      list-style: none !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    body.prints-shop-page > nav .nav-links li { list-style: none !important; margin: 0 !important; padding: 0 !important; }
    body.prints-shop-page > nav .nav-links a {
      color: rgba(255,255,255,.70) !important;
      font-size: .68rem !important;
      font-weight: 500 !important;
      letter-spacing: 1.1px !important;
      text-transform: uppercase !important;
      text-decoration: none !important;
    }
    body.prints-shop-page > nav .nav-links a:hover { color: #fff !important; }
    body.prints-shop-page > nav .nav-links .nav-active {
      color: #fff !important;
      font-weight: 700 !important;
      border-bottom: 1px solid #aab590 !important;
      padding-bottom: 3px !important;
    }

    body.prints-shop-page > nav > .nav-cta {
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

    body.prints-shop-page > nav .hamburger {
      display: none !important;
      flex-direction: column !important;
      gap: 5px !important;
      padding: 6px !important;
      border: 0 !important;
      background: transparent !important;
      cursor: pointer !important;
    }
    body.prints-shop-page > nav .hamburger span {
      display: block !important;
      width: 24px !important;
      height: 2px !important;
      background: #fff !important;
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
    body.prints-shop-page > #mobileMenu.open {
      display: flex !important;
      flex-direction: column !important;
    }
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

    @media (max-width: 900px) {
      body.prints-shop-page > nav .nav-links,
      body.prints-shop-page > nav > .nav-cta { display: none !important; }
      body.prints-shop-page > nav .hamburger { display: flex !important; }
    }
  `;
  document.head.appendChild(style);

  function closePrintsMenu() {
    var menu = document.getElementById('mobileMenu');
    var button = document.querySelector('body.prints-shop-page > nav .hamburger');
    if (menu) menu.classList.remove('open');
    if (button) {
      button.classList.remove('open');
      button.setAttribute('aria-expanded', 'false');
    }
  }

  /* Never let the mobile menu render open on initial load. */
  closePrintsMenu();

  document.querySelectorAll('body.prints-shop-page > #mobileMenu a').forEach(function (link) {
    link.addEventListener('click', closePrintsMenu);
  });
})();
