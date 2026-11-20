"""True-colour drape: the ground as Copernicus Sentinel-2 saw it on one clear
day. Red, green and blue surface reflectance (Level-2A, bands B04, B03 and
B02, 10 m) are given a gentle tone curve and painted over the relief model.
The scenes are the cloud-optimised GeoTIFFs of the Earth Search archive on
AWS (s3://sentinel-cogs), read a window at a time through /vsicurl/: the
Magadi sheet (42 by 51 km at 10 m) read 146 MB by GDAL's network statistics,
an eighth of the 1.15 GB of its two scenes' red, green and blue files. The
result is cached, so the imagery is read once per sheet.

    drape: true-colour                        # in a plate or a map spec
    drape_options:
      date: 2025-09-14                        # the day to use (else chosen, see below)
      months: [6, 7, 8, 9]                    # months to search; default all
      years: 2                                # how far back to search; default 1
      exposure: 1.0                           # brighter (> 1) or darker
      lake: { name: ..., lon: ..., lat: ..., below: ... }   # optional fact; see below
      zex: 4                                  # printed in the facts row; keep equal to zex
      detail: 3                               # texture cells per model cell; default 10 m
                                              # (1 for a quick proof: 30 m, from the overviews)

Works for any area up to a few Sentinel-2 tiles (about 100 km each; more
than 16 tiles is refused). For a shop plate set `date`, so the plate renders
the same next year; without it a custom area gets the most recent clear day.

Choosing a day. The tiles that cover the sheet are found from the MGRS grid
(a tile is a 100 km square stretched to 109.8 km), the fewest that cover it
are kept, and their scenes are listed month by month back from today. A
scene is kept if its tile is under 40 % cloud. The scene classification
layer (SCL) of each is read at about 170 to 200 m over the sheet, and every
date is scored by the share of the sheet that is clear: inside the scene
and not cloud, cloud shadow or cirrus (classes 3, 8, 9, 10). The SCL
misreads salt and soda crust as cloud and dark brine as shadow, in patches
that move with the state of a lake (at Magadi on 14 September 2025 nearly
all the flags, all but about 0.02 % of the sheet, were on the lake), so a
flag is not counted on a cell the SCL flags again and again on nearly clear
dates: on at least 3 of the dates with 98 % of the sheet clear, and on more
than a quarter of them. (An earlier rule that ignored every flag over open
water let clouded coasts and lake shores through as clear.) The most recent
date with at least 99.9 % of the sheet clear is used. If no date reaches it, the
clearest is used and its cloudy cells, widened by 120 m for the haze at
their edges, are filled from up to three more dates, and the facts row says
so.

Colour. Reflectance is DN x 0.0001. ESA adds 1000 to every DN from
processing baseline 04.00 (25 January 2022), but Earth Search takes it off
the pixels when it converts the scenes, and neither its
earthsearch:boa_offset_applied flag nor the -0.1 offset in raster:bands can
be trusted to say so (`dn_offset` lets the pixels decide). The three bands
are scaled together, so grey ground stays grey, and passed through a tone
curve that is linear in the shadows and rolls the highlights off toward
white instead of clipping them. ESA's TCI product saturates at a reflectance
of about 0.25 (over Magadi on 14 September 2025, 82 % of the pixels with a
red reflectance of 0.3 to 0.5 are at 255), which turns the soda crust into
flat white; here the whites of the pan and the pinks of the brine keep their
detail. The curve is then encoded as sRGB, the space the renderer reads
textures in. The legend prints the same curve on a grey surface.

Resolution. The texture is made at an integer multiple of the model grid
(three times for a 30 m model: the native 10 m), so the image is sharper
than the terrain under it; relief.py's mesh maps the texture by cell
centres, which an integer multiple keeps exact. (So `tex` is not on the
model grid, as drapes.py says a drape's is; relief.py only uses its shape
when it paints water, which this drape never asks for.)

The lake fact. `lake` measures a lake from the elevation model: the ground
at or below `below` metres joined to the given point, and states how far it
runs north to south. Choose `below` by laying the outline over the scene;
for Magadi 605 m follows the shore of the pan (603 m leaves holes in the
crust; from 604 to 608 m the length runs from 27.7 to 31.4 km, which is why
the sheet gives it in whole kilometres).

Licence: Copernicus Sentinel data are free and open (Legal Notice on the
use of Copernicus Sentinel Data and Service Information). Credit: "Contains
modified Copernicus Sentinel data <year>".
"""
import concurrent.futures as cf
import datetime as dt
import json
import math
import xml.etree.ElementTree as ET

import numpy as np

import drapes
from common import CACHE, draw_text, font, warp_to_map

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
ROOT = "sentinel-s2-l2a-cogs"
S3NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
TILE_M = 109_800                       # a Sentinel-2 tile: the MGRS square plus 9.8 km
COLS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")
ROWS = "ABCDEFGHJKLMNPQRSTUV"
BANDS = "CDEFGHJKLMNPQRSTUVWX"
CLOUD = (3, 8, 9, 10)                  # SCL: cloud shadow, cloud medium, cloud high, cirrus
MAX_TILE_CLOUD = 40.0
CLEAR_ENOUGH = 0.999
STORE = CACHE / "drapes" / "s2"
MAX_TILES = 16                         # more is refused: the drape is for areas up to a few hundred km


# --------------------------------------------------------------------------- listing

def _http():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "zeropoint-prints"
    return s


def _subprefixes(session, prefix):
    """The 'folders' one level under prefix in the bucket."""
    out, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "delimiter": "/"}
        if token:
            params["continuation-token"] = token
        for attempt in range(4):
            try:
                r = session.get(BUCKET + "/", params=params, timeout=60)
                r.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
        root = ET.fromstring(r.content)
        out += [p.text for p in root.findall("s3:CommonPrefixes/s3:Prefix", S3NS)]
        if root.findtext("s3:IsTruncated", namespaces=S3NS) != "true":
            return out
        token = root.findtext("s3:NextContinuationToken", namespaces=S3NS)


def _ring(bbox, n=21):
    w, s, e, n_ = bbox
    lons, lats = np.linspace(w, e, n), np.linspace(s, n_, n)
    return (np.concatenate([lons, np.full(n, e), lons[::-1], np.full(n, w)]),
            np.concatenate([np.full(n, s), lats, np.full(n, n_), lats[::-1]]))


def candidate_tiles(bbox):
    """Sentinel-2 tiles that may touch bbox, from the MGRS grid:
    [(zone, latitude bands to try, square, epsg, (x0, y0, x1, y1) in UTM)]."""
    from pyproj import Transformer
    w, s, e, n = bbox
    rl, rb = _ring(bbox)
    z0, z1 = int((w + 180) // 6) + 1, int((e + 180) // 6) + 1
    out = []
    for zone in range(max(1, z0 - 1), min(60, z1 + 1) + 1):
        for south in sorted({s < 0, n < 0}):
            epsg = (32700 if south else 32600) + zone
            fwd = Transformer.from_crs(4326, epsg, always_xy=True)
            inv = Transformer.from_crs(epsg, 4326, always_xy=True)
            x, y = fwd.transform(rl, rb)
            x0, x1, y0, y1 = min(x), max(x), min(y), max(y)
            for col in range(1, 9):
                tx0 = col * 100_000 - 20
                if tx0 + TILE_M <= x0 or tx0 >= x1:
                    continue
                for k in range(int(y0 // 100_000) - 1, int(y1 // 100_000) + 1):
                    if k < 0 or (south and k >= 100) or (not south and k >= 94):
                        continue
                    ty1 = (k + 1) * 100_000 + 40
                    if ty1 <= y0 or ty1 - TILE_M >= y1:
                        continue
                    sq = COLS[(zone - 1) % 3][col - 1] + ROWS[(k + (5 if zone % 2 == 0 else 0)) % 20]
                    lats = [inv.transform(tx0 + TILE_M / 2, yy)[1] for yy in (ty1 - TILE_M / 2, ty1 - TILE_M, ty1)]
                    bands = []
                    for lat in lats:
                        b = BANDS[min(max(int((lat + 80) // 8), 0), len(BANDS) - 1)]
                        if b not in bands:
                            bands.append(b)
                    out.append((zone, bands, sq, epsg, (tx0, ty1 - TILE_M, tx0 + TILE_M, ty1)))
    return out


def tiles_for(bbox):
    """The tiles in the archive that cover bbox: [(path, epsg, footprint box in UTM)], where
    path is '<zone>/<band>/<square>'. The list is cached per bbox."""
    STORE.mkdir(parents=True, exist_ok=True)
    f = STORE / f"tiles_{'_'.join(f'{v:.3f}' for v in bbox)}.json"
    if f.exists():
        return [tuple(t) for t in json.loads(f.read_text())]
    from pyproj import Transformer
    from shapely.geometry import Polygon, box
    session = _http()
    found = []
    for zone, bands, sq, epsg, rect in candidate_tiles(bbox):
        for band in bands:
            path = f"{zone}/{band}/{sq}"
            if _subprefixes(session, f"{ROOT}/{path}/"):
                # how much of bbox the tile's square covers, in lon/lat
                inv = Transformer.from_crs(epsg, 4326, always_xy=True)
                xs, ys = _ring(rect)
                lon, lat = inv.transform(xs, ys)
                cover = Polygon(zip(lon, lat)).intersection(box(*bbox)).area
                found.append((path, epsg, list(rect), cover))
                break
    f.write_text(json.dumps(found))
    return [tuple(t) for t in found]


def tiles_needed(bbox):
    """How many Sentinel-2 tiles cover bbox, from the MGRS grid alone (no network): what search()
    reads, give or take a tile at sea."""
    return len(cover(bbox, [(f"{z}/{bands[0]}/{sq}", epsg, rect, 0)
                            for z, bands, sq, epsg, rect in candidate_tiles(bbox)]))


def cover(bbox, tiles):
    """The fewest tiles that cover bbox, greedily: the tile covering most of what is left
    first, so an area inside one UTM zone is read from that zone's tiles."""
    from pyproj import Transformer
    from shapely.geometry import Polygon, box
    area = box(*bbox)
    polys = []
    for path, epsg, rect, _ in tiles:
        inv = Transformer.from_crs(epsg, 4326, always_xy=True)
        lon, lat = inv.transform(*_ring(rect))
        polys.append(((path, epsg, rect), Polygon(zip(lon, lat)).intersection(area)))
    left, chosen = area, []
    while polys and left.area > 0.002 * area.area:
        gain = [p.intersection(left).area for _, p in polys]
        i = int(np.argmax(gain))
        if gain[i] < 0.002 * area.area:
            break
        chosen.append(polys[i][0])
        left = left.difference(polys.pop(i)[1])
    return chosen


def _months_back(years, months, today=None):
    today = today or dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(int(round(years * 12))):
        if not months or m in months:
            out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def scenes(session, path, year, month):
    """Scene folders of one tile in one month; months that are over are cached."""
    f = STORE / "months" / f"{path.replace('/', '')}_{year}_{month:02d}.json"
    if f.exists():
        return json.loads(f.read_text())
    got = _subprefixes(session, f"{ROOT}/{path}/{year}/{month}/")
    today = dt.date.today()
    if (year, month) < (today.year, today.month) and (today - dt.date(year, month, 1)).days > 45:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(got))
    return got


def _epsg_of(sid):
    """UTM EPSG code from a scene id such as S2B_36MZD_20260904_0_L2A."""
    tile = sid.split("_")[1]
    zone, band = int(tile[:2]), tile[2]
    return (32600 if band >= "N" else 32700) + zone


def item(session, prefix):
    """The facts kept from a scene's STAC item (cached): date, tile cloud, sun, footprint,
    band URLs and the scale that turns DN into reflectance (the offset: `dn_offset`)."""
    sid = prefix.rstrip("/").rsplit("/", 1)[-1]
    f = STORE / "items" / f"{sid}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = None
    for attempt in range(4):
        try:
            r = session.get(f"{BUCKET}/{prefix}{sid}.json", timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            break
        except Exception:
            if attempt == 3:
                raise
    d = r.json()
    p, a = d["properties"], d["assets"]

    def band(*names):
        name = next(n for n in names if n in a)
        rb = (a[name].get("raster:bands") or [{}])[0]
        return dict(href=a[name]["href"], scale=rb.get("scale", 1e-4))

    keep = dict(id=sid, datetime=p["datetime"], cloud=p.get("eo:cloud_cover", 100.0),
                epsg=p.get("proj:epsg") or _epsg_of(sid), sun_az=p.get("view:sun_azimuth"),
                sun_el=p.get("view:sun_elevation"), baseline=p.get("s2:processing_baseline"),
                late=p["datetime"][:10] >= "2022-01-25", geometry=d["geometry"],
                red=band("red", "B04"), green=band("green", "B03"), blue=band("blue", "B02"),
                scl=band("scl", "SCL"))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(keep))
    return keep


def search(bbox, years=1, months=None, max_cloud=MAX_TILE_CLOUD, date=None, workers=8):
    """Scenes over bbox, as {date 'YYYY-MM-DD': [item, ...]} (one item per tile)."""
    from shapely.geometry import box, shape
    tiles = cover(bbox, tiles_for(bbox))
    if not tiles:
        raise SystemExit(f"true colour: no Sentinel-2 tiles found for {bbox}")
    if len(tiles) > MAX_TILES:
        raise SystemExit(f"true colour: {len(tiles)} Sentinel-2 tiles; the drape is made for areas "
                         "up to a few hundred kilometres across")
    session = _http()
    if date:
        d = dt.date.fromisoformat(str(date))
        when = [(d.year, d.month)]
    else:
        when = _months_back(years, months)
    jobs = [(path, y, m) for path, *_ in tiles for (y, m) in when]
    with cf.ThreadPoolExecutor(workers) as ex:
        folders = list(ex.map(lambda j: scenes(session, *j), jobs))
    prefixes = [p for fs in folders for p in fs]
    if date:
        tag = str(date).replace("-", "")
        prefixes = [p for p in prefixes if f"_{tag}_" in p]
    print(f"  true colour: {len(tiles)} tile(s) ({', '.join(t[0] for t in tiles)}), "
          f"{len(prefixes)} scenes listed", flush=True)
    with cf.ThreadPoolExecutor(workers) as ex:
        items = [i for i in ex.map(lambda p: item(session, p), prefixes) if i]
    area = box(*bbox)
    by_date = {}
    for it in items:
        if it["cloud"] > max_cloud and not date:
            continue
        if not shape(it["geometry"]).intersects(area):
            continue
        by_date.setdefault(it["datetime"][:10], []).append(it)
    return by_date


# --------------------------------------------------------------------------- reading

def dn_offset(it):
    """1000 if the scene's pixels still carry ESA's offset, else 0.

    ESA adds 1000 to every DN from processing baseline 04.00 (25 January 2022). Earth
    Search takes it off when it converts the scenes, but its items do not say so
    reliably: over Magadi, scenes flagged earthsearch:boa_offset_applied = false have
    pixels as dark as DN 70, which cannot carry the offset, and the -0.1 in raster:bands
    would make the median blue reflectance -0.04. So the pixels decide: the offset is
    there only if the darkest half per cent of the tile, read from its coarsest
    overview, is at DN 1000 or more. Cached per scene."""
    f = STORE / "offsets.json"
    known = json.loads(f.read_text()) if f.exists() else {}
    if it["id"] in known:
        return known[it["id"]]
    off = 0
    if it.get("late", True):
        import rasterio
        with rasterio.Env(**drapes.ENV), rasterio.open("/vsicurl/" + it["blue"]["href"]) as src:
            k = (src.overviews(1) or [1])[-1]
            a = src.read(1, out_shape=(max(1, src.height // k), max(1, src.width // k)))
        v = a[a > 0]
        off = 1000 if v.size and np.percentile(v, 0.5) >= 1000 else 0
    known = json.loads(f.read_text()) if f.exists() else {}
    known[it["id"]] = off
    f.write_text(json.dumps(known))
    return off


def read_band(asset, epsg, dst_bounds, dst_res, dst_crs, classes=False, offset=0):
    """One band of one scene on the map grid at dst_res: reflectance (float32), or the
    class codes for SCL; NaN outside the scene. Only the window over the map is read,
    through the file's overviews when dst_res is coarser than the band."""
    import rasterio
    from pyproj import Transformer
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.windows import Window, from_bounds
    xs, ys = Transformer.from_crs(dst_crs, epsg, always_xy=True).transform(*_ring(dst_bounds))
    with rasterio.Env(**drapes.ENV), rasterio.open("/vsicurl/" + asset["href"]) as src:
        if src.crs is None or src.transform.is_identity:
            print(f"  true colour: {asset['href'].rsplit('/', 2)[-2]} has no georeferencing; skipped")
            return None
        pad = 3 * max(dst_res, src.res[0])
        win = from_bounds(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad, src.transform)
        try:
            win = win.intersection(Window(0, 0, src.width, src.height))
        except Exception:
            return None
        win = Window(int(win.col_off), int(win.row_off), int(math.ceil(win.width)), int(math.ceil(win.height)))
        if win.width < 2 or win.height < 2:
            return None
        f = max(1.0, dst_res / src.res[0])
        shape = (max(2, int(round(win.height / f))), max(2, int(round(win.width / f))))
        a = src.read(1, window=win, out_shape=shape,
                     resampling=Resampling.nearest if classes else Resampling.average)
        tr = src.window_transform(win) * Affine.scale(win.width / shape[1], win.height / shape[0])
    a = a.astype("float32")
    a[a == 0] = np.nan                                   # 0 is no data in every band and in SCL
    if not classes:
        a = (a - offset) * asset["scale"]
    out, _ = warp_to_map(a, tr, dst_bounds, dst_res, resampling="nearest" if classes else "bilinear",
                         src_crs=f"EPSG:{epsg}", dst_crs=dst_crs)
    return out


# --------------------------------------------------------------------------- colour

GAIN = 2.7            # reflectance x GAIN = linear light; savanna (red ~0.15) lands mid-tone
KNEE = 0.62           # above this (linear), highlights roll off toward white instead of clipping
SATURATION = 1.05     # a touch, for what the blend of cells and the paper take away


def tone(refl, exposure=1.0):
    """Surface reflectance (..., 3) -> display sRGB 0..1. The three bands share one curve,
    so grey ground stays grey: linear up to KNEE, then an exponential shoulder that
    reaches white only at infinity, then sRGB encoding."""
    from common import linear_to_srgb
    x = np.clip(np.nan_to_num(refl, nan=0.0), 0, None) * (GAIN * exposure)
    room = 1.0 - KNEE
    y = np.where(x > KNEE, KNEE + room * (1 - np.exp(-(x - KNEE) / room)), x)
    out = linear_to_srgb(y)
    lum = out @ np.array([0.2126, 0.7152, 0.0722], "float32")
    out = lum[..., None] + (out - lum[..., None]) * SATURATION
    return np.clip(out, 0, 1).astype("float32")


def legend(exposure=1.0):
    """The key: how much of the sunlight a surface reflects, in each band, and the tone
    it is printed in (the curve above, on a grey surface)."""
    vmax = 0.6

    def draw(d, right, top, pl):
        from PIL import Image
        w, h = pl.px(96), pl.px(3.2)
        xl, yb = right - w, top + pl.px(4.5)
        vals = np.linspace(0, vmax, int(w), dtype="float32")
        strip = (tone(np.repeat(vals[:, None], 3, 1)[None], exposure) * 255).astype("uint8")
        pl.img.paste(Image.fromarray(np.repeat(strip, max(1, int(h)), 0)), (int(xl), int(yb)))
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("IBMPlexMono-400", pl.px(2.3))
        draw_text(d, (xl, top), "TONE: SHARE OF SUNLIGHT REFLECTED, RED, GREEN AND BLUE ALIKE", f_k,
                  pl.mix(0.55), 0.2)
        ticks = (0, 10, 20, 30, 40, 50, 60)
        for t in ticks:
            x = xl + t / 100 / vmax * w
            d.line([(x, yb + h), (x, yb + h + pl.px(1.4))], fill=pl.mix(0.5), width=max(1, int(pl.px(0.15))))
            anchor = "ls" if t == ticks[0] else ("rs" if t == ticks[-1] else "ms")
            draw_text(d, (x, yb + h + pl.px(5.0)), f"{t} %", f_v, pl.mix(0.62), 0, anchor)
    return draw


# --------------------------------------------------------------------------- choosing

def _scene_scl(it, bounds, res, crs):
    """The scene classification of one scene on a coarse map grid, 0 where no data. Cached."""
    f = drapes.cache_path("s2scl", it["id"], [round(v) for v in bounds], round(res, 3), str(crs))
    if f.exists():
        return np.load(f)["scl"]
    try:
        a = read_band(it["scl"], it["epsg"], bounds, res, crs, classes=True)
    except Exception as err:                             # a scene that cannot be read is skipped
        print(f"  true colour: {it['id']} SCL unreadable ({err.__class__.__name__})", flush=True)
        return None
    x0, y0, x1, y1 = bounds
    shape = (int(round((y1 - y0) / res)), int(round((x1 - x0) / res)))
    a = np.zeros(shape, "uint8") if a is None else np.nan_to_num(a, nan=0).astype("uint8")
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, scl=a)
    return a


def _coarse(mask, shape):
    """A boolean grid resampled to another shape by nearest cell."""
    r = (np.arange(shape[0]) * mask.shape[0] / shape[0]).astype(int)
    c = (np.arange(shape[1]) * mask.shape[1] / shape[1]).astype(int)
    return mask[np.ix_(r, c)]


def score(by_date, ctx, workers=6):
    """For each date, the share of the sheet that is inside the scene and clear, from the
    SCL at about 200 m. Returns (scores, coarse SCL per date, persistent-flag mask, res)."""
    x0, y0, x1, y1 = ctx["bounds"]
    res = max(150.0, round(max(x1 - x0, y1 - y0) / 300, -1))
    jobs = [(d, it) for d in sorted(by_date) for it in by_date[d]]
    with cf.ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(lambda j: _scene_scl(j[1], ctx["bounds"], res, ctx["crs"]), jobs))
    merged = {}
    for (d, _), a in zip(jobs, got):
        if a is None:
            continue
        merged[d] = a if d not in merged else np.where(merged[d] == 0, a, merged[d])
    if not merged:
        raise SystemExit("true colour: no readable Sentinel-2 scene over the sheet")
    dates = sorted(merged)
    stack = np.stack([merged[d] for d in dates])
    has, flag = stack > 0, np.isin(stack, CLOUD)
    # The scene classification misreads soda crust as cloud and dark brine as shadow.
    # Such a misreading comes back date after date, where real cloud does not: a flag is
    # not counted on a cell flagged on at least 3 of the nearly clear dates (98 % of the
    # sheet clear or more) and on more than a quarter of them. Open water as such is not
    # exempt, or clouded coasts and lake shores would pass as clear.
    persistent = np.zeros(has.shape[1:], bool)
    if len(dates) >= 5:
        raw = (has & ~flag).mean((1, 2))
        calm = raw >= 0.98
        if calm.sum() >= 3:
            cnt = flag[calm].sum(0)
            persistent = (cnt >= 3) & (cnt / np.maximum(has[calm].sum(0), 1) > 0.25)
    aoi = np.ones(has.shape[1:], bool) if ctx.get("valid") is None else _coarse(ctx["valid"], has.shape[1:])
    clear = has & ~(flag & ~persistent)
    scores = {d: float(clear[i][aoi].mean()) for i, d in enumerate(dates)}
    return scores, {d: clear[i] for i, d in enumerate(dates)}, persistent, res


def choose(scores, clear, aoi=None, extra=3):
    """The most recent date with the sheet clear enough; failing that the clearest, with up
    to `extra` more dates, each the one that clears most of what is still cloudy."""
    good = [d for d, v in scores.items() if v >= CLEAR_ENOUGH]
    if good:
        return [max(good)]
    first = max(scores, key=lambda d: (scores[d], d))
    used, done = [first], clear[first].copy()
    aoi = np.ones(done.shape, bool) if aoi is None else aoi
    for _ in range(extra):
        if done[aoi].mean() >= CLEAR_ENOUGH:
            break
        rest = [d for d in scores if d not in used]
        if not rest:
            break
        nxt = max(rest, key=lambda d: ((clear[d] & ~done & aoi).sum(), d))
        if not (clear[nxt] & ~done & aoi).any():
            break
        used.append(nxt)
        done |= clear[nxt]
    return used


# --------------------------------------------------------------------------- the drape

RGB = ("red", "green", "blue")


def compose(dates, by_date, ctx, k, persistent=None):
    """Reflectance on the texture grid (k x the model grid): the first date wherever it has
    data, then each further date only where the cells are still empty or were cloud.
    Each tile after the first reads only the part of the sheet still missing."""
    x0, y0, x1, y1 = ctx["bounds"]
    res = ctx["cell"] / k
    rows, cols = ctx["shape"][0] * k, ctx["shape"][1] * k
    out = np.full((rows, cols, 3), np.nan, "float32")
    masked = len(dates) > 1
    for i, d in enumerate(dates):
        for it in by_date[d]:
            need = np.isnan(out[..., 0])
            if not need.any():
                break
            rr, cc = np.nonzero(need.any(1))[0], np.nonzero(need.any(0))[0]
            r0, r1, c0, c1 = rr[0], rr[-1] + 1, cc[0], cc[-1] + 1
            sub = (x0 + c0 * res, y1 - r1 * res, x0 + c1 * res, y1 - r0 * res)
            off = dn_offset(it)
            chans = [read_band(it[b], it["epsg"], sub, res, ctx["crs"], offset=off) for b in RGB]
            if chans[0] is None:
                continue
            a = np.stack(chans, -1)
            ok = ~np.isnan(a).any(-1) & need[r0:r1, c0:c1]
            if masked:
                scl = read_band(it["scl"], it["epsg"], sub, res, ctx["crs"], classes=True)
                cloudy = np.isin(np.nan_to_num(scl, nan=0), CLOUD)
                if persistent is not None:
                    full = _coarse(persistent, (rows, cols))[r0:r1, c0:c1]
                    cloudy &= ~full
                # the haze at a cloud's edge is not classed; take 120 m more around each
                from scipy import ndimage
                cloudy = ndimage.binary_dilation(cloudy, iterations=max(1, int(round(120 / res))))
                ok &= ~cloudy
            out[r0:r1, c0:c1][ok] = a[ok]
            print(f"  true colour: {it['id']} filled {ok.sum() / ok.size * 100:.1f} % of its window", flush=True)
    if masked and np.isnan(out[..., 0]).any():             # still a hole: the first date, cloud and all
        need = np.isnan(out[..., 0])
        for it in by_date[dates[0]]:
            off = dn_offset(it)
            a = np.stack([read_band(it[b], it["epsg"], ctx["bounds"], res, ctx["crs"], offset=off)
                          for b in RGB], -1)
            put = need & ~np.isnan(a).any(-1)
            out[put] = a[put]
            need &= ~put
    return out


def texture_factor(ctx, opts):
    """How many texture cells per model cell: the native 10 m where the model is coarser,
    never more than 8 192 texture cells along a side."""
    if opts.get("detail"):
        return max(1, int(opts["detail"]))
    k = max(1, int(round(ctx["cell"] / 10.0)))
    return max(1, min(k, 8192 // max(ctx["shape"])))


def lake_extent(ctx, lake):
    """A lake measured from the elevation model: the ground at or below `below` metres
    joined to the given point. Returns (km north to south, km2, touches the sheet edge)."""
    from pyproj import Transformer
    from scipy import ndimage
    x, y = Transformer.from_crs("EPSG:4326", ctx["crs"], always_xy=True).transform(lake["lon"], lake["lat"])
    x0, y0, x1, y1 = ctx["bounds"]
    cell, z = ctx["cell"], ctx["z"]
    r, c = int((y1 - y) / cell), int((x - x0) / cell)
    if not (0 <= r < z.shape[0] and 0 <= c < z.shape[1]):
        return None
    lab, _ = ndimage.label(z <= float(lake["below"]))
    if lab[r, c] == 0:
        print(f"  true colour: {lake['name']} point is above {lake['below']} m; no lake fact")
        return None
    m = lab == lab[r, c]
    rr, cc = np.nonzero(m)
    edge = rr.min() == 0 or cc.min() == 0 or rr.max() == z.shape[0] - 1 or cc.max() == z.shape[1] - 1
    return (rr.max() - rr.min() + 1) * cell / 1000, m.sum() * cell ** 2 / 1e6, edge


def _day(d):
    return dt.date.fromisoformat(d).strftime("%-d %b %Y")


def drape(ctx):
    opts = ctx["options"]
    w, s, e, n = ctx["ll"]
    pad = 0.01
    bbox = (w - pad, s - pad, e + pad, n + pad)
    exposure = float(opts.get("exposure", 1.0))
    by_date = search(bbox, years=float(opts.get("years", 1)), months=opts.get("months"),
                     date=opts.get("date"))
    if not by_date:
        raise SystemExit("true colour: no Sentinel-2 scene found; widen `years` or check `date`")
    persistent = None
    if opts.get("date"):
        dates = [str(opts["date"])]
        if dates[0] not in by_date:
            raise SystemExit(f"true colour: no scene on {dates[0]} over the sheet")
    else:
        scores, clear, persistent, _ = score(by_date, ctx)
        aoi = None if ctx.get("valid") is None else _coarse(ctx["valid"], next(iter(clear.values())).shape)
        dates = choose(scores, clear, aoi)
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        print("  true colour: clearest dates " + ", ".join(f"{d} {v * 100:.1f} %" for d, v in best))
        if len(dates) > 1:
            persistent = persistent if persistent.any() else None
    k = texture_factor(ctx, opts)
    ids = [it["id"] for d in dates for it in by_date[d]]
    print(f"  true colour: {', '.join(dates)} ({', '.join(ids)}), texture {k} x the model grid, "
          f"{ctx['cell'] / k:g} m", flush=True)

    f = drapes.cache_path("truecolour", [round(v, 1) for v in ctx["bounds"]], ctx["cell"], k,
                          str(ctx["crs"]), ids)
    if f.exists():
        q = np.load(f)["refl"]
        refl = q.astype("float32") / 10000
        refl[q == 65535] = np.nan
        del q
    else:
        refl = compose(dates, by_date, ctx, k, persistent)
        q = np.where(np.isnan(refl), 65535, np.round(np.clip(refl, 0, 6.5) * 10000)).astype("uint16")
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, refl=q)
        # the same values a later run loads, so the texture (and the render cache) match
        refl = q.astype("float32") / 10000
        refl[q == 65535] = np.nan
        del q
    missing = np.isnan(refl[..., 0])
    if missing.mean() > 0.001:
        print(f"  true colour: {missing.mean() * 100:.1f} % of the sheet has no scene; left bone")
    tex = tone(refl, exposure)
    tex[missing] = np.array([0xeb, 0xe6, 0xda], "float32") / 255
    del refl

    # facts: the day (or days), a measured lake, the exaggeration
    first = _day(dates[0])
    facts = [("Sentinel-2 scene", first) if len(dates) == 1 else
             ("Sentinel-2 scenes", f"{first} + {len(dates) - 1} more")]
    lake = opts.get("lake")
    if lake:
        got = lake_extent(ctx, lake)
        if got:
            km, area, edge = got
            print(f"  true colour: {lake['name']} below {lake['below']} m: {km:.1f} km north to south, "
                  f"{area:.1f} km2" + (" (cut by the sheet edge)" if edge else ""))
            facts.append((f"{lake['name']} below {lake['below']} m",
                          f"{'over ' if edge else ''}{km:.0f} km north to south"))
    z, valid = ctx["z"], ctx.get("valid")
    if ctx.get("zex"):                                   # relief.py's own figure, when it passes it
        zex = float(ctx["zex"])
    elif opts.get("zex"):
        zex = float(opts["zex"])
    else:                                                # the rule relief.py uses for a map spec
        import regions
        zlo = float(z[valid].min() if valid is not None else z.min())
        zex = regions.default_exaggeration(ctx["bounds"][2] - ctx["bounds"][0], float(z.max()) - zlo)
    facts.append(("Vertical exaggeration", f"×{zex:g}"))

    years = sorted({d[:4] for d in dates})
    return dict(
        tex=tex, legend=legend(exposure), facts=facts[:3], water=False,
        key=dict(ids=ids, k=k, gain=GAIN, knee=KNEE, sat=SATURATION, exposure=exposure),
        credit=f"Imagery: contains modified Copernicus Sentinel data {', '.join(years)} (Sentinel-2 L2A).")
