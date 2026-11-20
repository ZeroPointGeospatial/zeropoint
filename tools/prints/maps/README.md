# Map specs

A map spec is a short YAML file that describes a custom plate: the area, the
style, the title and the labels. The pipeline works out the rest (projection,
scale, elevation data, hexagon size, colours, sheet) the same way it does for
the plates in the shop, so a custom map looks like the collection.

    python relief.py spec:maps/africa-relief.yml 100 16        # proof, about 2 minutes
    python relief.py spec:maps/africa-relief.yml 300 40        # print master
    python population.py spec:maps/africa-population.yml 100 16
    python proof_jpeg.py $ZP_OUT/africa-relief_100.png          # watermarked proof for the customer
    python export_print.py                                       # print-ready JPEGs of every master

The arguments after the spec are the dpi and the samples per pixel. A master
is A2 at 300 dpi with 3 mm of bleed; anything under 250 dpi is saved as a
proof, with `_<dpi>` in its name.

## Fields

| Field | Used by | Meaning |
| --- | --- | --- |
| `slug` | both | file name of the output, lowercase-with-hyphens |
| `title` | both | the big word on the sheet: usually the place name |
| `subtitle` | both | one line under it, in capitals on the sheet |
| `label`, `number` | both | the small line above the title, e.g. `CUSTOM` `A1`, or `PLATE` `16` |
| `region` | both | the area; see below |
| `labels` | relief | point labels: `name`, optional `value` (a height), `lon`, `lat`, `side` (left/right), `snap` (metres: move the dot to the highest ground within this distance) |
| `names` | relief | italic area names: `text`, `lon`, `lat`, optional `angle` (degrees) and `size` (mm) |
| `towns` | population | `name`, `lon`, `lat`, `offset` [right, down] in mm for the text, `side` |
| `scale` | relief, contours | relief: force a scale, e.g. `2400000`, normally chosen to fill the sheet. Contours: required. Population ignores it |
| `model_width` | population | share of the map box the model spans, default 0.90; raise it toward 1.0 to make the area bigger on the sheet |
| `crs` | both | force a projection (EPSG code or proj string); normally UTM for small areas and Lambert equal-area for large ones |
| `zex` | relief | force the vertical exaggeration; normally from the area's width and relief |
| `stops` | relief | colour stops `[[metres, "#hex"], ...]`; normally the shared ramp, or the area's own range when it has less than 1 500 m of relief |
| `cut` | relief | `false` draws a rectangle around the area instead of cutting to its outline |
| `h3_res` | population | force the hexagon size (H3 resolution 4 to 8; 8 is 400 m) |
| `max_height_km` | population | height of the tallest column; normally half the width of the area |
| `credit` | relief | replace the boundary credit, e.g. for a customer's own outline |
| `centre` | contours | `[lon, lat]` of the sheet centre, required; contours take no `region` |
| `interval` | contours | contour interval in metres, required |
| `index` | contours | every how many metres a contour is drawn heavier and labelled; default five intervals |
| `city` | city roads | `{ name, country, lon, lat, radius_km }`; the slug must end in `-gold`; takes no `region` |

Contour specs also take `labels` and `names`, as relief does.

## Regions

    region: { countries: [Kenya, Uganda, United Republic of Tanzania] }
    region: { continent: Africa }
    region: { bbox: [36.55, -1.50, 36.75, -1.30] }      # west, south, east, north
    region: { geojson: maps/clients/smith-farm.geojson }
    region: { county: Nakuru }

Country names follow Natural Earth's `ADMIN` column; common alternatives
(Tanzania, DRC, Ivory Coast) are understood. Countries and continents lose
small islands far from the coast unless `keep_islands: true` is added inside
`region`. A `bbox` is drawn as a rectangular block; every other region is cut
to its outline.

## Where the data comes from

- **Elevation**: Copernicus DEM. GLO-30 (30 m) for areas up to about
  1:400 000, GLO-90 above that. For a country or a continent the tiles are
  read at reduced resolution straight from Amazon S3, so even Africa takes
  about a minute.
- **Population**: Kontur Population 2023, one file per country, downloaded
  once into `$ZP_DATA/kontur`. Kontur's 400 m hexagons (H3 resolution 8) are
  kept for areas up to about 700 km across; for larger areas they are summed
  into coarser H3 hexagons whose edge prints about a third of a millimetre
  (0.5 to 0.9 mm across). Kenya as a spec gets resolution 7; set `h3_res: 8`
  to match plate 01.
- **Outlines**: Natural Earth 1:10 m countries; Kenya's counties from
  OpenStreetMap via Overture Maps.

Each source's credit is printed on the sheet automatically.
