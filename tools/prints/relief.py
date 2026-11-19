"""Relief plates: a terrain model lit from the north-west and path-traced
in plan view, so the sheet keeps an exact map scale.

    python relief.py mount-kenya [dpi] [spp]
    python relief.py kilimanjaro
    python relief.py rift-valley
    python relief.py kenya
    python relief.py kenya-forest       # the same model, bone white, with tree cover

Plate numbers: 03 Kenya, 05 Kenya forest, 06 Mount Kenya, 07 Kilimanjaro,
08 Rift Valley.
"""
import sys
import time

import numpy as np
from scipy import ndimage

import render3d as r3
from common import (HYPSO, INK, MAP_CRS, OLIVE, PAPER, Plate, annotate, apply_ramp,
                    draw_text, font, hex_rgb, hypso_rgb, kenya, load_dem, place_render, ramp,
                    ramp_legend, rasterize_geom, transformer, warp_to_map)

WATER = np.array([0.60, 0.69, 0.72])        # muted blue-grey for lakes
BONE = np.array(hex_rgb("#ebe6da")) / 255   # the unpainted model
# canopy cover 0..1 -> colour; denser forest is darker, as it is from the air
CANOPY = ramp([(0.0, "#ebe6da"), (0.08, "#dfe0c6"), (0.22, "#b7cc9a"), (0.42, "#7bab6b"),
               (0.65, "#3f8250"), (0.85, "#1f5f3b"), (1.0, "#12452c")])

PLATES = {
    "mount-kenya": dict(
        number="06", title="Mount Kenya", subtitle="Relief of the Kirinyaga massif",
        centre=(37.335, -0.150), scale=175_000, source="glo30", cell=30, zex=3.0,
        ticks=[1500, 2500, 3500, 4500, 5199], vrange=(1100, 5199),
        labels=[("Batian", "5 199 m", 37.3083, -0.1517, "right", 2500),
                ("Ithanguni", "3 894 m", 37.468, -0.117, "right", 2500)]),
    "kilimanjaro": dict(
        number="07", title="Kilimanjaro", subtitle="Kibo, Mawenzi and the Shira plateau",
        centre=(37.365, -3.085), scale=200_000, source="glo30", cell=30, zex=2.6,
        ticks=[1000, 2000, 3000, 4000, 5000, 5895], vrange=(700, 5895),
        labels=[("Kibo · Uhuru Peak", "5 895 m", 37.3556, -3.0758, "left", 2500),
                ("Mawenzi", "5 149 m", 37.455, -3.095, "right", 2500),
                ("Shira", "3 962 m", 37.210, -3.058, "left", 3000)]),
    "rift-valley": dict(
        number="08", title="The Rift Valley", subtitle="Menengai to Suswa, central Kenya",
        centre=(36.25, -0.61), scale=350_000, source="glo30", cell=45, zex=4.0,
        ticks=[1500, 2000, 2500, 3000, 3500, 4001], vrange=(1300, 4001),
        labels=[("Menengai", "caldera", 36.07, -0.205, "right", 0),
                ("Lake Nakuru", None, 36.09, -0.365, "right", 0),
                ("Lake Elmenteita", None, 36.24, -0.44, "right", 0),
                ("Lake Naivasha", None, 36.36, -0.77, "right", 0),
                ("Longonot", "2 776 m", 36.43, -0.915, "right", 2500),
                ("Suswa", "2 356 m", 36.37, -1.175, "right", 3000),
                ("Lesatima", "4 001 m", 36.617, -0.317, "left", 3000),
                ("Kinangop", "3 906 m", 36.70, -0.63, "left", 3000),
                ("Eburru", "2 856 m", 36.24, -0.63, "left", 3000)]),
    "kenya": dict(
        number="03", title="Kenya", subtitle="Relief, from the coast to 5 199 metres",
        scale=2_400_000, source="glo90", cell=250, zex=22.0, country=True,
        ticks=[0, 1000, 2000, 3000, 4000, 5199], vrange=(0, 5199),
        labels=[("Mount Kenya", "5 199 m", 37.3083, -0.1517, "right", 6000),
                ("Mount Elgon", None, 34.56, 1.12, "right", 8000),
                ("Lake Turkana", None, 36.05, 3.55, "left", 0),
                ("Lake Victoria", None, 34.2, -0.35, "right", 0)]),
    "kenya-forest": dict(
        number="05", title="Kenya", subtitle="Tree cover and the water towers",
        scale=2_400_000, source="glo90", cell=250, zex=22.0, country=True, texture="forest",
        labels=[("Mount Kenya", None, 37.3083, -0.1517, "right", 6000),
                ("Aberdares", None, 36.66, -0.42, "left", 0),
                ("Mau", None, 35.62, -0.55, "left", 0),
                ("Mount Elgon", None, 34.56, 1.12, "right", 8000),
                ("Cherangani", None, 35.45, 1.25, "right", 0),
                ("Kakamega", None, 34.87, 0.27, "left", 0),
                ("Arabuko-Sokoke", None, 39.87, -3.32, "left", 0),
                ("Boni", None, 41.05, -1.70, "left", 0)]),
}


def canopy_legend(d, right, top, pl):
    from PIL import Image
    w, h = pl.px(96), pl.px(3.2)
    xl, yb = right - w, top + pl.px(4.5)
    strip = (apply_ramp(np.linspace(0, 1, int(w))[None, :], CANOPY) * 255).astype("uint8")
    pl.img.paste(Image.fromarray(np.repeat(strip, max(1, int(h)), 0)), (int(xl), int(yb)))
    f_k = font("Barlow-500", pl.px(2.25))
    f_v = font("IBMPlexMono-400", pl.px(2.3))
    draw_text(d, (xl, top), "TREE CANOPY COVER", f_k, pl.mix(0.55), 0.2)
    for i, tick in enumerate((0, 25, 50, 75, 100)):
        x = xl + tick / 100 * w
        d.line([(x, yb + h), (x, yb + h + pl.px(1.4))], fill=pl.mix(0.5),
               width=max(1, int(pl.px(0.15))))
        anchor = "ls" if i == 0 else ("rs" if i == 4 else "ms")
        draw_text(d, (x, yb + h + pl.px(5.0)), f"{tick} %", f_v, pl.mix(0.62), 0, anchor)


def water_mask(z, cell, min_km2):
    gy, gx = np.gradient(np.nan_to_num(z))
    flat = ndimage.binary_opening((np.abs(gx) + np.abs(gy)) < 1e-4, iterations=1)
    lab, n = ndimage.label(flat)
    if n == 0:
        return np.zeros(z.shape, bool)
    size = ndimage.sum(flat, lab, np.arange(1, n + 1)) * (cell / 1000) ** 2
    return ndimage.binary_dilation(np.isin(lab, np.nonzero(size >= min_km2)[0] + 1), iterations=1)


def main(name, dpi=100, spp=32):
    cfg = PLATES[name]
    t0 = time.time()
    plate = Plate(dpi=dpi, bg=PAPER, fg=INK, accent=OLIVE, block_mm=90)
    l, t, r, b = plate.map_box
    bw_mm, bh_mm = (r - l) / plate.px(1), (b - t) / plate.px(1)
    scale = cfg["scale"]
    view_w = bw_mm / 1000 * scale                    # ground metres across the map box
    view_h = bh_mm / 1000 * scale
    tf = transformer()

    if cfg.get("country"):
        ke = kenya(MAP_CRS)
        x0, y0, x1, y1 = ke.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        gw, gh = (x1 - x0) + 8000, (y1 - y0) + 8000
        dem, tr = load_dem((32, -6, 43, 7), cfg["source"], factor=2)
    else:
        cx, cy = tf.transform(*cfg["centre"])
        gw, gh = view_w * 0.90, view_h * 0.915       # leave room for the cast shadow
        lon0, lat0 = cfg["centre"]
        pad_lon, pad_lat = gw / 111000 * 0.6, gh / 111000 * 0.6
        dem, tr = load_dem((round(lon0 - pad_lon, 2), round(lat0 - pad_lat, 2),
                            round(lon0 + pad_lon, 2), round(lat0 + pad_lat, 2)),
                           cfg["source"])
    cell = cfg["cell"]
    bounds = (cx - gw / 2, cy - gh / 2, cx + gw / 2, cy + gh / 2)
    z, ztr = warp_to_map(dem, tr, bounds, cell)
    del dem
    valid = None
    if cfg.get("country"):
        valid = rasterize_geom(kenya(MAP_CRS), z.shape, ztr)
        z = np.where(valid, np.nan_to_num(z), 0)
    zlo = float(np.nanmin(z[valid]) if valid is not None else np.nanmin(z))
    zhi = float(np.nanmax(z))
    print(f"{name}: grid {z.shape}, {zlo:.0f}-{zhi:.0f} m, {time.time() - t0:.0f}s")

    facts_extra, legend, credit = None, None, None
    if cfg.get("texture") == "forest":
        import forest
        cover, dense, ctr = forest.canopy_grid()
        cmap, _ = warp_to_map(cover, ctr, bounds, cell, nodata=-1)
        tex = apply_ramp(np.clip(cmap, 0, 1), CANOPY)
        forest_km2, land_km2 = forest.kenya_stats(dense, ctr)
        print(f"  canopy >= 30 %: {forest_km2:,.0f} km2 of {land_km2:,.0f} km2")
        facts_extra = [("Canopy of 30 % or more", f"{round(forest_km2, -2):,.0f} km\u00b2".replace(",", " ")),
                       ("Share of the country", f"{forest_km2 / land_km2 * 100:.1f} %")]
        legend = canopy_legend
        credit = ("Tree cover: Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11, canopy in "
                  "2000 less loss 2001\u20132023 (CC BY 4.0). Relief: Copernicus DEM GLO-90. "
                  "Modelled by ZeroPoint Geospatial.")
    else:
        tex = hypso_rgb(z)
    wm = water_mask(z, cell, 0.4 if not cfg.get("country") else 6.0)
    if valid is not None:
        wm &= valid
    soft = ndimage.gaussian_filter(wm.astype("float32"), 0.7)[..., None]
    tex = tex * (1 - soft) + WATER * soft

    zex = cfg["zex"]
    thickness = view_w * 0.010                       # depth of the block under its lowest point
    verts, faces, uv, wv, wf = r3.heightfield_mesh((z - zlo) * zex, cell, valid=valid,
                                                   base=-thickness)
    shapes = [dict(verts=verts, faces=faces, uv=uv, texture=tex),
              dict(verts=wv, faces=wf, color=(0.78, 0.76, 0.70), flat=True)]

    # Camera: plan view of the whole sheet, so the shadow and the soft
    # shading the model throws on the paper fade out naturally. The model sits
    # in the map box, nudged up and left to leave room for its shadow.
    sheet_w = plate.w / plate.px(1) / 1000 * scale       # ground metres across the sheet
    mx = (l + r) / 2 - plate.px(3.0)                     # where the model centre lands, px
    my = (t + b) / 2 - plate.px(2.5)
    m_per_px = sheet_w / plate.w
    cam_x = (plate.w / 2 - mx) * m_per_px
    cam_y = -(plate.h / 2 - my) * m_per_px
    rgb, mask = r3.render(
        shapes, plate.w, plate.h, view_width=sheet_w, tilt=90, centre=(cam_x, cam_y, 0),
        sun_el=30, sun_size=7, spp=spp, floor=tuple(np.array(PAPER) / 255),
        floor_z=-thickness, edge_height=thickness,
        progress=lambda i, n: print(f"  tile {i}/{n} {time.time() - t0:.0f}s", flush=True))
    place_render(plate, rgb, mask)

    def to_px(x, y):
        return (mx + (x - cx) / m_per_px, my - (y - cy) / m_per_px)

    for label, value, lon, lat, side, snap in cfg["labels"]:
        x, y = tf.transform(lon, lat)
        if snap:  # move a summit label onto the highest cell nearby
            c0 = int((x - bounds[0]) / cell)
            r0 = int((bounds[3] - y) / cell)
            k = int(snap / cell)
            win = z[max(r0 - k, 0):r0 + k + 1, max(c0 - k, 0):c0 + k + 1]
            dr, dc = np.unravel_index(np.argmax(win), win.shape)
            x = bounds[0] + (max(c0 - k, 0) + dc + 0.5) * cell
            y = bounds[3] - (max(r0 - k, 0) + dr + 0.5) * cell
        annotate(plate, to_px(x, y), label, value, side)

    lon, lat = transformer(MAP_CRS, "EPSG:4326").transform(cx, cy)
    src = "GLO-30" if cfg["source"] == "glo30" else "GLO-90"
    facts = [("Scale at A2", f"1:{scale:,}".replace(",", " "))]
    facts += facts_extra or [("Vertical exaggeration", f"×{zex:g}"),
                             ("Projection", "UTM zone 37S, WGS 84")]
    if legend is None:
        legend = ramp_legend(HYPSO, "Elevation, metres", cfg["ticks"],
                             vmin=cfg["vrange"][0], vmax=cfg["vrange"][1])
    plate.title_block(
        cfg["title"], cfg["subtitle"], cfg["number"], facts=facts,
        credit=credit or (
            f"Elevation: Copernicus DEM {src} (© DLR / Airbus, provided under Copernicus "
            "by the EU and ESA). Relief modelled and ray-traced by ZeroPoint Geospatial."),
        centre=(lon, lat), legend=legend)
    path = plate.save(name if dpi >= 250 else f"{name}_{dpi}")
    print(path, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100,
         int(sys.argv[3]) if len(sys.argv) > 3 else 32)
