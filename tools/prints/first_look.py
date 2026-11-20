"""First look: turn a proof request from the website into a draft for you, not the client.

    python first_look.py "Ngong Hills"                       # relief, the default for a place
    python first_look.py "ngonghills" --style "Relief, ray-traced like the county plates"
    python first_look.py "Kisumu" --style gold
    python first_look.py "my farm near Limuru" --style contours --notes "-1.112, 36.650"
    python first_look.py --request request.txt     # the proof-request email, pasted into a file
    python first_look.py --request export.csv      # a Formspree CSV export: the newest row
    python first_look.py ... --no-render           # write the spec and notes only

What it does:

1. Reads the request: area, style, notes, and the size, frame and paper.
2. Finds the area: coordinates, a Kenyan county, a landmark in places.yml, a
   lake, a country or continent, a town or a named peak (Natural Earth), and
   last, when the computer is online, OpenStreetMap's search.
3. Picks the style (relief, contours, population or roads in gold) and writes a
   map spec, maps/drafts/<slug>.yml, in the house style.
4. Renders a quick proof (100 dpi), stamps it FIRST LOOK - NOT FOR THE CLIENT,
   and writes notes of what it assumed and what to check:
       $ZP_OUT/first-look/<slug>_FIRST-LOOK.jpg
       $ZP_OUT/first-look/<slug>_notes.md

The draft is a starting point. Edit the spec (the extent, title, subtitle,
labels), render it again with the usual command in the notes, and when it is
right make the customer's proof with proof_jpeg.py. Never send the FIRST-LOOK
file: it is marked so it cannot be mistaken for a proof.

maps/drafts/ is left out of git, because requests carry customers' details.
Run from tools/prints with ZP_DATA and ZP_OUT set, as for every other script.
"""
import argparse
import csv
import datetime as dt
import difflib
import json
import math
import re
import subprocess
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFTS = HERE / "maps" / "drafts"
UA = "ZeroPointGeospatial-first-look/1.0 (map print drafts)"   # no personal details

# The map box of an A2 plate in mm (common.Plate with the 90 mm title block):
# width 420 - 2 x 22, height 594 - 2 x 22 - 90 - 10.
BOX_MM = (376.0, 450.0)


# ------------------------------------------------------------------ the request

FIELDS = {                       # how the website's form fields may be labelled
    "name": "name", "phone": "phone", "phone or whatsapp": "phone", "email": "email",
    "area": "area", "area to map": "area", "style": "style", "size": "size", "frame": "frame",
    "paper": "paper", "finish": "paper", "notes": "notes",
    "names, places or wording to include": "notes", "names places or wording to include": "notes",
    "_subject": "subject", "subject": "subject",
}


def _field(label):
    key = re.sub(r"\s*\(optional\)\s*", "", label.strip().lower()).strip(" :")
    return FIELDS.get(key)


def parse_request_text(text):
    """Fields from a pasted form email: 'area: ngonghills' lines, or a label line
    followed by its value on the next line, as some mail apps show them."""
    out, lines = {}, [l.strip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][A-Za-z _,()]*?)\s*:\s*(.*)$", line)
        key = _field(m.group(1)) if m else _field(line)
        if key and key not in out:
            value = m.group(2).strip() if m else ""
            if not value:                                    # the value is on the next line
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines) and not _field(lines[j].split(":")[0]):
                    value, i = lines[j], j
            out[key] = value
        i += 1
    return out


def read_request(path, row=-1):
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "submissions" in data:
            data = data["submissions"]
        if isinstance(data, list):
            data = data[row]
        return {_field(k) or k: str(v) for k, v in data.items() if v is not None}
    if p.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        if not rows:
            raise SystemExit(f"{path}: no rows")
        return {_field(k) or k: v for k, v in rows[row].items() if k}
    return parse_request_text(text)


STYLE_WORDS = [                  # first match wins
    ("gold", ("gold", "road", "street")),
    ("contours", ("contour", "topographic", "topo")),
    ("population", ("population", "people", "density")),
    ("rivers", ("river", "drainage", "basin")),
    ("own", ("own survey", "own data", "gis data", "my own", "our own")),
    ("relief", ("relief", "terrain", "3d", "ray-traced", "elevation", "mountain")),
    ("unsure", ("not sure", "advise", "any")),
]


def style_of(text, subject=""):
    t = f"{text or ''} {subject or ''}".lower()
    for key, words in STYLE_WORDS:
        if any(w in t for w in words):
            return key
    return "unsure"


# ------------------------------------------------------------------ finding the area

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def keys_for(name):
    """Normalised spellings of a name: 'Mount Kenya' also as 'Mt Kenya'."""
    ks = {norm(name)}
    m = re.match(r"(?i)^(mount|mt\.?)\s+(.*)$", name)
    if m:
        ks |= {norm("mount " + m.group(2)), norm("mt " + m.group(2))}
    return ks


class Place(dict):
    """name, kind, source; and bbox (w, s, e, n), centre (lon, lat) or region."""


def km_box(lon, lat, width_km, height_km):
    dlon = width_km / 2 / (111.32 * math.cos(math.radians(lat)))
    dlat = height_km / 2 / 110.57
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fit_aspect(b, aspect=BOX_MM[0] / BOX_MM[1]):
    """Grow a box until its shape matches the map box, keeping its centre."""
    w, s, e, n = b
    lat = (s + n) / 2
    wk = (e - w) * 111.32 * math.cos(math.radians(lat))
    hk = (n - s) * 110.57
    if wk / hk < aspect:
        wk = hk * aspect
    else:
        hk = wk / aspect
    return km_box((w + e) / 2, lat, wk, hk)


def pad(b, frac=0.12, min_km=0.0):
    w, s, e, n = b
    lat = (s + n) / 2
    wk = max((e - w) * 111.32 * math.cos(math.radians(lat)) * (1 + 2 * frac), min_km)
    hk = max((n - s) * 110.57 * (1 + 2 * frac), min_km)
    return km_box((w + e) / 2, lat, wk, hk)


def coordinates(text):
    """A box 'w, s, e, n', a point 'lat, lon' (as Google Maps copies it), or a
    Google Maps link with @lat,lon. Returns a Place or None."""
    m = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", text)
    nums = [float(x) for x in re.findall(r"-?\d+\.\d+|-?\d+(?=\s*[,;\s]\s*-?\d)", text)] if not m else \
        [float(m.group(1)), float(m.group(2))]
    if len(nums) == 4 and not m:
        w, s, e, n = nums
        if w < e and s < n:
            return Place(name="Custom area", kind="box", bbox=(w, s, e, n), source="coordinates in the request")
    if len(nums) >= 2:
        a, b = nums[:2]
        if abs(a) > 90 >= abs(b):            # lon, lat
            lon, lat = a, b
        elif abs(b) <= 5 < abs(a) <= 42 and abs(a) >= 33:   # Kenya written lon first
            lon, lat = a, b
        else:                                 # lat, lon, as Google Maps gives it
            lat, lon = a, b
        if abs(lat) <= 90 and abs(lon) <= 180:
            return Place(name="Custom area", kind="point", centre=(lon, lat),
                         source="coordinates in the request")
    return None


@lru_cache(None)
def gazetteer():
    import yaml
    return yaml.safe_load((HERE / "places.yml").read_text(encoding="utf-8")) or []


@lru_cache(None)
def towns():
    """Named points: the towns on the county plates, places.yml towns, Natural Earth places."""
    out = []
    try:
        from relief import COUNTY_LABELS
        for cfg in COUNTY_LABELS.values():
            for name, value, lon, lat, *_ in cfg.get("labels", []):
                if value is None:
                    out.append(dict(name=name, centre=(lon, lat), pop=0, country="Kenya", source="the county plates"))
    except Exception:                                   # noqa: BLE001 - the list is a convenience
        pass
    for p in gazetteer():
        if p.get("kind") == "town":
            out.append(dict(name=p["name"], centre=tuple(p["centre"]), pop=0, country="Kenya",
                            radius_km=p.get("radius_km"), source="places.yml"))
    try:
        import geopandas as gpd
        from common import DATA
        g = gpd.read_file(DATA / "ne" / "ne_10m_populated_places",
                          columns=["NAME", "NAMEASCII", "ADM0NAME", "POP_MAX", "LATITUDE", "LONGITUDE"],
                          ignore_geometry=True)
        for r in g.itertuples():
            out.append(dict(name=str(r.NAME), alt=str(r.NAMEASCII), centre=(float(r.LONGITUDE), float(r.LATITUDE)),
                            pop=int(r.POP_MAX or 0), country=str(r.ADM0NAME), source="Natural Earth populated places"))
    except Exception as e:                              # noqa: BLE001
        print(f"  (Natural Earth places not available: {type(e).__name__})")
    return out


@lru_cache(None)
def peaks():
    try:
        import geopandas as gpd
        from common import DATA
        g = gpd.read_file(DATA / "ne" / "ne_10m_geography_regions_elevation_points", ignore_geometry=True)
        return [dict(name=r.name, centre=(float(r.long_x), float(r.lat_y)), elevation=float(r.elevation))
                for r in g.itertuples() if isinstance(r.name, str) and r.elevation == r.elevation]
    except Exception:                                   # noqa: BLE001 - optional layer
        return []


@lru_cache(None)
def lakes_ne():
    """Named lakes from Natural Earth, with their bounds."""
    try:
        import geopandas as gpd
        from common import DATA
        g = gpd.read_file(DATA / "ne" / "ne_10m_lakes", columns=["name"])
        return [dict(name=str(r.name), bbox=tuple(float(v) for v in r.geometry.bounds))
                for r in g.itertuples() if isinstance(r.name, str)]
    except Exception:                                   # noqa: BLE001
        return []


def candidates(area):
    """The parts of what the customer wrote that might be a place name, best first."""
    text = re.sub(r"\s+", " ", area.strip())
    out = [text]
    for word in (" near ", " in ", " around ", " at ", " of ", " by ", " outside "):
        if word in f" {text.lower()} ":
            out.append(re.split(word, f" {text} ", flags=re.I)[-1].strip())
    out += [p.strip() for p in re.split(r"[,;/]| and ", text) if p.strip()]
    filler = r"(?i)\b(my|our|the|a|family|farm|land|plot|shamba|home|house|estate|area|town|city|county|region)\b"
    out += [re.sub(r"\s+", " ", re.sub(filler, " ", c)).strip() for c in list(out)]
    seen, uniq = set(), []
    for c in out:
        if c and norm(c) and norm(c) not in seen:
            seen.add(norm(c))
            uniq.append(c)
    return uniq


def resolve(area, style, online=True):
    """Find the area. Returns (Place, alternatives considered, list of notes)."""
    notes = []
    pt = coordinates(area)
    if pt:
        return pt, [], notes
    import regions
    from common import county_boundaries
    counties = list(county_boundaries()["name"])
    gaz = gazetteer()
    town_list = towns()
    peak_list = peaks()
    wants_county = "county" in area.lower()
    wants_town = style == "gold" or bool(re.search(r"(?i)\b(town|city|centre|center|cbd)\b", area))

    def options(key, key_text, fuzzy):
        """Every place whose name matches `key`, as (preference, Place)."""
        found = []

        def hit(k):
            return k == key or (fuzzy and difflib.SequenceMatcher(None, k, key).ratio() >= 0.86)

        for c in counties:
            if hit(norm(c)) or hit(norm(c + " county")):
                found.append((0 if wants_county else 2, Place(name=c, kind="county", region={"county": c},
                                                               source="the county boundaries")))
        for p in gaz:
            if p.get("kind") == "town":
                continue
            if any(hit(k) for n in [p["name"]] + p.get("aliases", []) for k in keys_for(n)):
                found.append((1, Place(name=p["name"], kind=p["kind"], bbox=tuple(p["bbox"]),
                                       labels=p.get("labels", []), names=p.get("names", []),
                                       source="places.yml")))
        for t in town_list:
            if hit(norm(t["name"])) or (t.get("alt") and hit(norm(t["alt"]))):
                kenyan = t.get("country") == "Kenya"
                found.append((0 if wants_town else (3 if kenyan else 5),
                              Place(name=t["name"], kind="town", centre=t["centre"], pop=t.get("pop", 0),
                                    country=t.get("country", ""), radius_km=t.get("radius_km"),
                                    source=t["source"])))
        for lk in lakes_ne():
            if any(hit(k) for k in keys_for(lk["name"]) | keys_for("Lake " + lk["name"])):
                found.append((1, Place(name=lk["name"] if lk["name"].lower().startswith("lake") else
                                       "Lake " + lk["name"], kind="lake", bbox=pad(lk["bbox"], 0.08),
                                       source="Natural Earth lakes")))
        for pk in peak_list:
            if any(hit(k) for k in keys_for(pk["name"])):
                found.append((4, Place(name=pk["name"], kind="mountain", centre=pk["centre"],
                                       elevation=pk["elevation"], source="Natural Earth peaks")))
        if not fuzzy:
            try:
                geom, isos, what = regions.region_outline(
                    {"continent": "Africa"} if key == "africa" else {"countries": [key_text]})
                found.append((3, Place(name=what, kind="country", source="Natural Earth countries",
                                       region={"continent": "Africa"} if key == "africa"
                                       else {"countries": [key_text]})))
            except (SystemExit, Exception):                # noqa: BLE001 - not a country
                pass
        return found

    tried = []
    for fuzzy in (False, True):
        for cand in candidates(area):
            key, key_text = norm(cand), cand
            tried.append(cand)
            found = options(key, key_text, fuzzy)
            if found:
                found.sort(key=lambda f: f[0])
                best = found[0][1]
                others = list(dict.fromkeys(f"{p['name']} ({p['kind']})" for _, p in found[1:]
                                            if (p["name"], p["kind"]) != (best["name"], best["kind"])))[:3]
                if fuzzy:
                    notes.append(f'"{cand}" was read as {best["name"]} (a close spelling); check that is right.')
                if others:
                    notes.append("Also matched: " + "; ".join(others) + ". Change the spec if one of these was meant.")
                return best, tried, notes
    if online:
        p = nominatim(area)
        if p:
            notes.append("Found by OpenStreetMap search; check the extent carefully.")
            return p, tried, notes
    raise SystemExit(
        f'Could not find "{area}". Tried: {", ".join(dict.fromkeys(tried))}.\n'
        "Give coordinates instead (a point as 'lat, lon' from Google Maps, or a box as 'west, south, east, north'),\n"
        "or add the place to places.yml.")


def nominatim(area):
    """OpenStreetMap's search, used only when nothing local matches. One request."""
    import urllib.parse
    import urllib.request
    for extra in ("&countrycodes=ke", ""):
        url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q="
               + urllib.parse.quote(area) + extra)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.loads(r.read().decode())
        except Exception as e:                           # noqa: BLE001 - offline, blocked, refused
            print(f"  OpenStreetMap search not available ({type(e).__name__})")
            return None
        if res:
            r = res[0]
            s, n, w, e = (float(v) for v in r["boundingbox"])
            kind = "town" if r.get("addresstype") in ("city", "town", "village", "suburb") else r.get("type", "place")
            return Place(name=r.get("name") or area, kind=kind, bbox=(w, s, e, n),
                         centre=(float(r["lon"]), float(r["lat"])), source="OpenStreetMap search (Nominatim)")
    return None


# ------------------------------------------------------------------ the draft spec

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip("-")


def extent(place):
    """The box a block region draws for a place, in the map box's shape."""
    if place.get("bbox") and place["kind"] != "town":
        return fit_aspect(place["bbox"])
    lon, lat = place["centre"]
    if place["kind"] == "town":
        pop = place.get("pop") or 0
        size = 40 if pop >= 1_000_000 else 25 if pop >= 100_000 else 15
        return fit_aspect(km_box(lon, lat, size, size))
    if place["kind"] == "mountain":
        return fit_aspect(km_box(lon, lat, 30, 30))
    return fit_aspect(km_box(lon, lat, 8, 8))           # a point: a farm or a plot


def inside(b, lon, lat, margin=0.08):
    w, s, e, n = b
    mx, my = (e - w) * margin, (n - s) * margin
    return w + mx <= lon <= e - mx and s + my <= lat <= n - my


def nearby_towns(b, place, limit=4):
    """Towns inside the box for labels, largest first, without the place itself."""
    seen, out = set(), []
    for t in sorted(towns(), key=lambda t: -t.get("pop", 0)):
        k = norm(t["name"])
        if k in seen or k == norm(place["name"]) or not inside(b, *t["centre"]):
            continue
        seen.add(k)
        out.append(t)
        if len(out) == limit:
            break
    return out


def nice_interval(relief_m, lines=60):
    """The round interval that gives closest to `lines` contours (40 to 80 read well)."""
    return min((1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200),
               key=lambda v: abs(math.log(max(relief_m, 1) / v / lines)))


def relief_of(b):
    """Height range of a box from the 30 m model (downloads the tiles if needed)."""
    import fetch_data
    from common import load_dem
    w, s, e, n = b
    fetch_data.dem((math.floor(w), math.floor(s), math.ceil(e), math.ceil(n)), 10, "glo30")
    z, _ = load_dem((round(w, 3), round(s, 3), round(e, 3), round(n, 3)), "glo30")
    z = z[z > -100]
    return float(z.min()), float(z.max())


def label_entries(entries, b):
    return [dict(x) for x in entries if inside(b, x["lon"], x["lat"], 0.02)]


def build_spec(place, style, request):
    """Returns (spec dict, style actually drawn, notes)."""
    notes = []
    name = place["name"]
    number = "01"
    if style == "rivers":
        notes.append("Rivers are drawn for the whole of Kenya only (kenya_rivers.py); a river map of one area is "
                     "custom work. The draft is relief instead.")
        style = "relief"
    if style == "own":
        notes.append("The customer wants their own survey or GIS data on it: the draft is the relief of the area as "
                     "a base; add their data once it arrives.")
        style = "relief"
    if style == "unsure":
        style = "gold" if place["kind"] == "town" else "relief"
        notes.append(f"The customer was not sure: the draft is {'roads in gold' if style == 'gold' else 'relief'}, "
                     "the usual choice for a " + ("town." if style == "gold" else "natural area."))
    if style == "contours" and place.get("region"):
        notes.append(f"{name} is a whole {place['kind']}: too big for a contour study (they read best from "
                     "1:10 000 to 1:100 000), so the draft is relief. Ask which mountain, crater or farm they mean.")
        style = "relief"
    if style == "gold" and place["kind"] != "town":
        notes.append(f"Roads in gold need a town; {name} is a {place['kind']}, so the draft is relief.")
        style = "relief"

    if style == "gold":
        lon, lat = place["centre"]
        pop = place.get("pop") or 0
        radius = place.get("radius_km") or (7.0 if pop >= 1_000_000 else 5.5 if pop >= 200_000 else 3.5)
        spec = {"slug": f"draft-{slugify(name)}-gold",
                "city": {"name": name, "country": place.get("country") or "Kenya", "lon": round(float(lon), 4),
                         "lat": round(float(lat), 4), "radius_km": float(radius)}}
        notes.append(f"The circle reaches {radius:g} km from the centre of {name}; raise radius_km to take in more "
                     "of the town.")
        return spec, style, notes

    slug = f"draft-{slugify(name)}-{style}"
    title = name
    if place.get("region"):
        region, b = place["region"], None
    else:
        b = extent(place)
        region = {"bbox": [round(float(v), 4) for v in b]}

    if style == "contours":
        w, s, e, n = b
        wk = (e - w) * 111.32 * math.cos(math.radians((s + n) / 2))
        import regions
        scale = max(10_000, regions.tidy_scale(wk * 1000, (n - s) * 110_570, BOX_MM))
        if scale > 150_000:
            notes.append(f"{name} is large for contours (it needs 1:{scale:,}); the draft is held at 1:150 000 "
                         "around the centre. Contours read best from 1:10 000 to 1:100 000.")
            scale = 150_000
        try:
            lo, hi = relief_of(b)
            interval = nice_interval(hi - lo)
            notes.append(f"Heights in the area run from about {lo:,.0f} m to {hi:,.0f} m; "
                         f"a {interval:g} m interval gives about {int((hi - lo) / interval)} contours.")
        except Exception as e:                          # noqa: BLE001 - no elevation data offline
            interval = 10 if scale <= 25_000 else 20 if scale <= 75_000 else 50
            notes.append(f"Could not read the elevation to choose an interval ({type(e).__name__}); {interval} m "
                         "is a guess.")
        spec = {"slug": slug, "title": title, "subtitle": "A contour study", "label": "CUSTOM", "number": number,
                "centre": [round((w + e) / 2, 4), round((s + n) / 2, 4)], "scale": int(scale),
                "interval": interval, "index": interval * 5,
                "labels": label_entries(place.get("labels", []), b),
                "names": label_entries([dict(x, lon=x["lon"], lat=x["lat"]) for x in place.get("names", [])], b)}
        return spec, style, notes

    subtitle = {"relief": "Relief", "population": "Where people live"}[style]
    if place["kind"] == "county":
        subtitle = "County relief" if style == "relief" else "Where the county's people live"
    if place["kind"] in ("point", "box"):
        notes.append("The request gave coordinates, not a name: the title is \"Custom area\" until you set it.")
    spec = {"slug": slug, "title": title, "subtitle": subtitle, "label": "CUSTOM", "number": number,
            "region": region}
    if style == "relief":
        labels = list(place.get("labels", []))
        if place["kind"] == "county":
            from relief import COUNTY_LABELS
            cl = COUNTY_LABELS.get(name, {})
            labels += [dict(name=x[0], value=x[1], lon=x[2], lat=x[3], side=x[4], snap=x[5])
                       for x in cl.get("labels", [])]
            spec["names"] = [dict(text=x[0], lon=x[1], lat=x[2], angle=x[3], size=x[4]) for x in cl.get("names", [])]
            if not labels:
                notes.append(f"No towns are set up for {name} County yet; add the main towns as labels.")
        elif place.get("elevation") and place.get("centre"):
            lon, lat = place["centre"]
            labels.append(dict(name=name, value=f"{place['elevation']:,.0f} m".replace(",", " "), lon=round(lon, 4),
                               lat=round(lat, 4), side="right", snap=3000))
        elif b is not None and not labels:
            labels = [dict(name=t["name"], lon=round(float(t["centre"][0]), 4), lat=round(float(t["centre"][1]), 4),
                           side="right") for t in nearby_towns(b, place, 3)]
        if b is not None:
            labels = label_entries(labels, b)
        spec["labels"] = labels
        if place.get("names"):
            spec["names"] = spec.get("names", []) + label_entries(place["names"], b) if b else place["names"]
    else:                                                    # population
        if b is not None:
            near = nearby_towns(b, place, 4)
            if place["kind"] == "town":
                near = [dict(name=name, centre=place["centre"])] + near[:3]
        elif place["kind"] == "county":
            from relief import COUNTY_LABELS
            near = [dict(name=x[0], centre=(x[2], x[3])) for x in COUNTY_LABELS.get(name, {}).get("labels", [])
                    if x[1] is None][:4]
        else:
            near = []
        spec["towns"] = [dict(name=t["name"], lon=round(float(t["centre"][0]), 4), lat=round(float(t["centre"][1]), 4))
                         for t in near]
    return spec, style, notes


def notes_labels(request_notes, b):
    """Coordinates in the customer's notes become a marked point on the draft."""
    if not request_notes:
        return []
    pt = coordinates(request_notes)
    if pt and pt.get("centre") and (b is None or inside(b, *pt["centre"], 0.0)):
        lon, lat = pt["centre"]
        return [dict(name="Customer's place", lon=round(lon, 5), lat=round(lat, 5), side="right")]
    return []


# ------------------------------------------------------------------ render, stamp, notes

SCRIPT = {"relief": "relief.py", "population": "population.py", "contours": "contours.py", "gold": "cities.py"}


def render(spec_path, style, slug, dpi, spp):
    from common import OUT
    rel = spec_path.relative_to(HERE)
    if style == "gold":
        width = 1600
        cmd = [sys.executable, "cities.py", f"spec:{rel}", str(width)]
        out = OUT / f"{slug.removesuffix('-gold')}-gold_{width}.png"
    else:
        cmd = [sys.executable, SCRIPT[style], f"spec:{rel}", str(dpi)] + ([str(spp)] if style != "contours" else [])
        out = OUT / f"{slug}_{dpi}.png"
    print("  " + " ".join(cmd[1:]))
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    log = proc.stdout + proc.stderr
    if proc.returncode != 0 or not out.exists():
        tail = "\n".join(log.strip().splitlines()[-12:])
        raise SystemExit(f"The render failed:\n{tail}")
    facts = [l.strip() for l in proc.stdout.splitlines()
             if l.startswith(slug) or "left out" in l or l.startswith("  WARNING")]
    return out, facts


def stamp(src, dest, when):
    """The proof, with a red border and a band that says it is not for the client."""
    from PIL import Image, ImageDraw
    from common import font
    im = Image.open(src).convert("RGB")
    if im.width > 1800:
        im = im.resize((1800, round(im.height * 1800 / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    red = (178, 34, 34)
    edge = max(6, im.width // 160)
    d.rectangle([0, 0, im.width - 1, im.height - 1], outline=red, width=edge)
    band = max(44, im.width // 24)
    d.rectangle([0, 0, im.width, band], fill=red)
    text = f"FIRST LOOK  ·  FOR ZEROPOINT ONLY  ·  NOT FOR THE CLIENT  ·  {when}"
    try:
        f = font("Barlow-600", int(band * 0.42))
    except Exception:                                    # noqa: BLE001 - fonts not fetched
        from PIL import ImageFont
        f = ImageFont.load_default()
    d.text((im.width / 2, band / 2), text, font=f, fill=(255, 255, 255), anchor="mm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, quality=88, optimize=True)
    return dest


def write_notes(path, request, place, style, spec_path, spec, notes, facts, image, dpi):
    rel = spec_path.relative_to(HERE)
    script = SCRIPT[style]
    again = (f"python cities.py spec:{rel} 1600" if style == "gold" else
             f"python {script} spec:{rel} 100" + ("" if style == "contours" else " 16"))
    master = (f"python cities.py spec:{rel} 6744" if style == "gold" else
              f"python {script} spec:{rel} 300" + ("" if style == "contours" else " 40"))
    proof_src = (f"$ZP_OUT/{spec['slug'].removesuffix('-gold')}-gold_1600.png" if style == "gold"
                 else f"$ZP_OUT/{spec['slug']}_{dpi}.png")
    where = place.get("region") or (spec.get("region") or {}).get("bbox") or spec.get("centre") or spec.get("city")
    order = ", ".join(v for v in (request.get("size"), request.get("frame"), request.get("paper")) if v)
    lines = [
        f"# First look: {spec.get('title') or spec['city']['name']}, {style}",
        "",
        f"Made {dt.datetime.now():%Y-%m-%d %H:%M}. For ZeroPoint only: do not send this draft to the customer.",
        "",
        "## The request",
        "",
        f"- Area: \"{request.get('area', '')}\"",
        f"- Style: \"{request.get('style') or request.get('subject') or 'not given'}\"",
    ]
    if order:
        lines.append(f"- Order: {order}")
    if request.get("name"):
        lines.append(f"- From: {request['name']} (contact details are in the request email)")
    if request.get("notes"):
        lines.append(f"- Their notes: \"{request['notes']}\"")
    lines += [
        "",
        "## What the draft assumed",
        "",
        f"- Place: {place['name']} ({place['kind']}), from {place['source']}.",
        f"- Drawn: {where}",
        f"- Style: {style}.",
    ]
    lines += [f"- {n}" for n in notes]
    if facts:
        lines += ["", "## From the render", ""] + [f"    {f}" for f in facts]
    lines += [
        "",
        "## Before the customer sees a proof",
        "",
        "- [ ] The extent: is this the area they meant, and is anything important cut off?",
        "- [ ] Title and subtitle: the place as they would name it, and a subtitle with something to say.",
        "- [ ] Labels: the names they asked for, each on the right spot; heights only from a source you can name.",
    ]
    if request.get("notes"):
        lines.append("- [ ] Their notes, above: everything they asked for is on the sheet.")
    lines += [
        "- [ ] The plate number (now \"CUSTOM 01\").",
        "- [ ] The house-style review list: .claude/skills/zeropoint-map-print/references/house-style.md.",
        "",
        "## Next",
        "",
        f"    # edit {rel}, then render again:",
        f"    {again}",
        "    # the customer's proof, watermarked and too small to print from:",
        f"    python proof_jpeg.py {proof_src}",
        "    # once they approve and pay, the print master:",
        f"    {master}",
        "",
        f"Draft image: {image}" if image else "Not rendered (--no-render).",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("area", nargs="?", help="the area, as the customer wrote it")
    ap.add_argument("--style", default="", help="relief, contours, population, gold, or the form's wording")
    ap.add_argument("--notes", default="", help="the customer's notes (names, places, coordinates)")
    ap.add_argument("--request", help="a pasted request email (.txt), a Formspree export (.csv or .json)")
    ap.add_argument("--row", type=int, default=-1, help="which row of a CSV or JSON export (default: the newest)")
    ap.add_argument("--dpi", type=int, default=100)
    ap.add_argument("--spp", type=int, default=16)
    ap.add_argument("--offline", action="store_true", help="never use OpenStreetMap's search")
    ap.add_argument("--no-render", action="store_true", help="write the spec and notes only")
    args = ap.parse_args()

    request = read_request(args.request, args.row) if args.request else {}
    if args.area:
        request["area"] = args.area
    if args.style:
        request["style"] = args.style
    if args.notes:
        request["notes"] = args.notes
    area = (request.get("area") or "").strip()
    if not area:
        raise SystemExit("No area: give it as the first argument or in the request file.")
    style = style_of(request.get("style"), request.get("subject"))
    print(f"Request: \"{area}\", style {style}")

    place, _, notes = resolve(area, style, online=not args.offline)
    print(f"  found {place['name']} ({place['kind']}) in {place['source']}")
    spec, style, more = build_spec(place, style, request)
    notes += more
    b = tuple((spec.get("region") or {}).get("bbox") or ()) or None
    extra = notes_labels(request.get("notes"), b)
    if extra and "labels" in spec:
        spec["labels"] = spec["labels"] + extra
        notes.append("The coordinates in their notes are marked \"Customer's place\"; rename the label.")
    elif request.get("notes"):
        notes.append("Their notes are not on the draft yet: add the names they asked for by hand.")

    import yaml
    DRAFTS.mkdir(parents=True, exist_ok=True)
    spec_path = DRAFTS / f"{spec['slug']}.yml"
    head = (f"# First-look draft from a proof request, {dt.date.today():%Y-%m-%d}. Edit freely; see maps/README.md.\n"
            f"# Request: area \"{area}\", style \"{request.get('style') or request.get('subject') or ''}\"\n")
    spec_path.write_text(head + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=110),
                         encoding="utf-8")
    print(f"  spec: {spec_path.relative_to(HERE)}")

    from common import OUT
    folder = OUT / "first-look"
    image, facts = None, []
    if not args.no_render:
        src, facts = render(spec_path, style, spec["slug"], args.dpi, args.spp)
        image = stamp(src, folder / f"{spec['slug']}_FIRST-LOOK.jpg", f"{dt.date.today():%d %b %Y}".upper())
        print(f"  draft: {image}")
    folder.mkdir(parents=True, exist_ok=True)
    path = write_notes(folder / f"{spec['slug']}_notes.md", request, place, style, spec_path, spec, notes,
                       facts, image, args.dpi)
    print(f"  notes: {path}")
    for n in notes:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
