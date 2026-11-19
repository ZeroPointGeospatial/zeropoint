# ZeroPoint Geospatial website

The site at https://zeropointgeospatial.github.io/zeropoint/. It is a
Jekyll site, built by GitHub Pages from the `main` branch.

## Where things are

| To change | Edit |
| --- | --- |
| Phone numbers, email, WhatsApp, social links, booking link | `_data/contact.yml` |
| Navigation | `_data/nav.yml` |
| Services, client types, survey packs, FAQ on the home page | `_data/services.yml`, `audiences.yml`, `packs.yml`, `faq.yml` |
| Project cards | `_data/projects.yml` |
| Print prices, sizes and frame options | `_data/shop.yml` |
| One print's title, description and facts | its file in `_prints/` |
| A blog post | a Markdown file in `_posts/` named `YYYY-MM-DD-title.md` |
| Colours, type and layout | `css/site.css` |
| Page furniture (head, navigation, footer) | `_includes/` and `_layouts/` |

Pages: `index.html` (home), `projects.html`, `prints/index.html` (shop),
`blog/index.html`. Each print gets its own page at `/prints/<name>/` from
`_layouts/print.html`.

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

A county relief plate or a city print for a customer is one command: see
`tools/prints/README.md`. `tools/prints/PRINTING.md` has the notes for the
print shop.

## Running it locally

    bundle install
    bundle exec jekyll serve --baseurl ""

## Folders that are not published

`tools/` holds the Python that draws the map plates and builds the web
images. `originals/` holds full-size source files: the logo, the site
photos and the three Nairobi print files. Both are excluded from the
built site in `_config.yml`, but this repository is public, so anything
you want to keep private (for example print-resolution artwork) should
not be committed here.
