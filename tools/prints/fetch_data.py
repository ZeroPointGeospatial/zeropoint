"""Download the open datasets the print pipeline is built from.

    python fetch_data.py dem90        # Copernicus GLO-90 tiles, Kenya + margin
    python fetch_data.py dem30 NAME   # Copernicus GLO-30 tiles for one landform
    python fetch_data.py population   # Kontur Population, Kenya, 400 m H3
    python fetch_data.py naturalearth # country outline, lakes, ocean, places
    python fetch_data.py forest       # Hansen Global Forest Change tiles
    python fetch_data.py fonts        # typefaces used on the plates
    python fetch_data.py rainfall     # CHIRPS mean annual rainfall, 1991-2020

Everything lands in $ZP_DATA (default: ./data next to this file). Nothing
here is committed to the site repo: the files are large and all of them are
re-downloadable.

Sources and licences
  Copernicus DEM GLO-30 / GLO-90  (c) DLR e.V. 2010-2014 and (c) Airbus Defence
      and Space GmbH 2014-2018, provided under COPERNICUS by the European
      Union and ESA. Free for any use, attribution required.
  Kontur Population 2023          CC BY 4.0, Kontur Inc.
  Natural Earth                   public domain.
  Hansen/UMD/Google/USGS/NASA     Global Forest Change 2000-2023 v1.11,
      CC BY 4.0 (Hansen et al., Science 342, 2013).
  CHIRPS v2.0 rainfall            Climate Hazards Center, UC Santa Barbara,
      public domain; read from Digital Earth Africa's copy on AWS.
  Barlow, IBM Plex Mono, Playfair Display   SIL Open Font License 1.1.
"""
import concurrent.futures as cf
import gzip
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

import requests

DATA = Path(os.environ.get("ZP_DATA", Path(__file__).parent / "data"))

# lon_min, lat_min, lon_max, lat_max (whole degrees, max exclusive)
KENYA_MARGIN = (32, -6, 43, 7)
LANDFORMS = {
    "mount-kenya": (36, -1, 38, 1),
    "kilimanjaro": (36, -4, 38, -2),
    "rift": (35, -2, 37, 1),
}


def tile_name(lat, lon, arcsec):
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_{arcsec}_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch(url, dest, quiet=False):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        if r.status_code in (403, 404):
            return "absent"  # open-ocean DEM tiles do not exist
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    if not quiet:
        print(f"  {dest.name}  {dest.stat().st_size / 1e6:.1f} MB")
    return "ok"


def dem(bbox, arcsec, sub):
    res = {10: "30m", 30: "90m"}[arcsec]
    jobs = []
    for lat in range(bbox[1], bbox[3]):
        for lon in range(bbox[0], bbox[2]):
            n = tile_name(lat, lon, arcsec)
            url = f"https://copernicus-dem-{res}.s3.amazonaws.com/{n}/{n}.tif"
            jobs.append((url, DATA / sub / f"{n}.tif"))
    with cf.ThreadPoolExecutor(8) as ex:
        out = list(ex.map(lambda j: fetch(j[0], j[1], quiet=True), jobs))
    print(f"{sub}: {out.count('ok')} downloaded, {out.count('cached')} cached, "
          f"{out.count('absent')} ocean tiles skipped")


def population():
    gz = DATA / "kontur" / "kontur_population_KE_20231101.gpkg.gz"
    print(fetch("https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/"
                "kontur_datasets/kontur_population_KE_20231101.gpkg.gz", gz))
    out = gz.with_suffix("")
    if not out.exists():
        with gzip.open(gz, "rb") as a, open(out, "wb") as b:
            shutil.copyfileobj(a, b)


def naturalearth():
    layers = [
        ("10m_cultural", "ne_10m_admin_0_countries"),
        ("10m_cultural", "ne_10m_admin_1_states_provinces"),
        ("10m_cultural", "ne_10m_populated_places"),
        ("10m_physical", "ne_10m_lakes"),
        ("10m_physical", "ne_10m_ocean"),
        ("10m_physical", "ne_10m_rivers_lake_centerlines"),
    ]
    for group, name in layers:
        z = DATA / "ne" / f"{name}.zip"
        print(name, fetch(f"https://naturalearth.s3.amazonaws.com/{group}/{name}.zip", z))
        with zipfile.ZipFile(z) as f:
            f.extractall(DATA / "ne" / name)


def forest():
    base = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/"
    jobs = [(f"{base}Hansen_GFC-2023-v1.11_{layer}_{tile}.tif",
             DATA / "hansen" / f"{layer}_{tile}.tif")
            for layer in ("treecover2000", "lossyear")
            for tile in ("10N_030E", "10N_040E", "00N_030E", "00N_040E")]
    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda j: fetch(*j), jobs))


def fonts():
    """Static TTFs straight from Google Fonts (an old UA gets TTF, not WOFF2)."""
    wanted = {
        "Barlow": "wght@300;400;500;600;700",
        "Barlow:ital": "ital,wght@1,400;1,500",
        "IBM Plex Mono": "wght@400;500",
        "Playfair Display": "wght@400;500;600",
    }
    for family, axes in wanted.items():
        name, italic = family.split(":")[0], family.endswith(":ital")
        css = requests.get(
            "https://fonts.googleapis.com/css2",
            params={"family": f"{name}:{axes}"},
            headers={"User-Agent": "Mozilla/4.0"}, timeout=60).text
        for weight, url in re.findall(
                r"font-weight:\s*(\d+);.*?url\((https://[^)]+\.ttf)\)", css, re.S):
            stem = f"{name.replace(' ', '')}{'Italic' if italic else ''}-{weight}"
            fetch(url, DATA / "fonts" / f"{stem}.ttf")


def rainfall(first=1991, last=2020):
    """Mean annual rainfall over Kenya and its catchments, in mm, from the
    CHIRPS monthly grids. Each month is read as a small window straight from
    the cloud-optimised GeoTIFF, so only a few hundred kB are transferred."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds

    base = "https://deafrica-input-datasets.s3.af-south-1.amazonaws.com/rainfall_chirps_monthly/"
    w, s, e, n = KENYA_MARGIN
    jobs = [f"{base}chirps-v2.0_{y}.{m:02d}.tif" for y in range(first, last + 1) for m in range(1, 13)]
    env = dict(GDAL_HTTP_PROXY=os.environ.get("HTTPS_PROXY", ""),
               CURL_CA_BUNDLE=os.environ.get("CURL_CA_BUNDLE", ""),
               GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4")

    def month(url):
        with rasterio.Env(**env), rasterio.open("/vsicurl/" + url) as ds:
            win = from_bounds(w, s, e, n, ds.transform).round_offsets().round_lengths()
            return ds.read(1, window=win), ds.window_transform(win)

    with cf.ThreadPoolExecutor(8) as ex:
        parts = list(ex.map(month, jobs))
    stack = np.stack([np.where(a < 0, 0, a) for a, _ in parts])
    mean = stack.sum(0) / (last - first + 1)
    out = DATA / "cache" / f"chirps_annual_{first}_{last}.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, mm=mean.astype("float32"), transform=np.array(tuple(parts[0][1])[:6]))
    print(f"rainfall {first}-{last}: {mean.shape}, {mean.min():.0f} to {mean.max():.0f} mm a year")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("dem90", "all"):
        dem(KENYA_MARGIN, 30, "glo90")
    if what == "dem30":
        dem(LANDFORMS[sys.argv[2]], 10, "glo30")
    if what in ("population", "all"):
        population()
    if what in ("naturalearth", "all"):
        naturalearth()
    if what in ("forest", "all"):
        forest()
    if what in ("fonts", "all"):
        fonts()
    if what in ("rainfall", "all"):
        rainfall()
