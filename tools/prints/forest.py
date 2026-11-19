"""Tree canopy cover for Kenya from the Hansen / UMD Global Forest Change
dataset: per cent canopy in the year 2000, with every 30 m cell that lost
its tree cover between 2001 and 2023 set to zero, averaged to about 220 m.

    python fetch_data.py forest    # once, about 1.5 GB

Used by `relief.py kenya-forest`.
"""
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

from common import CACHE, DATA, kenya, rasterize_geom

PX = 0.00025                                # native cell, degrees (about 28 m)
BLOCK = 8                                   # 8 x 8 cells: divides the 40 000 px tiles evenly
BBOX = (33.8, -4.9, 42.0, 5.6)              # w, s, e, n: multiples of BLOCK * PX
TILES = {"10N_030E": (30, 10), "10N_040E": (40, 10), "00N_030E": (30, 0), "00N_040E": (40, 0)}


def canopy_grid():
    """Returns (mean canopy 0..1, share of each cell with >= 30 % canopy, transform)."""
    f = CACHE / "kenya_canopy.npz"
    if f.exists():
        z = np.load(f)
        return z["mean"], z["dense"], Affine(*z["transform"])
    step = PX * BLOCK
    w, s, e, n = BBOX
    nc, nr = int(round((e - w) / step)), int(round((n - s) / step))
    mean = np.zeros((nr, nc), "float32")
    dense = np.zeros((nr, nc), "float32")
    for tile, (tw, tn) in TILES.items():
        c0 = int(round((max(w, tw) - tw) / PX))
        c1 = int(round((min(e, tw + 10) - tw) / PX))
        r0 = int(round((tn - min(n, tn)) / PX))
        r1 = int(round((tn - max(s, tn - 10)) / PX))
        if c1 <= c0 or r1 <= r0:
            continue
        with rasterio.open(DATA / "hansen" / f"treecover2000_{tile}.tif") as tc, \
                rasterio.open(DATA / "hansen" / f"lossyear_{tile}.tif") as ly:
            rows = BLOCK * 500
            for ra in range(r0, r1, rows):
                rb = min(ra + rows, r1)
                win = Window(c0, ra, c1 - c0, rb - ra)
                cover = tc.read(1, window=win).astype("float32")
                cover[ly.read(1, window=win) > 0] = 0
                h, wd = cover.shape[0] // BLOCK, cover.shape[1] // BLOCK
                blk = cover.reshape(h, BLOCK, wd, BLOCK)
                gr = int(round((n - (tn - ra * PX)) / step))
                gc = int(round(((tw + c0 * PX) - w) / step))
                mean[gr:gr + h, gc:gc + wd] = blk.mean((1, 3)) / 100
                dense[gr:gr + h, gc:gc + wd] = (blk >= 30).mean((1, 3))
        print(f"  forest tile {tile} done", flush=True)
    tr = Affine(step, 0, w, 0, -step, n)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, mean=mean, dense=dense, transform=np.array(tuple(tr)[:6]))
    return mean, dense, tr


def kenya_stats(dense, tr):
    """Area of Kenya with at least 30 % canopy, and Kenya's land area, in km2."""
    kmask = rasterize_geom(kenya(), dense.shape, tr)
    lat = tr.f + tr.e * (np.arange(dense.shape[0]) + 0.5)
    cell_km2 = (abs(tr.e) * 110.57) * (tr.a * 111.32 * np.cos(np.radians(lat)))
    land = float((kmask * cell_km2[:, None]).sum())
    forest = float((dense * kmask * cell_km2[:, None]).sum())
    return forest, land
