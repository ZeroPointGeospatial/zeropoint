"""Any area of the world, for custom plates.

A region is described in a map spec (see maps/README.md) in one of these ways:

    region: { countries: [Kenya, Uganda, Tanzania] }   # Natural Earth country names
    region: { continent: Africa }
    region: { bbox: [33.5, -5.0, 42.0, 5.5] }          # west, south, east, north, degrees
    region: { geojson: path/to/area.geojson }          # any outline, e.g. a farm or a ranch
    region: { county: Kiambu }                          # one of Kenya's 47 counties

This module turns that into an outline, a projection that suits it, a tidy
map scale for the A2 sheet, and elevation data at the right resolution.
"""
import concurrent.futures as cf
import math
from pathlib import Path

import numpy as np

from common import CACHE, DATA, countries, transformer

# Map scales a printed sheet can state without looking odd.
TIDY_SCALES = [10_000, 15_000, 20_000, 25_000, 50_000, 75_000, 100_000, 125_000, 150_000, 175_000,
               200_000, 250_000, 300_000, 350_000, 400_000, 500_000, 600_000, 750_000, 1_000_000,
               1_250_000, 1_500_000, 2_000_000, 2_400_000, 3_000_000, 4_000_000, 4_500_000, 5_000_000,
               6_000_000, 7_500_000, 10_000_000, 12_500_000, 15_000_000, 17_500_000, 20_000_000, 22_500_000,
               25_000_000, 30_000_000, 40_000_000, 50_000_000]

# Natural Earth names that people write differently
ALIASES = {"tanzania": "United Republic of Tanzania", "drc": "Democratic Republic of the Congo",
           "dr congo": "Democratic Republic of the Congo", "congo": "Republic of the Congo",
           "ivory coast": "Ivory Coast", "cote d'ivoire": "Ivory Coast", "usa": "United States of America",
           "uk": "United Kingdom", "swaziland": "eSwatini", "eswatini": "eSwatini",
           "south sudan": "South Sudan", "somaliland": "Somaliland"}


def region_outline(region):
    """(outline in WGS 84, list of ISO 3166 alpha-2 codes it covers, short description)."""
    import geopandas as gpd
    import shapely
    from shapely.geometry import box
    g = countries()
    if "countries" in region:
        names = [ALIASES.get(n.lower(), n) for n in region["countries"]]
        sel = g[g["ADMIN"].isin(names) | g["NAME"].isin(names)]
        missing = set(names) - set(sel["ADMIN"]) - set(sel["NAME"])
        if missing:
            raise SystemExit(f"unknown countries {sorted(missing)}; names follow Natural Earth's ADMIN column")
        what = ", ".join(region["countries"])
    elif "continent" in region:
        sel = g[g["CONTINENT"] == region["continent"]]
        if sel.empty:
            raise SystemExit(f"unknown continent {region['continent']!r}; one of {sorted(set(g['CONTINENT']))}")
        what = region["continent"]
    elif "bbox" in region:
        w, s, e, n = region["bbox"]
        geom = box(w, s, e, n)
        sel = g[g.intersects(geom)]
        return geom, iso_codes(sel), f"{w}..{e} E, {s}..{n} N"
    elif "geojson" in region:
        shp = gpd.read_file(region["geojson"]).to_crs("EPSG:4326")
        geom = shapely.make_valid(shp.geometry.union_all())
        return geom, iso_codes(g[g.intersects(geom)]), Path(region["geojson"]).stem
    elif "county" in region:
        from common import CACHE as C
        c = gpd.read_file(C / "kenya_counties.gpkg")
        c = c[c["name"].str.lower() == region["county"].lower()]
        if c.empty:
            raise SystemExit(f"no county called {region['county']!r}")
        return shapely.make_valid(c.geometry.union_all()), ["KE"], region["county"] + " County"
    else:
        raise SystemExit("region needs one of: countries, continent, bbox, geojson, county")
    geom = shapely.make_valid(sel.geometry.union_all())
    if not region.get("keep_islands"):
        geom = drop_far_islands(geom)
    return geom, iso_codes(sel), what


def drop_far_islands(geom_ll, keep_km2=2500, near_km=60, near_min_km2=50):
    """Leave out small islands far from the coast (Cape Verde, the Comoros, the
    Prince Edward Islands for Africa). On a relief model they become spikes and
    they stretch the frame. Large islands (Madagascar) and those just offshore
    (Zanzibar, Bioko) stay. Set keep_islands: true in a spec to keep them all."""
    import shapely
    from shapely.geometry import MultiPolygon
    parts = list(getattr(geom_ll, "geoms", [geom_ll]))
    if len(parts) < 2:
        return geom_ll
    w, s, e, n = geom_ll.bounds
    crs = f"+proj=laea +lat_0={(s + n) / 2:.2f} +lon_0={(w + e) / 2:.2f} +datum=WGS84 +units=m"
    proj = [project(p, crs) for p in parts]
    areas = [p.area / 1e6 for p in proj]
    main = proj[int(np.argmax(areas))]
    keep = [p for p, q, a in zip(parts, proj, areas)
            if a >= keep_km2 or (a >= near_min_km2 and q.distance(main) <= near_km * 1000)]
    dropped = len(parts) - len(keep)
    if dropped:
        print(f"  left out {dropped} small islands far from the coast")
    return shapely.make_valid(MultiPolygon(keep)) if len(keep) > 1 else keep[0]


def iso_codes(sel):
    codes = [c for c in sel["ISO_A2_EH"] if isinstance(c, str) and len(c) == 2]
    if "Somaliland" in set(sel["ADMIN"]) and "SO" not in codes:
        codes.append("SO")                     # Kontur counts Somaliland with Somalia
    return sorted(set(codes))


def projection_for(geom_ll, override=None):
    """(proj string or EPSG code, its name for the sheet). UTM for small areas, so
    distances read true; Lambert azimuthal equal-area centred on the area for large
    ones, so a continent keeps its true proportions of area."""
    if override:
        return override, override
    w, s, e, n = geom_ll.bounds
    lon0, lat0 = (w + e) / 2, (s + n) / 2
    if e - w <= 6 and n - s <= 10:
        zone = int((lon0 + 180) // 6) + 1
        epsg = (32600 if lat0 >= 0 else 32700) + zone
        return f"EPSG:{epsg}", f"UTM zone {zone}{'N' if lat0 >= 0 else 'S'}, WGS 84"
    return (f"+proj=laea +lat_0={lat0:.2f} +lon_0={lon0:.2f} +datum=WGS84 +units=m +no_defs",
            "Lambert azimuthal equal-area")


def project(geom_ll, crs):
    import shapely
    from shapely.ops import transform
    t = transformer("EPSG:4326", crs)
    return shapely.make_valid(transform(lambda x, y: t.transform(x, y), geom_ll))


def tidy_scale(width_m, height_m, box_mm, fill=(0.94, 0.93)):
    need = max(width_m / (box_mm[0] * fill[0] / 1000), height_m / (box_mm[1] * fill[1] / 1000))
    return next((s for s in TIDY_SCALES if s >= need), TIDY_SCALES[-1])


def scale_label(scale):
    return f"1:{scale:,}".replace(",", " ")


def default_exaggeration(width_m, relief_m):
    """Enough height to read from across a room: modest for a county, strong for
    a continent, where mountains are a few millimetres wide."""
    relief_m = max(relief_m, 250)
    if width_m < 300_000:
        return float(np.clip(round(0.07 * width_m / relief_m), 3, 12))
    return float(np.clip(round(0.12 * width_m / relief_m), 3, 100))


# --------------------------------------------------------------------------- elevation

def _tile_url(lat, lon, source):
    arcsec, res = (30, "90m") if source == "glo90" else (10, "30m")
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    name = f"Copernicus_DSM_COG_{arcsec}_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
    return f"https://copernicus-dem-{res}.s3.amazonaws.com/{name}/{name}.tif"


def load_dem_coarse(bbox, res_deg, source="glo90", land=None, workers=24):
    """Copernicus DEM over bbox = (w, s, e, n) at res_deg degrees, read straight from
    the cloud-optimised tiles at reduced resolution, so a continent costs a few
    hundred megabytes of requests rather than many gigabytes of downloads. Tiles
    that do not touch `land` (a WGS 84 geometry) are not requested. Cached."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from shapely.geometry import box
    w, s, e, n = (math.floor(bbox[0]), math.floor(bbox[1]), math.ceil(bbox[2]), math.ceil(bbox[3]))
    per = max(1, round(1 / res_deg))                     # cells per one-degree tile
    key = f"coarse_{source}_{w}_{s}_{e}_{n}_{per}".replace("-", "m")
    npy, meta = CACHE / f"{key}.npy", CACHE / f"{key}.txt"
    tr = Affine(1 / per, 0, w, 0, -1 / per, n)
    if npy.exists():
        return np.load(npy), tr
    arr = np.zeros(((n - s) * per, (e - w) * per), dtype="float32")
    jobs = [(lat, lon) for lat in range(s, n) for lon in range(w, e)
            if land is None or land.intersects(box(lon, lat, lon + 1, lat + 1))]
    print(f"  elevation: {len(jobs)} tiles at {per} cells per degree")
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
               GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="FALSE")

    def read(job):
        lat, lon = job
        try:
            with rasterio.Env(**env), rasterio.open("/vsicurl/" + _tile_url(lat, lon, source)) as src:
                return job, src.read(1, out_shape=(per, per), resampling=Resampling.average)
        except rasterio.errors.RasterioIOError:
            return job, None                                  # ocean: no tile

    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for (lat, lon), a in ex.map(read, jobs):
            done += 1
            if a is not None:
                r0, c0 = (n - lat - 1) * per, (lon - w) * per
                arr[r0:r0 + per, c0:c0 + per] = a
            if done % 250 == 0:
                print(f"  {done}/{len(jobs)} tiles", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(npy, arr)
    meta.write_text(" ".join(repr(v) for v in tuple(tr)[:6]))
    return arr, tr


# --------------------------------------------------------------------------- population

KONTUR = ("https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/kontur_datasets/"
          "kontur_population_{iso}_20231101.gpkg.gz")

# Mean H3 hexagon edge length in km, by resolution
H3_EDGE_KM = {4: 22.6, 5: 8.54, 6: 3.23, 7: 1.22, 8: 0.46}


def kontur_file(iso):
    """Kontur Population 2023 for one country (ISO alpha-2), downloaded once."""
    import gzip
    import shutil
    from fetch_data import fetch
    gpkg = DATA / "kontur" / f"kontur_population_{iso}_20231101.gpkg"
    if not gpkg.exists():
        gz = gpkg.with_suffix(".gpkg.gz")
        state = fetch(KONTUR.format(iso=iso), gz, quiet=True)
        if state == "absent":
            return None
        with gzip.open(gz, "rb") as fi, open(gpkg, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        gz.unlink()
    return gpkg


def h3_resolution_for(scale, target_mm=0.35):
    """The H3 resolution whose hexagons print about `target_mm` across at this scale."""
    want_km = target_mm * scale / 1e6
    return min(H3_EDGE_KM, key=lambda r: abs(math.log(H3_EDGE_KM[r] / want_km)))


def population_hexagons(iso_codes, res, outline_ll=None):
    """People per H3 hexagon at resolution `res` (8 is Kontur's own 400 m grid;
    coarser resolutions sum it). Returns (h3 cells, population)."""
    import h3
    import pyogrio
    cells, pops = [], []
    for iso in iso_codes:
        path = kontur_file(iso)
        if path is None:
            print(f"  no Kontur file for {iso}")
            continue
        df = pyogrio.read_dataframe(path, columns=["h3", "population"], read_geometry=False)
        cells.append(df["h3"].to_numpy())
        pops.append(df["population"].to_numpy("float64"))
        print(f"  {iso}: {len(df):,} hexagons, {df['population'].sum() / 1e6:.1f} M people")
    c = np.concatenate(cells)
    p = np.concatenate(pops)
    if res < 8:
        parent = np.array([h3.cell_to_parent(x, res) for x in c])
        uniq, inv = np.unique(parent, return_inverse=True)
        p = np.bincount(inv, weights=p)
        c = uniq
    else:
        uniq, inv = np.unique(c, return_inverse=True)  # a hexagon on a border appears in both countries
        p = np.bincount(inv, weights=p)
        c = uniq
    if outline_ll is not None:
        from shapely import points, intersects
        ll = np.array([h3.cell_to_latlng(x) for x in c])
        keep = intersects(outline_ll.buffer(0.05), points(ll[:, 1], ll[:, 0]))
        c, p = c[keep], p[keep]
    return c, p


def hexagon_rings(cells, crs):
    """(n, 6, 2) projected corner coordinates, counter-clockwise; pentagons dropped."""
    import h3
    t = transformer("EPSG:4326", crs)
    rings, keep = [], []
    for i, x in enumerate(cells):
        b = h3.cell_to_boundary(x)
        if len(b) != 6:
            continue
        lat, lon = zip(*b)
        X, Y = t.transform(lon, lat)
        rings.append(np.column_stack([X, Y]))
        keep.append(i)
    xy = np.array(rings)
    a2 = np.sum(xy[:, :, 0] * np.roll(xy[:, :, 1], -1, 1) - np.roll(xy[:, :, 0], -1, 1) * xy[:, :, 1], 1)
    xy[a2 < 0] = xy[a2 < 0][:, ::-1]
    return xy, np.array(keep)
