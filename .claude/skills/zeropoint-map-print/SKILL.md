---
name: zeropoint-map-print
description: Make a map print in ZeroPoint Geospatial's house style for any place and theme, using the print pipeline in tools/prints. Use this whenever someone asks for a map, poster, wall map, print, plate or proof of any area, whether a continent, a country, a county, a town, a mountain, a crater or a customer's own land, as relief, population, contours or roads in gold. That includes custom orders from the shop ("can you do one of Uganda", "Africa population", "my farm in Limuru", "Kampala in gold"), a proof request pasted from the website's form or email ("a request came in", "make a first look", "sketch this out for me"), first-look drafts, proofs to send a customer, and new plates for the collection, even when the request does not say "house style" or name the pipeline.
---

# ZeroPoint map prints

Every ZeroPoint print, from the Kenya atlas to a one-off customer order, comes
out of the same pipeline in `tools/prints`. That is what makes them look like a
collection: the same A2 sheet, title block, type, colours, light and credits.
A custom map is not made by drawing something new. It is made by describing the
area in a **map spec** and letting the pipeline draw it the way it draws
everything else. Don't hand-build a figure in matplotlib or another tool, even
when that looks quicker. It won't match the collection, and matching is the
whole point.

Read `references/house-style.md` before judging a proof, and
`references/styles.md` when choosing or tuning a style.

## 0. A proof request came in: make a first look

When the owner pastes a proof request from the website (the Formspree email:
name, area, style, size, frame, paper, notes), or asks for a quick sketch of a
customer's area, start with the first-look script. It finds the area, picks the
style, writes a draft spec and renders a quick proof stamped FIRST LOOK, NOT
FOR THE CLIENT, with notes of what it assumed:

```bash
cd tools/prints
python first_look.py --request request.txt          # the email, saved as a text file
python first_look.py "ngonghills" --style "Relief, ray-traced like the county plates"
python first_look.py "my farm near Limuru" --style contours --notes "-1.112, 36.650"
```

It writes `maps/drafts/<slug>.yml` (left out of git: requests carry
customers' details), `$ZP_OUT/first-look/<slug>_FIRST-LOOK.jpg` and
`<slug>_notes.md`. Show the owner the FIRST-LOOK image and the notes' "What the
draft assumed" list, then carry on from step 3 with the draft spec: fix the
extent, the title and subtitle, and the labels the customer asked for, and
render again. The FIRST-LOOK file is for the owner only; the customer gets the
watermarked proof from step 6 once the draft is right.

Read the notes before trusting the draft. They say when a place was read from
a close spelling, when only the wider place was found ("Juja, Kiambu" drawn as
all of Kiambu), when the place found is outside Kenya, when the customer's
coordinates are not on the sheet, and when a county page's request is simply
the shop's county plate. A second request for the same place never replaces
an earlier draft: it gets the next number (`draft-limuru-2-contours.yml`).

If the script can't find the place, it says what it tried. Ask for
coordinates (a point copied from Google Maps, in any of its formats, or a box),
or add the place to `tools/prints/places.yml`. It never takes a foreign town
of the same name for a Kenyan one without saying so: offline, "Juja" or
"Bondo" stop with that message rather than draw Peru or Congo. When the
computer is online it asks OpenStreetMap's search, in Kenya first, sending
only the place-name part of the request (never plot numbers, phone numbers or
people's names). If a render fails, the notes still get written, with the
likely cause and the full log beside them.

## 1. Pin down the brief

You need four things. Take them from the request and ask only for what is
missing and can't be sensibly assumed.

- **Area**: a continent, countries, a Kenyan county, a box of coordinates, a
  customer's outline (GeoJSON or KML converted to GeoJSON), or a point and a
  scale for a contour study or city.
- **Style**: relief, population, contours or city roads in gold (table below).
  If the customer only says "a map of X", relief is the default for natural
  areas and roads in gold for towns.
- **Words**: the title (usually the place name), a one-line subtitle, and any
  names the customer wants on it (their town, farm, school, a river).
- **What it is for**: a proof for a customer, a master for printing, or a new
  plate for the shop.

Orders also carry a size, frame and paper (matte or satin). Those affect the
price and the framing, not the drawing: every plate is designed at A2 and
scales up to A1 and A0.

## 2. Choose the style

| Asked for | Style | Script | Works for |
| --- | --- | --- | --- |
| Relief, terrain, mountains, "3D map", a county plate | Relief | `relief.py spec:` | anywhere, from a hill to a continent |
| Population, "where people live", density | Population | `population.py spec:` | any country or group of countries (Kontur data) |
| Contours, topographic, a crater or summit "line art" | Contours | `contours.py spec:` | anywhere; best from 1:10 000 to 1:100 000 |
| A town or city's streets, "gold", like the Nairobi print | City roads | `cities.py spec:` | any town; roads are fetched on first use |
| Rivers and drainage basins | Rivers | `kenya_rivers.py` | Kenya only (see styles.md) |
| Every road and track, as density | Roads | `kenya_roads.py` | Kenya only (see styles.md) |
| One of Kenya's 47 counties | Relief | `relief.py county:<Name>` | already set up; add labels in `COUNTY_LABELS` |

Rivers and national roads for other countries are not built yet. Say so
plainly and offer relief or population for that area, or quote the extra work.
Don't fake them with another style.

## 3. Write the spec

Specs live in `tools/prints/maps/<slug>.yml`; `tools/prints/maps/README.md`
lists the fields of each style. A relief spec is usually this short:

```yaml
slug: uganda-relief
title: Uganda
subtitle: Relief, from Lake Albert to Margherita Peak
label: CUSTOM
number: "U1"
region: { countries: [Uganda] }
labels:
  - { name: Margherita Peak, value: "5 109 m", lon: 29.871, lat: 0.386, side: left, snap: 3000 }
names:
  - { text: Lake Victoria, lon: 33.0, lat: -0.3, size: 3.0 }
```

Worked examples to copy: `maps/africa-relief.yml`, `maps/africa-population.yml`,
`maps/example-ngong-hills.yml` (a small block), `maps/example-ngorongoro-contours.yml`,
`maps/example-kampala-gold.yml`.

**Labels need care.** Every name, height and coordinate on a sheet is a
statement the company is putting on someone's wall. Take heights and positions
from a source you trust (official surveys, Wikipedia's infobox with its
citation, OpenStreetMap). Use `snap` for peaks so the dot sits on the highest
ground nearby. If you can't verify a name or a figure, leave it off. A plate
with five correct labels beats one with twelve doubtful ones. As a guide, a
country or continent carries 6 to 10 point labels and a few italic area names;
a small area, 2 to 6.

Leave projection, scale, exaggeration, colours and hexagon size to the
pipeline unless the first proof shows a reason to change them. Its defaults
are what keep custom plates consistent with the shop.

## 4. Proof, look, fix

Set the data and output folders, then render a proof at 100 dpi:

```bash
cd tools/prints
export ZP_DATA=/path/to/data ZP_OUT=/path/to/out
python relief.py spec:maps/uganda-relief.yml 100 16
```

Once per data folder, before the first render, run `python fetch_data.py
fonts` and `python fetch_data.py naturalearth` (and `python fetch_overture.py
counties` for a county region; `tools/prints/README.md` has the full setup).
Without them the render stops at once on a missing font or `ne/` file. The
render itself then downloads the elevation tiles, or the Kontur population
file for each country, that it needs. A proof
takes one to three minutes; a continent's elevation adds about a minute.

**Open the proof image and look at it** before going further. Check it against
the review list in `references/house-style.md`. The usual fixes:

- Labels overlapping each other or a strong feature: move the italic names, or
  switch a point label's `side`.
- Spikes or slivers off the coast: small far-off islands. They are dropped by
  default for countries and continents (the log names each one, and warns if
  they add up to more than 1% of the area), so for other regions check the
  outline. If a customer wants an island that was dropped, set `keep_islands:
  true` in the region.
- Relief too flat or too spiky: set `zex`. Counties sit around 3 to 12, Kenya
  at 22, East Africa at 30, Africa at 100.
- The area too small on the sheet: for relief, set `scale` to the next tidy
  value down; for population, raise `model_width` (default 0.90) toward 1.0.
- A flat area that is all one colour: the pipeline already uses the area's own
  range under 1 500 m of relief. Check that `stops` is not set by mistake.

Render again until the proof passes the review list. The render is cached by
everything that affects it, so a change to labels or type re-runs in seconds.

## 5. Master and print files

```bash
python relief.py spec:maps/uganda-relief.yml 300 40    # A2, 300 dpi, 3 mm bleed, sRGB
python export_print.py                                  # JPEGs with and without bleed
```

A 3D master takes about ten minutes. City prints use a pixel width instead of
a dpi (`cities.py spec:... 6744`). `tools/prints/PRINTING.md` covers the files
a print shop needs.

## 6. Send the proof to the customer

```bash
python proof_jpeg.py $ZP_OUT/uganda-relief_100.png
```

This writes `uganda-relief_PROOF.jpg`: the whole sheet, readable, watermarked,
and too small to print from. Send that, never the master, until the customer
has approved and paid. Custom orders allow two rounds of changes (see
`proof` in `_data/shop.yml`).

## 7. Adding it to the shop (only if asked)

1. Add the slug to `PLATES` (or `CITY_PRINTS`) in `tools/site_assets.py` and
   run `python tools/site_assets.py prints`.
2. Write `_prints/<slug>.md` like its neighbours: `series` must be one of the
   series in `_data/shop.yml`, which also sets its price. The facts should
   come from the render log and the sheet (scale, data, exaggeration), not
   from memory.
3. Build the site and check the page before committing.

## What to report back

Say what you made and show the proof image. Give the scale, projection and data
source, any label you left off because you couldn't verify it, and anything
the customer should decide (a name to add, a different crop). If the pipeline
can't do what was asked (rivers outside Kenya, for example), say so and offer
the nearest thing it can do.
