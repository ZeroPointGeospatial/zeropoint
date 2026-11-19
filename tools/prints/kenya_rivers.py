"""Plate 02 - Kenya: rivers and drainage basins.

Draws the stream network computed by kenya_hydro.py. Line weight follows
upstream catchment area; colour follows the basin the water ends up in.

    python kenya_hydro.py          # once
    python kenya_rivers.py [dpi]   # 150 for a proof, 300 for the master
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFilter
from rasterio.transform import Affine

import hydro
from common import (CACHE, MAP_CRS, Plate, draw_text, font, hex_rgb, kenya,
                    transformer, warp_to_map)

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


def main(dpi=150):
    z = np.load(CACHE / "kenya_hydro.npz")
    plate = Plate(dpi=dpi, bg=BG, block_mm=90)
    ke = kenya(MAP_CRS)
    x0, y0, x1, y1 = ke.bounds
    scale = plate.px(1000) / SCALE_A2                # px per metre
    mw, mh = (x1 - x0) * scale, (y1 - y0) * scale
    l, t, r, b = plate.map_box
    box = (l + (r - l - mw) / 2, t + (b - t - mh) / 2,
           l + (r - l + mw) / 2, t + (b - t + mh) / 2)
    to_px = lambda x, y: (box[0] + (np.asarray(x) - x0) * scale,
                          box[1] + (y1 - np.asarray(y)) * scale)
    denom = SCALE_A2

    # --- land and standing water ------------------------------------------
    base = Image.new("RGB", plate.img.size, BG)
    d = ImageDraw.Draw(base)
    polys = list(ke.geoms) if ke.geom_type == "MultiPolygon" else [ke]
    for p in polys:
        d.polygon(list(zip(*to_px(*p.exterior.xy))), fill=LAND)

    shape = tuple(z["water_shape"])
    water = np.unpackbits(z["water"])[:shape[0] * shape[1]].reshape(shape).astype("float32")
    res = 1 / scale
    wmap, _ = warp_to_map(water, Affine(*z["transform"]), (x0, y0, x1, y1), res, nodata=-1)
    wmask = Image.fromarray((np.clip(wmap, 0, 1) * 255).astype("uint8"))
    land_mask = Image.new("L", plate.img.size, 0)
    dm = ImageDraw.Draw(land_mask)
    for p in polys:
        dm.polygon(list(zip(*to_px(*p.exterior.xy))), fill=255)
    wfull = Image.new("L", plate.img.size, 0)
    wfull.paste(wmask.resize((int(round(box[2] - box[0])), int(round(box[3] - box[1]))),
                             Image.LANCZOS), (int(round(box[0])), int(round(box[1]))))
    wfull = Image.fromarray(np.minimum(np.asarray(wfull), np.asarray(land_mask)))
    base.paste(Image.new("RGB", base.size, WATER), (0, 0), wfull)

    # --- streams ------------------------------------------------------------
    fig = plt.figure(figsize=(plate.w / dpi, plate.h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    xs, ys = to_px(z["x"], z["y"])
    offs, area, basin = z["offs"], z["area"], z["basin"]
    lo, hi = np.log10(float(z["threshold"])), np.log10(2.5e5)
    t = np.clip((np.log10(area) - lo) / (hi - lo), 0, 1)
    width_mm = 0.085 + 1.25 * t ** 1.75
    alpha = 0.50 + 0.50 * np.clip(t * 2.2, 0, 1)

    for key, _, colour in BASINS:
        sel = np.nonzero(basin == key)[0]
        sel = sel[np.argsort(area[sel])]             # big rivers drawn last
        segs, lw, cols = [], [], []
        rgb = np.array(hex_rgb(colour)) / 255
        for i in sel:
            a, b = offs[i], offs[i + 1]
            if b - a < 2:
                continue
            sx, sy = hydro.chaikin(xs[a:b].astype("float64"), ys[a:b].astype("float64"), 2)
            segs.append(np.column_stack([sx, sy]))
            lw.append(width_mm[i] * PT)
            cols.append((*rgb, alpha[i]))
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
    base = base.convert("RGBA")
    base.alpha_composite(Image.fromarray(ba.astype("uint8"), "RGBA"))
    base.alpha_composite(lines)
    plate.img = base.convert("RGB")

    # country outline, hairline
    d = ImageDraw.Draw(plate.img)
    for p in polys:
        pts = list(zip(*to_px(*p.exterior.xy)))
        d.line(pts + [pts[0]], fill=plate.mix(0.20), width=max(1, int(round(plate.px(0.12)))))

    def legend(d, right, top, pl):
        f_n = font("Barlow-500", pl.px(2.9))
        row = pl.px(5.6)
        widest = max(f_n.getlength(n.upper()) + 0.14 * f_n.size * (len(n) - 1) for _, n, _ in BASINS)
        x = right - widest
        for i, (_, name, colour) in enumerate(BASINS):
            y = top + i * row
            d.line([(x - pl.px(13), y - pl.px(1.0)), (x - pl.px(4), y - pl.px(1.0))],
                   fill=hex_rgb(colour), width=max(2, int(round(pl.px(0.7)))))
            draw_text(d, (x, y), name.upper(), f_n, pl.mix(0.72), 0.14)

    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lon, lat = transformer(MAP_CRS, "EPSG:4326").transform(cx, cy)
    plate.title_block(
        "Kenya", "Rivers and drainage basins", "02",
        facts=[("Scale at A2", f"1:{denom:,}".replace(",", " ")),
               ("Projection", "UTM zone 37S, WGS 84"),
               ("Stream threshold", f"{float(z['threshold']):.0f} km² catchment")],
        credit="Stream network derived by ZeroPoint Geospatial from Copernicus DEM GLO-90 "
               "(© DLR / Airbus, provided under Copernicus by the EU and ESA). "
               "Boundaries: Natural Earth.",
        centre=(lon, lat), legend=legend)
    path = plate.save("kenya-rivers" if dpi >= 250 else f"kenya-rivers_{dpi}")
    print(path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
