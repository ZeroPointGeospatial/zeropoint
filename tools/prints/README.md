# Print pipeline

The scripts that draw the nine ZeroPoint map plates from open data. Nothing
in this folder is published with the website; it is here so every plate can
be re-rendered, changed or made for another area.

## Plates

| No. | Plate | Script | Source data |
| --- | --- | --- | --- |
| 01 | Kenya, population | `population.py kenya` | Kontur Population 2023 |
| 02 | Kenya, rivers and basins | `kenya_hydro.py`, then `kenya_rivers.py` | Copernicus DEM GLO-90 |
| 03 | Kenya, relief | `relief.py kenya` | Copernicus DEM GLO-90 |
| 04 | Kenya, roads | `fetch_roads.py`, then `kenya_roads.py` | OpenStreetMap via Overture Maps |
| 05 | Kenya, tree cover | `relief.py kenya-forest` | Hansen Global Forest Change, GLO-90 |
| 06 | Mount Kenya | `relief.py mount-kenya` | Copernicus DEM GLO-30 |
| 07 | Kilimanjaro | `relief.py kilimanjaro` | Copernicus DEM GLO-30 |
| 08 | The Rift Valley | `relief.py rift-valley` | Copernicus DEM GLO-30 |
| 09 | Longonot contours | `contours.py` | Copernicus DEM GLO-30 |

Plates 10 to 12 (the Nairobi prints) were made separately; their files are
in `originals/prints/`.

## Setting up

Python 3.11 or newer.

    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt

    export ZP_DATA=/path/with/space     # about 3 GB of downloads and caches
    export ZP_OUT=/path/for/output

    python fetch_data.py all            # elevation, population, boundaries, forest, fonts
    for n in mount-kenya kilimanjaro rift; do python fetch_data.py dem30 $n; done
    python fetch_roads.py               # Kenya's roads, about a minute
    python kenya_hydro.py               # drainage analysis, about a minute

## Rendering

    python relief.py mount-kenya 100    # a quick proof at 100 dpi
    sh render_all.sh                    # every plate at A2, 300 dpi (4961 x 7016 px)

Every plate is designed at A2 portrait. The second argument is the dpi and
the third, for the 3D plates, the samples per pixel (48 is plenty with the
denoiser). On a four-core machine a 3D plate takes about ten minutes at
300 dpi; the line plates take seconds.

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
filled. Each stream is then labelled by the outlet it reaches and grouped
into Kenya's five drainage basins. Areas inside Kenya from the current run:
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

**Sheet.** `common.py` holds the plate layout: title block, plate number,
facts row, credit line, legends and labels. All dimensions are in
millimetres on A2.

## Licences of the data

Each plate prints its own credit line. If you sell prints, keep it.

- Copernicus DEM GLO-30 and GLO-90: © DLR e.V. 2010-2014 and © Airbus
  Defence and Space GmbH 2014-2018, provided under COPERNICUS by the
  European Union and ESA. Free for commercial use with attribution.
- Kontur Population 2023: CC BY 4.0.
- OpenStreetMap, via Overture Maps: ODbL 1.0. Printed maps are a "produced
  work"; attribution to OpenStreetMap contributors is required.
- Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11: CC BY 4.0.
- Natural Earth boundaries and lakes: public domain.
- Barlow and IBM Plex Mono typefaces: SIL Open Font License 1.1.

Country outlines come from Natural Earth at 1:10 million. They are fine
for a wall print and not a statement about any boundary.
