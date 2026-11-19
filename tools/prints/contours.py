"""Plate 09 - Mount Longonot: a contour study.

Linework only: contours at 20 m with index contours every 100 m, inside a
neat line carrying UTM grid ticks, the way a topographic sheet is framed.

    python contours.py [dpi]

The contours are interpolated from the 30 m Copernicus surface model. They
are a drawing of the mountain's form, not a substitute for a ground survey.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw
from scipy import ndimage

from common import (DATA, MAP_CRS, Plate, annotate, draw_text, font, hex_rgb, load_dem,
                    transformer, warp_to_map)

BG = hex_rgb("#0b0d0c")
LINE = hex_rgb("#d9d6cc")
INDEX = hex_rgb("#aab590")
CENTRE = (36.440, -0.916)            # Mount Longonot
SCALE_A2 = 25_000
INTERVAL, INDEX_EVERY = 20, 100
PT = 72 / 25.4


def main(dpi=150):
    plate = Plate(dpi=dpi, bg=BG, block_mm=90)
    l, t, r, b = plate.map_box
    # the map fills its box exactly; shrink the box a little to make room for tick labels
    inset = plate.px(7)
    l, t, r, b = l + inset, t + inset, r - inset, b - inset
    m_per_px = SCALE_A2 / plate.px(1000)
    gw, gh = (r - l) * m_per_px, (b - t) * m_per_px
    tf = transformer()
    cx, cy = tf.transform(*CENTRE)
    x0, y0, x1, y1 = cx - gw / 2, cy - gh / 2, cx + gw / 2, cy + gh / 2

    dem, tr = load_dem((CENTRE[0] - 0.12, CENTRE[1] - 0.12, CENTRE[0] + 0.12, CENTRE[1] + 0.12),
                       "glo30")
    cell = 10.0
    z, _ = warp_to_map(dem, tr, (x0 - 200, y0 - 200, x1 + 200, y1 + 200), cell, resampling="cubic")
    z = ndimage.gaussian_filter(z, 2.2)
    ny, nx = z.shape
    xs = (x0 - 200) + (np.arange(nx) + 0.5) * cell
    ys = (y1 + 200) - (np.arange(ny) + 0.5) * cell
    px = l + (xs - x0) / m_per_px
    py = t + (y1 - ys) / m_per_px
    print(f"grid {z.shape}, {z.min():.0f}-{z.max():.0f} m")

    fig = plt.figure(figsize=(plate.w / dpi, plate.h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    lo = np.floor(z.min() / INTERVAL) * INTERVAL
    levels = np.arange(lo, z.max() + INTERVAL, INTERVAL)
    minor = [v for v in levels if v % INDEX_EVERY]
    major = [v for v in levels if v % INDEX_EVERY == 0]
    rgb = lambda c, a=1.0: (*(np.array(c) / 255), a)
    ax.contour(px, py, z, levels=minor, colors=[rgb(LINE, 0.62)], linewidths=0.085 * PT)
    cs = ax.contour(px, py, z, levels=major, colors=[rgb(INDEX)], linewidths=0.22 * PT)
    mono = font_manager.FontProperties(fname=str(DATA / "fonts" / "IBMPlexMono-500.ttf"),
                                       size=2.05 * PT)
    for text in ax.clabel(cs, fmt=lambda v: f"{v:.0f}", inline=True,
                          inline_spacing=plate.px(1.2), fontsize=2.05 * PT, colors=[rgb(INDEX)]):
        text.set_fontproperties(mono)
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    fig.canvas.draw()
    lines = Image.frombuffer("RGBA", fig.canvas.get_width_height(),
                             fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1).copy()
    plt.close(fig)

    # keep only what falls inside the neat line
    clip = Image.new("L", plate.img.size, 0)
    ImageDraw.Draw(clip).rectangle([l, t, r, b], fill=255)
    la = np.asarray(lines).copy()
    la[..., 3] = (la[..., 3].astype("float32") * (np.asarray(clip) / 255)).astype("uint8")
    base = plate.img.convert("RGBA")
    base.alpha_composite(Image.fromarray(la, "RGBA"))
    plate.img = base.convert("RGB")

    # neat line with UTM ticks every 1 km, figures every 2 km
    d = ImageDraw.Draw(plate.img)
    wline = max(1, int(round(plate.px(0.2))))
    d.rectangle([l, t, r, b], outline=plate.mix(0.75), width=wline)
    f_t = font("IBMPlexMono-400", plate.px(2.1))
    tick = plate.px(1.6)
    for e in np.arange(np.ceil(x0 / 1000) * 1000, x1, 1000):
        x = l + (e - x0) / m_per_px
        for yy, sgn in ((t, -1), (b, 1)):
            d.line([(x, yy), (x, yy + sgn * tick)], fill=plate.mix(0.75), width=wline)
        if int(e / 1000) % 2 == 0:
            draw_text(d, (x, t - plate.px(3.0)), f"{int(e / 1000)} km E", f_t, plate.mix(0.5), 0, "ms")
    for n in np.arange(np.ceil(y0 / 1000) * 1000, y1, 1000):
        y = t + (y1 - n) / m_per_px
        for xx, sgn in ((l, -1), (r, 1)):
            d.line([(xx, y), (xx + sgn * tick, y)], fill=plate.mix(0.75), width=wline)
        if int(n / 1000) % 2 == 0:
            label = Image.new("RGBA", (int(plate.px(30)), int(plate.px(4))), (0, 0, 0, 0))
            draw_text(ImageDraw.Draw(label), (label.width / 2, label.height * 0.78),
                      f"{int(n / 1000)} km N", f_t, plate.mix(0.5) + (255,), 0, "ms")
            label = label.rotate(90, expand=True)
            plate.img.paste(label, (int(l - plate.px(5.2)), int(y - label.height / 2)), label)

    # summit spot height: highest cell on the crater rim
    ry, rx = np.unravel_index(np.argmax(z), z.shape)
    annotate(plate, (px[rx], py[ry]), "Kilele Ngamia", "2 776 m", "right", on_dark=True)

    lon, lat = transformer(MAP_CRS, "EPSG:4326").transform(cx, cy)

    def legend(d, right, top, pl):
        f_n = font("Barlow-500", pl.px(2.9))
        rows = [(f"Index contour, {INDEX_EVERY} m", INDEX, 0.55), (f"Contour, {INTERVAL} m", LINE, 0.22)]
        widest = max(f_n.getlength(n.upper()) + 0.14 * f_n.size * (len(n) - 1) for n, _, _ in rows)
        x = right - widest
        for i, (name, colour, wd) in enumerate(rows):
            y = top + i * pl.px(5.6)
            d.line([(x - pl.px(13), y - pl.px(1.0)), (x - pl.px(4), y - pl.px(1.0))],
                   fill=colour, width=max(1, int(round(pl.px(wd)))))
            draw_text(d, (x, y), name.upper(), f_n, pl.mix(0.72), 0.14)

    plate.title_block(
        "Longonot", "A contour study of the crater and its cone", "09",
        facts=[("Scale at A2", f"1:{SCALE_A2:,}".replace(",", " ")),
               ("Contour interval", f"{INTERVAL} m, index {INDEX_EVERY} m"),
               ("Grid", "UTM zone 37S, WGS 84")],
        credit="Contours interpolated from Copernicus DEM GLO-30 (© DLR / Airbus, provided under "
               "Copernicus by the EU and ESA). Drawn by ZeroPoint Geospatial. Not a ground survey.",
        centre=(lon, lat), legend=legend)
    path = plate.save("longonot-contours" if dpi >= 250 else f"longonot-contours_{dpi}")
    print(path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
