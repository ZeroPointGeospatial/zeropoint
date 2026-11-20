# Site checks

Three checks to run after changing the site and before merging to `main`.
None of them is needed to build the site.

Build and serve the site first, from the repository root:

    bundle exec jekyll build
    mkdir -p /tmp/srv && ln -sfn "$PWD/_site" /tmp/srv/zeropoint
    python3 -m http.server 4000 --directory /tmp/srv &

Then:

    python3 tools/checks/links.py _site
    node tools/checks/interact.js http://localhost:4000/zeropoint/
    node tools/checks/phone.js http://localhost:4000/zeropoint/ /tmp/phone_ ",prints/,projects/,blog/"

- `links.py` reads every built page and reports broken internal links,
  anchors and images, images without a size or alt text, duplicate ids and
  invalid JSON-LD. `404.html` is listed with four "broken" links: they are
  absolute on purpose, because that page is served from any address.
- `interact.js` drives a browser through the print order options, the zoom,
  the catalogue filters, the FAQ, the quote form and the phone menu. The
  form's network request is intercepted, so nothing is sent to Formspree.
- `phone.js` opens each page at phone width, reports horizontal overflow
  and failed requests, and saves a full-page screenshot.

The two browser checks need Node and Playwright (`npm i playwright`, then
`npx playwright install chromium`).
