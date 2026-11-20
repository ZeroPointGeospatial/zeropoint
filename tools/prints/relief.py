"""Relief plates: a terrain model lit from the north-west and path-traced
in plan view, so the sheet keeps an exact map scale.

    python relief.py mount-kenya [dpi] [spp]
    python relief.py kilimanjaro | rift-valley | east-africa
    python relief.py kenya              # the country, cut to its outline
    python relief.py kenya-forest       # the same model, bone white, with tree cover
    python relief.py county:Kiambu      # any of the 47 counties, scale chosen to fit
    python relief.py spec:maps/africa-relief.yml   # any area, from a map spec (maps/README.md)

A finished render is cached, so changing labels or type and running again
takes seconds. Set ZP_FRESH=1 to force a new render.
"""
import sys
from pathlib import Path
import time

import numpy as np
from scipy import ndimage

import render3d as r3
from common import (HYPSO, INK, MAP_CRS, OLIVE, PAPER, Plate, annotate, apply_ramp,
                    cached_render, draw_text, font, hex_rgb, hypso_rgb, kenya, load_dem,
                    name_label, place_render, ramp, ramp_legend, rasterize_geom, transformer,
                    warp_to_map)

WATER = np.array([0.60, 0.69, 0.72])        # muted blue-grey for lakes and sea
BONE = np.array(hex_rgb("#ebe6da")) / 255   # the unpainted model
# canopy cover 0..1 -> colour; denser forest is darker, as it is from the air
CANOPY = ramp([(0.0, "#ebe6da"), (0.08, "#dfe0c6"), (0.22, "#b7cc9a"), (0.42, "#7bab6b"),
               (0.65, "#3f8250"), (0.85, "#1f5f3b"), (1.0, "#12452c")])
LAEA_EAST_AFRICA = "+proj=laea +lat_0=-3.3 +lon_0=35.2 +datum=WGS84 +units=m +no_defs"

# The Rift plate uses its own elevation breaks: the valley floor stays sand
# and the shoulders turn green, which the shared ramp would flatten to one tone.
RIFT_STOPS = [(1300, "#e9dfc6"), (1600, "#dfd0a6"), (1850, "#cdbb8c"), (2050, "#b9af80"),
              (2250, "#9da375"), (2500, "#778a61"), (2800, "#4e6b4d"), (3150, "#61704f"),
              (3550, "#8f8865"), (3900, "#8d857b"), (4100, "#b3aea6")]

# Point labels: (name, figure, lon, lat, side, snap radius in metres or 0)
# Names: (text, lon, lat, rotation, size mm), set in italic for ranges and water.
PLATES = {
    "mount-kenya": dict(
        number="06", title="Mount Kenya", subtitle="Relief of the Kirinyaga massif",
        centre=(37.335, -0.150), scale=175_000, source="glo30", cell=30, zex=3.0,
        ticks=[1500, 2500, 3500, 4500, 5199], vrange=(1100, 5199),
        labels=[("Batian", "5 199 m", 37.3083, -0.1517, "right", 2500),
                ("Ithanguni", "3 894 m", 37.468, -0.117, "right", 2500)]),
    "kilimanjaro": dict(
        number="07", title="Kilimanjaro", subtitle="Kibo, Mawenzi and the Shira plateau",
        centre=(37.345, -3.075), scale=150_000, source="glo30", cell=30, zex=2.4,
        ticks=[1500, 2500, 3500, 4500, 5895], vrange=(1100, 5895),
        labels=[("Kibo · Uhuru Peak", "5 895 m", 37.3556, -3.0758, "left", 2500),
                ("Mawenzi", "5 149 m", 37.455, -3.095, "right", 2500),
                ("Shira", "3 962 m", 37.210, -3.058, "left", 3000)]),
    "rift-valley": dict(
        number="08", title="The Rift Valley", subtitle="Menengai to Suswa, central Kenya",
        centre=(36.25, -0.61), scale=350_000, source="glo30", cell=45, zex=5.0, sun_el=27,
        stops=RIFT_STOPS, ticks=[1500, 2000, 2500, 3000, 3500, 4001], vrange=(1300, 4001),
        labels=[("Menengai", "caldera", 36.07, -0.205, "right", 0),
                ("Longonot", "2 776 m", 36.43, -0.915, "right", 2500),
                ("Suswa", "2 356 m", 36.37, -1.175, "right", 3000),
                ("Lesatima", "4 001 m", 36.617, -0.317, "left", 3000),
                ("Kinangop", "3 906 m", 36.70, -0.63, "left", 3000),
                ("Eburru", "2 856 m", 36.24, -0.63, "left", 3000)],
        names=[("Lake Nakuru", 36.09, -0.315, 0, 2.8), ("Lake Elmenteita", 36.29, -0.405, 0, 2.6),
               ("Lake Naivasha", 36.36, -0.705, 0, 2.8), ("Mau Escarpment", 35.90, -0.72, -62, 3.4),
               ("Aberdare Range", 36.72, -0.47, -68, 3.4)]),
    "east-africa": dict(
        number="14", title="East Africa", subtitle="The Great Rift, from Lake Turkana to Lake Malawi",
        centre=(35.2, -3.3), scale=4_500_000, source="glo90", cell=500, factor=5, zex=30.0,
        crs=LAEA_EAST_AFRICA, projection="Lambert azimuthal equal-area", min_water_km2=80,
        ticks=[0, 1000, 2000, 3000, 4000, 5895], vrange=(0, 5895),
        labels=[("Kilimanjaro", "5 895 m", 37.3556, -3.0758, "right", 15000),
                ("Mount Kenya", "5 199 m", 37.3083, -0.1517, "right", 15000),
                ("Rwenzori", "5 109 m", 29.87, 0.386, "left", 20000),
                ("Mount Meru", "4 566 m", 36.75, -3.247, "left", 12000),
                ("Karisimbi", "4 507 m", 29.45, -1.507, "left", 12000),
                ("Mount Elgon", "4 321 m", 34.56, 1.12, "left", 15000)],
        names=[("Lake Victoria", 33.0, -1.2, 0, 4.2), ("Lake Tanganyika", 29.75, -6.1, -72, 3.6),
               ("Lake Turkana", 36.9, 3.55, 0, 3.0), ("Lake Malawi", 34.55, -10.7, 0, 3.0),
               ("Lake Albert", 30.55, 1.95, 0, 2.6), ("Lake Rukwa", 32.6, -7.75, 0, 2.6),
               ("Indian Ocean", 41.0, -7.0, 0, 4.2)]),
    "kenya": dict(
        number="03", title="Kenya", subtitle="Relief, from the coast to 5 199 metres",
        scale=2_400_000, source="glo90", cell=250, zex=22.0, shape="kenya",
        ticks=[0, 1000, 2000, 3000, 4000, 5199], vrange=(0, 5199),
        labels=[("Mount Kenya", "5 199 m", 37.3083, -0.1517, "right", 6000),
                ("Mount Elgon", None, 34.56, 1.12, "right", 8000),
                ("Nairobi", None, 36.817, -1.286, "right", 0),
                ("Mombasa", None, 39.664, -4.043, "left", 0),
                ("Mount Marsabit", None, 37.98, 2.30, "right", 6000),
                ("Mount Kulal", None, 36.93, 2.72, "right", 6000)],
        names=[("Lake Turkana", 36.62, 3.60, 0, 3.0), ("Lake Victoria", 34.38, -0.42, 0, 3.0),
               ("Aberdare Range", 36.48, -0.62, 0, 2.7), ("Mau Escarpment", 35.35, -0.95, 0, 2.7),
               ("Cherangani Hills", 35.42, 1.42, 0, 2.7), ("Chyulu Hills", 37.75, -2.72, 0, 2.7),
               ("Taita Hills", 38.28, -3.62, 0, 2.7), ("Rift Valley", 36.05, 1.55, -78, 3.2)]),
    "kenya-forest": dict(
        number="05", title="Kenya", subtitle="Tree cover and the water towers",
        scale=2_400_000, source="glo90", cell=250, zex=22.0, shape="kenya", texture="forest",
        labels=[("Mount Kenya", None, 37.3083, -0.1517, "right", 6000),
                ("Aberdares", None, 36.66, -0.42, "left", 0),
                ("Mau", None, 35.62, -0.55, "left", 0),
                ("Mount Elgon", None, 34.56, 1.12, "right", 8000),
                ("Cherangani", None, 35.45, 1.25, "right", 0),
                ("Kakamega", None, 34.87, 0.27, "left", 0),
                ("Arabuko-Sokoke", None, 39.87, -3.32, "left", 0),
                ("Boni", None, 41.05, -1.70, "left", 0)]),
}

# Official county numbers, printed on county plates.
COUNTY_NUMBERS = {name: n for n, name in enumerate(
    ["Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta", "Garissa", "Wajir",
     "Mandera", "Marsabit", "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos",
     "Makueni", "Nyandarua", "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana",
     "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu", "Elgeyo-Marakwet", "Nandi",
     "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet", "Kakamega",
     "Vihiga", "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii",
     "Nyamira", "Nairobi"], start=1)}

# Labels for the county plates made so far. A county without an entry is drawn unlabelled.
COUNTY_LABELS = {
    "Kiambu": dict(
        labels=[("Kiambu", None, 36.835, -1.171, "right", 0), ("Thika", None, 37.070, -1.040, "right", 0),
                ("Limuru", None, 36.642, -1.107, "left", 0), ("Ruiru", None, 36.962, -1.146, "right", 0),
                ("Kikuyu", None, 36.664, -1.246, "left", 0), ("Githunguri", None, 36.777, -1.058, "right", 0)],
        names=[("Kikuyu Escarpment", 36.58, -0.97, -58, 2.8)]),
    "Nakuru": dict(
        labels=[("Nakuru", None, 36.070, -0.283, "right", 0), ("Naivasha", None, 36.433, -0.716, "right", 0),
                ("Gilgil", None, 36.322, -0.498, "right", 0), ("Molo", None, 35.732, -0.248, "left", 0),
                ("Menengai", None, 36.07, -0.205, "left", 0), ("Longonot", "2 776 m", 36.43, -0.915, "right", 2500)],
        names=[("Lake Nakuru", 36.09, -0.39, 0, 2.5), ("Lake Naivasha", 36.36, -0.78, 0, 2.6),
               ("Mau Escarpment", 35.83, -0.62, -58, 3.0)]),
    "Kajiado": dict(
        labels=[("Kajiado", None, 36.782, -1.852, "right", 0), ("Ngong", None, 36.656, -1.362, "left", 0),
                ("Kitengela", None, 36.960, -1.474, "right", 0), ("Namanga", None, 36.787, -2.545, "right", 0),
                ("Loitokitok", None, 37.510, -2.925, "left", 0), ("Magadi", None, 36.285, -1.900, "right", 0)],
        names=[("Ngong Hills", 36.63, -1.44, 0, 2.5), ("Nguruman Escarpment", 36.03, -1.85, -80, 2.8),
               ("Amboseli", 37.25, -2.65, 0, 2.6)]),
    "Nyeri": dict(
        labels=[("Nyeri", None, 36.951, -0.420, "right", 0), ("Karatina", None, 37.126, -0.483, "right", 0),
                ("Othaya", None, 36.944, -0.548, "left", 0), ("Naro Moru", None, 37.020, -0.163, "left", 0),
                ("Batian", "5 199 m", 37.3083, -0.1517, "left", 2500),
                ("Lesatima", "4 001 m", 36.617, -0.317, "right", 3000)],
        names=[("Aberdare Range", 36.69, -0.45, -70, 2.8)]),
    "Machakos": dict(
        labels=[("Machakos", None, 37.263, -1.517, "right", 0), ("Athi River", None, 36.983, -1.456, "right", 0),
                ("Kangundo", None, 37.345, -1.305, "right", 0), ("Matuu", None, 37.540, -1.150, "right", 0),
                ("Ol Donyo Sabuk", "2 145 m", 37.255, -1.135, "left", 2500)],
        names=[("Yatta Plateau", 37.62, -1.42, -52, 2.8)]),
}
TIDY_SCALES = [50_000, 75_000, 100_000, 125_000, 150_000, 200_000, 250_000, 300_000, 400_000,
               500_000, 600_000, 750_000, 1_000_000, 1_250_000, 1_500_000, 2_000_000]


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


def local_stops(zlo, zhi):
    """Elevation colours for a single county: the sand-to-forest part of the
    shared ramp is stretched over the county's own range, so a county that
    sits entirely in one height band still shows its shape. Above 3 200 m
    the shared colours (moorland, rock, ice) keep their true heights."""
    cols = ["#e9dfc6", "#dfd0a6", "#cdbb8c", "#b9af80", "#9da375", "#778a61", "#4e6b4d"]
    top = min(zhi, 3000.0)
    stops = [(zlo + (top - zlo) * i / (len(cols) - 1), c) for i, c in enumerate(cols)]
    return stops + [(z, c) for z, c in HYPSO if z >= 3200 and zhi > 3200]


def county_config(name, box_mm):
    """Build a plate description for one county: pick the largest tidy scale
    at which it fits the sheet, and a vertical exaggeration to suit its relief."""
    from common import county_boundaries
    g = county_boundaries()
    row = g[g["name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"no county called {name!r}; try one of: {', '.join(sorted(g['name']))}")
    name = row["name"].iloc[0]
    geom = row.to_crs(MAP_CRS).geometry.iloc[0]
    x0, y0, x1, y1 = geom.bounds
    need = max((x1 - x0) / (box_mm[0] * 0.94 / 1000), (y1 - y0) / (box_mm[1] * 0.93 / 1000))
    scale = next(s for s in TIDY_SCALES if s >= need)
    fine = scale <= 400_000
    cell = max(30 if fine else 90, round(scale * 0.00017 / 5) * 5)
    cfg = dict(number=f"{COUNTY_NUMBERS.get(name, 0):03d}", label="COUNTY", title=name,
               subtitle="County relief", scale=scale, source="glo30" if fine else "glo90",
               cell=cell, shape="county", geom=geom, labels=[], names=[],
               boundary="County boundary: OpenStreetMap contributors, via Overture Maps (ODbL).")
    cfg.update(COUNTY_LABELS.get(name, {}))
    return cfg


def spec_config(path, box_mm):
    """Build a plate description from a map spec file (see maps/README.md)."""
    import yaml
    import regions
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    geom_ll, _, what = regions.region_outline(spec["region"])
    crs, proj_name = regions.projection_for(geom_ll, spec.get("crs"))
    geom = regions.project(geom_ll, crs)
    x0, y0, x1, y1 = geom.bounds
    scale = spec.get("scale") or regions.tidy_scale(x1 - x0, y1 - y0, box_mm)
    cell = spec.get("cell") or max(30, round(scale * 0.00017 / 5) * 5)
    cut = spec.get("cut", "bbox" not in spec["region"])
    w, s_, e, n = geom_ll.bounds
    boundary = {"countries": "Boundaries: Natural Earth (public domain).",
                "continent": "Boundaries: Natural Earth (public domain).",
                "county": "County boundary: OpenStreetMap contributors, via Overture Maps (ODbL).",
                }.get(next(iter(spec["region"])), "")
    cfg = dict(
        slug=spec["slug"], title=spec["title"], subtitle=spec.get("subtitle", "Relief"),
        label=spec.get("label", "CUSTOM"), number=str(spec.get("number", "")),
        scale=scale, cell=cell, crs=crs, projection=spec.get("projection", proj_name),
        shape="outline" if cut else "block", geom=geom, geom_ll=geom_ll,
        centre=((w + e) / 2, (s_ + n) / 2), source=spec.get("source") or ("glo30" if scale <= 400_000 else "glo90"),
        coarse=cell >= 300, zex=spec.get("zex"), sun_el=spec.get("sun_el", 30), spec=True,
        stops=[(z, c) for z, c in spec["stops"]] if spec.get("stops") else None,
        min_water_km2=spec.get("min_water_km2", max(0.4, (cell / 1000) ** 2 * 25)),
        boundary=spec.get("credit", boundary),
        labels=[(x["name"], x.get("value"), x["lon"], x["lat"], x.get("side", "right"), x.get("snap", 0))
                for x in spec.get("labels", [])],
        names=[(x["text"], x["lon"], x["lat"], x.get("angle", 0), x.get("size", 3.0))
               for x in spec.get("names", [])])
    print(f"{cfg['slug']}: {what}, {proj_name}, 1:{scale:,}, {cell} m cells"
          + (", coarse elevation" if cfg["coarse"] else ""))
    return cfg


def main(name, dpi=100, spp=32):
    t0 = time.time()
    plate = Plate(dpi=dpi, bg=PAPER, fg=INK, accent=OLIVE, block_mm=90)
    l, t, r, b = plate.map_box
    bw_mm, bh_mm = (r - l) / plate.px(1), (b - t) / plate.px(1)
    if name.startswith("county:"):
        cfg = county_config(name.split(":", 1)[1], (bw_mm, bh_mm))
        slug = "county-" + cfg["title"].lower().replace(" ", "-").replace("'", "")
    elif name.startswith("spec:"):
        cfg = spec_config(name.split(":", 1)[1], (bw_mm, bh_mm))
        slug = cfg["slug"]
    else:
        cfg, slug = PLATES[name], name
    crs = cfg.get("crs", MAP_CRS)
    scale = cfg["scale"]
    view_w = bw_mm / 1000 * scale                    # ground metres across the map box
    view_h = bh_mm / 1000 * scale
    tf = transformer("EPSG:4326", crs)
    back = transformer(crs, "EPSG:4326")
    shape = cfg.get("shape", "block")
    cell = cfg["cell"]

    # --- ground extent and the outline to cut to, if any ---------------------
    outline = None
    if shape == "kenya":
        outline = kenya(MAP_CRS)
    elif shape in ("county", "outline"):
        outline = cfg["geom"]
    if outline is not None:
        x0, y0, x1, y1 = outline.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        gw, gh = (x1 - x0) + 16 * cell, (y1 - y0) + 16 * cell
    else:
        cx, cy = tf.transform(*cfg["centre"])
        gw, gh = view_w * 0.90, view_h * 0.915       # leave room for the cast shadow
    bounds = (cx - gw / 2, cy - gh / 2, cx + gw / 2, cy + gh / 2)

    # --- elevation --------------------------------------------------------------
    if shape == "kenya":
        dem, tr = load_dem((32, -6, 43, 7), cfg["source"], factor=2)
    elif cfg.get("coarse"):
        # a large area: read the elevation tiles at reduced resolution, straight from the cloud
        import regions
        xs = [bounds[0], bounds[2], bounds[0], bounds[2], cx, cx, bounds[0], bounds[2]]
        ys = [bounds[1], bounds[1], bounds[3], bounds[3], bounds[1], bounds[3], cy, cy]
        lons, lats = back.transform(xs, ys)
        gw_ll = cfg["geom_ll"].bounds
        ll = (min(min(lons), gw_ll[0]) - 0.5, min(min(lats), gw_ll[1]) - 0.5,
              max(max(lons), gw_ll[2]) + 0.5, max(max(lats), gw_ll[3]) + 0.5)
        land = cfg["geom_ll"].buffer(0.5) if shape == "outline" else None
        dem, tr = regions.load_dem_coarse(ll, cell / 111_320 / 1.5, cfg["source"], land=land)
    else:
        xs = [bounds[0], bounds[2], bounds[0], bounds[2], cx, cx]
        ys = [bounds[1], bounds[1], bounds[3], bounds[3], bounds[1], bounds[3]]
        lons, lats = back.transform(xs, ys)
        ll = (np.floor(min(lons) * 20 - 1) / 20, np.floor(min(lats) * 20 - 1) / 20,
              np.ceil(max(lons) * 20 + 1) / 20, np.ceil(max(lats) * 20 + 1) / 20)
        import fetch_data
        fetch_data.dem((int(np.floor(ll[0])), int(np.floor(ll[1])),
                        int(np.ceil(ll[2])), int(np.ceil(ll[3]))),
                       10 if cfg["source"] == "glo30" else 30, cfg["source"])
        dem, tr = load_dem(tuple(float(v) for v in ll), cfg["source"], factor=cfg.get("factor", 1))
    z, ztr = warp_to_map(dem, tr, bounds, cell, dst_crs=crs)
    del dem
    valid = None
    if outline is not None:
        valid = rasterize_geom(outline, z.shape, ztr)
        z = np.where(valid, np.nan_to_num(z), 0)
    z = np.nan_to_num(z)
    zlo = float(z[valid].min() if valid is not None else z.min())
    zhi = float(z.max())
    # A county's exaggeration is set from its own relief, and kept modest: the
    # elevation data is a surface model, so forest edges become cliffs if pushed.
    if cfg.get("spec") and not cfg.get("zex"):
        import regions
        zex = regions.default_exaggeration(gw, zhi - zlo)
    else:
        zex = cfg.get("zex") or float(np.clip(round(0.07 * gw / max(zhi - zlo, 250)), 3, 12))
    print(f"{slug}: 1:{scale:,}, grid {z.shape} at {cell} m, {zlo:.0f}-{zhi:.0f} m, "
          f"exaggeration x{zex:g}, {time.time() - t0:.0f}s")

    # --- colour -----------------------------------------------------------------
    local = shape == "county" or (cfg.get("spec") and zhi - zlo < 1500)
    stops = cfg.get("stops") or (local_stops(zlo, zhi) if local else HYPSO)
    facts_extra, legend, credit = None, None, None
    if cfg.get("texture") == "forest":
        import forest
        cover, dense, ctr = forest.canopy_grid()
        cmap, _ = warp_to_map(cover, ctr, bounds, cell, nodata=-1)
        tex = apply_ramp(np.clip(cmap, 0, 1), CANOPY)
        forest_km2, land_km2 = forest.kenya_stats(dense, ctr)
        facts_extra = [("Canopy of 30 % or more", f"{round(forest_km2, -2):,.0f} km²".replace(",", " ")),
                       ("Share of the country", f"{forest_km2 / land_km2 * 100:.1f} %")]
        legend = canopy_legend
        credit = ("Tree cover: Hansen/UMD/Google/USGS/NASA Global Forest Change v1.11, canopy in "
                  "2000 less loss 2001–2023 (CC BY 4.0). Relief: Copernicus DEM GLO-90. "
                  "Modelled by ZeroPoint Geospatial.")
    else:
        tex = hypso_rgb(z, stops)
    min_water = cfg.get("min_water_km2", 6.0 if shape == "kenya" else 0.4)
    wm = water_mask(z, cell, min_water)
    if valid is not None:
        wm &= valid
    soft = ndimage.gaussian_filter(wm.astype("float32"), 0.7)[..., None]
    tex = tex * (1 - soft) + WATER * soft

    # --- model and render -------------------------------------------------------
    sheet_w = plate.w / plate.px(1) / 1000 * scale       # ground metres across the sheet
    mx = (l + r) / 2 - plate.px(3.0)                     # where the model centre lands, px
    my = (t + b) / 2 - plate.px(2.5)
    m_per_px = sheet_w / plate.w
    thickness = view_w * 0.010                       # depth of the block under its lowest point
    sun_el = cfg.get("sun_el", 30)

    def render():
        verts, faces, uv, wv, wf = r3.heightfield_mesh((z - zlo) * zex, cell, valid=valid,
                                                       base=-thickness)
        shapes = [dict(verts=verts, faces=faces, uv=uv, texture=tex),
                  dict(verts=wv, faces=wf, color=(0.78, 0.76, 0.70), flat=True)]
        # Plan view of the whole sheet, so the shadow and the soft shading the
        # model throws on the paper fade out naturally.
        cam_x = (plate.w / 2 - mx) * m_per_px
        cam_y = -(plate.h / 2 - my) * m_per_px
        return r3.render(
            shapes, plate.w, plate.h, view_width=sheet_w, tilt=90, centre=(cam_x, cam_y, 0),
            sun_el=sun_el, sun_size=7, spp=spp, floor=tuple(np.array(PAPER) / 255),
            floor_z=-thickness, edge_height=thickness,
            progress=lambda i, n: print(f"  tile {i}/{n} {time.time() - t0:.0f}s", flush=True))

    key = dict(plate=slug, size=(plate.w, plate.h), spp=spp, scale=scale, cell=cell, zex=zex,
               sun=sun_el, stops=stops, texture=cfg.get("texture"), bounds=[round(v) for v in bounds],
               zsum=round(float(z.sum()), 1))
    rgb, mask = cached_render(key, render)
    place_render(plate, rgb, mask)

    # --- labels -----------------------------------------------------------------
    def to_px(x, y):
        return (mx + (x - cx) / m_per_px, my - (y - cy) / m_per_px)

    for text, lon, lat, angle, size in cfg.get("names", []):
        x, y = tf.transform(lon, lat)
        name_label(plate, to_px(x, y), text, (40, 46, 42), (250, 249, 244), size_mm=size,
                   angle=angle, tracking=0.12, weight=500)
    for label, value, lon, lat, side, snap in cfg.get("labels", []):
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

    # --- title block ------------------------------------------------------------
    lon, lat = back.transform(cx, cy)
    src = "GLO-30" if cfg["source"] == "glo30" else "GLO-90"
    facts = [("Scale at A2", f"1:{scale:,}".replace(",", " "))]
    facts += facts_extra or [("Vertical exaggeration", f"×{zex:g}"),
                             ("Projection", cfg.get("projection", "UTM zone 37S, WGS 84"))]
    if legend is None:
        ticks = cfg.get("ticks")
        vr = cfg.get("vrange")
        if not ticks and cfg.get("spec") and not local:     # a large area on the shared colours
            step = next(s for s in (250, 500, 1000, 2000) if (zhi - max(zlo, 0)) / s <= 6)
            vr = (min(zlo, 0), zhi)
            span = vr[1] - vr[0]
            # round steps, then the top; a step too close to the top would overprint it
            ticks = [v for v in range(0, int(zhi) + 1, step) if zhi - v >= 0.12 * span] + [int(round(zhi))]
        if not ticks:                      # a county or a small area: round ticks across its own range
            step = next((s for s in (10, 20, 25, 50, 100, 200, 250, 500, 1000) if (zhi - zlo) / s <= 5), 2000)
            lo_t = int(np.ceil(zlo / step) * step)
            ticks = list(range(lo_t, int(zhi) + 1, step)) or [int(round(zlo)), int(round(zhi))]
            vr = (min(zlo, ticks[0]), max(zhi, ticks[-1]))
            if vr[1] <= vr[0]:
                vr = (vr[0] - 1, vr[0] + 1)
        legend = ramp_legend(stops, "Elevation, metres", ticks, vmin=vr[0], vmax=vr[1])
    plate.title_block(
        cfg["title"], cfg["subtitle"], cfg["number"], facts=facts,
        credit=credit or (
            f"Elevation: Copernicus DEM {src} (© DLR / Airbus, provided under Copernicus "
            "by the EU and ESA). " + cfg.get("boundary", "") +
            " Relief modelled and ray-traced by ZeroPoint Geospatial.").replace("  ", " "),
        centre=(lon, lat), legend=legend, label=cfg.get("label", "PLATE"))
    path = plate.save(slug if dpi >= 250 else f"{slug}_{dpi}")
    if shape == "county":
        write_county_facts(slug, cfg, scale, zex, zlo, zhi, outline, back)
    print(path, f"{time.time() - t0:.0f}s")


def write_county_facts(slug, cfg, scale, zex, zlo, zhi, outline, back):
    """Facts about a county plate, read by tools/county_pages.py to write its shop page."""
    import json
    from pyproj import Geod
    from shapely.ops import transform as reproject
    from common import OUT
    ll = reproject(lambda x, y: back.transform(x, y), outline)
    area = abs(Geod(ellps="WGS84").geometry_area_perimeter(ll)[0]) / 1e6
    x0, y0, x1, y1 = outline.bounds
    facts = dict(slug=slug, name=cfg["title"], number=cfg["number"], scale=scale, zex=zex,
                 zmin=round(zlo), zmax=round(zhi), area_km2=round(area),
                 width_km=round((x1 - x0) / 1000), height_km=round((y1 - y0) / 1000),
                 source=cfg["source"])
    (OUT / f"{slug}.json").write_text(json.dumps(facts, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100,
         int(sys.argv[3]) if len(sys.argv) > 3 else 32)
