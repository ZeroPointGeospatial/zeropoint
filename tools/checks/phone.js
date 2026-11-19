// usage: node mobile.js <base> <prefix> <pages>
const { chromium, devices } = require('playwright');
(async () => {
  const [base, prefix, pages] = process.argv.slice(2);
  const b = await chromium.launch();
  const ctx = await b.newContext({ ...devices['iPhone 13'] });
  for (const p of pages.split(',')) {
    const page = await ctx.newPage();
    const errs = [];
    page.on('response', r => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url()); });
    page.on('pageerror', e => errs.push('JS ' + e.message));
    await page.goto(base + p, { waitUntil: 'load' });
    await page.waitForTimeout(700);
    await page.evaluate(async () => { const H = document.documentElement.scrollHeight; for (let y = 0; y < H; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } window.scrollTo(0, 0); });
    await page.waitForTimeout(700);
    const d = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, sh: document.documentElement.scrollHeight }));
    const name = (p.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home');
    await page.screenshot({ path: `${prefix}${name}.png`, fullPage: true });
    console.log(p, JSON.stringify(d), d.sw > d.cw ? 'OVERFLOW' : '', errs.join(' | '));
    await page.close();
  }
  await b.close();
})();
