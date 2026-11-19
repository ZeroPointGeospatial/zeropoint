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


class Plate:
    """An A2 portrait sheet with the ZeroPoint title block along the foot.

    The map goes in `self.map_box` (pixels). Call `title_block(...)` last.
    """

    def __init__(self, dpi=150, bg=INK, fg=PAPER, accent=OLIVE_LIGHT, block_mm=92.0):
        self.dpi = dpi
        self.bg, self.fg, self.accent = bg, fg, accent
        self.w = int(round(mm(SHEET_MM[0], dpi)))
        self.h = int(round(mm(SHEET_MM[1], dpi)))
        self.img = Image.new("RGB", (self.w, self.h), bg)
        m = mm(MARGIN_MM, dpi)
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
                    legend=None):
        """Draw the foot of the sheet.

        title     e.g. "Kenya"
        subtitle  e.g. "Rivers and drainage basins"
        number    plate number, e.g. "02"
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
        draw_text(d, (left, y), f"PLATE {number}", f_label, self.accent, 0.22)
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
        f_k = font("Barlow-500", px(2.25))
        f_v = font("IBMPlexMono-400", px(2.55))
        x = left
        cells = list(facts)
        if centre is not None:
            cells.append(("Sheet centre", coord_label(*centre)))
        col = (right - left) / max(len(cells), 1)
        for k, v in cells:
            draw_text(d, (x, y_rule + px(7.0)), k.upper(), f_k, faint, 0.2)
            draw_text(d, (x, y_rule + px(12.2)), v, f_v, soft, 0.0)
            x += col

        # credit line at the very foot
        f_c = font("Barlow-400", px(2.25))
        y_c = self.h - m
        draw_text(d, (left, y_c), credit, f_c, faint, 0.04)
        draw_text(d, (right, y_c), "zeropointgeospatial · Nairobi, Kenya", f_c, faint,
                  0.04, anchor="rs")
        return self

    def save(self, name, quality=92):
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"{name}.png"
        self.img.save(path, optimize=False, dpi=(self.dpi, self.dpi))
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


def annotate(plate, xy, name, value=None, side="right", on_dark=False):
    """A spot label: a dot, the name in caps and an optional figure in mono,
    over a soft halo so it reads on any terrain colour."""
    x, y = xy
    ink = (250, 249, 244) if on_dark else (18, 20, 19)
    halo = (14, 16, 15) if on_dark else (250, 249, 244)
    f_n = font("Barlow-600", plate.px(2.9))
    f_v = font("IBMPlexMono-500", plate.px(2.5))
    r = plate.px(0.6)
    off = plate.px(2.8) * (1 if side == "right" else -1)
    anchor = "ls" if side == "right" else "rs"
    ty = y + plate.px(1.0)
    vy = ty + plate.px(3.7)

    def paint(d, colour):
        d.ellipse([x - r, y - r, x + r, y + r], fill=colour)
        draw_text(d, (x + off, ty), name.upper(), f_n, colour, 0.14, anchor)
        if value:
            draw_text(d, (x + off, vy), value, f_v, colour, 0, anchor)

    pad = int(plate.px(60))
    x0, y0 = int(x) - pad, int(y) - pad
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(int(x) + pad, plate.w), min(int(y) + pad, plate.h)
    glow = Image.new("L", plate.img.size, 0)
    paint(ImageDraw.Draw(glow), 255)
    patch = glow.crop((x0, y0, x1, y1))
    patch = patch.filter(ImageFilter.MaxFilter(2 * int(max(1, plate.px(0.35))) + 1))
    patch = patch.filter(ImageFilter.GaussianBlur(plate.px(0.7)))
    patch = patch.point(lambda v: min(255, int(v * 1.5 * 0.62)))
    plate.img.paste(Image.new("RGB", patch.size, halo), (x0, y0), patch)
    paint(ImageDraw.Draw(plate.img), ink)
