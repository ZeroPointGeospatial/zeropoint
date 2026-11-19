"""Plate 04 - Kenya: every mapped road.

Minor roads and tracks are accumulated into a density layer (brightness =
length of road per pixel), so towns glow and empty country stays dark. The
classified network, trunk to tertiary, is drawn over it as crisp lines.

    python fetch_overture.py roads   # once
    python kenya_roads.py [dpi]
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from numba import njit, prange
from PIL import Image, ImageDraw, ImageFilter

from common import (CACHE, KenyaFrame, Plate, annotate, apply_ramp, hex_rgb, line_key, ramp,
                    transformer)

BG = hex_rgb("#0b1f14")             # the deep green of the Nairobi Gold prints
GOLD = "#d3b795"
SCALE_A2 = 2_400_000
PT = 72 / 25.4

# class code -> (line width mm at A2, colour, opacity); see fetch_roads.CLASSES
MAJOR = {
    3: (0.10, "#a8906c", 0.80),     # tertiary
    2: (0.16, "#c4a880", 0.90),     # secondary
    1: (0.26, "#dfc9a4", 1.00),     # primary
    0: (0.42, "#f6ead2", 1.00),     # motorway and trunk
}
DENSITY_RAMP = ramp([(0.0, "#0b1f14"), (0.25, "#2b3a26"), (0.55, "#6f6a4a"),
                     (0.82, "#b89c76"), (1.0, "#e9d6b3")])

# name, lon, lat, side of the dot the name sits on
TOWNS = [
    ("Nairobi", 36.817, -1.286, "right"), ("Mombasa", 39.664, -4.043, "right"),
    ("Kisumu", 34.754, -0.092, "left"), ("Nakuru", 36.070, -0.283, "left"),
    ("Eldoret", 35.270, 0.520, "left"), ("Kitale", 35.006, 1.016, "left"),
    ("Nanyuki", 37.073, 0.017, "left"), ("Meru", 37.650, 0.047, "right"),
    ("Garissa", 39.646, -0.456, "right"), ("Malindi", 40.117, -3.218, "right"),
    ("Lamu", 40.902, -2.271, "right"), ("Voi", 38.567, -3.396, "left"),
    ("Namanga", 36.787, -2.545, "left"), ("Marsabit", 37.990, 2.335, "right"),
    ("Moyale", 39.056, 3.521, "right"), ("Mandera", 41.855, 3.937, "left"),
    ("Wajir", 40.057, 1.747, "right"), ("Lodwar", 35.597, 3.119, "left"),
    ("Narok", 35.871, -1.078, "left"), ("Kisii", 34.767, -0.681, "left"),
    ("Kitui", 38.012, -1.367, "right"), ("Isiolo", 37.582, 0.354, "right"),
    ("Kakuma", 34.852, 3.713, "left"), ("Busia", 34.111, 0.460, "left"),
]


@njit(cache=True, parallel=False)
def accumulate(px, py, offs, sel, out, weight):
    """Add road length (in pixels) to `out`, splatting bilinearly along each line."""
    h, w = out.shape
    for li in sel:
        for k in range(offs[li], offs[li + 1] - 1):
            x0, y0, x1, y1 = px[k], py[k], px[k + 1], py[k + 1]
            length = np.hypot(x1 - x0, y1 - y0)
            n = max(1, int(np.ceil(length * 2.0)))
            step = length / n * weight
            for s in range(n):
                t = (s + 0.5) / n
                x, y = x0 + (x1 - x0) * t - 0.5, y0 + (y1 - y0) * t - 0.5
                ix, iy = int(np.floor(x)), int(np.floor(y))
                if ix < 0 or iy < 0 or ix >= w - 1 or iy >= h - 1:
                    continue
                fx, fy = x - ix, y - iy
                out[iy, ix] += step * (1 - fx) * (1 - fy)
                out[iy, ix + 1] += step * fx * (1 - fy)
                out[iy + 1, ix] += step * (1 - fx) * fy
                out[iy + 1, ix + 1] += step * fx * fy


def main(dpi=150):
    z = np.load(CACHE / "kenya_roads.npz")
    xy, offs, code = z["xy"], z["offs"], z["code"]
    plate = Plate(dpi=dpi, bg=BG, fg=hex_rgb("#efe6d2"), accent=hex_rgb(GOLD), block_mm=90)
    f = KenyaFrame(plate, SCALE_A2)
    X, Y = transformer().transform(xy[:, 0].astype("float64"), xy[:, 1].astype("float64"))
    px, py = f.to_px(X, Y)
    px, py = px.astype("float32"), py.astype("float32")
    m = f.mask()

    # --- density of minor roads and tracks -------------------------------
    dens = np.zeros((plate.h, plate.w), dtype="float32")
    accumulate(px, py, offs, np.nonzero(code == 4)[0], dens, 1.0)
    accumulate(px, py, offs, np.nonzero(code == 5)[0], dens, 0.7)
    total = np.zeros_like(dens)
    accumulate(px, py, offs, np.arange(len(code)), total, 1.0)
    km = float((total * m).sum() / f.k / 1000)
    print(f"mapped length inside Kenya: {km:,.0f} km")
    # road length per pixel is resolution dependent; normalise to the 150 dpi proof
    dens *= 150.0 / dpi
    tone = 1.0 - np.exp(-dens * 0.55)
    tone = np.power(tone, 0.80) * m
    rgb = apply_ramp(tone, DENSITY_RAMP)
    plate.img = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype("uint8"))

    # --- classified network as lines ----------------------------------------
    fig = plt.figure(figsize=(plate.w / dpi, plate.h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    for c in (3, 2, 1, 0):
        width, colour, alpha = MAJOR[c]
        idx = np.nonzero(code == c)[0]
        segs = [np.column_stack([px[offs[i]:offs[i + 1]], py[offs[i]:offs[i + 1]]]) for i in idx]
        ax.add_collection(LineCollection(
            segs, linewidths=width * PT, colors=[(*(np.array(hex_rgb(colour)) / 255), alpha)],
            capstyle="round", joinstyle="round"))
    fig.canvas.draw()
    lines = Image.frombuffer("RGBA", fig.canvas.get_width_height(),
                             fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1).copy()
    plt.close(fig)
    la = np.asarray(lines, dtype="float32")
    la[..., 3] *= m
    lines = Image.fromarray(la.astype("uint8"), "RGBA")
    bloom = lines.filter(ImageFilter.GaussianBlur(plate.px(0.7)))
    ba = np.asarray(bloom, dtype="float32")
    ba[..., 3] *= 0.35
    base = plate.img.convert("RGBA")
    base.alpha_composite(Image.fromarray(ba.astype("uint8"), "RGBA"))
    base.alpha_composite(lines)
    plate.img = base.convert("RGB")
    f.outline(0.22)

    for name, lon, lat, side in TOWNS:
        annotate(plate, f.lonlat(lon, lat), name, None, side, size_mm=2.6,
                 ink=hex_rgb("#f6ead2"), halo=BG)

    rows = [("Trunk and motorway", hex_rgb(MAJOR[0][1]), MAJOR[0][0] * 2.2),
            ("Primary", hex_rgb(MAJOR[1][1]), MAJOR[1][0] * 2.2),
            ("Secondary", hex_rgb(MAJOR[2][1]), MAJOR[2][0] * 2.2),
            ("Tertiary", hex_rgb(MAJOR[3][1]), MAJOR[3][0] * 2.2),
            ("Local roads and tracks", hex_rgb("#6f6a4a"), 0.5)]
    plate.title_block(
        "Kenya", "Every mapped road and track", "04",
        facts=[("Scale at A2", f"1:{SCALE_A2:,}".replace(",", " ")),
               ("Mapped length", f"{round(km, -3):,.0f} km".replace(",", " ")),
               ("Projection", "UTM zone 37S, WGS 84")],
        credit="Roads: \u00a9 OpenStreetMap contributors, via Overture Maps "
               f"{str(z['release'])} (ODbL). Boundaries: Natural Earth. "
               "Cartography by ZeroPoint Geospatial.",
        centre=f.centre_lonlat, legend=line_key(rows))
    path = plate.save("kenya-roads" if dpi >= 250 else f"kenya-roads_{dpi}")
    print(path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
