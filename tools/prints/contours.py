"""Contour studies: linework only, inside a neat line carrying UTM grid
ticks, the way a topographic sheet is framed.

    python contours.py longonot [dpi]             # plate 09
    python contours.py mount-kenya-summit [dpi]   # plate 15

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

from common import (DATA, MAP_CRS, Plate, annotate, draw_text, font, hex_rgb, line_key, load_dem,
                    name_label, transformer, warp_to_map)

BG = hex_rgb("#0b0d0c")
LINE = hex_rgb("#d9d6cc")
INDEX = hex_rgb("#aab590")
PT = 72 / 25.4

# labels: (name, figure, lon, lat, side, snap to the highest cell within this many metres)
STUDIES = {
    "longonot": dict(
        number="09", title="Longonot", subtitle="A contour study of the crater and its cone",
        centre=(36.441, -0.915), scale=20_000, interval=10, index=50,
        labels=[("Kilele Ngamia", "2 776 m", 36.43, -0.915, "left", 1500)], names=[]),
    "mount-kenya-summit": dict(
        number="15", title="Mount Kenya", subtitle="A contour study of the summit and its valleys",
        centre=(37.312, -0.152), scale=25_000, interval=20, index=100,
        labels=[("Batian", "5 199 m", 37.3083, -0.1517, "left", 400),
                ("Point Lenana", "4 985 m", 37.3186, -0.1550, "right", 300)],
        names=[("Teleki Valley", 37.283, -0.166, 0, 3.0), ("Mackinder Valley", 37.311, -0.118, 0, 3.0),
               ("Gorges Valley", 37.343, -0.160, 0, 3.0), ("Hobley Valley", 37.335, -0.186, 0, 3.0)]),
}


def main(name, dpi=150):
    cfg = STUDIES[name]
    interval, index_every, scale = cfg["interval"], cfg["index"], cfg["scale"]
    plate = Plate(dpi=dpi, bg=BG, block_mm=90)
    l, t, r, b = plate.map_box
    # the map fills its box exactly; shrink the box a little to make room for tick labels
    inset = plate.px(7)
    l, t, r, b = l + inset, t + inset, r - inset, b - inset
    m_per_px = scale / plate.px(1000)
    gw, gh = (r - l) * m_per_px, (b - t) * m_per_px
    tf = transformer()
    lon0, lat0 = cfg["centre"]
    cx, cy = tf.transform(lon0, lat0)
    x0, y0, x1, y1 = cx - gw / 2, cy - gh / 2, cx + gw / 2, cy + gh / 2

    dem, tr = load_dem((round(lon0 - 0.12, 3), round(lat0 - 0.12, 3),
                        round(lon0 + 0.12, 3), round(lat0 + 0.12, 3)), "glo30")
    cell = 10.0
    z, _ = warp_to_map(dem, tr, (x0 - 200, y0 - 200, x1 + 200, y1 + 200), cell, resampling="cubic")
    z = ndimage.gaussian_filter(z, 2.0)
    ny, nx = z.shape
    xs = (x0 - 200) + (np.arange(nx) + 0.5) * cell
    ys = (y1 + 200) - (np.arange(ny) + 0.5) * cell
    px = l + (xs - x0) / m_per_px
    py = t + (y1 - ys) / m_per_px
    print(f"{name}: grid {z.shape}, {z.min():.0f}-{z.max():.0f} m")

    fig = plt.figure(figsize=(plate.w / dpi, plate.h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, plate.w)
    ax.set_ylim(plate.h, 0)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    lo = np.floor(z.min() / interval) * interval
    levels = np.arange(lo, z.max() + interval, interval)
    minor = [v for v in levels if v % index_every]
    major = [v for v in levels if v % index_every == 0]
    rgb = lambda c, a=1.0: (*(np.array(c) / 255), a)
    ax.contour(px, py, z, levels=minor, colors=[rgb(LINE, 0.66)], linewidths=0.105 * PT)
    cs = ax.contour(px, py, z, levels=major, colors=[rgb(INDEX)], linewidths=0.27 * PT)
    mono = font_manager.FontProperties(fname=str(DATA / "fonts" / "IBMPlexMono-500.ttf"),
                                       size=2.15 * PT)
    for text in ax.clabel(cs, fmt=lambda v: f"{v:.0f}", inline=True,
                          inline_spacing=plate.px(1.2), fontsize=2.15 * PT, colors=[rgb(INDEX)]):
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

    def to_px(lon, lat, snap=0):
        x, y = tf.transform(lon, lat)
        if snap:  # move a summit label onto the highest cell nearby
            c0, r0, k = int((x - xs[0]) / cell), int((ys[0] - y) / cell), int(snap / cell)
            win = z[max(r0 - k, 0):r0 + k + 1, max(c0 - k, 0):c0 + k + 1]
            dr, dc = np.unravel_index(np.argmax(win), win.shape)
            x, y = xs[max(c0 - k, 0) + dc], ys[max(r0 - k, 0) + dr]
        return l + (x - x0) / m_per_px, t + (y1 - y) / m_per_px

    for text, lon, lat, angle, size in cfg["names"]:
        name_label(plate, to_px(lon, lat), text, hex_rgb("#e9e6dc"), BG, size_mm=size, angle=angle,
                   tracking=0.12)
    for label, value, lon, lat, side, snap in cfg["labels"]:
        annotate(plate, to_px(lon, lat, snap), label, value, side, on_dark=True)

    plate.title_block(
        cfg["title"], cfg["subtitle"], cfg["number"],
        facts=[("Scale at A2", f"1:{scale:,}".replace(",", " ")),
               ("Contour interval", f"{interval} m, index {index_every} m"),
               ("Grid", "UTM zone 37S, WGS 84")],
        credit="Contours interpolated from Copernicus DEM GLO-30 (© DLR / Airbus, provided under "
               "Copernicus by the EU and ESA). Drawn by ZeroPoint Geospatial. Not a ground survey.",
        centre=transformer(MAP_CRS, "EPSG:4326").transform(cx, cy),
        legend=line_key([(f"Index contour, {index_every} m", INDEX, 0.55),
                         (f"Contour, {interval} m", LINE, 0.22)]))
    slug = f"{name}-contours" if name == "longonot" else name
    path = plate.save(slug if dpi >= 250 else f"{slug}_{dpi}")
    print(path)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 150)
