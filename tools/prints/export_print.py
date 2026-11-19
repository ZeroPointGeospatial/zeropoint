"""Print-ready files from the masters.

    python export_print.py [folder]         # default: $ZP_OUT/print

For every A2 plate in $ZP_OUT this writes two JPEGs:

    <plate>_A2.jpg         the sheet exactly, 420 x 594 mm
    <plate>_A2_bleed.jpg   the sheet with 3 mm of bleed on every side, 426 x 600 mm

and one for every city print, which has no bleed:

    <city>-gold.jpg

JPEG quality 95 without chroma subsampling, the sRGB profile embedded and
the resolution set, so the file opens at its true size. PRINTING.md says
which file to hand to a print shop and how.
"""
import os
import re
import sys
from pathlib import Path

from PIL import Image

from common import BLEED_MM, OUT, srgb_profile

Image.MAX_IMAGE_PIXELS = None
NAMES = {"kenya": "kenya-relief"}           # master file stem -> the name it is sold under


def save(im, path, dpi):
    im.convert("RGB").save(path, "JPEG", quality=95, subsampling=0, optimize=True,
                           dpi=(dpi, dpi), icc_profile=srgb_profile())
    mm = [round(v / dpi * 25.4) for v in im.size]
    print(f"  {path.name:38s} {im.width} x {im.height} px  {mm[0]} x {mm[1]} mm  "
          f"{path.stat().st_size / 1e6:.1f} MB")


def main(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for src in sorted(OUT.glob("*.png")):
        if re.search(r"_\d+$", src.stem):            # a low-resolution proof
            continue
        im = Image.open(src)
        dpi = round(im.info.get("dpi", (300, 300))[0])
        name = NAMES.get(src.stem, src.stem)
        if src.stem.endswith("-gold"):
            save(im, folder / f"{name}.jpg", dpi)
            continue
        b = round(BLEED_MM * dpi / 25.4)
        save(im, folder / f"{name}_A2_bleed.jpg", dpi)
        save(im.crop((b, b, im.width - b, im.height - b)), folder / f"{name}_A2.jpg", dpi)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "print")
