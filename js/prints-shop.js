/* ZeroPoint Geospatial — Prints Shop page-specific polish */
(function () {
  'use strict';

  var style = document.createElement('style');
  style.id = 'prints-page-polish';
  style.textContent = `
    body.prints-shop-page > nav .nav-logo::after {
      content: '← MAIN SITE' !important;
      display: inline-flex !important;
      align-items: center !important;
      margin-left: .8rem !important;
      padding-left: .8rem !important;
      border-left: 1px solid rgba(255,255,255,.18) !important;
      color: rgba(255,255,255,.62) !important;
      font-size: .55rem !important;
      font-weight: 600 !important;
      letter-spacing: 1.2px !important;
      white-space: nowrap !important;
    }
    body.prints-shop-page > nav .nav-logo:hover::after { color:#fff !important; }

    /* Floating WhatsApp: green, circular and deliberately separate from shop order links. */
    body.prints-shop-page .whatsapp-float,
    body.prints-shop-page .floating-whatsapp,
    body.prints-shop-page .whatsapp-button,
    body.prints-shop-page .whatsapp-fab {
      background:#25D366 !important;
      color:#fff !important;
      border-radius:50% !important;
      width:54px !important;
      height:54px !important;
      min-width:54px !important;
      min-height:54px !important;
      padding:0 !important;
      display:flex !important;
      align-items:center !important;
      justify-content:center !important;
      border:0 !important;
      box-shadow:0 8px 24px rgba(0,0,0,.18) !important;
    }
    body.prints-shop-page .whatsapp-float svg,
    body.prints-shop-page .floating-whatsapp svg,
    body.prints-shop-page .whatsapp-button svg,
    body.prints-shop-page .whatsapp-fab svg {
      width:25px !important;
      height:25px !important;
      fill:currentColor !important;
    }
    body.prints-shop-page .whatsapp-float img,
    body.prints-shop-page .floating-whatsapp img,
    body.prints-shop-page .whatsapp-button img,
    body.prints-shop-page .whatsapp-fab img {
      width:25px !important;
      height:25px !important;
      object-fit:contain !important;
    }

    body.prints-shop-page > #mobileMenu { display:none !important; }
    body.prints-shop-page > #mobileMenu.open { display:flex !important; flex-direction:column !important; }

    @media (max-width:900px) {
      body.prints-shop-page > nav .nav-logo::after { content:'←' !important; font-size:.95rem !important; }
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

  closePrintsMenu();

  document.querySelectorAll('body.prints-shop-page > #mobileMenu a').forEach(function (link) {
    link.addEventListener('click', closePrintsMenu);
  });
})();
