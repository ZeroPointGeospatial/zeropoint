"""Build the website's images from their sources.

    python tools/site_assets.py            # photos, logo mark, textures, print previews

Run from the repository root. Print masters are read from $ZP_OUT (the nine
plates rendered by tools/prints) and from originals/prints/ (the three
Nairobi prints); photos and the logo come from originals/. Nothing here is needed to build the site itself: the outputs in
assets/ are committed.
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent / "prints"))
Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "assets" / "img"
PRINTS = ROOT / "assets" / "prints"
MASTERS = Path(os.environ.get("ZP_OUT", ROOT / "tools" / "prints" / "out"))
ORIGINALS = ROOT / "originals"

PLATES = ["kenya-population", "kenya-rivers", "kenya-relief", "kenya-roads", "kenya-forest",
          "mount-kenya", "kilimanjaro", "rift-valley", "longonot-contours"]
MASTER_NAME = {"kenya-relief": "kenya"}                 # plate slug -> master file stem
OWN_PRINTS = ["nairobi-gold", "nairobi-gold-centre", "nairobi-county-population"]
INK, PAPER, PAPER2 = (11, 13, 12), (241, 240, 235), (232, 231, 225)


def webp(im, path, quality=80):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path, "WEBP", quality=quality, method=6)
    return path.stat().st_size


def fit_width(im, w):
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def cover(im, w, h, focus=(0.5, 0.5)):
    """Crop to w x h, keeping the point `focus` (fractions of the source) in frame."""
    s = max(w / im.width, h / im.height)
    r = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = min(max(round(r.width * focus[0] - w / 2), 0), r.width - w)
    y = min(max(round(r.height * focus[1] - h / 2), 0), r.height - h)
    return r.crop((x, y, x + w, y + h))


def master(slug):
    if slug in OWN_PRINTS:
        return Image.open(ORIGINALS / "prints" / f"{slug}.png").convert("RGB")
    stem = MASTER_NAME.get(slug, slug)
    for name in (f"{stem}.png", f"{stem}_150.png", f"{stem}_100.png"):   # master, else a proof
        if (MASTERS / name).exists():
            if name != f"{stem}.png":
                print(f"  note: using proof {name} for {slug}")
            return Image.open(MASTERS / name).convert("RGB")
    raise FileNotFoundError(stem)


def photos():
    a = ORIGINALS / "photos"
    field = Image.open(a / "rtk-base-station-field.jpg")
    # the phone's watermark sits in the bottom-left corner: crop above it
    webp(field.crop((0, 230, 720, 1190)), IMG / "hero-field.webp", 64)
    webp(cover(field.crop((0, 150, 720, 1300)), 900, 600, (0.5, 0.42)), IMG / "rtk-field.webp", 68)
    webp(cover(Image.open(a / "boundary.jpg"), 900, 600, (0.5, 0.36)), IMG / "total-station.webp", 78)
    webp(cover(Image.open(a / "control.jpg"), 900, 600, (0.5, 0.45)), IMG / "construction.webp", 78)
    webp(cover(Image.open(a / "plans.jpg"), 900, 600), IMG / "plans.webp", 78)


def logo():
    src = Image.open(ORIGINALS / "brand" / "logo.webp").convert("RGB")
    em = src.crop((180, 6, 646, 372))                    # the compass emblem
    edge = np.concatenate([np.asarray(em)[0], np.asarray(em)[-1]])
    bg = tuple(int(v) for v in np.median(edge, 0))
    side = max(em.size) + 36
    sq = Image.new("RGB", (side, side), bg)
    sq.paste(em, ((side - em.width) // 2, (side - em.height) // 2))
    webp(sq.resize((160, 160), Image.LANCZOS), IMG / "logo-mark.webp", 88)
    sq.resize((96, 96), Image.LANCZOS).save(IMG / "favicon.png", optimize=True)


def textures():
    """Contour lines around Mount Kenya, as a quiet background for page heads."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import ndimage
    from common import load_dem, transformer, warp_to_map
    dem, tr = load_dem((36.8, -0.7, 37.9, 0.4), "glo30")
    cx, cy = transformer().transform(37.36, -0.15)
    w, h = 1280, 784
    res = 47.0
    z, _ = warp_to_map(dem, tr, (cx - w * res / 2, cy - h * res / 2, cx + w * res / 2, cy + h * res / 2),
                       res, resampling="cubic")
    z = ndimage.gaussian_filter(z, 1.6)
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    fig.patch.set_facecolor("#0b0d0c")
    levels = np.arange(1000, 5300, 50)
    ax.contour(z[::-1], levels=[v for v in levels if v % 250], colors=["#aab590"],
               linewidths=0.5, alpha=0.55)
    ax.contour(z[::-1], levels=[v for v in levels if v % 250 == 0], colors=["#aab590"],
               linewidths=1.0, alpha=0.8)
    fig.canvas.draw()
    im = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba(),
                          "raw", "RGBA", 0, 1).convert("RGB")
    plt.close(fig)
    webp(im, IMG / "contours.webp", 40)


def project_crops():
    """Two project cards are illustrated with our own cartography."""
    c = master("longonot-contours")
    w, h = c.size
    webp(cover(c.crop((int(w * 0.2), int(h * 0.22), int(w * 0.8), int(h * 0.56))), 900, 600),
         IMG / "topo-contours.webp", 80)
    r = master("kenya-roads")
    webp(cover(r.crop((int(w * 0.22), int(h * 0.36), int(w * 0.62), int(h * 0.55))), 900, 600),
         IMG / "gis.webp", 80)


def print_previews():
    """640, 1280 and 2000 px wide previews of every print, plus their sizes."""
    lines = ["# Pixel sizes of the print previews in assets/prints/.",
             "# Written by tools/site_assets.py; do not edit by hand."]
    for slug in PLATES + OWN_PRINTS:
        try:
            im = master(slug)
        except FileNotFoundError:
            print(f"  missing master for {slug}, skipped")
            continue
        dims = {}
        for w, q in ((640, 82), (1280, 80), (2000, 76)):
            out = fit_width(im, w)
            kb = webp(out, PRINTS / f"{slug}-{w}.webp", q) / 1024
            dims[w] = out.size
            print(f"  {slug}-{w}.webp  {out.size[0]}x{out.size[1]}  {kb:.0f} KB")
        lines.append(f"{slug}: {{ w: {dims[640][0]}, h: {dims[640][1]}, "
                     f"w2000: {dims[2000][0]}, h2000: {dims[2000][1]} }}")
        share_card(slug, im)
    (ROOT / "_data" / "print_images.yml").write_text("\n".join(lines) + "\n")


def hang(canvas, im, x, y, h, frame=(20, 22, 21)):
    """Paste a framed print with a soft shadow; (x, y) is its top-left corner."""
    w = round(im.width * h / im.height)
    pic = im.resize((w, h), Image.LANCZOS)
    b = max(4, round(h * 0.022))
    framed = Image.new("RGB", (w + 2 * b, h + 2 * b), frame)
    framed.paste(pic, (b, b))
    sh = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(sh).rectangle([x + 6, y + 14, x + framed.width + 6, y + framed.height + 18], fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), sh)
    canvas.paste(framed, (x, y))
    return framed.width


def share_card(slug, im):
    """1200 x 630 social preview for one print."""
    card = Image.new("RGB", (1200, 630), PAPER2)
    h = 540
    w = round(im.width * h / im.height) + 2 * round(h * 0.022)
    hang(card, im, (1200 - w) // 2, 34, h)
    card.save(PRINTS / f"{slug}-share.jpg", quality=84, optimize=True)


def share_site():
    """1200 x 630 social previews for the site and for the shop."""
    from common import draw_text, font
    for name, slugs in (("og-prints", ["kenya-rivers", "kenya-population"]),
                        ("og-image", ["kenya-relief", "kenya-rivers"])):
        card = Image.new("RGB", (1200, 630), INK)
        x = 612
        for i, s in enumerate(slugs):
            x += hang(card, master(s), x, 138 - 34 * i, 380, frame=(40, 43, 41)) + 20
        d = ImageDraw.Draw(card)
        draw_text(d, (64, 118), "ZEROPOINT GEOSPATIAL", font("Barlow-600", 22), (170, 181, 144), 0.16)
        if name == "og-prints":
            big, lines, sub = font("Barlow-300", 66), ("KENYA, MAPPED", "FOR THE WALL"), "Map prints from real data"
        else:
            big, lines, sub = font("Barlow-300", 54), ("PRECISION DATA.", "SMARTER DECISIONS."), "Land surveying and GIS, Kenya"
        for i, t in enumerate(lines):
            draw_text(d, (62, 290 + i * (big.size + 6)), t, big, (244, 243, 238), -0.02)
        draw_text(d, (64, 520), sub.upper(), font("Barlow-500", 20), (160, 163, 158), 0.14)
        card.save(IMG / f"{name}.jpg", quality=86, optimize=True)


if __name__ == "__main__":
    steps = sys.argv[1:] or ["photos", "logo", "textures", "prints", "crops", "share"]
    IMG.mkdir(parents=True, exist_ok=True)
    if "photos" in steps:
        photos()
    if "logo" in steps:
        logo()
    if "textures" in steps:
        textures()
    if "prints" in steps:
        print_previews()
    if "crops" in steps:
        project_crops()
    if "share" in steps:
        share_site()
    print("done")
