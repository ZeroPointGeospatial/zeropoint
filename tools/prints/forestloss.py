"""Forest loss drape: Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11.

Each 30 m cell of the dataset (one arc-second, 0.00025 degrees) is put in one
of three states and coloured:

    not forest in 2000       canopy under the threshold (30 %): the bone of the model
    forest still standing    forest in 2000 with no loss recorded 2001 to 2023: green
    forest lost in year Y    forest in 2000 that the dataset records as lost in Y:
                             a ramp from pale yellow (2001) to deep red (2023)

The cells are coloured at their own resolution and averaged onto the model
grid, so a model cell that is part forest, part cleared takes a mix of the
two colours, as it does from the air. Areas are summed at full resolution,
each cell weighted by its true area on the ellipsoid.

    drape: forest-loss                     # in a plate or a map spec
    drape_options: {threshold: 30}         # canopy % that counts as forest in 2000

"Loss" here is the dataset's own definition: a stand-replacing disturbance,
the canopy removed from a 30 m cell. It includes the harvest of plantations
and losses to fire, as well as clearing for farms, and it does not net off
regrowth. The sheet says "forest lost", not "deforested".

Tiles: the four Kenya tiles that `fetch_data.py forest` puts in
$ZP_DATA/hansen are read from disk; any other tile is read from the
dataset's own bucket on storage.googleapis.com, a window at a time.
"""
import hashlib
import json
import math

import numpy as np

import drapes
from common import DATA, OUT, draw_text, font, hex_rgb, rasterize_geom

VERSION = "GFC-2023-v1.11"
REMOTE = ("https://storage.googleapis.com/earthenginepartners-hansen/" + VERSION +
          "/Hansen_" + VERSION + "_{layer}_{tile}.tif")
PX = 0.00025                     # one arc-second: about 28 m at the equator
FIRST, LAST = 2001, 2023         # the loss years in v1.11 (lossyear 1..23)

NOT_FOREST = "#ebe6da"           # the bone of an unpainted model
STANDING = "#2f6a45"             # the tree green of the land cover plate
# loss year -> colour: early losses pale, recent ones deep, so the order reads
# at a glance. Stops in years; interpolated in linear light.
YEAR_STOPS = [(2001, "#f1d98a"), (2006, "#ecb35a"), (2011, "#df7e3c"),
              (2016, "#c2452e"), (2020, "#951f2a"), (2023, "#661227")]


def tile_name(top, left):
    return f"{abs(top):02d}{'N' if top >= 0 else 'S'}_{abs(left):03d}{'E' if left >= 0 else 'W'}"


def tiles_for(bbox):
    """[(tile name, top, left)] of the 10-degree tiles that cover bbox."""
    w, s, e, n = bbox
    out = []
    for top in range(int(math.ceil(n / 10) * 10), int(math.floor(s / 10) * 10), -10):
        for left in range(int(math.floor(w / 10) * 10), int(math.ceil(e / 10) * 10), 10):
            out.append((tile_name(top, left), top, left))
    return out


def tile_path(layer, tile):
    f = DATA / "hansen" / f"{layer}_{tile}.tif"
    return str(f) if f.exists() else "/vsicurl/" + REMOTE.format(layer=layer, tile=tile)


def year_rgb(year):
    """The colour of a loss year, 0..255 sRGB."""
    from common import srgb_to_linear, linear_to_srgb
    ys = np.array([y for y, _ in YEAR_STOPS], "float32")
    cs = srgb_to_linear(np.array([hex_rgb(c) for _, c in YEAR_STOPS], "float32") / 255)
    lin = np.array([np.interp(year, ys, cs[:, i]) for i in range(3)])
    return np.round(linear_to_srgb(lin) * 255).astype("uint8")


def colour_table():
    """Class code -> colour: 0 not forest, 1 standing forest, 1 + k lost in year 2000 + k."""
    t = np.zeros((256, 3), "uint8")
    t[:] = hex_rgb(NOT_FOREST)
    t[1] = hex_rgb(STANDING)
    for y in range(FIRST, LAST + 1):
        t[1 + y - 2000] = year_rgb(y)
    return t


def row_areas_km2(lat_top, n_rows, res):
    """True area of one cell in each row of a lon/lat grid, km², on the WGS 84 ellipsoid."""
    from pyproj import Geod
    g = Geod(ellps="WGS84")
    out = np.empty(n_rows, "float64")
    for i in range(n_rows):
        n = lat_top - i * res
        s = n - res
        a, _ = g.polygon_area_perimeter([0, res, res, 0], [s, s, n, n])
        out[i] = abs(a) / 1e6
    return out


def sheet_outline_ll(ctx):
    """The area the facts are counted over, in WGS 84: the model's rectangle,
    cut to the plate's outline when it has one."""
    from shapely.geometry import box
    from shapely.ops import transform as reproject
    from common import transformer
    x0, y0, x1, y1 = ctx["bounds"]
    back = transformer(ctx["crs"], "EPSG:4326")
    rect = reproject(lambda x, y: back.transform(x, y), box(x0, y0, x1, y1).segmentize(ctx["cell"] * 20))
    ol = ctx.get("outline_ll")
    return rect.intersection(ol) if ol is not None else rect


def read_classes(bbox, block, threshold, inside_ll):
    """Read the tiles over bbox a strip at a time.

    Returns (rgb, transform, stats): rgb is the colour of each cell averaged over
    block x block dataset cells (float 0..1, lon/lat grid); stats are areas in km²
    inside `inside_ll`: forest in 2000 and loss per year."""
    import rasterio
    from rasterio.transform import Affine
    from rasterio.windows import Window
    table = colour_table().astype("float32") / 255
    remote = [tile for tile, _, _ in tiles_for(bbox) if tile_path("treecover2000", tile).startswith("/vsicurl/")]
    sq_deg = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if remote and sq_deg > 4 and not ALLOW_DOWNLOAD[0]:
        raise SystemExit(f"forest loss: {sq_deg:.0f} square degrees from tiles not on disk ({', '.join(remote)}) "
                         "would mean gigabytes of reads; download them first (fetch_data.py forest has the URLs) "
                         "or set drape_options allow_download: true")
    step = PX * block
    w, s, e, n = bbox
    w, s = math.floor(w / step) * step, math.floor(s / step) * step
    e, n = math.ceil(e / step) * step, math.ceil(n / step) * step
    cols, rows = int(round((e - w) / PX)), int(round((n - s) / PX))
    rgb = np.zeros((rows // block, cols // block, 3), "float32")
    forest_km2 = 0.0
    loss_km2 = np.zeros(LAST - FIRST + 1, "float64")
    strip = block * max(1, 1024 // block)
    for tile, top, left in tiles_for((w, s, e, n)):
        tw, tn = max(w, left), min(n, top)
        te, ts = min(e, left + 10), max(s, top - 10)
        if te <= tw or tn <= ts:
            continue
        c0, c1 = int(round((tw - left) / PX)), int(round((te - left) / PX))
        r0, r1 = int(round((top - tn) / PX)), int(round((top - ts) / PX))
        gc, gr = int(round((tw - w) / PX)), int(round((n - tn) / PX))     # where it lands in the grid
        try:
            with rasterio.Env(**drapes.ENV), rasterio.open(tile_path("treecover2000", tile)) as tc, \
                    rasterio.open(tile_path("lossyear", tile)) as ly:
                for ra in range(r0, r1, strip):
                    rb = min(ra + strip, r1)
                    win = Window(c0, ra, c1 - c0, rb - ra)
                    cover = tc.read(1, window=win)
                    year = ly.read(1, window=win)
                    forest = cover >= threshold
                    cls = np.where(forest, 1 + np.where(year > 0, year, 0), 0).astype("uint8")
                    # areas, inside the sheet, at full resolution
                    lat_top = top - ra * PX
                    tr = Affine(PX, 0, left + c0 * PX, 0, -PX, lat_top)
                    inside = rasterize_geom(inside_ll, cls.shape, tr)
                    area = row_areas_km2(lat_top, cls.shape[0], PX)[:, None]
                    forest_km2 += float((area * (forest & inside)).sum())
                    lost = forest & inside & (year > 0)
                    loss_km2 += np.bincount(year[lost].astype("int64"),
                                            weights=np.broadcast_to(area, cls.shape)[lost],
                                            minlength=LAST - FIRST + 2)[1:LAST - FIRST + 2]
                    # colour, averaged over blocks
                    gr0 = gr + (ra - r0)
                    h = (rb - ra) // block * block
                    wd = (c1 - c0) // block * block
                    if h == 0 or wd == 0:
                        continue
                    part = table[cls[:h, :wd]]
                    rgb[gr0 // block:gr0 // block + h // block, gc // block:gc // block + wd // block] = \
                        part.reshape(h // block, block, wd // block, block, 3).mean((1, 3))
        except rasterio.errors.RasterioIOError as err:
            raise SystemExit(f"forest loss: cannot read tile {tile} ({err}); run `python fetch_data.py forest`"
                             " or check the network") from err
        print(f"  forest loss: tile {tile} read", flush=True)
    return rgb, Affine(step, 0, w, 0, -step, n), dict(forest_km2=forest_km2, loss_km2=loss_km2.tolist())


def legend_for(stats):
    """Loss each year as small bars in the year's own colour, over the year ramp,
    with swatches for standing forest and land that was not forest."""
    loss = np.array(stats["loss_km2"])
    peak = float(loss.max()) or 1.0
    # a round scale value at or below the tallest bar (1, 2 or 5 x 10^k): the bars keep a scale, but
    # no one year carries a figure (the years either side of 2011 were mapped differently)
    mag = 10 ** math.floor(math.log10(peak))
    ref = max(v * mag for v in (1, 2, 5) if v * mag <= peak)
    table = colour_table()

    def draw(d, right, top, pl):
        w = pl.px(96)
        x0 = right - w
        n = LAST - FIRST + 1
        slot = w / n
        gap = max(1, int(round(pl.px(0.55))))
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("IBMPlexMono-400", pl.px(2.3))
        f_s = font("Barlow-400", pl.px(2.6))
        f_n = font("IBMPlexMono-400", pl.px(2.0))
        draw_text(d, (x0, top), "FOREST LOSS MAPPED EACH YEAR, KM²", f_k, pl.mix(0.55), 0.2)
        base = top + pl.px(14.0)                          # foot of the bars
        hmax = pl.px(8.6)
        if loss.max() > 0:                                # the scale line, behind the bars
            yr = base - ref / peak * hmax
            d.line([(x0, yr), (right, yr)], fill=pl.mix(0.30), width=max(1, int(pl.px(0.12))))
            draw_text(d, (x0 - pl.px(1.2), yr + pl.px(0.7)), f"{ref:g}", f_n, pl.mix(0.55), 0, "rs")
        for i in range(n):
            col = tuple(int(v) for v in table[1 + FIRST - 2000 + i])
            xa, xb = x0 + i * slot + gap / 2, x0 + (i + 1) * slot - gap / 2
            hb = max(pl.px(0.25), loss[i] / peak * hmax)
            d.rectangle([xa, base - hb, xb, base], fill=col)
        # the year ramp, one step a year, under the bars
        ys = base + pl.px(0.7)
        hs = pl.px(2.4)
        for i in range(n):
            col = tuple(int(v) for v in table[1 + FIRST - 2000 + i])
            d.rectangle([x0 + i * slot, ys, x0 + (i + 1) * slot, ys + hs], fill=col)
        for yr in (2001, 2005, 2010, 2015, 2020, 2023):
            i = yr - FIRST
            x = x0 + (i + 0.5) * slot
            d.line([(x, ys + hs), (x, ys + hs + pl.px(1.2))], fill=pl.mix(0.5),
                   width=max(1, int(pl.px(0.15))))
            anchor = "ls" if yr == FIRST else ("rs" if yr == LAST else "ms")
            xt = x0 if yr == FIRST else (right if yr == LAST else x)
            draw_text(d, (xt, ys + hs + pl.px(4.6)), str(yr), f_v, pl.mix(0.62), 0, anchor)
        # swatches
        sq = pl.px(2.8)
        yq = ys + hs + pl.px(7.6)
        for k, (label, colour) in enumerate((("Forest in 2000, no loss mapped", STANDING),
                                             ("Not forest in 2000", NOT_FOREST))):
            cx = x0 + k * w * 0.62
            d.rectangle([cx, yq, cx + sq, yq + sq], fill=hex_rgb(colour), outline=pl.mix(0.35),
                        width=max(1, int(pl.px(0.12))))
            draw_text(d, (cx + sq + pl.px(1.8), yq + sq - pl.px(0.2)), label, f_s, pl.mix(0.62), 0.0)
    return draw


ALLOW_DOWNLOAD = [False]


def drape(ctx):
    opts = ctx["options"]
    threshold = int(opts.get("threshold", 30))
    ALLOW_DOWNLOAD[0] = bool(opts.get("allow_download", False))
    # pre-average only for coarse models: to about half the model cell, by a factor that
    # divides the 40 000-cell tiles so the blocks line up across tile edges
    want = ctx["cell"] / 2 / (PX * 111_320)
    block = max(b for b in (1, 2, 4, 5, 8, 10, 16, 20, 25, 32, 40) if b <= max(1.0, want))
    w, s, e, n = ctx["ll"]
    pad = 3 * PX * block
    bbox = (w - pad, s - pad, e + pad, n + pad)
    inside = sheet_outline_ll(ctx)

    f = drapes.cache_path("forestloss", VERSION, [round(v, 5) for v in bbox], block, threshold,
                          hashlib.sha1(inside.wkb).hexdigest(), YEAR_STOPS, STANDING, NOT_FOREST)
    if f.exists():
        from rasterio.transform import Affine
        z = np.load(f)
        rgb, tr = z["rgb"].astype("float32") / 255, Affine(*z["transform"])
        stats = json.loads(str(z["stats"]))
    else:
        print(f"  forest loss: Hansen {VERSION}, canopy >= {threshold} %, "
              f"cells averaged {block} x {block} before warping")
        rgb, tr, stats = read_classes(bbox, block, threshold, inside)
        rgb = np.round(rgb * 255) / 255                  # as the cache holds it, so both runs match
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, rgb=np.round(rgb * 255).astype("uint8"), transform=np.array(tuple(tr)[:6]),
                            stats=json.dumps(stats))
    tex = drapes.to_map(rgb, tr, ctx)

    forest, loss = stats["forest_km2"], np.array(stats["loss_km2"])
    lost = float(loss.sum())
    peak_i = int(np.argmax(loss))
    stats.update(threshold=threshold, lost_km2=lost, lost_share=lost / forest if forest else 0.0,
                 peak_year=FIRST + peak_i, peak_km2=float(loss[peak_i]),
                 sheet_km2=float(_area_km2(inside)), years=list(range(FIRST, LAST + 1)))
    print(f"  forest loss: forest in 2000 {forest:,.1f} km², lost 2001-2023 {lost:,.1f} km² "
          f"({drapes.pct(stats['lost_share'])}), most in {stats['peak_year']} ({loss[peak_i]:.1f} km²); "
          f"sheet {stats['sheet_km2']:,.0f} km²")
    print("  loss by year (km²): " + ", ".join(f"{FIRST + i} {v:.1f}" for i, v in enumerate(loss)))
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{ctx['slug']}_forest-loss.json").write_text(json.dumps(stats, indent=1))
    except OSError:
        pass

    # areas to the nearest 10 km²: the model's edges move by a cell between a proof and
    # a master, and the data supports no finer figure for a whole sheet
    # The figures cover the whole sheet, not one named forest, and say so. No single year is
    # singled out: the data's makers warn that loss before 2011 was mapped with an earlier
    # method, so years either side of it should not be compared closely.
    sheet = stats["sheet_km2"] or 1.0
    facts = [("Forest on the sheet, 2000", f"{drapes.km2(round(forest, -1))} · {drapes.pct(forest / sheet)}"),
             (f"Loss mapped on the sheet, {FIRST}–{LAST}",
              f"{drapes.km2(round(lost, -1))} · {drapes.pct(stats['lost_share'])}")]
    return dict(
        # lakes and the sea are painted blue-grey from the elevation model, not left the
        # colour of land that was never forest
        tex=tex, legend=legend_for(stats), facts=facts, water=bool(opts.get("water", True)),
        key=dict(version=VERSION, threshold=threshold, block=block, stops=YEAR_STOPS),
        stats=stats,
        credit=f"Forest: Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11, canopy ≥ {threshold} % "
               f"in 2000, loss by year {FIRST}–{LAST} (CC BY 4.0).")


def _area_km2(geom_ll):
    from pyproj import Geod
    return abs(Geod(ellps="WGS84").geometry_area_perimeter(geom_ll)[0]) / 1e6
