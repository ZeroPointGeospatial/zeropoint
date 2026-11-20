"""A watermarked proof of a plate, small enough for WhatsApp or email.

    python proof_jpeg.py $ZP_OUT/africa-relief.png            # -> africa-relief_PROOF.jpg
    python proof_jpeg.py $ZP_OUT/county-kwale_150.png 1800    # width in pixels

The customer sees the whole sheet, readable, but marked PROOF across it and
too small to print from. Send this, not the master, until they have approved
and paid.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from common import BLEED_MM, font, srgb_profile

Image.MAX_IMAGE_PIXELS = None


def proof(src, width=1600):
    im = Image.open(src)
    dpi = im.info.get("dpi", (300, 300))[0]
    if im.width / max(im.height, 1) < 0.72:             # an A2 plate with bleed: show the cut sheet
        b = round(BLEED_MM * dpi / 25.4)
        im = im.crop((b, b, im.width - b, im.height - b))
    im = im.convert("RGB").resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    mark = Image.new("RGBA", (im.width * 2, im.height * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(mark)
    f = font("Barlow-500", round(width * 0.045))
    text = "PROOF  ·  ZEROPOINT GEOSPATIAL  ·  NOT FOR PRINTING"
    step = round(width * 0.16)
    for i, y in enumerate(range(0, mark.height, step)):
        d.text(((i % 2) * step * 2 - step, y), (text + "      ") * 4, font=f, fill=(120, 120, 120, 70))
    mark = mark.rotate(30, resample=Image.BICUBIC)
    l, t = (mark.width - im.width) // 2, (mark.height - im.height) // 2
    mark = mark.crop((l, t, l + im.width, t + im.height))
    out = im.convert("RGBA")
    out.alpha_composite(mark)
    dst = Path(src).with_name(Path(src).stem.split("_")[0] + "_PROOF.jpg")
    out.convert("RGB").save(dst, "JPEG", quality=82, icc_profile=srgb_profile())
    return dst


if __name__ == "__main__":
    print(proof(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1600))
