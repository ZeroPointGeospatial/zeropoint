"""City road prints in the gold-on-green design of the original Nairobi
print: the road network inside a circle, the city's name in a serif below,
its coordinates at the foot.

    python cities.py mombasa [width_px]
    python cities.py kisumu | nakuru | eldoret
    python cities.py spec:maps/example-kampala-gold.yml [width_px]   # any town (maps/README.md)

The layout, colours and proportions are measured from the existing Nairobi
file so new cities hang with it as one series. Format is 11 x 14 inches
(the same 0.79 ratio), 6744 x 8557 px by default.

    python fetch_overture.py roads   # once
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer

from common import CACHE, DATA, OUT, draw_text, font, hex_rgb, srgb_profile, text_width

BG = (11, 31, 20)
RING = (162, 143, 107)
TITLE = (200, 170, 130)
SOFT = (140, 126, 98)
RATIO = 4285 / 3384

# name, lon, lat, radius of the circle in km
CITIES = {
    "mombasa": ("Mombasa", 39.6650, -4.0500, 7.0),
    "kisumu": ("Kisumu", 34.7680, -0.0917, 5.5),
    "nakuru": ("Nakuru", 36.0800, -0.3031, 5.5),
    "eldoret": ("Eldoret", 35.2698, 0.5143, 5.5),
}
# road class (see fetch_overture.CLASSES) -> (width as a fraction of sheet width, colour)
STYLE = {
    5: (0.00042, "#4f4028"),      # service roads, tracks
    4: (0.00070, "#7c6644"),      # local streets
    3: (0.00135, "#9a8260"),      # tertiary
    2: (0.00210, "#a88e6a"),      # secondary
    1: (0.00360, "#c4a67e"),      # primary
    0: (0.00560, "#d3b795"),      # trunk and motorway
}


def dms(v, pos, neg):
    hemi = pos if v >= 0 else neg
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = int(round(((v - d) * 60 - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{d}°{m:02d}′{s:02d}″{hemi}"


def city_spec(path):
    """(key, name, lon, lat, radius km, country line, roads file) from a map spec.
    Roads outside Kenya are fetched for the circle the first time."""
    from pathlib import Path
    import yaml
    sp = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    c = sp["city"]
    key = sp["slug"].removesuffix("-gold")
    roads = CACHE / f"roads_{key}.npz"
    if c.get("country", "Kenya").lower() != "kenya" and not roads.exists():
        import fetch_overture
        import math
        pad = c["radius_km"] / 100 * 1.6                       # degrees of latitude, with room to spare
        pad_lon = pad / math.cos(math.radians(c["lat"]))       # degrees of longitude shrink away from the equator
        fetch_overture.roads(fetch_overture.latest_release(),
                             (c["lon"] - pad_lon, c["lat"] - pad, c["lon"] + pad_lon, c["lat"] + pad), f"roads_{key}")
    return (key, c["name"], c["lon"], c["lat"], c["radius_km"], c.get("country", "Kenya").upper(),
            roads if roads.exists() else CACHE / "kenya_roads.npz")


def main(key, width=6744):
    if key.startswith("spec:"):
        key, name, lon0, lat0, radius_km, country, roads_file = city_spec(key.split(":", 1)[1])
    else:
        (name, lon0, lat0, radius_km), country, roads_file = CITIES[key], "KENYA", CACHE / "kenya_roads.npz"
    w, h = width, int(round(width * RATIO))
    z = np.load(roads_file)
    xy, offs, code = z["xy"], z["offs"], z["code"]

    # an azimuthal projection centred on the city keeps the circle true
    tf = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84",
                              always_xy=True)
    pad = radius_km / 100
    pad_lon = pad / np.cos(np.radians(lat0))
    near = ((xy[:, 0] > lon0 - pad_lon) & (xy[:, 0] < lon0 + pad_lon)
            & (xy[:, 1] > lat0 - pad) & (xy[:, 1] < lat0 + pad))
    # keep every road with at least one vertex near the city, and project all
    # of its vertices, so a road that leaves the area is not bent back in
    touched = np.add.reduceat(near.astype("int32"), offs[:-1]) > 0
    whole = np.repeat(touched, np.diff(offs))
    X = np.zeros(len(xy))
    Y = np.zeros(len(xy))
    X[whole], Y[whole] = tf.transform(xy[whole, 0].astype("float64"), xy[whole, 1].astype("float64"))
    cx, cy, r = 0.5 * w, 0.3946 * h, 0.4665 * w
    k = r / (radius_km * 1000)                       # pixels per metre

    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")
    fig.patch.set_facecolor(np.array(BG) / 255)
    clip = plt.Circle((cx, cy), r, transform=ax.transData)
    for c in (5, 4, 3, 2, 1, 0):
        frac, colour = STYLE[c]
        idx = np.nonzero((code == c) & touched)[0]
        segs = [np.column_stack([cx + X[offs[i]:offs[i + 1]] * k, cy - Y[offs[i]:offs[i + 1]] * k])
                for i in idx]
        col = LineCollection(segs, linewidths=frac * w * 72 / 100, colors=[np.array(hex_rgb(colour)) / 255],
                             capstyle="round", joinstyle="round")
        col.set_clip_path(clip)
        ax.add_collection(col)
    ax.add_patch(plt.Circle((cx, cy), r, fill=False, lw=0.0009 * w * 72 / 100, ec=np.array(RING) / 255))
    fig.canvas.draw()
    img = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba(),
                           "raw", "RGBA", 0, 1).convert("RGB")
    plt.close(fig)

    # --- lettering, at the positions measured on the Nairobi print --------------
    d = ImageDraw.Draw(img)
    rule = max(2, int(round(0.0012 * h)))
    y = 0.8262 * h
    d.line([(0.287 * w, y), (0.39 * w, y)], fill=SOFT, width=rule)
    d.line([(0.61 * w, y), (0.713 * w, y)], fill=SOFT, width=rule)
    # title: scaled so its capitals are as tall as on the Nairobi print (0.0516 of the height)
    f_t = font("PlayfairDisplay-400", 0.0728 * h)
    while text_width(name.upper(), f_t, 0.02) > 0.62 * w:      # a long name must still fit
        f_t = font("PlayfairDisplay-400", f_t.size * 0.96)
    draw_text(d, (w / 2, 0.8973 * h), name.upper(), f_t, TITLE, 0.02, "ms")
    f_c = font("PlayfairDisplay-400", 0.0128 * h)
    draw_text(d, (w / 2, 0.9351 * h), country, f_c, SOFT, 1.05, "ms")
    y = 0.9627 * h
    d.line([(0.393 * w, y), (0.607 * w, y)], fill=tuple(int(v * 0.75) for v in SOFT), width=rule)
    mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                              int(round(0.0086 * h)))
    coords = f"{dms(lat0, 'N', 'S')}    {dms(lon0, 'E', 'W')}"
    d.text((w / 2, 0.9897 * h), coords, font=mono, fill=tuple(int(v * 0.8) for v in SOFT), anchor="ms")

    # the road data is OpenStreetMap's, whose licence asks for a visible credit
    f_s = font("Barlow-500", 0.0046 * h)
    dim = tuple(int(v * 0.62) for v in SOFT)
    draw_text(d, (0.033 * w, 0.9897 * h), "\u00a9 OPENSTREETMAP CONTRIBUTORS", f_s, dim, 0.16)
    draw_text(d, (0.967 * w, 0.9897 * h), "ZEROPOINT GEOSPATIAL", f_s, dim, 0.16, "rs")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (f"{key}-gold.png" if width >= 5000 else f"{key}-gold_{width}.png")
    img.save(path, dpi=(width / 22, width / 22), icc_profile=srgb_profile())
    print(path, img.size)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 6744)
