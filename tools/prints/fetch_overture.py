"""Fetch vector data for Kenya from Overture Maps: road centre lines
(built from OpenStreetMap) and county boundaries.

    python fetch_overture.py roads
    python fetch_overture.py counties
    python fetch_overture.py roads-bbox 32.45,0.20,32.75,0.45 kampala   # any area, for a city print

Overture publishes GeoParquet on S3. The files are spatially sorted and
every row group carries bounding-box statistics, so this script reads only
the file footers plus the few row groups that touch Kenya (a few hundred MB
out of tens of GB), over plain HTTPS range requests.

Outputs, in $ZP_DATA/cache:
  kenya_roads.npz      line vertices in lon/lat, line offsets, class per line
  kenya_counties.gpkg  the 47 counties as polygons with their names

Licence: OpenStreetMap contributors, Overture Maps Foundation, ODbL 1.0.
"""
import concurrent.futures as cf
import io
import re
import sys

import numpy as np
import pyarrow.parquet as pq
import requests
import shapely

from common import CACHE

BUCKET = "https://overturemaps-us-west-2.s3.amazonaws.com/"
BBOX = (33.85, -4.80, 41.95, 5.55)          # Kenya: w, s, e, n

# Drawing classes, most important first.
CLASSES = {
    "motorway": 0, "trunk": 0,
    "primary": 1,
    "secondary": 2,
    "tertiary": 3,
    "unclassified": 4, "residential": 4, "living_street": 4,
    "service": 5, "track": 5, "pedestrian": 5,
}


class RangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests, with block caching."""

    BLOCK = 4 << 20

    def __init__(self, url, session=None):
        self.url, self.pos = url, 0
        self.s = session or requests.Session()
        # A one-byte ranged GET gives the size reliably ("bytes 0-0/12345");
        # HEAD does not always carry Content-Length through a proxy.
        r = self.s.get(url, headers={"Range": "bytes=0-0"}, timeout=60)
        r.raise_for_status()
        self.size = int(r.headers["Content-Range"].split("/")[1])
        self.blocks = {}

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _block(self, i):
        if i not in self.blocks:
            a = i * self.BLOCK
            b = min(a + self.BLOCK, self.size) - 1
            for attempt in range(5):
                try:
                    r = self.s.get(self.url, headers={"Range": f"bytes={a}-{b}"}, timeout=180)
                    r.raise_for_status()
                    self.blocks[i] = r.content
                    break
                except requests.RequestException:
                    if attempt == 4:
                        raise
        return self.blocks[i]

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            i, o = divmod(self.pos, self.BLOCK)
            chunk = self._block(i)[o:o + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def latest_release():
    xml = requests.get(BUCKET, params={"list-type": 2, "prefix": "release/", "delimiter": "/"},
                       timeout=60).text
    return sorted(re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", xml))[-1]


def list_files(release, theme="transportation", kind="segment"):
    prefix = f"release/{release}/theme={theme}/type={kind}/"
    xml = requests.get(BUCKET, params={"list-type": 2, "prefix": prefix, "max-keys": 1000},
                       timeout=60).text
    return [BUCKET + k for k in re.findall(r"<Key>([^<]+\.parquet)</Key>", xml)]


def touching_row_groups(url):
    """Row groups of one file whose bbox statistics overlap Kenya."""
    f = RangeFile(url)
    md = pq.ParquetFile(f).metadata
    names = [md.schema.column(i).path for i in range(md.num_columns)]
    ix = {k: names.index(f"bbox.{k}") for k in ("xmin", "xmax", "ymin", "ymax")}
    hits = []
    for g in range(md.num_row_groups):
        rg = md.row_group(g)
        st = {k: rg.column(i).statistics for k, i in ix.items()}
        if any(s is None or not s.has_min_max for s in st.values()):
            hits.append(g)
            continue
        if (st["xmax"].max >= BBOX[0] and st["xmin"].min <= BBOX[2]
                and st["ymax"].max >= BBOX[1] and st["ymin"].min <= BBOX[3]):
            hits.append(g)
    return url, hits


def read_group(job):
    url, g = job
    t = pq.ParquetFile(RangeFile(url)).read_row_group(
        g, columns=["geometry", "subtype", "class", "bbox"])
    bb = t.column("bbox").combine_chunks()
    xmin, xmax = bb.field("xmin").to_numpy(), bb.field("xmax").to_numpy()
    ymin, ymax = bb.field("ymin").to_numpy(), bb.field("ymax").to_numpy()
    sub = np.array(t.column("subtype").to_pylist(), dtype=object)
    cls = np.array(t.column("class").to_pylist(), dtype=object)
    keep = ((xmax >= BBOX[0]) & (xmin <= BBOX[2]) & (ymax >= BBOX[1]) & (ymin <= BBOX[3])
            & (sub == "road"))
    code = np.array([CLASSES.get(c, -1) for c in cls])
    keep &= code >= 0
    wkb = t.column("geometry").combine_chunks().filter(keep).to_pylist()
    geoms = shapely.from_wkb(wkb)
    return geoms, code[keep]


def roads(release, bbox=None, name="kenya_roads"):
    """Roads inside bbox (default: Kenya), saved as $ZP_DATA/cache/<name>.npz."""
    global BBOX
    if bbox:
        BBOX = tuple(bbox)
    files = list_files(release)
    print(f"Overture {release}: {len(files)} segment files")
    with cf.ThreadPoolExecutor(12) as ex:
        hits = [(u, g) for u, gs in ex.map(touching_row_groups, files) for g in gs]
    print(f"{len(hits)} row groups in {len({u for u, _ in hits})} files touch {BBOX}")
    geoms, codes = [], []
    with cf.ThreadPoolExecutor(6) as ex:
        for i, (g, c) in enumerate(ex.map(read_group, hits)):
            geoms.append(g)
            codes.append(c)
            print(f"  {i + 1}/{len(hits)}  {sum(len(x) for x in geoms):,} roads", flush=True)
    geoms, codes = np.concatenate(geoms), np.concatenate(codes)
    simple = shapely.get_type_id(geoms) == 1                    # LineString
    geoms, codes = geoms[simple], codes[simple]
    xy, idx = shapely.get_coordinates(geoms, return_index=True)
    offs = np.concatenate([[0], np.cumsum(np.bincount(idx, minlength=len(geoms)))])
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE / f"{name}.npz", xy=xy.astype("float32"), offs=offs,
                        code=codes.astype("int8"), release=release)
    print(f"saved {len(geoms):,} roads, {len(xy):,} vertices; "
          f"per class: {np.bincount(codes).tolist()}")


def read_counties(job):
    url, g = job
    t = pq.ParquetFile(RangeFile(url)).read_row_group(
        g, columns=["geometry", "subtype", "country", "class", "names", "region"])
    sub = np.array(t.column("subtype").to_pylist(), dtype=object)
    cty = np.array(t.column("country").to_pylist(), dtype=object)
    cls = np.array(t.column("class").to_pylist(), dtype=object)
    keep = (sub == "region") & (cty == "KE") & (cls == "land")
    if not keep.any():
        return []
    rows = t.filter(keep).to_pylist()
    return [(r["names"]["primary"], r["region"], shapely.from_wkb(r["geometry"])) for r in rows]


def counties(release):
    import geopandas as gpd
    files = list_files(release, "divisions", "division_area")
    with cf.ThreadPoolExecutor(12) as ex:
        hits = [(u, g) for u, gs in ex.map(touching_row_groups, files) for g in gs]
    print(f"Overture {release}: {len(hits)} division row groups touch Kenya")
    rows = []
    with cf.ThreadPoolExecutor(6) as ex:
        for part in ex.map(read_counties, hits):
            rows += part
    g = gpd.GeoDataFrame({"name": [r[0] for r in rows], "code": [r[1] for r in rows]},
                         geometry=[r[2] for r in rows], crs="EPSG:4326")
    g = g.drop_duplicates("code").sort_values("name").reset_index(drop=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    g.to_file(CACHE / "kenya_counties.gpkg", driver="GPKG")
    print(f"saved {len(g)} counties: " + ", ".join(g["name"].head(8)) + " ...")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "roads"
    if what == "roads-bbox":
        bbox = [float(v) for v in sys.argv[2].split(",")]
        roads(latest_release(), bbox, f"roads_{sys.argv[3]}")
        return
    release = sys.argv[2] if len(sys.argv) > 2 else latest_release()
    {"roads": roads, "counties": counties}[what](release)


if __name__ == "__main__":
    main()
