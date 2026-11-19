"""Compute Kenya's drainage network from the Copernicus GLO-90 surface.

Output: $ZP_DATA/cache/kenya_hydro.npz with the traced stream lines (in
map coordinates), their upstream areas and basin classes, plus a raster of
standing water. `kenya_rivers.py` draws the plate from that file.

Method
  1. Mosaic GLO-90 over Kenya plus a margin wide enough to hold the upper
     catchments, block-averaged to 6 arc-seconds (about 185 m).
  2. Priority-Flood from the sea, the edge of the sheet and the terminal
     (endorheic) lakes and pans, so closed basins stay closed while DEM
     noise and reservoirs are flooded through. A second pass also keeps
     every other deep closed depression open (calderas such as Menengai,
     Suswa and Silali, Lake Solai, desert pans) instead of flooding it.
  3. D8 routing by steepest descent, flow accumulation in km2.
  4. Each cell is labelled with the outlet it reaches, and outlets are
     grouped into Kenya's five drainage basins.
"""
import sys
import time

import numpy as np
from rasterio.transform import rowcol
from scipy import ndimage

import hydro
from common import CACHE, DATA, kenya, load_dem, rasterize_geom, transformer

BBOX = (32, -6, 43, 7)          # w, s, e, n
THRESHOLD_KM2 = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0

# Terminal lakes and dry pans: (name, lon, lat, basin, tolerance m)
# basin: 1 Lake Victoria, 2 Rift Valley, 5 Ewaso Ng'iro North
SINKS = [
    ("Lake Victoria", 33.30, -1.00, 1, 0.6),
    ("Lake Turkana", 36.10, 3.50, 2, 0.6),
    ("Lake Logipi", 36.56, 2.23, 2, 1.5),
    ("Lake Baringo", 36.08, 0.62, 2, 0.6),
    ("Lake Bogoria", 36.10, 0.25, 2, 0.6),
    ("Lake Nakuru", 36.09, -0.37, 2, 0.6),
    ("Lake Elmenteita", 36.24, -0.44, 2, 0.6),
    ("Lake Naivasha", 36.35, -0.77, 2, 0.6),
    ("Lake Magadi", 36.27, -1.90, 2, 1.5),
    ("Lake Natron", 36.02, -2.35, 2, 1.5),
    ("Chew Bahir", 36.90, 4.70, 2, 1.5),
    ("Lotikipi Plain", 34.85, 4.45, 2, 1.5),
    ("Lake Amboseli", 37.13, -2.62, 3, 1.5),
    ("Chalbi Desert", 37.546, 2.916, 5, 1.5),
    ("Lake Eyasi", 35.00, -3.60, 0, 1.5),
    ("Lake Manyara", 35.82, -3.60, 0, 1.5),
]

BASINS = {1: "Lake Victoria", 2: "Rift Valley", 3: "Athi", 4: "Tana", 5: "Ewaso Ng'iro North"}


def main():
    t0 = time.time()
    dem, tr = load_dem(BBOX, "glo90", factor=2)
    dem = np.ascontiguousarray(dem, dtype="float32")
    nr, nc = dem.shape
    cell_deg = tr.a
    print(f"DEM {dem.shape}, cell {cell_deg * 3600:.1f} arc-sec, {time.time() - t0:.0f}s")

    import geopandas as gpd
    from shapely.geometry import box
    ocean = gpd.read_file(DATA / "ne" / "ne_10m_ocean").clip(box(*BBOX)).geometry.union_all()
    sea = rasterize_geom(ocean, dem.shape, tr) & (dem <= 0.5)

    seeds = sea.copy()
    seeds[0, :] = seeds[-1, :] = True
    seeds[:, 0] = seeds[:, -1] = True
    sink_class = np.zeros(dem.shape, dtype="uint8")
    for name, lon, lat, basin, tol in SINKS:
        r, c = rowcol(tr, lon, lat)
        # start from the lowest cell within ~6 km so a dry pan is seeded at its floor
        w = 32
        win = dem[r - w:r + w + 1, c - w:c + w + 1]
        dr, dc = np.unravel_index(np.argmin(win), win.shape)
        r, c = r - w + dr, c - w + dc
        m = hydro.flood_region(dem, r, c, tol, 12_000_000)
        seeds |= m
        sink_class[m] = 100 + basin
        print(f"  {name:16s} {dem[r, c]:7.1f} m  {m.sum() * (cell_deg * 111.2) ** 2:9.0f} km2")

    lat = tr.f + tr.e * (np.arange(nr) + 0.5)
    cell_km2 = (cell_deg * 111.32) ** 2 * np.cos(np.radians(lat))
    weight = np.repeat(cell_km2.astype("float32")[:, None], nc, 1)

    def route():
        _, recv, filled = hydro.priority_flood(dem, seeds)
        recv = hydro.steepest_receivers(filled, recv, seeds)
        root = hydro.outlet_of(recv)
        rr, rc = root // nc, root % nc
        root_lat = (tr.f + tr.e * (rr + 0.5)).reshape(dem.shape)
        root_lon = (tr.c + tr.a * (rc + 0.5)).reshape(dem.shape)
        root_sink = sink_class.ravel()[root].reshape(dem.shape)
        root_sea = sea.ravel()[root].reshape(dem.shape)
        basin = np.zeros(dem.shape, dtype="uint8")
        basin[root_sink > 100] = (root_sink[root_sink > 100] - 100)
        # Indian Ocean outlets, split by where the mouth lies along the coast
        basin[root_sea & (root_lat < -2.90)] = 3                        # Athi-Galana-Sabaki, south coast
        basin[root_sea & (root_lat >= -2.90) & (root_lat < -1.66)] = 4  # Tana, Lamu coast
        basin[root_sea & (root_lat >= -1.66)] = 5                       # Lagh Dera / Juba
        edge = (basin == 0) & (root_sink == 0) & ~root_sea
        basin[edge & (root_lon > 42.9)] = 5                             # east edge: Somalia
        basin[edge & (root_lon < 32.1)] = 1                             # west edge: Nile system
        basin[edge & (root_lat > 6.9)] = 5
        basin[edge & (root_lat < -5.9)] = 3
        return recv, filled, basin

    recv, filled, basin = route()
    print(f"first pass {time.time() - t0:.0f}s")

    # Second pass. A depression deeper than 10 m and wider than 10 km2 is a
    # real closed basin (a caldera, a pan), not DEM noise: seed its floor so
    # it stays open, and class it with the basin it would have spilled into.
    depth = filled - dem
    lab, n = ndimage.label(depth > 10)
    size = ndimage.sum(depth > 10, lab, np.arange(1, n + 1)) * (cell_deg * 111.32) ** 2
    keep = np.nonzero(size >= 10)[0]
    for i in keep:
        r, c = ndimage.maximum_position(depth, lab, i + 1)
        seeds[r, c] = True
        sink_class[r, c] = 100 + basin[r, c]
    print(f"  {len(keep)} further closed basins kept open")
    recv, filled, basin = route()
    acc = hydro.flow_accumulation(filled, recv, weight)
    print(f"second pass {time.time() - t0:.0f}s, largest catchment {acc.max():.0f} km2")

    ke = rasterize_geom(kenya(), dem.shape, tr)
    for k, name in BASINS.items():
        print(f"  basin {k} {name:20s} {(weight[(basin == k) & ke]).sum():9.0f} km2 in Kenya")
    print(f"  unclassified in Kenya: {(weight[(basin == 0) & ke]).sum():.0f} km2")

    # standing water: flat DEM facets of 2 km2 or more (lakes, reservoirs)
    gy, gx = np.gradient(dem)
    flat = (np.abs(gx) + np.abs(gy) == 0) & ~sea
    flat = ndimage.binary_opening(flat, iterations=1)
    lab, n = ndimage.label(flat)
    sizes = ndimage.sum(flat, lab, np.arange(1, n + 1)) * cell_km2.mean()
    water = np.isin(lab, np.nonzero(sizes >= 2.0)[0] + 1)
    water = ndimage.binary_dilation(water, iterations=1)

    stream = (acc >= THRESHOLD_KM2) & ke & ~water
    rows, cols, offs, area = hydro.trace_streams(recv, acc, stream, dem.shape)
    print(f"{len(area)} stream lines, {stream.sum()} cells, {time.time() - t0:.0f}s")

    tf = transformer()
    x, y = tf.transform(tr.c + tr.a * (cols + 0.5), tr.f + tr.e * (rows + 0.5))
    line_basin = basin[rows[offs[:-1]], cols[offs[:-1]]]

    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE / "kenya_hydro.npz", x=x.astype("float32"), y=y.astype("float32"),
        offs=offs, area=area, basin=line_basin, water=np.packbits(water),
        water_shape=np.array(water.shape), transform=np.array(tuple(tr)[:6]),
        basin_grid=basin[::4, ::4], threshold=THRESHOLD_KM2)
    print(f"saved, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
