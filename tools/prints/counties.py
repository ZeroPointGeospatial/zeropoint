"""Plate 13 - Kenya: the 47 counties.

A reference sheet: every county tinted so that neighbours differ, numbered
with its official county code, named where the name fits, over a faint
relief. All 47 are listed by number in the empty corner below the border.

    python fetch_overture.py counties   # once
    python counties.py [dpi]

Boundaries are OpenStreetMap's, by way of Overture Maps. They are good for
a wall map and are not an authority on where any boundary runs.
"""
import sys

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import box
from shapely.ops import polylabel

from common import (CACHE, INK, county_boundaries, KenyaFrame, MAP_CRS, OLIVE, PAPER, Plate, draw_text, font,
                    hex_rgb, load_dem, text_width, warp_to_map)
from relief import COUNTY_NUMBERS

SCALE_A2 = 2_400_000
TINTS = [hex_rgb(c) for c in ("#e8dab4", "#cdd6b6", "#e4c4ab", "#d8ccb8", "#b7c299", "#eadfc9")]
WATER = hex_rgb("#9db5bf")


def load_counties():
    g = county_boundaries()                  # with the Ilemi Triangle in Turkana, as on Kenyan maps
    g["number"] = g["name"].map(COUNTY_NUMBERS)
    assert g["number"].notna().all() and len(g) == 47, sorted(g["name"])
    return g.to_crs(MAP_CRS).sort_values("number").reset_index(drop=True)


def colour_counties(g):
    """Greedy map colouring: no two neighbours share a tint."""
    touching = {i: [j for j in g.index if j != i and g.geometry[i].buffer(300).intersects(g.geometry[j])]
                for i in g.index}
    order = sorted(g.index, key=lambda i: -len(touching[i]))
    colour = {}
    for i in order:
        used = {colour[j] for j in touching[i] if j in colour}
        colour[i] = next(c for c in range(len(TINTS)) if c not in used)
    return [colour[i] for i in g.index]


def main(dpi=150):
    g = load_counties()
    g["tint"] = colour_counties(g)
    plate = Plate(dpi=dpi, bg=PAPER, fg=INK, accent=OLIVE, block_mm=90)
    f = KenyaFrame(plate, SCALE_A2)
    ss = 2
    W, H = plate.w * ss, plate.h * ss

    def ring_px(ring, s=1):
        px, py = f.to_px(*ring.xy)
        return list(zip(px * s, py * s))

    def parts(geom):
        return list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]

    # --- tints, supersampled for clean edges -------------------------------------
    fill = Image.new("RGB", (W, H), PAPER)
    mask = Image.new("L", (W, H), 0)
    d, dm = ImageDraw.Draw(fill), ImageDraw.Draw(mask)
    for geom, tint in zip(g.geometry, g["tint"]):
        for p in parts(geom):
            d.polygon(ring_px(p.exterior, ss), fill=TINTS[tint])
            dm.polygon(ring_px(p.exterior, ss), fill=255)
    fill = np.asarray(fill.resize((plate.w, plate.h), Image.LANCZOS), dtype="float32") / 255
    land = np.asarray(mask.resize((plate.w, plate.h), Image.LANCZOS), dtype="float32")[..., None] / 255

    # --- faint relief under the tints ------------------------------------------------
    dem, dtr = load_dem((32, -6, 43, 7), "glo90", factor=2)
    res = 1 / f.k
    z, _ = warp_to_map(dem, dtr, f.bounds, res, nodata=0)
    del dem
    zs = ndimage.gaussian_filter(z, 1.2)
    gy, gx = np.gradient(zs, res)
    az, el, zex = np.radians(315), np.radians(45), 7.0
    nx, ny = -gx * zex, gy * zex
    shade = (nx * np.sin(az) * np.cos(el) + ny * np.cos(az) * np.cos(el) + np.sin(el)) \
        / np.sqrt(nx ** 2 + ny ** 2 + 1) / np.sin(el)
    light = np.ones((plate.h, plate.w), "float32")
    oy, ox = int(round(f.oy)), int(round(f.ox))
    hh, ww = min(z.shape[0], plate.h - oy), min(z.shape[1], plate.w - ox)
    light[oy:oy + hh, ox:ox + ww] = np.clip(0.80 + 0.20 * shade[:hh, :ww], 0.70, 1.06)

    # --- standing water from the drainage model -----------------------------------
    hz = np.load(CACHE / "kenya_hydro.npz")
    shp = tuple(hz["water_shape"])
    water = np.unpackbits(hz["water"])[:shp[0] * shp[1]].reshape(shp).astype("float32")
    wmap, _ = warp_to_map(water, Affine(*hz["transform"]), f.bounds, res, nodata=-1)
    wfull = np.zeros((plate.h, plate.w), "float32")
    wfull[oy:oy + hh, ox:ox + ww] = np.clip(wmap[:hh, :ww], 0, 1)
    wfull = ndimage.gaussian_filter(wfull, 0.6)[..., None] * land

    paper = np.array(PAPER, dtype="float32") / 255
    rgb = fill * light[..., None]
    rgb = rgb * (1 - wfull) + (np.array(WATER) / 255) * wfull
    rgb = rgb * land + paper * (1 - land)
    plate.img = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype("uint8"))

    # --- boundaries ---------------------------------------------------------------
    lines = Image.new("L", (W, H), 0)
    dl = ImageDraw.Draw(lines)
    wd = max(1, int(round(plate.px(0.16) * ss)))
    for geom in g.geometry:
        for p in parts(geom):
            pts = ring_px(p.exterior, ss)
            dl.line(pts + [pts[0]], fill=255, width=wd, joint="curve")
    outline = g.geometry.union_all()
    for p in parts(outline):
        pts = ring_px(p.exterior, ss)
        dl.line(pts + [pts[0]], fill=255, width=max(2, int(round(plate.px(0.34) * ss))), joint="curve")
    lines = lines.resize((plate.w, plate.h), Image.LANCZOS).point(lambda v: int(v * 0.78))
    plate.img.paste(Image.new("RGB", plate.img.size, (52, 58, 54)), (0, 0), lines)

    # --- numbers and names -----------------------------------------------------------
    d = ImageDraw.Draw(plate.img)
    f_num = font("IBMPlexMono-500", plate.px(2.25))
    ink, soft = (28, 32, 30), (84, 92, 86)
    for _, row in g.iterrows():
        main_part = max(parts(row.geometry), key=lambda p: p.area)
        pt = polylabel(main_part, tolerance=500)
        x, y = f.to_px(pt.x, pt.y)
        x, y = float(x), float(y)
        name = row["name"].upper()
        placed = False
        for size in (3.7, 3.2, 2.8, 2.5, 2.2):
            fn = font("Barlow-600", plate.px(size))
            tw = text_width(name, fn, 0.12)
            half_w, half_h = (tw / 2 + plate.px(0.8)) / f.k, plate.px(size * 1.25) / f.k
            if box(pt.x - half_w, pt.y - half_h, pt.x + half_w, pt.y + half_h * 0.75).within(main_part):
                draw_text(d, (x, y - plate.px(0.4)), name, fn, ink, 0.12, "ms")
                draw_text(d, (x, y + plate.px(3.2)), f"{int(row['number']):03d}", f_num, soft, 0, "ms")
                placed = True
                break
        if not placed:
            draw_text(d, (x, y + plate.px(0.9)), f"{int(row['number']):03d}", f_num, ink, 0, "ms")

    # --- index of all 47, in the empty corner below the south-west border ----------
    l, t, r, b = plate.map_box
    cols, rows_per = 3, 16
    col_w, row_h = plate.px(41), plate.px(4.55)
    top = b - rows_per * row_h + plate.px(1.5)
    draw_text(d, (l, top - plate.px(6.2)), "COUNTIES BY NUMBER", font("Barlow-500", plate.px(2.5)),
              plate.mix(0.55), 0.2)
    d.line([(l, top - plate.px(3.6)), (l + cols * col_w - plate.px(6), top - plate.px(3.6))],
           fill=plate.mix(0.22), width=max(1, int(plate.px(0.18))))
    f_in = font("Barlow-500", plate.px(2.75))
    f_im = font("IBMPlexMono-400", plate.px(2.35))
    for i, (_, row) in enumerate(g.iterrows()):
        cx, cy = l + (i // rows_per) * col_w, top + (i % rows_per) * row_h + plate.px(2.4)
        draw_text(d, (cx, cy), f"{int(row['number']):03d}", f_im, plate.mix(0.5), 0)
        draw_text(d, (cx + plate.px(8.2), cy), row["name"], f_in, plate.mix(0.86), 0.01)

    plate.title_block(
        "Kenya", "The 47 counties", "13",
        facts=[("Scale at A2", f"1:{SCALE_A2:,}".replace(",", " ")),
               ("Projection", "UTM zone 37S, WGS 84"),
               ("Boundaries", "indicative only")],
        credit="County boundaries: © OpenStreetMap contributors, via Overture Maps (ODbL); not an "
               "authority on any boundary. Relief: Copernicus DEM GLO-90. Cartography by ZeroPoint Geospatial.",
        centre=f.centre_lonlat)
    path = plate.save("kenya-counties" if dpi >= 250 else f"kenya-counties_{dpi}")
    print(path)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
