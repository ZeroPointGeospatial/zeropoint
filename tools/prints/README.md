# Print pipeline

The scripts that draw the ZeroPoint map plates from open data. Nothing in
this folder is published with the website; it is here so every plate can be
re-rendered, changed or made for another area. `PRINTING.md` has the notes
for sending the files to a print shop.

## Plates

| No. | Plate | Script | Source data |
| --- | --- | --- | --- |
| 01 | Kenya, population | `population.py kenya` | Kontur Population 2023 |
| 02 | Kenya, rivers and basins | `kenya_hydro.py`, then `kenya_rivers.py` | Copernicus DEM GLO-90, CHIRPS rainfall |
| 03 | Kenya, relief | `relief.py kenya` | Copernicus DEM GLO-90 |
| 04 | Kenya, roads | `kenya_roads.py` | OpenStreetMap via Overture Maps |
| 05 | Kenya, tree cover | `relief.py kenya-forest` | Hansen Global Forest Change, GLO-90 |
| 06 | Mount Kenya | `relief.py mount-kenya` | Copernicus DEM GLO-30 |
| 07 | Kilimanjaro | `relief.py kilimanjaro` | Copernicus DEM GLO-30 |
| 08 | The Rift Valley | `relief.py rift-valley` | Copernicus DEM GLO-30 |
| 09 | Longonot contours | `contours.py longonot` | Copernicus DEM GLO-30 |
| 13 | Kenya, the 47 counties | `counties.py` | OpenStreetMap via Overture Maps, GLO-90 |
| 14 | East Africa, relief | `relief.py east-africa` | Copernicus DEM GLO-90 |
| 15 | Mount Kenya summit contours | `contours.py mount-kenya-summit` | Copernicus DEM GLO-30 |
| 20 | Africa, relief | `relief.py spec:maps/africa-relief.yml` | Copernicus DEM GLO-90 (read at reduced resolution), Natural Earth |
| 21 | Africa, population | `population.py spec:maps/africa-population.yml` | Kontur Population 2023, Natural Earth |
| 22 | Kenya, land cover | `relief.py kenya-landcover` | ESA WorldCover 2021, GLO-90 |
| 23 | The Mau Forest, forest loss | `relief.py spec:maps/mau-forest-loss.yml` | Hansen Global Forest Change v1.11, GLO-30 |
| 24 | Baringo & Bogoria, the growing lakes | `relief.py spec:maps/baringo-bogoria-water.yml` | JRC Global Surface Water v1.4, GLO-30, OpenStreetMap names |
| 25 | Lake Victoria, population | `population.py spec:maps/lake-victoria-population.yml` | Kontur Population 2023, Natural Earth |
| 26 | Lake Magadi, true colour | `relief.py spec:maps/magadi-true-colour.yml` | Copernicus Sentinel-2 L2A, GLO-30, OpenStreetMap names |
| County | Relief of one county | `relief.py county:Kiambu` | Copernicus DEM, Overture Maps boundary |
| City | Roads of a town in gold | `cities.py mombasa` | OpenStreetMap via Overture Maps |

Plates 10 to 12 (the Nairobi prints) were made separately; their files are
in `originals/prints/`. Plates 16 to 19 are the gold city prints of Mombasa,
Kisumu, Nakuru and Eldoret (`cities.py`). The city prints copy the layout of the Nairobi gold
print so they hang as a set.

**A county to order.** `python relief.py county:Machakos` draws any of the
47 counties: it fetches the elevation tiles it needs, picks a tidy scale
that fills the sheet, sets the colour breaks to the county's own range of
heights and numbers the plate with the official county code. Names and
spot heights for a county go in `COUNTY_LABELS` in `relief.py`; without an
entry the plate is drawn unlabelled.

**Another town.** Add a line to `CITIES` in `cities.py` with the centre and
the radius in kilometres, or write a map spec (below) for a town anywhere.

## Custom maps of any area

Relief, population, contour and city prints can be made for any area from a
short YAML file in `maps/`: the area (countries, a continent, a box, an
outline, a county), the title and the labels. The pipeline chooses the
projection, scale, elevation data and hexagon size, so a custom map matches
the collection. `maps/README.md` lists the fields; `maps/africa-relief.yml`,
`maps/africa-population.yml` and the `maps/example-*.yml` files are worked
examples.

    python relief.py spec:maps/africa-relief.yml 100 16          # proof
    python population.py spec:maps/africa-population.yml 300 40   # master
    python contours.py spec:maps/example-ngorongoro-contours.yml 100
    python cities.py spec:maps/example-kampala-gold.yml 1600
    python proof_jpeg.py $ZP_OUT/africa-relief_100.png            # watermarked proof for a customer

For large areas the elevation tiles are read at reduced resolution straight
from S3 (`regions.load_dem_coarse`), so all of Africa takes about a minute.
Population for several countries is downloaded once per country and, for large
areas, summed into larger H3 hexagons.

Claude Code sessions in this repository have a skill for this,
`.claude/skills/zeropoint-map-print`, which holds the house style and the
proof-review-print steps. Asking for "a relief map of Uganda" or "Kampala in
gold, like the Nairobi print" is enough.

## Setting up

Python 3.11 or newer.

    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt

    export ZP_DATA=/path/with/space     # about 3 GB of downloads and caches
    export ZP_OUT=/path/for/output

    python fetch_data.py all            # elevation, population, boundaries, forest, rainfall, fonts
    for n in mount-kenya kilimanjaro rift; do python fetch_data.py dem30 $n; done
    python fetch_overture.py roads      # Kenya's roads, about a minute
    python fetch_overture.py counties   # county boundaries
    python kenya_hydro.py               # drainage analysis, about two minutes

## First looks from proof requests

When a proof request arrives from the website, `first_look.py` turns it into
a draft for you, not for the customer:

    python first_look.py --request request.txt     # the request email saved as text
    python first_look.py "ngonghills" --style relief
    python first_look.py "Kisumu" --style gold

It finds the area: coordinates (a Google Maps link or pin, decimal degrees,
degrees-minutes-seconds with N/S/E/W, or a box), then a Kenyan county, a
landmark in `places.yml`, a town, a lake, a peak or a country; when online,
OpenStreetMap's search in Kenya (sent the place name only); then close
spellings of Kenyan names; then the wider place the request names. A town
abroad with the same name is used only when it is in a neighbouring country
or the country is named, and the notes flag it. It writes
`maps/drafts/<slug>.yml`, renders a 100 dpi proof stamped FIRST LOOK, NOT FOR
THE CLIENT into `$ZP_OUT/first-look/`, and writes notes of what it assumed
and what to check (also when the render fails, with the log beside them).
Edit the spec, render again with the command in the notes, then make the
customer's proof with `proof_jpeg.py`. A relief draft takes about half a
minute. `maps/drafts/` is not committed; an existing draft there is never
written over (the new one gets the next number) unless you pass `--replace`.
For a Formspree export, `--row` picks a row (0 is the oldest; the newest by
date is the default; when the dates can't be read it asks for `--row`). The
form's land cover, forest loss, water and true colour styles become relief
drafts with a `drape:`, and the notes name the drape and carry its figures
(for true colour, the scene date to pin). A style written into the area
("Kenya land cover") is used when the request gives none.

## Rendering

    python relief.py mount-kenya 100    # a quick proof at 100 dpi
    sh render_all.sh                    # every plate in the table at A2, 300 dpi
    sh render_counties.sh               # all 47 county plates (previews at 150 dpi)
    python export_print.py              # print-ready JPEGs in $ZP_OUT/print

Every plate is designed at A2 portrait. The second argument is the dpi and
the third, for the 3D plates, the samples per pixel (40 is plenty with the
denoiser). On a four-core machine a 3D plate takes about ten minutes at
300 dpi; the line plates take seconds.

A master is the A2 sheet plus 3 mm of bleed on every side (5031 x 7086 px
at 300 dpi), saved as a PNG with the sRGB profile embedded. `export_print.py`
turns the masters into the two JPEGs a print shop may ask for, with and
without the bleed.

The ray-traced image of a 3D plate is cached in `$ZP_DATA/cache/renders`,
keyed by everything that affects it. Changing a label, a colour in the
title block or the type and running the plate again takes seconds, not
minutes. Set `ZP_FRESH=1` to ignore the cache.

For A0, the 300 dpi A2 file prints at 150 dpi, which is fine at viewing
distance. For a sharper A0, render the line plates at 600 dpi
(`DPI=600 sh render_all.sh`); the 3D plates gain little beyond 300 dpi
because the elevation data is no finer than that.

After rendering, `python tools/site_assets.py prints share` (run from the
repository root) rebuilds the web previews in `assets/prints/`.

## How the plates are made

**Rivers.** No river dataset is downloaded. `kenya_hydro.py` mosaics the
90 m surface model over Kenya and the surrounding catchments, floods it from
the sea, the sheet edge and the terminal lakes (Priority-Flood), routes flow
by steepest descent and accumulates upstream area. Closed basins such as
the Rift lakes, the Chalbi and the calderas are kept open rather than
filled; a "closed basin" that swallows more than 1 500 km2 of catchment and
is not a named lake is treated as a gorge the 90 m model fails to resolve,
and is allowed to spill (this is what carries the Kerio through to Lake
Turkana). A river is drawn through a reservoir it flows out of and stops
at a lake it ends in. Each stream is then labelled by the outlet it
reaches and grouped into Kenya's five drainage basins.

Line weight is estimated mean flow, not catchment area. Mean annual
rainfall (CHIRPS, 1991 to 2020) is turned into runoff with the Budyko
curve, using Woodhead's potential evaporation for Kenya as a function of
altitude, and accumulated downstream. It is an estimate for drawing with:
it puts the Tana at Garissa at about 135 m3/s against a gauged mean of
roughly 150 m3/s or a little more,
but it has no losses to the river bed, so dryland rivers such as the lower
Turkwel are drawn heavier than they run. The Ewaso Ng'iro is ended at the
Lorian Swamp. Areas inside Kenya from the current run:
Lake Victoria 51 100 km2, Rift Valley 130 400 km2, Athi 67 300 km2, Tana
116 300 km2, Ewaso Ng'iro North 224 600 km2. The Athi and Tana split along
the coast is by river mouth, which is not how the official catchment
boundary is drawn there, so check before quoting these.

**Relief and population.** `render3d.py` builds a mesh and path-traces it
with Mitsuba 3: one soft sun from the north-west, an even sky, a paper
floor that catches the shadow, and Intel Open Image Denoise. Lighting is
normalised so colours come back as specified. Relief plates are in plan
view so the stated scale holds.

**Roads.** Local roads are accumulated into a density layer (road length
per pixel); trunk to tertiary roads are drawn over it as lines.

**Counties.** Boundaries are the OpenStreetMap county relations as
published by Overture Maps. The Ilemi Triangle is drawn as part of Turkana.
Neighbouring counties are given different tints by a greedy colouring.

**Contours.** Interpolated from the 30 m surface model after light
smoothing, with labelled index contours and UTM grid ticks on the neat
line.

**Sheet.** `common.py` holds the plate layout: title block, plate number,
facts row, credit line, legends, place labels and the bleed. All dimensions
are in millimetres on A2.

## Licences of the data

Each plate prints its own credit line. If you sell prints, keep it.

- Copernicus DEM GLO-30 and GLO-90: © DLR e.V. 2010-2014 and © Airbus
  Defence and Space GmbH 2014-2018, provided under COPERNICUS by the
  European Union and ESA. Free for commercial use with attribution.
- Kontur Population 2023: CC BY 4.0.
- OpenStreetMap, via Overture Maps: ODbL 1.0. Printed maps are a "produced
  work"; attribution to OpenStreetMap contributors is required.
- Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11: CC BY 4.0.
- CHIRPS rainfall (Climate Hazards Center, UC Santa Barbara): public
  domain.
- Natural Earth boundaries and lakes: public domain.
- Barlow, IBM Plex Mono and Playfair Display typefaces: SIL Open Font
  License 1.1.

Country outlines come from Natural Earth at 1:10 million and county
boundaries from OpenStreetMap. They are fine for a wall print and not a
statement about any boundary.
