# House style

What makes a sheet look like a ZeroPoint print, and the checks to run on every
proof. The pipeline applies most of this automatically. This file is for judging
the result and for knowing what not to override.

## The sheet

- **A2 portrait, 420 × 594 mm**, designed in millimetres, rendered at 300 dpi,
  with 3 mm of bleed on every side and an embedded sRGB profile. A1 and A0 are
  the same drawing enlarged, which is why the scale is stated "at A2".
- **Margins of 22 mm.** The map sits in the box above the title block; the
  title block is the bottom 90 mm. Nothing is placed outside the margins except
  the paper colour and the cast shadow.
- **Title block** (drawn by `Plate.title_block` in `common.py`; never draw your
  own): a hairline rule, the label and number (`PLATE 03`, `COUNTY 022`,
  `CUSTOM A1`) small and in olive, "ZEROPOINT GEOSPATIAL" on the right, the
  title large in Barlow Light capitals, the subtitle in spaced small capitals,
  a second rule, then four facts in a row (scale at A2, exaggeration or
  interval, projection or grid, sheet centre in degrees and minutes), and the
  credit line at the foot.
- **The credit line is required.** It names every data source and its licence
  (Copernicus, Kontur CC BY 4.0, OpenStreetMap ODbL, Natural Earth) and says
  the map was made by ZeroPoint Geospatial. The licences allow selling prints
  on the condition that this line stays.

## Type

- Barlow (300 for titles; 400, 500 and 600 for labels and small capitals) and
  IBM Plex Mono for figures: heights, coordinates, scale, legend values.
- The gold city prints use Playfair Display for the city name, to match the
  original Nairobi print.
- Point labels are capitals with a dot and a mono figure beneath, on a soft
  halo (`annotate`). Water, ranges, basins and deserts are italic and may be
  rotated along the feature (`name_label`), as on a topographic sheet.

## Colour

| Plates | Ground | Ink | Accent |
| --- | --- | --- | --- |
| Relief, population, counties (light) | paper `#f1f0eb` | ink `#0b0d0c` | olive `#788653` |
| Contours, rivers (dark) | near black `#0a0c0b` | warm off-white | the basin colours, or pale sand for contours |
| City prints and national roads | deep green `#0b1f14` | gold `#d3b795` | brighter gold for major roads |

- Relief uses the shared elevation ramp (`HYPSO` in `common.py`): sand, then
  olive green, forest green, brown rock, then pale grey to white above 5 200 m. An area with
  less than 1 500 m of relief gets the same ramp stretched over its own range,
  so it doesn't print as a single colour.
- Population uses sand to ochre to burnt orange to maroon, on a log scale that
  starts at the same density on every plate (about 30 to 40 people per km²:
  30 people in a resolution-8 Kontur hexagon of about 0.74 km², and the same
  density on coarser hexagons), so sparse land stays pale and colour deepens
  with density, darkest in the cities.
- Lakes and the sea are a muted blue-grey, never bright blue.

## Light and form

- Relief and population are 3D models, path-traced with one soft sun from the
  north-west, low (about 30°), and an even sky, standing on the paper so they
  cast a real shadow onto it.
- Relief is drawn straight down (plan view) so the stated scale holds across
  the sheet. Population is tilted (about 62°) so the columns read.
- Vertical exaggeration is printed on the sheet. It grows with the area: 3 to
  12 for a county, 22 for Kenya, 30 for East Africa, about 100 for a continent.

## What the sheets never do

- No drop shadows on text, no gradients behind the map, no frames or borders
  drawn round the map (the 3D block or the outline is the shape), no north
  arrow on relief (north is up and the grid or the sheet centre says so), no
  decorative compass roses, no invented legends.
- No claims the data can't support. A 30 m or 90 m surface model includes trees
  and buildings, and coarse cells lower the peaks. The legend shows what the
  model holds; the point labels give the surveyed heights.

## Review a proof against this list

Open the proof image and check each of these. Fix and re-render until all pass.

1. **The shape fills the map box** without touching the margins, and sits in
   the middle. If it looks small, try the next tidy scale down.
2. **Nothing odd at the edges**: no spikes or slivers (tiny islands, data
   holes), no missing corner (a missing elevation tile), no flat-topped
   plateau where there should be relief.
3. **The relief reads** from across a room but isn't caricature: valleys and
   ranges are clear, and no single peak dominates the sheet.
4. **Colour has range.** Not all sand, not all green. For population, colour
   gathers in cities and dense countryside, and empty land is pale.
5. **Labels**: none overlapping each other or the title block; each dot on the
   right feature; names spelled as the country spells them; heights from a
   source you can name.
6. **Title block**: title, subtitle, label and number correct; the four facts
   filled; the credit names every source used.
7. **Water** is blue-grey and in the right places. Big lakes show; the sea
   outside a cut outline is paper, not blue.
8. **It looks like it belongs** next to the Kenya relief, Kenya population,
   Longonot contours or Nairobi gold print. If it would look out of place on
   that wall, find out why before sending it.
