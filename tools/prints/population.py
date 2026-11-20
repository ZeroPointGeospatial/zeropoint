"""Population plates: every 400 m hexagon of the Kontur dataset is a column
whose height is the number of people living in it.

    python population.py kenya [dpi] [spp]      # plate 01
    python population.py spec:maps/africa-population.yml [dpi] [spp]   # any area (maps/README.md)

For a large area the 400 m hexagons are summed into bigger H3 hexagons, chosen
so that each prints about a third of a millimetre across.
"""
import sys
import time

import numpy as np
import shapely
from shapely.geometry import box

import render3d as r3
from common import (DATA, INK, MAP_CRS, OLIVE, PAPER, Plate, annotate, cached_render, draw_text,
                    font, hex_rgb, kenya, lakes, place_render, ramp, transformer)

# sand -> ochre -> burnt orange -> red -> maroon
RAMP = ramp([(0.0, "#e9e2cf"), (0.14, "#ecd29c"), (0.32, "#e9b062"), (0.52, "#dc7f40"),
             (0.72, "#bd4a2e"), (0.88, "#8a2029"), (1.0, "#45101f")])
LAND = hex_rgb("#e6e3da")
LAKE = hex_rgb("#b9c8cc")

PLATES = {
    "kenya": dict(
        number="01", title="Kenya", subtitle="Where 55 million people live",
        tilt=62.0, max_height_km=440.0, model_width=0.90, drop=0.075,
        # name, lon, lat, where the text sits relative to the place (mm right, mm down), side
        towns=[("Nairobi", 36.817, -1.286, (9, 21), "right"),
               ("Mombasa", 39.664, -4.043, (9, 7), "right"),
               ("Kisumu", 34.754, -0.092, (-9, 13), "left")]),
}
# A plate can also be limited to one city by adding `bounds_lonlat=(w, s, e, n)`.
# Mind that Kontur caps very dense hexagons: central Nairobi tops out at
# 37 287 people in dozens of neighbouring cells, which shows as a flat-topped
# block at city scale. At country scale it does not.


def polygon_slab(poly, thickness):
    """Triangulated top face and side walls for a (multi)polygon lying at z = 0."""
    tris = shapely.constrained_delaunay_triangles(poly)
    coords = np.array([np.asarray(t.exterior.coords)[:3] for t in tris.geoms])
    # make every triangle counter-clockwise so its normal points up
    a, b, c = coords[:, 0], coords[:, 1], coords[:, 2]
    cw = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) < 0
    coords[cw] = coords[cw][:, ::-1]
    top_v = np.concatenate([coords.reshape(-1, 2), np.zeros((len(coords) * 3, 1))], 1)
    top_f = np.arange(len(top_v), dtype="int32").reshape(-1, 3)

    rings = []
    for p in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
        rings.append(np.asarray(p.exterior.coords))
        rings += [np.asarray(i.coords) for i in p.interiors]
    wv, wf, n = [], [], 0
    for ring in rings:
        p0, p1 = ring[:-1], ring[1:]
        k = len(p0)
        v = np.concatenate([
            np.column_stack([p0, np.zeros(k)]), np.column_stack([p1, np.zeros(k)]),
            np.column_stack([p0, np.full(k, -thickness)]),
            np.column_stack([p1, np.full(k, -thickness)])])
        i = np.arange(k, dtype="int32") + n
        wf.append(np.concatenate([np.column_stack([i, i + 2 * k, i + k]),
                                  np.column_stack([i + k, i + 2 * k, i + 3 * k])]))
        wv.append(v)
        n += 4 * k
    return top_v.astype("float32"), top_f, np.concatenate(wv).astype("float32"), np.concatenate(wf)


def spec_config(path, box_w_mm):
    """Plate description, hexagons and outline for a map spec (see maps/README.md)."""
    from pathlib import Path
    import yaml
    import regions
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    geom_ll, isos, what = regions.region_outline(spec["region"])
    crs, proj_name = regions.projection_for(geom_ll, spec.get("crs"))
    land = regions.project(geom_ll, crs)
    x0, y0, x1, y1 = land.bounds
    model_width = spec.get("model_width", 0.90)
    scale = (x1 - x0) / (box_w_mm * model_width / 1000)
    res = spec.get("h3_res") or regions.h3_resolution_for(scale)
    print(f"{spec['slug']}: {what}, {proj_name}, about 1:{scale:,.0f}, H3 resolution {res}, "
          f"countries {', '.join(isos)}")
    cells, pop = regions.population_hexagons(isos, res, geom_ll)
    xy, keep = regions.hexagon_rings(cells, crs)
    lk = lakes(crs)
    water = lk[lk.intersects(land)].geometry.union_all().intersection(land)
    cfg = dict(number=str(spec.get("number", "")), label=spec.get("label", "CUSTOM"),
               title=spec["title"], subtitle=spec.get("subtitle", "Where people live"),
               tilt=spec.get("tilt", 62.0), model_width=model_width, drop=spec.get("drop", 0.075),
               max_height_km=spec.get("max_height_km", 0.5 * (x1 - x0) / 1000), crs=crs, h3_res=res,
               slug=spec["slug"], projection=proj_name,
               towns=[(x["name"], x["lon"], x["lat"], tuple(x.get("offset", (9, 9))), x.get("side", "right"))
                      for x in spec.get("towns", [])])
    return cfg, xy, pop[keep], land, water


def main(name, dpi=100, spp=32):
    import geopandas as gpd
    t0 = time.time()
    plate = Plate(dpi=dpi, bg=PAPER, fg=INK, accent=OLIVE, block_mm=90)
    l, t, r, b = plate.map_box
    if name.startswith("spec:"):
        cfg, xy, pop, land, water = spec_config(name.split(":", 1)[1], (r - l) / plate.px(1))
        return draw(plate, cfg, xy, pop, land, water, cfg["crs"], cfg["slug"], dpi, spp, t0)
    cfg = PLATES[name]

    g = gpd.read_file(DATA / "kontur" / "kontur_population_KE_20231101.gpkg").to_crs(MAP_CRS)
    if "bounds_lonlat" in cfg:
        tf = transformer()
        w, s, e, n = cfg["bounds_lonlat"]
        x0, y0 = tf.transform(w, s)
        x1, y1 = tf.transform(e, n)
        region = box(x0, y0, x1, y1)
        g = g[g.geometry.centroid.within(region)]
        land = region
        water = None
    else:
        land = kenya(MAP_CRS)
        x0, y0, x1, y1 = land.bounds
        lk = lakes(MAP_CRS)
        water = lk[lk.intersects(land)].geometry.union_all().intersection(land)
    pop = g["population"].to_numpy("float64")
    # hexagon rings -> (n, 6, 2), counter-clockwise
    xy = shapely.get_coordinates(g.geometry.values).reshape(len(g), 7, 2)[:, :6]
    area2 = np.sum(xy[:, :, 0] * np.roll(xy[:, :, 1], -1, 1) - np.roll(xy[:, :, 0], -1, 1) * xy[:, :, 1], 1)
    xy[area2 < 0] = xy[area2 < 0][:, ::-1]
    cfg = dict(cfg, crs=MAP_CRS, h3_res=8)
    return draw(plate, cfg, xy, pop, land, water, MAP_CRS,
                f"{name}-population", dpi, spp, t0, bounds=(x0, y0, x1, y1))


def draw(plate, cfg, xy, pop, land, water, crs, slug, dpi, spp, t0, bounds=None):
    """Extrude the hexagons over the land, render, and set the sheet."""
    l, t, r, b = plate.map_box
    x0, y0, x1, y1 = bounds or land.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    total, peak = pop.sum(), pop.max()
    print(f"{slug}: {len(pop):,} hexagons, {total / 1e6:.2f} M people, peak {peak:,.0f}, "
          f"{time.time() - t0:.0f}s")
    xy = xy - np.array([cx, cy])
    # shrink each hexagon a touch so neighbouring columns read as separate
    cen = xy.mean(1, keepdims=True)
    xy = cen + (xy - cen) * 0.92

    height = pop / peak * cfg["max_height_km"] * 1000.0
    # Colour starts at the same density on every plate: 30 people in a
    # resolution-8 hexagon (about 0.74 km2), about 40 per km2, so sparse land
    # stays pale whatever the hexagon size. Each coarser H3 resolution has
    # seven times the area (the rounding below brings it to 28 to 40 per km2).
    floor = 30.0 * 7 ** (8 - cfg["h3_res"])
    if floor >= 100:
        floor = float(round(floor, -int(np.floor(np.log10(floor)))))   # 10 290 -> 10 000
    lo, hi = np.log10(floor), np.log10(peak)
    tcol = np.clip((np.log10(np.maximum(pop, 1)) - lo) / (hi - lo), 0, 1)
    pv, pf, puv = r3.prisms(xy.astype("float32"), np.maximum(height, 1.0),
                            np.column_stack([tcol, np.full(len(tcol), 0.5)]))
    tex = np.repeat(RAMP[None, :, :], 2, 0)

    width_m = x1 - x0
    thickness = width_m * 0.006
    shift = shapely.affinity.translate
    tv, tf_, wv, wf = polygon_slab(shift(land, -cx, -cy), thickness)
    shapes = [dict(verts=pv, faces=pf, uv=puv, texture=tex, flat=True),
              dict(verts=tv, faces=tf_, color=np.array(LAND) / 255, flat=True),
              dict(verts=wv, faces=wf, color=np.array(LAND) / 255 * 0.93, flat=True)]
    if water is not None and not water.is_empty:
        lv, lf, _, _ = polygon_slab(shift(water, -cx, -cy), thickness)
        lv[:, 2] += width_m * 0.0004            # a hair above the land, to avoid z-fighting
        shapes.append(dict(verts=lv, faces=lf, color=np.array(LAKE) / 255, flat=True))

    # camera: looking north, tilted; the model's base centre lands in the map box
    tilt = cfg["tilt"]
    sin_t = np.sin(np.radians(tilt))
    box_w_px = r - l
    m_per_px = width_m / (box_w_px * cfg["model_width"])
    sheet_w = m_per_px * plate.w
    depth_px = (y1 - y0) * sin_t / m_per_px
    mx = (l + r) / 2
    my = (t + b) / 2 + (b - t) * cfg["drop"]            # sit the model low: columns rise above it
    cam_x = (plate.w / 2 - mx) * m_per_px
    cam_y = -(plate.h / 2 - my) * m_per_px / sin_t
    def render():
        return r3.render(
            shapes, plate.w, plate.h, view_width=sheet_w, tilt=tilt, centre=(cam_x, cam_y, 0),
            sun_az=305, sun_el=36, sun_size=8, spp=spp, floor=tuple(np.array(PAPER) / 255),
            floor_z=-thickness, edge_height=thickness,
            progress=lambda i, n: print(f"  tile {i}/{n} {time.time() - t0:.0f}s", flush=True))

    key = dict(plate=slug, size=(plate.w, plate.h), spp=spp, tilt=tilt,
               height=cfg["max_height_km"], width=cfg["model_width"], drop=cfg["drop"],
               hexagons=len(pop), people=round(float(total)))
    rgb, mask = cached_render(key, render)
    place_render(plate, rgb, mask)

    # A few towns, named at the foot of their columns. In this tilted view a
    # point (east, north, up) lands at x = east, y = north sin(tilt) + up cos(tilt).
    tf = transformer("EPSG:4326", crs)
    for town, lon, lat, offset, side in cfg.get("towns", []):
        x, y = tf.transform(lon, lat)
        sx = mx + (x - cx) / m_per_px
        sy = my - (y - cy) * sin_t / m_per_px
        annotate(plate, (sx, sy), town, None, side, leader=offset, size_mm=2.9)

    import regions
    hex_km = "400 M" if cfg["h3_res"] == 8 else f"{2 * regions.H3_EDGE_KM[cfg['h3_res']]:.0f} KM"

    def short(v):
        return f"{v / 1e6:.1f} M" if v >= 1e6 else f"{v:,.0f}".replace(",", " ")

    def legend(d, right, top, pl):
        w, h = pl.px(96), pl.px(3.2)
        xl, yb = right - w, top + pl.px(4.5)
        from PIL import Image
        strip = (RAMP[np.linspace(0, len(RAMP) - 1, int(w)).astype(int)] * 255).astype("uint8")
        pl.img.paste(Image.fromarray(np.repeat(strip[None], max(1, int(h)), 0)), (int(xl), int(yb)))
        f_k = font("Barlow-500", pl.px(2.25))
        f_v = font("IBMPlexMono-400", pl.px(2.3))
        draw_text(d, (xl, top), f"PEOPLE PER {hex_km} HEXAGON", f_k, pl.mix(0.55), 0.2)
        ticks = ([floor] + [10 ** k for k in range(int(np.ceil(lo + 0.3)), int(hi) + 1) if 10 ** k < peak / 2]
                 + [peak])
        for i, v in enumerate(ticks):
            x = xl + np.clip((np.log10(v) - lo) / (hi - lo), 0, 1) * w
            d.line([(x, yb + h), (x, yb + h + pl.px(1.4))], fill=pl.mix(0.5),
                   width=max(1, int(pl.px(0.15))))
            anchor = "ls" if i == 0 else ("rs" if i == len(ticks) - 1 else "ms")
            draw_text(d, (x, yb + h + pl.px(5.0)), short(v), f_v,
                      pl.mix(0.62), 0, anchor)

    lon, lat = transformer(crs, "EPSG:4326").transform(cx, cy)
    summed = "" if cfg["h3_res"] == 8 else f", summed to H3 resolution {cfg['h3_res']} hexagons about {hex_km.lower()} across"
    total_txt = f"{total / 1e9:.2f} billion" if total >= 1e9 else f"{total / 1e6:.1f} million"
    plate.title_block(
        cfg["title"], cfg["subtitle"], cfg["number"],
        facts=[("Column height", f"people per {hex_km.lower()} hexagon"),
               ("Tallest column", f"{peak:,.0f} people".replace(",", " ")),
               ("Total shown", total_txt)],
        credit=f"Population: Kontur Population 2023, 400 m H3 hexagons (CC BY 4.0){summed}. "
               "Boundaries: Natural Earth. Modelled and ray-traced by ZeroPoint Geospatial.",
        centre=(lon, lat), legend=legend, label=cfg.get("label", "PLATE"))
    path = plate.save(slug if dpi >= 250 else f"{slug}_{dpi}")
    print(path, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100,
         int(sys.argv[3]) if len(sys.argv) > 3 else 32)
