"""Write a shop page for every county relief plate.

    python tools/county_pages.py

Run from the repository root after `tools/prints/render_counties.sh`. For each
county it reads the facts file the renderer wrote ($ZP_OUT/county-<name>.json),
works out the neighbouring counties and countries from the boundaries, and
writes _prints/county-<name>.md. Pages written by hand (without
`generated: true`) are left alone, so a county can be given its own text at
any time by editing its page and deleting that line.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "prints"))

from common import DATA, MAP_CRS, OUT  # noqa: E402
from relief import COUNTY_NUMBERS  # noqa: E402

COASTAL = {"Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu"}
LAKE_VICTORIA = {"Busia", "Siaya", "Kisumu", "Homa Bay", "Migori"}


def slug_of(name):
    return "county-" + name.lower().replace(" ", "-").replace("'", "")


def spaced(n):
    return f"{n:,}".replace(",", " ")


def about(v, step):
    return spaced(int(round(v / step) * step))


def join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def neighbours():
    """County -> (neighbouring counties, neighbouring countries), from shared boundary length."""
    import geopandas as gpd
    import shapely
    from common import county_boundaries
    g = county_boundaries().to_crs(MAP_CRS)
    countries = gpd.read_file(DATA / "ne" / "ne_10m_admin_0_countries").cx[30:46, -8:8]
    countries = countries[countries["ADMIN"] != "Kenya"].copy()
    countries["geometry"] = shapely.make_valid(countries.geometry.values)
    countries = countries.to_crs(MAP_CRS)
    out = {}
    for _, row in g.iterrows():
        edge = row.geometry.boundary
        near = []
        for _, other in g.iterrows():
            if other["name"] == row["name"]:
                continue
            shared = edge.intersection(other.geometry.buffer(300)).length
            if shared > 2000:                       # a real shared border, not a corner
                near.append(other["name"])
        abroad = []
        for _, c in countries.iterrows():
            if edge.intersection(c.geometry.buffer(3000)).length > 5000:
                abroad.append(c["ADMIN"].replace("United Republic of Tanzania", "Tanzania"))
        out[row["name"]] = (sorted(near, key=COUNTY_NUMBERS.get), sorted(abroad))
    return out


def page(f, near, abroad):
    name, number = f["name"], int(f["number"])
    scale = f["scale"]
    data = "Copernicus DEM GLO-30" if f["source"] == "glo30" else "Copernicus DEM GLO-90"
    cell = 30 if f["source"] == "glo30" else 90
    zmin, zmax = f["zmin"], f["zmax"]
    area = f["area_km2"]
    area_txt = about(area, 10 if area < 1000 else 100)
    borders = []
    if near:
        borders.append(join(near) + (" County" if len(near) == 1 else " counties"))
    borders += abroad
    water = []
    if name in COASTAL:
        water.append("the Indian Ocean")
    if name in LAKE_VICTORIA:
        water.append("Lake Victoria")
    low = "sea level" if zmin < 5 else f"about {about(zmin, 10)} metres"
    rise = (f"The land rises from {low} to about {about(zmax, 10)} metres"
            if zmax - zmin >= 100 else f"The land lies between {low} and about {about(zmax, 10)} metres")
    border_txt = ""
    if borders:
        border_txt = f" It borders {join(borders)}"
        border_txt += f", and reaches {join(water)}." if water else "."
    elif water:
        border_txt = f" It reaches {join(water)}."
    facts = [
        ("Scale", f"1:{spaced(scale)} at A2, 1:{spaced(scale // 2)} at A0"),
        ("Elevation", ("sea level" if zmin < 5 else f"about {about(zmin, 10)} m") + f" to about {about(zmax, 10)} m"),
        ("Area", f"about {area_txt} km² within the boundary drawn"),
        ("Vertical exaggeration", f"×{f['zex']:g}"),
        ("Data", f"{data} (DLR / Airbus, EU and ESA); boundary © OpenStreetMap contributors, via Overture Maps (ODbL), indicative only"),
        ("Projection", "UTM zone 37S, WGS 84"),
    ]
    if near:
        facts.insert(3, ("Neighbours", ", ".join(near + abroad)))
    fm = ["---", f"slug: {f['slug']}", f"order: {100 + number}", f'plate: "{number:03d}"',
          "plate_label: County", "series: Counties", f"short: {name} County", f"title: {name}",
          "theme: County relief", f"summary: {name} County as a relief model, cut to its boundary.",
          "tone: light", "proof: true", "catalogue: false", "generated: true", "facts:"]
    fm += [f'  - [{k}, "{v}"]' for k, v in facts]
    fm.append("---")
    body = (
        f"{name} County, number {number:03d}, modelled from {cell} metre elevation data and cut to its "
        f"boundary. {rise}, across about {f['width_km']} by {f['height_km']} km.{border_txt}\n\n"
        "The picture shows the plate as we draw it before naming places. When you order, we add the "
        "towns, peaks, rivers and lakes, and anything else you ask for, such as your home town or "
        "your farm, and send you the full sheet to approve before it is printed.\n")
    return "\n".join(fm) + "\n" + body


def main():
    out_dir = Path(os.environ.get("ZP_OUT", OUT))
    borders = neighbours()
    written = kept = missing = 0
    for name in sorted(COUNTY_NUMBERS, key=COUNTY_NUMBERS.get):
        slug = slug_of(name)
        src = out_dir / f"{slug}.json"
        dst = ROOT / "_prints" / f"{slug}.md"
        if dst.exists() and "generated: true" not in dst.read_text():
            kept += 1
            continue
        if not src.exists():
            print(f"  no facts for {name}: render it first")
            missing += 1
            continue
        near, abroad = borders.get(name, ([], []))
        dst.write_text(page(json.loads(src.read_text()), near, abroad))
        written += 1
    print(f"{written} pages written, {kept} hand-written pages kept, {missing} counties not rendered yet")


if __name__ == "__main__":
    main()
