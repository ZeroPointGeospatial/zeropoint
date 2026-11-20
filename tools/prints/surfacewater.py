"""Surface water drape: where water stood at the start of the Landsat record and
where it stands in 2021, from the transitions layer of the JRC Global Surface
Water dataset (v1.4, 1984 to 2021, cells of 0.00025 degrees, about 28 m).

    drape: water                                   # in a plate or a map spec
    drape_options:
      lakes:                                       # water bodies measured for the facts row
        - { name: Lake Baringo, lon: 36.118, lat: 0.619 }
        - { name: Lake Bogoria, lon: 36.102, lat: 0.271 }
      zex: 3                                       # printed as a fact (see below)

What the classes mean (JRC Data Users Guide v4, 2021, "Transitions"): for each
cell JRC finds the first year with enough Landsat observations to be sure
whether water was there (the "start", 1984 or later) and compares its class
(not water, seasonal, permanent) with the class in 2021. Seasonal water is
under water for less than twelve months of the year. The classes say nothing
about the years in between: "new permanent" means land at the start and water
all through 2021, not a steady rise. The layer's codes are 0 not water,
1 permanent, 2 new permanent, 3 lost permanent, 4 seasonal, 5 new seasonal,
6 lost seasonal, 7 seasonal to permanent, 8 permanent to seasonal, 9 ephemeral
permanent, 10 ephemeral seasonal, 255 no data. Ephemeral water (there in some
years between, but land at both ends) is painted as land, which it was at
both dates.

The sheet groups them into five colours: water at both dates in deep blue,
new permanent water in a strong coral, new seasonal water in a paler coral,
lost water in olive, and land in the bone of the model.

Facts: for each lake in `lakes`, the water body is the connected patch of
cells that were water at some time (codes 1 to 10, small gaps closed) that
holds the given point; its area at the start (codes 1, 3, 4, 6, 7, 8) and in
2021 (codes 1, 2, 4, 5, 7, 8) is summed over the native cells, each weighted
by its true area. With two lakes the third fact is the vertical exaggeration,
taken from ctx["zex"] when relief.py passes it, else from drape_options.zex.

Licence: produced under the Copernicus Programme, free of charge and without
restriction of use; maps must carry "Source: EC JRC/Google" and cite Pekel et
al. (2016), Nature 540, 418-422.
"""
import json
import math

import numpy as np

import drapes
from common import draw_text, font, hex_rgb

URL = ("https://storage.googleapis.com/global-surface-water/downloads2021/{layer}/"
       "{layer}_{tile}v1_4_2021.tif")
NATIVE = 0.00025                       # the layer's cell in degrees, about 28 m

BONE = "#ebe6da"
# (label on the sheet, colour, transition codes painted with it)
GROUPS = [
    ("Water at the start and in 2021", "#3b6481", (1, 4, 7, 8)),
    ("New permanent water", "#d8613a", (2,)),
    ("New seasonal water", "#efa983", (5,)),
    ("Water lost by 2021", "#8f8a3e", (3, 6)),
    ("Land at the start and in 2021", BONE, (0, 9, 10)),
]
TABLE = np.zeros((256, 3), "uint8")
TABLE[:] = hex_rgb(BONE)                                # no data (255) as bare model
for _, colour, codes in GROUPS:
    for c in codes:
        TABLE[c] = hex_rgb(colour)

START = (1, 3, 4, 6, 7, 8)             # water (seasonal or permanent) in the first year
END = (1, 2, 4, 5, 7, 8)               # water in 2021


def tile_name(lon, lat):
    """10-degree tiles, named by their north-west corner: 30E_10N covers 30-40 E, 0-10 N."""
    w = int(math.floor(lon / 10) * 10)
    n = int(math.floor(lat / 10) * 10) + 10
    return f"{abs(w)}{'E' if w >= 0 else 'W'}_{abs(n)}{'N' if n >= 0 else 'S'}"


def tiles(bbox, layer="transitions"):
    w, s, e, n = bbox
    out = []
    for lat in range(int(math.floor(s / 10) * 10), int(math.ceil(n / 10) * 10), 10):
        for lon in range(int(math.floor(w / 10) * 10), int(math.ceil(e / 10) * 10), 10):
            out.append((URL.format(layer=layer, tile=tile_name(lon, lat)), (lon, lat, lon + 10, lat + 10)))
    return out


def classes(bbox, res=NATIVE, layer="transitions"):
    """The transitions grid over bbox at res degrees (native by default). Cached."""
    f = drapes.cache_path("gsw-" + layer, [round(v, 5) for v in bbox], res)
    if f.exists():
        z = np.load(f)
        from rasterio.transform import Affine
        return z["cls"], Affine(*z["transform"])
    print(f"  surface water: JRC GSW {layer} at about {res * 111_320:.0f} m")
    cls, tr = drapes.mosaic(tiles(bbox, layer), bbox, res, "uint8", 255, "nearest")
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, cls=cls, transform=np.array(tuple(tr)[:6]))
    return cls, tr


def cell_km2(cls, tr):
    """True area of each lon/lat cell in km², one value per row."""
    lat = tr.f + tr.e * (np.arange(cls.shape[0]) + 0.5)
    return np.cos(np.radians(lat)) * (abs(tr.a) * 111_320) * (abs(tr.e) * 110_574) / 1e6


def class_areas(cls, tr, mask=None):
    """km² in each transition code (0..255) inside mask (the whole grid if None)."""
    w = np.broadcast_to(cell_km2(cls, tr)[:, None], cls.shape)
    m = np.ones(cls.shape, bool) if mask is None else mask
    return np.bincount(cls[m].ravel(), weights=w[m].ravel(), minlength=256)


def inside_sheet(shape, tr, ctx):
    """Cells of a lon/lat grid that fall on the model: inside the outline if there is one,
    else inside the model grid's bounds in the map projection."""
    ol = ctx.get("outline_ll")
    if ol is not None:
        from common import rasterize_geom
        return rasterize_geom(ol, shape, tr)
    from common import transformer
    lon = tr.c + tr.a * (np.arange(shape[1]) + 0.5)
    lat = tr.f + tr.e * (np.arange(shape[0]) + 0.5)
    x0, y0, x1, y1 = ctx["bounds"]
    t = transformer("EPSG:4326", ctx["crs"])
    out = np.zeros(shape, bool)
    for r in range(0, shape[0], 512):
        lo, la = np.meshgrid(lon, lat[r:r + 512])
        x, y = t.transform(lo, la)
        out[r:r + 512] = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    return out


def lake_areas(cls, tr, lon, lat):
    """(km² of water at the start, km² in 2021, extent) of the water body holding (lon, lat)."""
    from scipy import ndimage
    ever = (cls >= 1) & (cls <= 10)
    lab, _ = ndimage.label(ndimage.binary_closing(ever, iterations=2) | ever)
    r, c = int((tr.f - lat) / -tr.e), int((lon - tr.c) / tr.a)
    if not (0 <= r < cls.shape[0] and 0 <= c < cls.shape[1]):
        raise SystemExit(f"surface water: the lake point {lon}, {lat} is off the sheet")
    if not ever.any():
        raise SystemExit("surface water: no water anywhere on the sheet, so no lake can be measured")
    k = lab[r, c]
    if k == 0:                                          # the point is on land: take the nearest water
        _, (ri, ci) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
        k = lab[ri[r, c], ci[r, c]]
    body = (lab == k) & ever
    if not body.any():
        raise SystemExit(f"surface water: no water body found near {lon}, {lat}")
    a = class_areas(cls, tr, body)
    rows, cols = np.nonzero(body)
    ext = (tr.c + cols.min() * tr.a, tr.f + (rows.max() + 1) * tr.e,
           tr.c + (cols.max() + 1) * tr.a, tr.f + rows.min() * tr.e)
    return float(sum(a[i] for i in START)), float(sum(a[i] for i in END)), ext, a


def lake_native(lon, lat, guess_ext):
    """Measure a lake on the native 30 m grid: read a window round the extent found on a
    coarser grid, and grow it until the water body no longer touches the window's edge."""
    w, s, e, n = guess_ext
    m = max(0.02, 0.15 * max(e - w, n - s))
    for _ in range(4):
        box = (w - m, s - m, e + m, n + m)
        cls, tr = classes(box)
        a0, a1, ext, a = lake_areas(cls, tr, lon, lat)
        touches = (ext[0] <= box[0] + 2 * NATIVE or ext[1] <= box[1] + 2 * NATIVE or
                   ext[2] >= box[2] - 2 * NATIVE or ext[3] >= box[3] - 2 * NATIVE)
        if not touches:
            return a0, a1, ext, a
        w, s, e, n = ext
        m *= 2
    return a0, a1, ext, a


def legend(items, title, notes, width_mm=86):
    """Swatches in two columns, then a two-line note on what the classes mean."""
    def draw(d, right, top, pl):
        w = pl.px(width_mm)
        x0 = right - w
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("Barlow-400", pl.px(2.6))
        f_n = font("Barlow-400", pl.px(2.25))
        draw_text(d, (x0, top), title.upper(), f_k, pl.mix(0.55), 0.2)
        cols = 2
        col_w, row_h, sq = w / cols, pl.px(4.6), pl.px(2.8)
        per_col = math.ceil(len(items) / cols)
        for i, (label, colour) in enumerate(items):
            cx = x0 + (i // per_col) * col_w
            cy = top + pl.px(3.8) + (i % per_col) * row_h
            d.rectangle([cx, cy, cx + sq, cy + sq], fill=hex_rgb(colour),
                        outline=pl.mix(0.35), width=max(1, int(pl.px(0.12))))
            draw_text(d, (cx + sq + pl.px(1.8), cy + sq - pl.px(0.2)), label, f_v, pl.mix(0.62), 0.0)
        y = top + pl.px(3.8) + per_col * row_h + pl.px(3.2)
        for line in notes:
            draw_text(d, (x0, y), line, f_n, pl.mix(0.5), 0.02)
            y += pl.px(3.5)
    return draw


def drape(ctx):
    opts = ctx["options"]
    w, s, e, n = ctx["ll"]
    pad = 0.01
    # the texture at about half the model cell (native 30 m on a detailed sheet), coloured
    # and blended 2 x 2, so a county or a country-sized sheet stays within memory
    res = max(NATIVE, ctx["cell"] / 2 / 111_320)
    block = 1 if res == NATIVE else 2
    cls, tr = classes((w - pad, s - pad, e + pad, n + pad), res)
    if block == 1:
        rgb = TABLE[cls].astype("float32") / 255
        tex = drapes.to_map(rgb, tr, ctx, resampling="average")
    else:
        from rasterio.transform import Affine
        rgb = drapes.classes_to_rgb_blocks(cls, TABLE, 2)
        tex = drapes.to_map(rgb, Affine(tr.a * 2, 0, tr.c, 0, tr.e * 2, tr.f), ctx)

    # what is on the sheet (the model grid, or the outline when there is one), for the legend
    on_sheet = class_areas(cls, tr, inside_sheet(cls.shape, tr, ctx))
    nodata = on_sheet[255]
    print("  transitions on the sheet, km²: " + ", ".join(
        f"{c}:{on_sheet[c]:.2f}" for c in list(range(11)) + [255] if on_sheet[c] > 0.005))
    if nodata > 0.01:
        print(f"  WARNING: {nodata:.2f} km² without data, drawn as land")
    present = []
    for label, colour, codes in GROUPS:
        area = sum(on_sheet[c] for c in codes)
        if codes[0] == 0 or area >= 0.05:
            if codes[0] == 3 and area < 2:                # a trace: say how little, so no one hunts for it
                label = f"{label}, {area:.1f} km²"
            present.append((label, colour))

    # the lakes, measured on the native grid (cached with the class grid)
    facts, measured = [], {}
    key = drapes.cache_path("gsw-lakes", [round(v, 5) for v in (w, s, e, n)], opts.get("lakes"),
                            "v2-native-window-closing2-cosarea")      # bump when lake_areas changes
    f = key.with_suffix(".json")
    if f.exists():
        measured = json.loads(f.read_text())
    else:
        for lk in opts.get("lakes") or []:
            a0, a1, ext, a = lake_areas(cls, tr, lk["lon"], lk["lat"])
            if res != NATIVE:                                 # measure on the native grid
                a0, a1, ext, a = lake_native(lk["lon"], lk["lat"], ext)
            measured[lk["name"]] = dict(start=a0, end=a1, extent=ext,
                                        codes={str(i): float(a[i]) for i in range(1, 11) if a[i] > 0})
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(measured, indent=1))
    for name, m in measured.items():
        new = m["codes"].get("2", 0) + m["codes"].get("5", 0)
        lost = m["codes"].get("3", 0) + m["codes"].get("6", 0)
        change = f"{(m['end'] / m['start'] - 1) * 100:+.0f} %" if m["start"] > 0 else "new"
        x0, y0, x1, y1 = m["extent"]
        print(f"  {name}: water at the start {m['start']:.1f} km², in 2021 {m['end']:.1f} km² ({change}), "
              f"new water {new:.1f} km², lost {lost:.2f} km²; body spans {x0:.4f}..{x1:.4f} E, "
              f"{y0:.4f}..{y1:.4f} N")
        facts.append((f"{name}, start to 2021", f"{m['start']:.0f} → {m['end']:.0f} km²"))
    if not facts:                                        # no lakes named: the sheet's own totals
        a0, a1 = sum(on_sheet[c] for c in START), sum(on_sheet[c] for c in END)
        facts = [("Water, start to 2021", f"{a0:.0f} → {a1:.0f} km²"),
                 ("New water by 2021", drapes.km2(sum(on_sheet[c] for c in (2, 5))))]
    zex = ctx.get("zex") or opts.get("zex")
    if zex and len(facts) < 3:
        facts.append(("Vertical exaggeration", f"×{zex:g}"))

    notes = opts.get("notes") or [
        "Start: each place's first year with enough Landsat views, from 1984.",
        "New: land at the start, water in 2021. Seasonal: under water less than 12 months.",
    ]
    return dict(
        tex=tex, legend=legend(present, opts.get("legend_title", "Surface water, 1984 to 2021"), notes),
        facts=facts[:3], water=False, key=dict(groups=[(g[1], g[2]) for g in GROUPS], v="1.4-2021"),
        credit="Surface water: EC JRC/Google, Global Surface Water v1.4, 1984–2021 (Pekel et al. 2016; "
               "Copernicus, free and open).")
