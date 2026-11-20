"""Shared pieces of the ZeroPoint print pipeline: paths, data loaders,
projection, colour helpers and the plate (poster) layout.

Every plate is designed at ISO A2 portrait (420 x 594 mm). All sizes below are
in millimetres at that sheet size, so a plate rendered at a different dpi is
the same drawing, only sharper.
"""
import math
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

Image.MAX_IMAGE_PIXELS = None

HERE = Path(__file__).parent
DATA = Path(os.environ.get("ZP_DATA", HERE / "data"))
OUT = Path(os.environ.get("ZP_OUT", HERE / "out"))
CACHE = DATA / "cache"

SHEET_MM = (420.0, 594.0)          # A2 portrait
MARGIN_MM = 22.0
BLEED_MM = 3.0                     # extra image on every side, trimmed off after printing

# House colours, shared with the website.
INK = (11, 13, 12)
PAPER = (241, 240, 235)
OLIVE = (120, 134, 83)
OLIVE_LIGHT = (170, 181, 144)

# Projection used for every country-scale plate: WGS 84 / UTM zone 37S.
MAP_CRS = "EPSG:32737"


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def countries():
    import geopandas as gpd
    return gpd.read_file(DATA / "ne" / "ne_10m_admin_0_countries")


@lru_cache(maxsize=None)
def county_boundaries():
    """Kenya's 47 counties (OpenStreetMap via Overture Maps, EPSG:4326), named as the shop names
    them (Murang'a, Taita-Taveta), with the Ilemi Triangle merged into Turkana as on Kenyan maps.
    Needs `python fetch_overture.py counties` once."""
    import geopandas as gpd
    import shapely
    g = gpd.read_file(CACHE / "kenya_counties.gpkg")
    g["geometry"] = shapely.make_valid(g.geometry.values)
    g["name"] = g["name"].str.replace("`", "'").str.replace("Taita Taveta", "Taita-Taveta")
    g.loc[g["name"].str.contains("Elemi|Ilemi"), "name"] = "Turkana"
    return g[["name", "geometry"]].dissolve("name", as_index=False)


def kenya(crs="EPSG:4326"):
    """Kenya as a single (multi)polygon."""
    g = countries()
    geom = g.loc[g["ADMIN"] == "Kenya"].to_crs(crs).geometry.union_all()
    return geom


@lru_cache(maxsize=None)
def lakes(crs="EPSG:4326"):
    import geopandas as gpd
    return gpd.read_file(DATA / "ne" / "ne_10m_lakes").to_crs(crs)


def transformer(src="EPSG:4326", dst=MAP_CRS):
    from pyproj import Transformer
    return Transformer.from_crs(src, dst, always_xy=True)


# --------------------------------------------------------------------------
# elevation
# --------------------------------------------------------------------------
def load_dem(bbox, source="glo90", factor=1):
    """Mosaic Copernicus DEM tiles over bbox = (w, s, e, n) in degrees.

    Returns (array float32 [rows, cols], affine transform). `factor` block-
    averages the native grid (3 arc-seconds for glo90, 1 for glo30). Results
    are cached on disk because the country-wide mosaic takes a while.
    """
    import rasterio
    from rasterio.merge import merge
    from rasterio.transform import Affine

    w, s, e, n = bbox
    key = f"{source}_{w}_{s}_{e}_{n}_f{factor}".replace(".", "p").replace("-", "m")
    npy, meta = CACHE / f"{key}.npy", CACHE / f"{key}.txt"
    if npy.exists():
        t = [float(v) for v in meta.read_text().split()]
        return np.load(npy, mmap_mode="r"), Affine(*t)

    arcsec = {"glo90": 30, "glo30": 10}[source]
    tiles = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            name = f"Copernicus_DSM_COG_{arcsec}_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM.tif"
            p = DATA / source / name
            if p.exists():
                tiles.append(p)
    srcs = [rasterio.open(p) for p in tiles]
    arr, tr = merge(srcs, bounds=(w, s, e, n), nodata=0, dtype="float32")
    for src in srcs:
        src.close()
    arr = arr[0]
    if factor > 1:
        h, wd = (arr.shape[0] // factor) * factor, (arr.shape[1] // factor) * factor
        arr = arr[:h, :wd].reshape(h // factor, factor, wd // factor, factor).mean((1, 3))
        tr = tr * Affine.scale(factor)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(npy, arr.astype("float32"))
    meta.write_text(" ".join(repr(v) for v in tuple(tr)[:6]))
    return arr, tr


def warp_to_map(arr, transform, dst_bounds, dst_res, resampling="bilinear",
                src_crs="EPSG:4326", dst_crs=MAP_CRS, nodata=np.nan):
    """Reproject a lon/lat raster onto the plate projection."""
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    x0, y0, x1, y1 = dst_bounds
    wd, ht = int(round((x1 - x0) / dst_res)), int(round((y1 - y0) / dst_res))
    dst = np.full((ht, wd), nodata, dtype="float32")
    reproject(np.asarray(arr, dtype="float32"), dst, src_transform=transform,
              src_crs=src_crs, dst_transform=from_origin(x0, y1, dst_res, dst_res),
              dst_crs=dst_crs, resampling=getattr(Resampling, resampling),
              src_nodata=None, dst_nodata=nodata, num_threads=4)
    return dst, from_origin(x0, y1, dst_res, dst_res)


def rasterize_geom(geom, shape, transform, all_touched=False):
    from rasterio.features import rasterize
    return rasterize([(geom, 1)], out_shape=shape, transform=transform,
                     fill=0, all_touched=all_touched, dtype="uint8").astype(bool)


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_linear(c):
    c = np.asarray(c, dtype="float32")
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype="float32"), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def ramp(stops, n=256):
    """Colour ramp interpolated in linear light.

    stops: list of hex strings, or (position, hex) pairs with positions 0..1.
    Returns an (n, 3) float array of sRGB values in 0..1.
    """
    if isinstance(stops[0], str):
        stops = [(i / (len(stops) - 1), s) for i, s in enumerate(stops)]
    pos = np.array([p for p, _ in stops], dtype="float32")
    cols = srgb_to_linear(np.array([hex_rgb(c) for _, c in stops], dtype="float32") / 255)
    x = np.linspace(0, 1, n, dtype="float32")
    out = np.stack([np.interp(x, pos, cols[:, i]) for i in range(3)], 1)
    return linear_to_srgb(out)


def apply_ramp(values, table):
    """Map values in 0..1 through a ramp table -> float RGB image."""
    idx = np.clip(np.nan_to_num(values) * (len(table) - 1), 0, len(table) - 1)
    lo = np.floor(idx).astype("int32")
    hi = np.minimum(lo + 1, len(table) - 1)
    f = (idx - lo)[..., None].astype("float32")
    return table[lo] * (1 - f) + table[hi] * f


# --------------------------------------------------------------------------
# plate layout
# --------------------------------------------------------------------------
def mm(v, dpi):
    return v * dpi / 25.4


@lru_cache(maxsize=None)
def font(name, size_px):
    return ImageFont.truetype(str(DATA / "fonts" / f"{name}.ttf"), max(1, int(round(size_px))))


def text_width(text, fnt, tracking=0.0):
    """Width of `text` with `tracking` given as a fraction of the font size."""
    return fnt.getlength(text) + tracking * fnt.size * max(len(text) - 1, 0)


def draw_text(draw, xy, text, fnt, fill, tracking=0.0, anchor="ls"):
    """Draw text with letter-spacing. anchor: l/m/r + baseline 's'."""
    x, y = xy
    total = text_width(text, fnt, tracking)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    if tracking == 0:
        draw.text((x, y), text, font=fnt, fill=fill, anchor="l" + anchor[1])
        return total
    prev = ""
    for ch in text:
        if prev:  # keep the font's own kerning for the pair
            x += fnt.getlength(prev + ch) - fnt.getlength(ch) + tracking * fnt.size
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="l" + anchor[1])
        prev = ch
    return total


def dms(value, pos, neg):
    hemi = pos if value >= 0 else neg
    v = abs(value)
    d = int(v)
    m = int(round((v - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}′{hemi}"


def coord_label(lon, lat):
    return f"{dms(lat, 'N', 'S')}  {dms(lon, 'E', 'W')}"


def srgb_profile():
    """The sRGB colour profile, embedded in every file so a print shop's
    software knows what the numbers mean."""
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


class Plate:
    """An A2 portrait sheet with the ZeroPoint title block along the foot.

    The image is drawn 3 mm larger than the sheet on every side (bleed), so
    a printer can trim to 420 x 594 mm without a white edge. `margin`,
    `map_box` and the title block are all measured from the trim edge.

    The map goes in `self.map_box` (pixels). Call `title_block(...)` last.
    """

    def __init__(self, dpi=150, bg=INK, fg=PAPER, accent=OLIVE_LIGHT, block_mm=92.0,
                 sheet_mm=SHEET_MM, bleed_mm=BLEED_MM):
        self.dpi = dpi
        self.bg, self.fg, self.accent = bg, fg, accent
        self.sheet_mm = sheet_mm
        self.bleed = int(round(mm(bleed_mm, dpi)))
        self.w = int(round(mm(sheet_mm[0], dpi))) + 2 * self.bleed
        self.h = int(round(mm(sheet_mm[1], dpi))) + 2 * self.bleed
        self.img = Image.new("RGB", (self.w, self.h), bg)
        m = mm(MARGIN_MM, dpi) + self.bleed
        self.margin = m
        self.block_top = self.h - m - mm(block_mm, dpi)
        # left, top, right, bottom of the area available to the map
        self.map_box = (m, m, self.w - m, self.block_top - mm(10, dpi))

    def px(self, v):
        return mm(v, self.dpi)

    def mix(self, t):
        """Foreground colour at opacity t over the sheet background."""
        return tuple(int(round(b + (f - b) * t)) for f, b in zip(self.fg, self.bg))

    def paste(self, layer, box=None):
        """Paste an RGB/RGBA PIL image, by default filling the whole sheet."""
        if layer.size != self.img.size and box is None:
            layer = layer.resize(self.img.size, Image.LANCZOS)
        if layer.mode == "RGBA":
            self.img.paste(layer, box or (0, 0), layer)
        else:
            self.img.paste(layer, box or (0, 0))

    def title_block(self, title, subtitle, number, facts, credit, centre=None,
                    legend=None, label="PLATE"):
        """Draw the foot of the sheet.

        title     e.g. "Kenya"
        subtitle  e.g. "Rivers and drainage basins"
        number    plate number, e.g. "02" (`label` sets the word before it)
        facts     short (label, value) pairs set under the rule
        credit    data / method line
        centre    (lon, lat) printed as the sheet's reference coordinate
        legend    optional callable(draw, x_right, y_top, plate) for a key
        """
        d = ImageDraw.Draw(self.img)
        px, m = self.px, self.margin
        left, right = m, self.w - m
        top = self.block_top
        strong, soft, faint = self.fg, self.mix(0.62), self.mix(0.38)
        rule = self.mix(0.22)

        # top rule with a survey tick at each end
        d.line([(left, top), (right, top)], fill=rule, width=max(1, int(px(0.18))))
        for x in (left, right):
            d.line([(x, top - px(1.6)), (x, top + px(1.6))], fill=soft,
                   width=max(1, int(px(0.25))))

        # plate number and series, small caps over the title
        f_label = font("Barlow-500", px(3.0))
        y = top + px(11.0)
        draw_text(d, (left, y), f"{label} {number}", f_label, self.accent, 0.22)
        draw_text(d, (right, y), "ZEROPOINT GEOSPATIAL", f_label, soft, 0.22, anchor="rs")

        # title
        f_title = font("Barlow-300", px(30.0))
        y_title = top + px(40.0)
        draw_text(d, (left - px(1.2), y_title), title.upper(), f_title, strong, -0.012)

        # subtitle
        f_sub = font("Barlow-500", px(4.3))
        y_sub = y_title + px(11.5)
        draw_text(d, (left, y_sub), subtitle.upper(), f_sub, soft, 0.2)

        if legend is not None:
            legend(d, right, top + px(19.0), self)

        # lower rule and facts
        y_rule = y_sub + px(9.5)
        d.line([(left, y_rule), (right, y_rule)], fill=rule, width=max(1, int(px(0.18))))
        f_k = font("Barlow-500", px(2.5))
        f_v = font("IBMPlexMono-400", px(2.95))
        x = left
        cells = list(facts)
        if centre is not None:
            cells.append(("Sheet centre", coord_label(*centre)))
        col = (right - left) / max(len(cells), 1)
        for k, v in cells:
            draw_text(d, (x, y_rule + px(7.0)), k.upper(), f_k, faint, 0.2)
            draw_text(d, (x, y_rule + px(12.6)), v, f_v, soft, 0.0)
            x += col

        # credit line at the very foot; a credit too long for one line is broken at a
        # sentence onto two, so it never runs into the copyright on the right
        f_c = font("Barlow-400", px(2.45))
        y_c = self.h - m
        mark = "© ZeroPoint Geospatial, Nairobi"
        room = (right - left) - text_width(mark, f_c, 0.04) - px(8)
        lines = [credit]
        if text_width(credit, f_c, 0.04) > room:
            parts = [s for s in credit.replace(". ", ".\n").split("\n")]
            best = None
            for k in range(1, len(parts)):
                a, b = " ".join(parts[:k]), " ".join(parts[k:])
                wa, wb = text_width(a, f_c, 0.04), text_width(b, f_c, 0.04)
                if wa <= right - left and wb <= room and (best is None or abs(wa - wb) < best[0]):
                    best = (abs(wa - wb), a, b)
            if best:
                lines = [best[1], best[2]]
        for i, line in enumerate(lines):
            draw_text(d, (left, y_c - (len(lines) - 1 - i) * px(3.6)), line, f_c, faint, 0.04)
        draw_text(d, (right, y_c), mark, f_c, faint, 0.04, anchor="rs")
        return self

    def save(self, name):
        """Write the sheet, bleed included, as a PNG tagged sRGB."""
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"{name}.png"
        self.img.save(path, optimize=False, dpi=(self.dpi, self.dpi),
                      icc_profile=srgb_profile())
        return path


def fit_box(box, aspect):
    """Largest rect of the given width/height aspect centred in box."""
    l, t, r, b = box
    bw, bh = r - l, b - t
    if bw / bh > aspect:
        w, h = bh * aspect, bh
    else:
        w, h = bw, bw / aspect
    return (l + (bw - w) / 2, t + (bh - h) / 2, l + (bw + w) / 2, t + (bh + h) / 2)


def glow(layer_rgba, radius_px, strength):
    """Soft additive bloom for a transparent line layer (returns RGBA)."""
    a = np.asarray(layer_rgba, dtype="float32") / 255
    blurred = layer_rgba.filter(ImageFilter.GaussianBlur(radius_px))
    b = np.asarray(blurred, dtype="float32") / 255
    out = b.copy()
    out[..., 3] = np.clip(b[..., 3] * strength, 0, 1)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype("uint8"), "RGBA")


# --------------------------------------------------------------------------
# hypsometric tints
# --------------------------------------------------------------------------
# One elevation ramp for every relief plate, so a height reads as the same
# colour from the coast to the summit of Mount Kenya. Stops are in metres.
HYPSO = [
    (0, "#e9dfc6"), (250, "#dfd0a6"), (700, "#cdbb8c"), (1150, "#b9af80"),
    (1600, "#9da375"), (2100, "#778a61"), (2700, "#4e6b4d"), (3200, "#61704f"),
    (3700, "#8f8865"), (4200, "#8d857b"), (4700, "#b3aea6"), (5200, "#d6d2cb"),
    (5600, "#f1f0ec"), (5900, "#ffffff"),
]


def hypso_rgb(elev, stops=HYPSO):
    """Elevation in metres -> float sRGB image, interpolated in linear light."""
    z = np.asarray([p for p, _ in stops], dtype="float32")
    cols = srgb_to_linear(np.array([hex_rgb(c) for _, c in stops], dtype="float32") / 255)
    e = np.nan_to_num(np.asarray(elev, dtype="float32"))
    out = np.stack([np.interp(e, z, cols[:, i]) for i in range(3)], -1)
    return linear_to_srgb(out)


def place_render(plate, rgb, mask, box=(0, 0), exposure=1.0):
    """Composite a path-traced layer onto a plate.

    The floor of the render is a shadow catcher. Lighting is normalised so
    an open, unshadowed floor comes back at exactly the paper colour; here it
    is clamped to that, so the sheet keeps its own paper tone and is darkened
    only where the model shades it.
    """
    import render3d as r3

    paper = srgb_to_linear(np.array(plate.bg, dtype="float32") / 255)
    floor_out = linear_to_srgb(np.minimum(rgb, paper))
    model_out = r3.tonemap(rgb, exposure)
    m = mask[..., None]
    out = floor_out * (1 - m) + model_out * m
    layer = Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype("uint8"))
    plate.img.paste(layer, (int(round(box[0])), int(round(box[1]))))
    return layer


def ramp_legend(stops, label, ticks, fmt=lambda v: f"{v:,.0f}".replace(",", " "),
                vmax=None, vmin=None):
    """A small horizontal colour key for the title block."""
    vmin = stops[0][0] if vmin is None else vmin
    vmax = stops[-1][0] if vmax is None else vmax

    def draw(d, right, top, pl):
        w, h = pl.px(96), pl.px(3.2)
        x0, y0 = right - w, top + pl.px(4.5)
        vals = np.linspace(vmin, vmax, int(w))
        strip = (hypso_rgb(vals[None, :], stops) * 255).astype("uint8")
        bar = Image.fromarray(np.repeat(strip, max(1, int(h)), 0))
        pl.img.paste(bar, (int(x0), int(y0)))
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("IBMPlexMono-400", pl.px(2.3))
        draw_text(d, (x0, top), label.upper(), f_k, pl.mix(0.55), 0.2)
        for t in ticks:
            x = x0 + (t - vmin) / (vmax - vmin) * w
            d.line([(x, y0 + h), (x, y0 + h + pl.px(1.4))], fill=pl.mix(0.5),
                   width=max(1, int(pl.px(0.15))))
            anchor = "ls" if t == ticks[0] else ("rs" if t == ticks[-1] else "ms")
            draw_text(d, (x, y0 + h + pl.px(5.0)), fmt(t), f_v, pl.mix(0.62), 0, anchor)
    return draw


def _soft_halo(plate, paint, xy, halo, reach_mm=60):
    """Paint `paint(draw, colour)` as a blurred halo patch behind a label."""
    x, y = xy
    pad = int(plate.px(reach_mm))
    x0, y0 = max(int(x) - pad, 0), max(int(y) - pad, 0)
    x1, y1 = min(int(x) + pad, plate.w), min(int(y) + pad, plate.h)
    if x1 <= x0 or y1 <= y0:
        return
    glow = Image.new("L", (x1 - x0, y1 - y0), 0)
    d = ImageDraw.Draw(glow)
    paint(d, 255, (-x0, -y0))
    glow = glow.filter(ImageFilter.MaxFilter(2 * int(max(1, plate.px(0.35))) + 1))
    glow = glow.filter(ImageFilter.GaussianBlur(plate.px(0.7)))
    glow = glow.point(lambda v: min(255, int(v * 0.93)))
    plate.img.paste(Image.new("RGB", glow.size, halo), (x0, y0), glow)


def annotate(plate, xy, name, value=None, side="right", on_dark=False, leader=None,
             size_mm=2.9, ink=None, halo=None):
    """A spot label: a dot, the name in caps and an optional figure in mono,
    over a soft halo so it reads on any terrain colour.

    leader  optional (dx_mm, dy_mm): put the text that far from the dot and
            join the two with a hairline, for crowded places.
    """
    x, y = xy
    ink = ink or ((250, 249, 244) if on_dark else (18, 20, 19))
    halo = halo or ((14, 16, 15) if on_dark else (250, 249, 244))
    f_n = font("Barlow-600", plate.px(size_mm))
    f_v = font("IBMPlexMono-500", plate.px(size_mm * 0.86))
    r = plate.px(0.6)
    lx, ly = x, y
    if leader:
        lx, ly = x + plate.px(leader[0]), y + plate.px(leader[1])
    off = plate.px(2.8 if not leader else 1.2) * (1 if side == "right" else -1)
    anchor = "ls" if side == "right" else "rs"
    ty = ly + plate.px(1.0)
    vy = ty + plate.px(size_mm * 1.28)

    def paint(d, colour, shift=(0, 0)):
        sx, sy = shift
        d.ellipse([x - r + sx, y - r + sy, x + r + sx, y + r + sy], fill=colour)
        if leader:
            d.line([(x + sx, y + sy), (lx + sx, ly + sy)], fill=colour,
                   width=max(1, int(round(plate.px(0.18)))))
        draw_text(d, (lx + off + sx, ty + sy), name.upper(), f_n, colour, 0.14, anchor)
        if value:
            draw_text(d, (lx + off + sx, vy + sy), value, f_v, colour, 0, anchor)

    _soft_halo(plate, paint, ((x + lx) / 2, (y + ly) / 2), halo, 60 + (abs(leader[0]) if leader else 0))
    paint(ImageDraw.Draw(plate.img), ink)


def name_label(plate, xy, text, colour, halo, size_mm=3.1, angle=0.0, italic=True,
               tracking=0.1, anchor="m", caps=False, weight=400):
    """A free-standing name (a river, a range, a lake), optionally rotated.
    Water and landform names are set in italic, as on a topographic sheet."""
    name = f"BarlowItalic-{weight if weight in (400, 500) else 400}" if italic else f"Barlow-{weight}"
    fnt = font(name, plate.px(size_mm))
    text = text.upper() if caps else text
    w = int(text_width(text, fnt, tracking)) + int(plate.px(8))
    h = int(plate.px(size_mm * 2.4))
    def layer(col):
        im = Image.new("L", (w, h), 0)
        draw_text(ImageDraw.Draw(im), (w / 2, h * 0.68), text, fnt, col, tracking, "ms")
        return im
    mask = layer(255)
    glow = mask.filter(ImageFilter.MaxFilter(2 * int(max(1, plate.px(0.35))) + 1))
    glow = glow.filter(ImageFilter.GaussianBlur(plate.px(0.7))).point(lambda v: min(255, int(v * 0.9)))
    if angle:
        mask = mask.rotate(angle, resample=Image.BICUBIC, expand=True)
        glow = glow.rotate(angle, resample=Image.BICUBIC, expand=True)
    x, y = xy
    dx = {"m": mask.width / 2, "l": 0, "r": mask.width}[anchor]
    pos = (int(round(x - dx)), int(round(y - mask.height / 2)))
    plate.img.paste(Image.new("RGB", glow.size, halo), pos, glow)
    plate.img.paste(Image.new("RGB", mask.size, colour), pos, mask)


def cached_render(key, render_fn):
    """Reuse a finished 3D render when only labels or type have changed.

    key        any dict describing the scene (plate, size, samples, model)
    render_fn  called with no arguments, returns (rgb, mask)
    Set ZP_FRESH=1 to ignore the cache.
    """
    import hashlib
    import json
    digest = hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]
    base = CACHE / "renders" / f"{key.get('plate', 'render')}_{digest}"
    rgb_f, mask_f = base.with_suffix(".rgb.npy"), base.with_suffix(".mask.npy")
    if rgb_f.exists() and mask_f.exists() and not os.environ.get("ZP_FRESH"):
        print(f"  reusing cached render {base.name}")
        return np.load(rgb_f).astype("float32"), np.load(mask_f).astype("float32") / 255
    rgb, mask = render_fn()
    base.parent.mkdir(parents=True, exist_ok=True)
    np.save(rgb_f, rgb.astype("float16"))
    np.save(mask_f, (np.clip(mask, 0, 1) * 255).astype("uint8"))
    return rgb, mask


class KenyaFrame:
    """Kenya drawn at a fixed scale in a plate's map box (UTM zone 37S).
    The rivers, roads and counties plates all use it, so they register."""

    def __init__(self, plate, scale_a2=2_400_000):
        self.plate = plate
        self.scale_a2 = scale_a2
        self.geom = kenya(MAP_CRS)
        self.x0, self.y0, self.x1, self.y1 = self.geom.bounds
        self.k = plate.px(1000) / scale_a2                    # pixels per metre
        l, t, r, b = plate.map_box
        self.w, self.h = (self.x1 - self.x0) * self.k, (self.y1 - self.y0) * self.k
        self.ox, self.oy = l + (r - l - self.w) / 2, t + (b - t - self.h) / 2
        self._tf = transformer()
        g = self.geom
        self.polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]

    def to_px(self, x, y):
        return (self.ox + (np.asarray(x) - self.x0) * self.k,
                self.oy + (self.y1 - np.asarray(y)) * self.k)

    def lonlat(self, lon, lat):
        x, y = self._tf.transform(lon, lat)
        px, py = self.to_px(x, y)
        return float(px), float(py)

    @property
    def bounds(self):
        return self.x0, self.y0, self.x1, self.y1

    @property
    def centre_lonlat(self):
        return transformer(MAP_CRS, "EPSG:4326").transform((self.x0 + self.x1) / 2,
                                                           (self.y0 + self.y1) / 2)

    def mask(self, supersample=2):
        """Anti-aliased land mask the size of the sheet, values 0..1."""
        ss = supersample
        m = Image.new("L", (self.plate.w * ss, self.plate.h * ss), 0)
        d = ImageDraw.Draw(m)
        for p in self.polys:
            px, py = self.to_px(*p.exterior.xy)
            d.polygon(list(zip(px * ss, py * ss)), fill=255)
        return np.asarray(m.resize((self.plate.w, self.plate.h), Image.LANCZOS), dtype="float32") / 255

    def outline(self, opacity=0.2, width_mm=0.12):
        d = ImageDraw.Draw(self.plate.img)
        for p in self.polys:
            pts = list(zip(*self.to_px(*p.exterior.xy)))
            d.line(pts + [pts[0]], fill=self.plate.mix(opacity),
                   width=max(1, int(round(self.plate.px(width_mm)))))


def line_key(rows, widest_of=None):
    """Legend made of short line samples. rows: (name, rgb colour, width mm)."""
    def draw(d, right, top, pl):
        f_n = font("Barlow-500", pl.px(2.9))
        widest = max(text_width(n.upper(), f_n, 0.14) for n, _, _ in rows)
        x = right - widest
        for i, (name, colour, wd) in enumerate(rows):
            y = top + i * pl.px(5.6)
            d.line([(x - pl.px(13), y - pl.px(1.0)), (x - pl.px(4), y - pl.px(1.0))],
                   fill=colour, width=max(1, int(round(pl.px(wd)))))
            draw_text(d, (x, y), name.upper(), f_n, pl.mix(0.72), 0.14)
    return draw
