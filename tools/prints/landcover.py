"""Land cover drape: ESA WorldCover 2021 (10 m, eleven classes), read at about
half the model's cell from the cloud-optimised tiles and blended into the
model grid, so a cell that is part cropland, part tree cover takes a mix of
the two colours, as the land looks from the air.

    drape: landcover                 # in a plate or a map spec
    drape_options: {year: 2021}      # 2020 (v100) or 2021 (v200)

Used by plate 16 (Kenya, land cover) and by any custom area.
"""
import numpy as np

import drapes
from common import hex_rgb

URLS = {2021: "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
              "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif",
        2020: "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/map/"
              "ESA_WorldCover_10m_2020_v100_{tile}_Map.tif"}
NATIVE = 1 / 12000                      # 10 m cells, in degrees

# (code, name on the sheet, colour): muted to sit on the paper, crops in ochre
# and towns in brick so the two stories of the map read first.
CLASSES = [
    (10, "Tree cover", "#2f6a45"),
    (95, "Mangroves", "#1d6b62"),
    (20, "Shrubland", "#c4bb8b"),
    (30, "Grassland", "#e4dcab"),
    (40, "Cropland", "#e09a45"),
    (50, "Built-up", "#b3372e"),
    (60, "Bare or sparse", "#f3eee3"),
    (70, "Snow and ice", "#fbfbf8"),
    (80, "Open water", "#6d98b0"),
    (90, "Wetland", "#7bb2a4"),
    (100, "Moss and lichen", "#cdd5c4"),
]
TABLE = np.zeros((256, 3), "uint8")
TABLE[:] = hex_rgb("#ebe6da")                         # no data: the bone of the model
for code, _, colour in CLASSES:
    TABLE[code] = hex_rgb(colour)


def tile_name(lat, lon):
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def tiles(bbox, year):
    w, s, e, n = bbox
    out = []
    for lat in range(int(np.floor(s / 3) * 3), int(np.ceil(n / 3) * 3), 3):
        for lon in range(int(np.floor(w / 3) * 3), int(np.ceil(e / 3) * 3), 3):
            out.append((URLS[year].format(tile=tile_name(lat, lon)), (lon, lat, lon + 3, lat + 3)))
    return out


def classes(bbox, res_deg, year=2021):
    """The WorldCover class grid over bbox at about res_deg (never finer than 10 m). Cached."""
    res = max(NATIVE, res_deg)
    f = drapes.cache_path("worldcover", [round(v, 4) for v in bbox], round(res, 8), year)
    if f.exists():
        z = np.load(f)
        from rasterio.transform import Affine
        return z["cls"], Affine(*z["transform"])
    print(f"  land cover: WorldCover {year} at about {res * 111_320:.0f} m")
    cls, tr = drapes.mosaic(tiles(bbox, year), bbox, res, "uint8", 0, "mode")
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, cls=cls, transform=np.array(tuple(tr)[:6]))
    return cls, tr


def shares_fine(bbox, outline_ll=None, year=2021, factor=4):
    """Share of the area in each class, read at 40 m (a quarter of the native resolution).
    The tiles' coarser overviews are built from the commonest class, which inflates the
    dominant classes by several points at 120 m; at 40 m the shares stay within about
    0.7 of a point of the full 10 m data. Read a tile at a time, so a country fits. Cached."""
    import json
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    from rasterio.transform import from_origin
    from shapely.geometry import box
    from common import rasterize_geom
    key = drapes.cache_path("worldcover-shares", [round(v, 4) for v in bbox], year, factor,
                            outline_ll.wkb_hex[:4000] if outline_ll is not None else None)
    f = key.with_suffix(".json")
    if f.exists():
        return {int(k): v for k, v in json.loads(f.read_text()).items()}
    tot = np.zeros(256, "float64")
    res = NATIVE * factor
    for url, (tw, ts, te, tn) in tiles(bbox, year):
        w, s, e, n = max(tw, bbox[0]), max(ts, bbox[1]), min(te, bbox[2]), min(tn, bbox[3])
        if e <= w or n <= s or (outline_ll is not None and not outline_ll.intersects(box(w, s, e, n))):
            continue
        rows, cols = int(round((n - s) / res)), int(round((e - w) / res))
        try:
            with rasterio.Env(**drapes.ENV), rasterio.open("/vsicurl/" + url) as src:
                a = src.read(1, window=from_bounds(w, s, e, n, src.transform), out_shape=(rows, cols),
                             resampling=Resampling.nearest)
        except rasterio.errors.RasterioIOError:
            continue
        tr = from_origin(w, n, res, res)
        m = rasterize_geom(outline_ll, a.shape, tr) if outline_ll is not None else np.ones(a.shape, bool)
        lat = n - res * (np.arange(rows) + 0.5)
        wts = np.broadcast_to(np.cos(np.radians(lat))[:, None], a.shape)
        tot += np.bincount(a[m].ravel(), weights=wts[m].ravel(), minlength=256)
        print(f"  shares: {url.rsplit('/', 1)[-1]}", flush=True)
    codes = [c for c, _, _ in CLASSES]
    total = sum(tot[c] for c in codes) or 1.0
    out = {c: tot[c] / total for c in codes}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def drape(ctx):
    opts = ctx["options"]
    year = int(opts.get("year", 2021))
    block = 2                                            # read at half the cell, then blend 2 x 2
    res = ctx["cell"] / block / 111_320
    w, s, e, n = ctx["ll"]
    pad = 2 * res
    cls, tr = classes((w - pad, s - pad, e + pad, n + pad), res, year)
    rgb = drapes.classes_to_rgb_blocks(cls, TABLE, block)
    from rasterio.transform import Affine
    tr_rgb = Affine(tr.a * block, 0, tr.c, 0, tr.e * block, tr.f)
    tex = drapes.to_map(rgb, tr_rgb, ctx)

    ol = ctx.get("outline_ll")
    shares = shares_fine(ol.bounds if ol is not None else (w, s, e, n), ol, year)
    present = [(name, colour) for code, name, colour in CLASSES if shares.get(code, 0) >= 0.0005]
    top = sorted(((shares[c], n) for c, n, _ in CLASSES if c in shares), reverse=True)
    names = {n: c for c, n, _ in CLASSES}
    if opts.get("facts"):                                # the classes a plate wants to state
        facts = [(n, drapes.pct(shares.get(names[n], 0))) for n in opts["facts"]][:3]
    else:                                                # the two largest, and the towns
        facts = [(top[0][1], drapes.pct(top[0][0])), (top[1][1], drapes.pct(top[1][0]))]
        if "Built-up" not in (top[0][1], top[1][1]):
            facts.append(("Built-up", drapes.pct(shares.get(50, 0))))
    print("  land cover shares: " + ", ".join(f"{n} {drapes.pct(v)}" for v, n in top if v >= 0.0005))
    return dict(
        tex=tex, legend=drapes.swatch_legend(present[:10], f"Land cover, {year}"),
        facts=facts, water=False, key=dict(year=year, block=block),
        shares={n: shares.get(c, 0) for c, n, _ in CLASSES},
        credit=f"Land cover: ESA WorldCover {year} (© ESA WorldCover project, Copernicus Sentinel data, "
               "CC BY 4.0).")
