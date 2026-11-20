const { chromium, devices } = require('playwright');
const base = process.argv[2] || 'http://localhost:4000/zeropoint/';
(async () => {
  const b = await chromium.launch();
  const out = [];
  const ok = (name, cond, extra = '') => out.push(`${cond ? 'PASS' : 'FAIL'}  ${name} ${extra}`);

  // --- desktop: print page options, order link, zoom ---
  let ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  let p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(base + 'prints/kenya-rivers/', { waitUntil: 'load' });
  let href = await p.getAttribute('#order-wa', 'href');
  ok('default order link names print, size, frame', decodeURIComponent(href).includes('"Kenya: Rivers and drainage basins", size A2, black frame'), decodeURIComponent(href).split('text=')[1]);
  await p.locator('label.option', { hasText: 'A0' }).click();
  await p.locator('label.option', { hasText: 'Gold frame' }).click();
  href = await p.getAttribute('#order-wa', 'href');
  ok('order link follows selection', decodeURIComponent(href).includes('size A0, gold frame'), decodeURIComponent(href).split('text=')[1]);
  ok('frame preview follows selection', (await p.getAttribute('.print__stage .frame', 'data-frame')) === 'gold');
  const mail = await p.getAttribute('#order-mail', 'href');
  ok('email link carries the order', decodeURIComponent(mail).includes('size A0, gold frame') && mail.startsWith('mailto:zeropointgeospatial@gmail.com'));
  await p.locator('.print__stage .frame').click();
  await p.waitForTimeout(600);
  ok('zoom dialog opens with the large image', await p.evaluate(() => document.getElementById('zoom').open && document.querySelector('#zoom img').src.includes('-2000.webp')));
  await p.keyboard.press('Escape');
  ok('zoom closes on Escape', await p.evaluate(() => !document.getElementById('zoom').open));
  await p.locator('label.option', { hasText: 'Natural wood' }).click();

  // --- catalogue filters ---
  await p.goto(base + 'prints/', { waitUntil: 'load' });
  const all = await p.locator('.print-card:visible').count();
  await p.locator('.filter', { hasText: 'Landforms' }).click();
  const land = await p.locator('.print-card:visible').count();
  await p.locator('.filter', { hasText: 'Regions' }).click();
  const reg = await p.locator('.print-card:visible').count();
  await p.locator('.filter', { hasText: 'Counties' }).click();
  const cty = await p.locator('.print-card:visible').count();
  await p.locator('.filter', { hasText: 'Cities' }).click();
  const nbo = await p.locator('.print-card:visible').count();
  ok('catalogue filters', all >= 12 && land >= 4 && reg >= 4 && cty >= 1 && nbo >= 2 && land + reg + cty + nbo < all, `all=${all} landforms=${land} regions=${reg} counties=${cty} cities=${nbo}`);
  const labels = await p.evaluate(() => [...document.querySelectorAll('.print-card__meta span:first-child')].map(e => e.textContent));
  ok('every card carries a plate or county number', labels.every(t => /^(Plate|County) \d+$|^\d+ plates$/.test(t)), labels.join(','));
  await p.locator('.print-card:visible').first().scrollIntoViewIfNeeded();
  await p.waitForTimeout(800);
  const lazyOk = await p.evaluate(() => [...document.querySelectorAll('.print-card:not([hidden]) img')].every(i => i.complete && i.naturalWidth > 0));
  ok('lazy images load once on screen', lazyOk);

  // --- old shop URL redirects ---
  await p.goto(base + 'prints-shop.html', { waitUntil: 'load' });
  await p.waitForTimeout(800);
  ok('old shop URL redirects to /prints/', p.url().endsWith('/prints/'), p.url());

  // --- home: FAQ, form validation and submit (network mocked) ---
  await p.goto(base, { waitUntil: 'load' });
  const faqBefore = await p.locator('.faq details[open]').count();
  await p.locator('.faq summary').nth(2).click();
  ok('FAQ opens', (await p.locator('.faq details[open]').count()) === faqBefore + 1);
  let posted = null;
  await p.route('https://formspree.io/**', async r => { posted = r.request().postData(); await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' }); });
  await p.fill('#fname', 'Test'); await p.fill('#lname', 'Client'); await p.fill('#email', 'test@example.com');
  await p.fill('#phone', '+254700000000'); await p.fill('#location', 'Kiambu');
  await p.selectOption('#service', { index: 2 }); await p.selectOption('#timeline', { index: 1 });
  await p.click('#quote-form button[type=submit]');
  await p.waitForTimeout(700);
  const status = await p.textContent('.form__status');
  ok('quote form posts to Formspree and confirms', !!posted && posted.includes('Kiambu') && status.includes('Thank you'), status.trim().slice(0, 60));
  await p.unroute('https://formspree.io/**');
  await p.route('https://formspree.io/**', r => r.abort());
  await p.fill('#fname', 'Test'); await p.fill('#lname', 'Client'); await p.fill('#email', 'test@example.com');
  await p.fill('#phone', '+254700000000'); await p.fill('#location', 'Kiambu');
  await p.selectOption('#service', { index: 2 }); await p.selectOption('#timeline', { index: 1 });
  await p.click('#quote-form button[type=submit]');
  await p.waitForTimeout(700);
  ok('form reports a failed send', (await p.textContent('.form__status')).includes('did not send'));
  const svc = await p.getAttribute('.svc__row .text-link', 'href');
  ok('service quote links open WhatsApp with text', svc.startsWith('https://wa.me/254743441757?text=Hello%20ZeroPoint'), svc.slice(0, 80));
  ok('no JS errors (desktop)', errs.length === 0, errs.join('; '));
  await ctx.close();

  // --- phone: navigation ---
  ctx = await b.newContext({ ...devices['iPhone 13'] });
  p = await ctx.newPage();
  const merrs = [];
  p.on('pageerror', e => merrs.push(e.message));
  await p.goto(base + 'projects/', { waitUntil: 'load' });
  ok('menu closed on load', !(await p.locator('#site-nav').isVisible()));
  await p.click('.nav-toggle');
  await p.waitForTimeout(300);
  ok('menu opens', await p.locator('#site-nav').isVisible() && (await p.getAttribute('.nav-toggle', 'aria-expanded')) === 'true');
  await p.locator('#site-nav a', { hasText: 'Prints' }).click();
  await p.waitForLoadState('load');
  ok('menu link navigates', p.url().endsWith('/prints/'), p.url());
  ok('mobile call bar visible, float hidden', await p.locator('.mobile-bar').isVisible() && !(await p.locator('.wa-float').isVisible()));
  ok('no JS errors (phone)', merrs.length === 0, merrs.join('; '));
  await b.close();
  console.log(out.join('\n'));
})();
