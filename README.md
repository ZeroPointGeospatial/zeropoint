# ZeroPoint Geospatial website

A Jekyll site. Two copies are published:

- https://zeropointgeospatial.pages.dev/ by Cloudflare Pages from the
  `cloudflare` branch, built with
  `bundle exec jekyll build --config _config.yml,_config.cloudflare.yml`.
  `_config.cloudflare.yml` holds the settings that differ: the address, the
  Search Console and analytics switches, and the `_headers` and `_redirects`
  files Cloudflare reads.
- https://zeropointgeospatial.github.io/zeropoint/ by GitHub Pages from
  the `main` branch, until the repository is made private.

## Where things are

| To change | Edit |
| --- | --- |
| Phone numbers, email, WhatsApp, social links, booking link | `_data/contact.yml` |
| Navigation | `_data/nav.yml` |
| Services, client types, survey packs, FAQ on the home page | `_data/services.yml`, `audiences.yml`, `packs.yml`, `faq.yml` |
| A client type's own page (`/for/<name>/`) | its file in `_sectors/` |
| Project cards | `_data/projects.yml` |
| Print prices, sizes, frames, paper, Paystack key, proof wording | `_data/shop.yml` |
| Photos of framed prints on real walls | `_data/wall_photos.yml`, photos in `assets/photos/` |
| One print's title, description and facts | its file in `_prints/` |
| A blog post | a Markdown file in `_posts/` named `YYYY-MM-DD-title.md`, with a `topic` from `_data/topics.yml` |
| Automatic blog posts | `tools/blog/` (see its README) |
| Colours, type and layout | `css/site.css` |
| Page furniture (head, navigation, footer) | `_includes/` and `_layouts/` |

Pages: `index.html` (home), `projects.html` (served at /projects/), `prints/index.html` (shop),
`prints/counties/` (all 47 counties), `prints/custom/` (made-to-order prints),
`blog/index.html`. Each print gets its own page at `/prints/<name>/` from
`_layouts/print.html`, and each client type one at `/for/<name>/` from
`_layouts/sector.html`.

## Taking payment

Prices are set in `_data/shop.yml` under `pricing`: one table per series,
by size (A2, A1, A0) and frame (none, black, natural wood, silver, gold).
The Kenya atlas runs from KSh 18 000 to 23 000, the counties from 9 000 to
20 000, the gold city prints from 10 000 to 16 500, and the landforms (with
the regional theme plates: the Mau, Baringo and Bogoria, Lake Victoria and
Lake Magadi) from 14 000 to 19 000. The paper (matte or satin)
does not change the price. Custom sizes are quoted by hand.

Prints from the collection can be paid for on the site by M-Pesa or card
through Paystack. It stays switched off until `paystack_key` in
`_data/shop.yml` holds the **public** key from the Paystack dashboard
(Settings > API Keys & Webhooks), starting `pk_live_`. Never put the secret
key in this repository.

The customer enters their name, phone, email and delivery address, pays in
the Paystack window, and the order is emailed to you through Formspree with
the Paystack reference. Every payment is also in the Paystack dashboard,
with the print, size and delivery details attached; check it there before
dispatching. County plates and custom areas are not paid on the site: they
go through a proof request, and you send a Paystack payment link once the
customer approves the proof.

## Search and measurement

- **Google Search Console.** Add `https://zeropointgeospatial.pages.dev/` as a
  URL-prefix property, choose the HTML tag method, and put the tag's
  `content` value in `google_site_verification` in `_config.cloudflare.yml`.
  Once verified, submit `sitemap.xml`.
- **Google Business Profile.** Create it at business.google.com with the same
  name, phone and website as the site. The home page already carries the
  matching structured data.
- **Analytics.** In Cloudflare, open the Pages project > Metrics and switch on
  Web Analytics. It sets no cookies, so no cookie banner is needed.

## Adding a print

1. Put the artwork in `originals/prints/<name>.png`, or render it with the
   pipeline in `tools/prints/`.
2. Add `<name>` to `OWN_PRINTS` (or to `PLATES` or `CITY_PRINTS` if the
   pipeline rendered it) in `tools/site_assets.py` and run
   `python tools/site_assets.py prints`. That writes the previews to
   `assets/prints/` and their sizes to `_data/print_images.yml`.
3. Copy a file in `_prints/`, rename it `<name>.md` and edit the text.
   `series` must be one of the series listed in `_data/shop.yml`; `order`
   sets its place in the catalogue.

Custom maps of any area (relief, population, contours, city roads) are made
from a short spec file: see "Custom maps of any area" in
`tools/prints/README.md`, or ask Claude Code, which has a skill for it in
`.claude/skills/zeropoint-map-print`.

When a proof request comes in from the website, `python
tools/prints/first_look.py --request request.txt` (the request email saved as
text) makes a first-look draft for you, never for the customer: it finds the
area, writes a draft spec and renders a quick proof stamped "FIRST LOOK, NOT
FOR THE CLIENT", with notes on what it assumed. Or paste the request into
Claude Code and ask for a first look.

County plates: `sh tools/prints/render_counties.sh` renders every county,
`python tools/county_pages.py` writes their pages, and
`python tools/site_assets.py counties` their previews. A city print for a
customer is one command: see `tools/prints/README.md`. `tools/prints/PRINTING.md` has the notes for the
print shop.

## Running it locally

    bundle install
    bundle exec jekyll serve --baseurl ""

## Folders that are not published

`tools/` holds the Python that draws the map plates, builds the web
images, writes the county pages and the automatic blog posts. `originals/` holds full-size source files: the logo, the site
photos and the three Nairobi print files. Both are excluded from the
built site in `_config.yml`, but this repository is public, so anything
you want to keep private (for example print-resolution artwork) should
not be committed here.
