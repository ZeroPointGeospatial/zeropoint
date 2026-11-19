"""Plate 02 - Kenya: rivers and drainage basins.

Draws the stream network computed by kenya_hydro.py. Line weight follows
the estimated mean flow of each reach (rainfall-driven runoff accumulated
downstream), so a channel crossing dry country stays thin however large its
catchment. Colour follows the basin the water ends up in.

    python kenya_hydro.py          # once
    python kenya_rivers.py [dpi]   # 150 for a proof, 300 for the master
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image, ImageFilter
from rasterio.transform import Affine

import hydro
from common import CACHE, KenyaFrame, Plate, hex_rgb, line_key, name_label, warp_to_map

BASINS = [
    # key, name, colour
    (1, "Lake Victoria", "#5aa9d6"),
    (2, "Rift Valley", "#efc55f"),
    (3, "Athi", "#e8735a"),
    (4, "Tana", "#63c3a4"),
    (5, "Ewaso Ng’iro North", "#cdbdf0"),
]
BG = hex_rgb("#0a0c0b")
LAND = hex_rgb("#0f1311")
WATER = hex_rgb("#1a2a33")
PT = 72 / 25.4                      # points per millimetre
SCALE_A2 = 2_400_000                # 1:2 400 000 at A2, 1:1 200 000 at A0
Q_MIN, Q_MAX = 0.03, 250.0          # m3/s: the flows mapped to the thinnest and widest line

# name, lon, lat, rotation in degrees (anticlockwise), basin key for the colour
RIVERS = [
    ("Tana", 38.98, -0.02, -6, 4),
    ("Tana", 40.33, -1.55, 0, 4),
    ("Athi", 37.92, -2.03, 0, 3),
    ("Galana", 39.25, -2.93, -6, 3),
    ("Ewaso Ng’iro", 38.45, 1.22, 9, 5),
    ("Turkwel", 35.08, 2.55, 0, 2),
    ("Kerio", 35.93, 2.46, 0, 2),
    ("Suguta", 36.64, 1.77, 0, 2),
    ("Nzoia", 34.72, 0.72, 0, 1),
    ("Mara", 35.42, -1.18, 0, 1),
    ("Daua", 41.25, 3.80, -4, 5),
]
LAKES = [("Lake Turkana", 36.62, 3.55, 0), ("Lake Victoria", 34.38, -0.72, 0)]


def main(dpi=150):
    z = np.load(CACHE / "kenya_hydro.npz")
    plate = Plate(dpi=dpi, bg=BG, block_mm=90)
    f = KenyaFrame(plate, SCALE_A2)

    # --- land and standing water ------------------------------------------
    land = f.mask()
    shape = tuple(z["water_shape"])
    water = np.unpackbits(z["water"])[:shape[0] * shape[1]].reshape(shape).astype("float32")
    wmap, _ = warp_to_map(water, Affine(*z["transform"]), f.bounds, 1 / f.k, nodata=-1)
    wfull = np.zeros((plate.h, plate.w), "float32")
    wm = np.asarray(Image.fromarray(np.clip(wmap, 0, 1)).resize(
        (int(round(f.w)), int(round(f.h))), Image.LANCZOS))
    oy, ox = int(round(f.oy)), int(round(f.ox))
    wfull[oy:oy + wm.shape[0], ox:ox + wm.shape[1]] = wm
    wfull = np.minimum(wfull, land)[..., None]
    rgb = (np.array(BG) * (1 - land[..., None]) + np.array(LAND) * land[..., None])
    rgb = rgb * (1 - wfull) + np.array(WATER) * wfull
    base = Image.fromarray(rgb.astype("uint8")).convert("RGBA")

    # --- streams ------------------------------------------------------------
    fig = plt.figure(figsize=(plate.w / dpi, plate.h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    xs, ys = f.to_px(z["x"], z["y"])
    offs, flow, basin = z["offs"], z["flow"], z["basin"]
    t = np.clip((np.log10(np.maximum(flow, Q_MIN)) - np.log10(Q_MIN))
                / (np.log10(Q_MAX) - np.log10(Q_MIN)), 0, 1)
    width_mm = 0.075 + 1.30 * t ** 1.9
    alpha = 0.34 + 0.66 * np.clip(t * 2.4, 0, 1)

    for key, _, colour in BASINS:
        sel = np.nonzero(basin == key)[0]
        sel = sel[np.argsort(flow[sel])]             # big rivers drawn last
        segs, lw, cols = [], [], []
        c = np.array(hex_rgb(colour)) / 255
        for i in sel:
            a, b = offs[i], offs[i + 1]
            if b - a < 2:
                continue
            sx, sy = hydro.chaikin(xs[a:b].astype("float64"), ys[a:b].astype("float64"), 2)
            segs.append(np.column_stack([sx, sy]))
            lw.append(width_mm[i] * PT)
            cols.append((*c, alpha[i]))
        ax.add_collection(LineCollection(segs, linewidths=lw, colors=cols,
                                         capstyle="round", joinstyle="round"))
    fig.canvas.draw()
    lines = Image.frombuffer("RGBA", fig.canvas.get_width_height(),
                             fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1).copy()
    plt.close(fig)

    # soft bloom under the main stems, then the crisp lines
    bloom = lines.filter(ImageFilter.GaussianBlur(plate.px(0.9)))
    ba = np.asarray(bloom, dtype="float32")
    ba[..., 3] *= 0.42
    base.alpha_composite(Image.fromarray(ba.astype("uint8"), "RGBA"))
    base.alpha_composite(lines)
    plate.img = base.convert("RGB")
    f.outline()

    # --- names --------------------------------------------------------------
    colour_of = {k: hex_rgb(c) for k, _, c in BASINS}
    for name, lon, lat, angle, key in RIVERS:
        tint = tuple(int(v * 0.55 + 255 * 0.45) for v in colour_of[key])
        name_label(plate, f.lonlat(lon, lat), name, tint, BG, size_mm=3.3, angle=angle)
    for name, lon, lat, angle in LAKES:
        name_label(plate, f.lonlat(lon, lat), name, (150, 176, 190), BG, size_mm=3.0, angle=angle)

    plate.title_block(
        "Kenya", "Rivers and drainage basins", "02",
        facts=[("Scale at A2", f"1:{SCALE_A2:,}".replace(",", " ")),
               ("Line weight", "estimated mean flow"),
               ("Stream threshold", f"{float(z['threshold']):.0f} km² catchment")],
        credit="Streams derived by ZeroPoint Geospatial from Copernicus DEM GLO-90 (© DLR / Airbus, "
               "provided under Copernicus by the EU and ESA). Runoff from CHIRPS rainfall 1991–2020. "
               "Boundaries: Natural Earth.",
        centre=f.centre_lonlat,
        legend=line_key([(n, hex_rgb(c), 0.7) for _, n, c in BASINS]))
    path = plate.save("kenya-rivers" if dpi >= 250 else f"kenya-rivers_{dpi}")
    print(path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
