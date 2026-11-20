"""Colour layers draped over a relief model, in place of the elevation colours:
land cover, forest loss, surface water and true colour.

A plate or a map spec asks for one with `drape: landcover` (and, for a spec,
`drape_options: {...}`); relief.py builds the terrain model as usual and
paints it with the drape instead of the elevation ramp.

Each drape is a module with a function `drape(ctx)` that returns a dict:

    tex      (rows, cols, 3) float RGB, 0..1, on the model grid
    legend   callable(draw, right, top, plate) for the title block, or None
    facts    up to three (label, value) pairs for the title block
    credit   the data line for the drape (relief.py adds the elevation credit)
    water    True to paint the lakes found in the elevation model (default
             False: most layers carry their own water)
    key      anything that changes the colours, for the render cache

`ctx` holds:

    bounds      (x0, y0, x1, y1) of the model grid in the map projection
    cell        grid cell in metres
    crs         the map projection
    shape       (rows, cols) of the model grid
    z, valid    the elevation grid, and the outline mask or None
    ll          (w, s, e, n) in degrees, a box that covers the grid
    outline_ll  the outline in WGS 84 (a country, county or region) or None
    options     the spec's drape_options, a dict
    slug        the plate's name, for cache files

The helpers below read cloud-optimised GeoTIFFs a window at a time, through
their overviews, so a country costs megabytes of requests, not gigabytes.
"""
import concurrent.futures as cf
import hashlib
import importlib
import json
import math

import numpy as np

from common import CACHE, draw_text, font, hex_rgb, warp_to_map

NAMES = {"landcover": "landcover", "forest-loss": "forestloss", "water": "surfacewater",
         "true-colour": "truecolour"}

ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
           GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="FALSE",
           GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")


def get(name):
    """The drape function for a name used in a plate or spec."""
    if name not in NAMES:
        raise SystemExit(f"unknown drape {name!r}; one of {', '.join(NAMES)}")
    return importlib.import_module(NAMES[name]).drape


def cache_path(kind, *parts):
    """A cache file named from what went into it."""
    digest = hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return CACHE / "drapes" / f"{kind}_{digest}.npz"


def grid_for(bbox, res_deg):
    """(rows, cols, transform) of a lon/lat grid over bbox at res_deg, snapped to whole cells."""
    from rasterio.transform import Affine
    w, s, e, n = bbox
    w, s = math.floor(w / res_deg) * res_deg, math.floor(s / res_deg) * res_deg
    e, n = math.ceil(e / res_deg) * res_deg, math.ceil(n / res_deg) * res_deg
    cols, rows = int(round((e - w) / res_deg)), int(round((n - s) / res_deg))
    return rows, cols, Affine(res_deg, 0, w, 0, -res_deg, n)


def mosaic(tiles, bbox, res_deg, dtype="uint8", fill=0, resampling="mode", workers=8):
    """Read lon/lat tiles over bbox onto one grid at about res_deg.

    tiles       [(url, (w, s, e, n) the tile covers), ...]; a tile that does not
                exist (the sea, for most global datasets) is skipped
    resampling  a rasterio Resampling name: 'mode' or 'nearest' for classes,
                'average' for measurements
    Returns (array, transform).
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    rows, cols, tr = grid_for(bbox, res_deg)
    out = np.full((rows, cols), fill, dtype=dtype)
    gw, gn = tr.c, tr.f

    def read(job):
        url, (tw, ts, te, tn) = job
        w, s = max(tw, gw), max(ts, gn - rows * res_deg)
        e, n = min(te, gw + cols * res_deg), min(tn, gn)
        if e <= w or n <= s:
            return None
        c0, c1 = int(round((w - gw) / res_deg)), int(round((e - gw) / res_deg))
        r0, r1 = int(round((gn - n) / res_deg)), int(round((gn - s) / res_deg))
        if c1 <= c0 or r1 <= r0:
            return None
        try:
            with rasterio.Env(**ENV), rasterio.open("/vsicurl/" + url) as src:
                win = from_bounds(w, s, e, n, src.transform)
                a = src.read(1, window=win, out_shape=(r1 - r0, c1 - c0),
                             resampling=getattr(Resampling, resampling), boundless=False)
        except rasterio.errors.RasterioIOError:
            return None
        return r0, c0, a

    with cf.ThreadPoolExecutor(workers) as ex:
        for i, got in enumerate(ex.map(read, tiles)):
            if got is not None:
                r0, c0, a = got
                out[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
            print(f"  {NAMES_BY_URL(tiles[i][0])} read", flush=True)
    return out, tr


def NAMES_BY_URL(url):                                   # noqa: N802 - a short name for progress lines
    return url.rsplit("/", 1)[-1]


def classes_to_rgb_blocks(cls, table, block):
    """Colour a class grid with `table` (256 x 3 uint8) and average it over block x block
    cells, a strip at a time so a country-sized grid fits in memory. Returns float RGB 0..1."""
    rows, cols = (cls.shape[0] // block) * block, (cls.shape[1] // block) * block
    out = np.zeros((rows // block, cols // block, 3), "float32")
    strip = block * 256
    for r in range(0, rows, strip):
        part = table[cls[r:min(r + strip, rows), :cols]].astype("float32")
        h = part.shape[0] // block
        out[r // block:r // block + h] = part.reshape(h, block, cols // block, block, 3).mean((1, 3)) / 255
    return out


def to_map(rgb, tr_ll, ctx, resampling="average"):
    """Warp a lon/lat RGB grid onto the model grid; cells it does not reach are left bone."""
    chans = []
    for i in range(3):
        a, _ = warp_to_map(rgb[..., i], tr_ll, ctx["bounds"], ctx["cell"], resampling=resampling,
                           dst_crs=ctx["crs"])
        chans.append(a)
    out = np.stack(chans, -1)
    bone = np.array(hex_rgb("#ebe6da")) / 255
    return np.where(np.isnan(out), bone, out).astype("float32")


def area_shares(cls, tr, outline_ll=None, codes=None):
    """Share of the area (inside the outline, if given) in each class code, weighted by the
    true area of each lon/lat cell. Returns {code: fraction}."""
    from common import rasterize_geom
    inside = rasterize_geom(outline_ll, cls.shape, tr) if outline_ll is not None else None
    lat = tr.f + tr.e * (np.arange(cls.shape[0]) + 0.5)
    wts = np.cos(np.radians(lat)).astype("float64")
    tot = np.zeros(256, "float64")
    for r in range(0, cls.shape[0], 2048):
        c = cls[r:r + 2048]
        m = inside[r:r + 2048] if inside is not None else np.ones(c.shape, bool)
        w = np.broadcast_to(wts[r:r + 2048, None], c.shape)
        tot += np.bincount(c[m].ravel(), weights=w[m].ravel(), minlength=256)
    keep = codes if codes is not None else [i for i in range(256) if tot[i] > 0]
    total = sum(tot[i] for i in keep) or 1.0
    return {i: tot[i] / total for i in keep}


def swatch_legend(items, title, cols=2):
    """A key of coloured squares for the title block: items = [(label, '#hex'), ...]."""
    def draw(d, right, top, pl):
        w = pl.px(96)
        x0 = right - w
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("Barlow-400", pl.px(2.6))
        draw_text(d, (x0, top), title.upper(), f_k, pl.mix(0.55), 0.2)
        col_w, row_h, sq = w / cols, pl.px(4.6), pl.px(2.8)
        per_col = math.ceil(len(items) / cols)
        for i, (label, colour) in enumerate(items):
            cx = x0 + (i // per_col) * col_w
            cy = top + pl.px(3.8) + (i % per_col) * row_h
            d.rectangle([cx, cy, cx + sq, cy + sq], fill=hex_rgb(colour) if isinstance(colour, str) else colour,
                        outline=pl.mix(0.35), width=max(1, int(pl.px(0.12))))
            draw_text(d, (cx + sq + pl.px(1.8), cy + sq - pl.px(0.2)), label, f_v, pl.mix(0.62), 0.0)
    return draw


def pct(v):
    """A share as the sheet prints it: '12.3 %', '0.4 %', '< 0.1 %'."""
    return "< 0.1 %" if v < 0.0005 else f"{v * 100:.1f} %"


def km2(v):
    return f"{v:,.0f} km²".replace(",", " ")
