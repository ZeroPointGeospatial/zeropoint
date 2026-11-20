# Styles

One section per style: what it is, when to use it, how to run it, the settings
worth changing, and what it can't do. All commands run from `tools/prints`
with `ZP_DATA` and `ZP_OUT` set.

## Relief

A ray-traced terrain model coloured by height, cut to an outline or drawn as
a rectangular block. The collection's Kenya, county, mountain and East Africa
plates are all this style.

```bash
python relief.py spec:maps/<slug>.yml 100 16     # proof
python relief.py spec:maps/<slug>.yml 300 40     # master
```

- **Region.** `countries`, `continent` and `geojson` are cut to their
  outline. `bbox` gives a block. Set `cut: false` to draw a block around an
  outline instead.
- **Projection.** UTM when the area is under about 6° by 10°, so distances
  read true; otherwise Lambert azimuthal equal-area centred on it.
- **Scale.** The largest tidy scale at which the outline fills the box. The
  scale sets the cell size (about 0.17 mm on paper) and the elevation source:
  GLO-30 tiles up to 1:400 000, GLO-90 beyond, read at reduced resolution
  from S3 once the cells pass 300 m.
- **Settings worth changing**: `labels`, `names`, `zex` if the relief looks
  flat or spiky, `sun_el` (default 30°; lower gives longer shadows), `scale`.
- **Kenyan counties**: `relief.py county:<Name>` is already set up. Put names
  and heights for a customer in `COUNTY_LABELS` in `relief.py`. The county
  boundaries need `python fetch_overture.py counties` once.
- **Limits**: the surface model shows forest canopy and buildings as relief.
  Below about 1:50 000 the canopy edges can look like cliffs, so keep `zex`
  low for small areas.

## Population

Population as columns of 3D hexagons rising from the land, tilted and
ray-traced. Kenya's plate 01 is this style.

```bash
python population.py spec:maps/<slug>.yml 100 16
python population.py spec:maps/<slug>.yml 300 40
```

- **Data**: Kontur Population 2023 (CC BY 4.0), one file per country,
  downloaded once. A `continent` or `countries` region picks the countries
  itself; a `bbox` or `geojson` region uses every country it touches.
- **Hexagon size**: Kontur's own 400 m hexagons (H3 resolution 8) only for
  areas up to about 700 km across, such as Uganda or Rwanda. Anything larger,
  Kenya included, is summed into coarser H3 hexagons whose edge prints about
  0.35 mm, so they are 0.5 to 0.9 mm across (Kenya gets resolution 7, about
  2.4 km). Force it with `h3_res` (8 is 400 m, 5 is about 17 km); use
  `h3_res: 8` for a Kenya plate that matches plate 01.
- **Size on the sheet**: the model spans 90% of the map box width. Raise
  `model_width` toward 1.0 to make it bigger; `scale` does nothing here.
  A tall country (Mozambique, Malawi, Madagascar) is shrunk automatically
  so the front of its base clears the title block.
- **Settings worth changing**: `towns` (name, position and where the text sits,
  with a leader line), `max_height_km` if the tallest city towers over
  everything, `tilt`.
- **Limits**: Kontur counts people where they sleep, not where they work. Small
  island states with no Kontur file are skipped and reported in the log. A
  hexagon on a border is in both countries' files; it is counted once.

## Contours

Contour lines on a near-black sheet with labelled index contours and a grid
ticked in kilometres. The Longonot and Mount Kenya summit studies are this
style.

```bash
python contours.py spec:maps/<slug>.yml 100
python contours.py spec:maps/<slug>.yml 300
```

- **Spec**: `centre: [lon, lat]`, `scale`, `interval` (metres), `index` (every
  how many metres a contour is drawn heavier and labelled), plus `labels` and
  `names`.
- **Choosing the interval**: about 40 to 80 contour lines across the relief of
  the area. Longonot (800 m of relief) uses 10 m at 1:20 000; Ngorongoro
  (1 800 m) uses 25 m at 1:75 000.
- **Limits**: contours are interpolated from a 30 m surface model. The sheet
  says "Not a ground survey", and it must keep saying it.

## City roads in gold

A town's road network inside a circle, gold on deep green, the name in
Playfair Display, the country beneath, the coordinates at the foot. The
original Nairobi print sets the layout; Mombasa, Kisumu, Nakuru and Eldoret
follow it.

```bash
python cities.py spec:maps/<slug>.yml 1600     # proof, 1600 px wide
python cities.py spec:maps/<slug>.yml 6744     # master, the Nairobi print's width
```

- **Spec**: `slug` (ending `-gold`), and `city: { name, country, lon, lat,
  radius_km }`. The radius sets how much of the town fits the circle: 5 to 7 km
  for a large town's centre and inner suburbs.
- **Data**: OpenStreetMap roads via Overture Maps. Kenyan towns use the
  national road file (`python fetch_overture.py roads` once); towns elsewhere
  have their roads fetched for the circle on the first run.
- **Format**: 4:5-ish (11 × 14 in), not A2, and no bleed. Point
  `tools/prints/PRINTING.md` out to the print shop.

## Rivers (Kenya only)

`kenya_hydro.py` then `kenya_rivers.py`. The drainage analysis is tuned to
Kenya: its five basins, its terminal lakes and swamps, the rainfall grid. For
another country it needs new sinks, basins and rainfall, and every river end
checked by eye. That is a day's work, not a spec. Quote it as custom work.

## National roads (Kenya only)

`kenya_roads.py` draws Kenya's roads as density with the classified network
over it. The Overture fetch takes any bounding box (`fetch_overture.py
roads-bbox`), but the plate's frame, scale and towns are Kenya's. Adapting it
to another country means copying the script and setting its frame and town
list.

## Drapes: land cover, forest loss, water, true colour

A drape paints the relief model with a data layer instead of the elevation
colours. Add `drape:` (and `drape_options:`) to a relief spec; everything else
in the spec works as for plain relief. The modules are in `tools/prints`
(`drapes.py` explains the contract); plates 22 to 26 are the examples.

- **Land cover** (`landcover`, plate 22): ESA WorldCover 2021, eleven classes,
  blended into the model cells. The legend lists the classes on the sheet.
  `drape_options: {facts: [Tree cover, Cropland, Built-up]}` chooses the
  classes stated in the title block; the shares are measured at 40 m (the
  coarser overviews inflate the dominant class). Say "as the satellite
  classification sees it" for cropland: smallholdings often read as tree
  cover or grassland.
- **Forest loss** (`forest-loss`, plate 23): Hansen Global Forest Change.
  Forest is canopy of 30 % or more in 2000; loss is coloured by year. Say
  "loss mapped", never "deforestation": it includes plantation harvest and
  fire and ignores regrowth. Don't rank single years: the makers warn that
  years before 2011 were mapped with an earlier method. The facts are for the
  whole sheet; say "on the sheet".
- **Water** (`water`, plate 24): JRC Global Surface Water transitions. Deep
  blue is water at the start of each place's record (from 1984) and in 2021,
  coral is new water. Name the lakes in `drape_options.lakes` to measure them
  (start and 2021 areas). The data compares two ends, not the years between.
- **True colour** (`true-colour`, plate 26): one Sentinel-2 scene (or a few,
  when none is clear), red, green and blue at 10 m with a gentle tone curve.
  For a shop plate pin `date:` so it renders the same next year. Large areas
  mean many tiles: keep custom true-colour areas to a district, a lake or a
  mountain.

Credit lines are built from each drape's credit plus the elevation credit; a
long credit breaks onto two lines on its own.

