"""First look: turn a proof request from the website into a draft for you, not the client.

    python first_look.py "Ngong Hills"                       # relief, the default for a place
    python first_look.py "ngonghills" --style "Relief, ray-traced like the county plates"
    python first_look.py "Kisumu" --style gold
    python first_look.py "my farm near Limuru" --style contours --notes "-1.112, 36.650"
    python first_look.py --request request.txt     # the proof-request email, pasted into a file
    python first_look.py --request export.csv      # a Formspree CSV or JSON export: the newest row
    python first_look.py ... --no-render           # write the spec and notes only

What it does:

1. Reads the request: area, style, notes, and the size, frame and paper.
2. Finds the area, in this order: coordinates; a Kenyan county, a landmark in
   places.yml, a Kenyan town, a lake, a peak or a country; then, when the
   computer is online, OpenStreetMap's search in Kenya; then close spellings of
   Kenyan names; and only last a town of that name abroad, which the notes flag.
3. Picks the style (relief, contours, population or roads in gold) and writes a
   map spec, maps/drafts/<slug>.yml, in the house style. A draft already there
   (another customer's, or one you have edited) is never written over: the new
   one gets the next number, unless you pass --replace.
4. Renders a quick proof (100 dpi), stamps it FIRST LOOK - NOT FOR THE CLIENT,
   and writes notes of what it assumed and what to check:
       $ZP_OUT/first-look/<slug>_FIRST-LOOK.jpg
       $ZP_OUT/first-look/<slug>_notes.md
   If the render fails, the notes say why and the full log is kept beside them.

The draft is a starting point. Edit the spec (the extent, title, subtitle,
labels), render it again with the command in the notes, and when it is right
make the customer's proof with proof_jpeg.py. Never send the FIRST-LOOK file:
it is marked so it cannot be mistaken for a proof.

maps/drafts/ is left out of git, because requests carry customers' details.
OpenStreetMap's search is sent place names only, never the customer's sentence,
numbers or names. Run from tools/prints with ZP_DATA and ZP_OUT set, as for
every other script.
"""
import argparse
import csv
import datetime as dt
import difflib
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFTS = HERE / "maps" / "drafts"
UA = "ZeroPointGeospatial-first-look/1.0 (map print drafts)"   # no personal details

# The map box of an A2 plate in mm (common.Plate with the 90 mm title block):
# width 420 - 2 x 22, height 594 - 2 x 22 - 90 - 10.
BOX_MM = (376.0, 450.0)
CONTOUR_INSET_MM = 7.0           # contours.py draws inside the map box less 7 mm each side

# Where customers' places are expected: a point outside this box is flagged.
EAST_AFRICA = (20.0, -15.0, 55.0, 20.0)
# Towns in these countries are plausible requests; elsewhere a town of the same
# name as the customer's is more likely a mistake than what they meant.
NEAR_KENYA = {"Kenya", "Uganda", "Tanzania", "United Republic of Tanzania", "Rwanda", "Burundi",
              "Ethiopia", "Somalia", "Somaliland", "South Sudan"}


# ------------------------------------------------------------------ the request

FIELDS = {                       # how the website's form fields may be labelled
    "name": "name", "phone": "phone", "phone or whatsapp": "phone", "email": "email",
    "area": "area", "area to map": "area", "style": "style", "size": "size", "frame": "frame",
    "paper": "paper", "finish": "paper", "notes": "notes",
    "names, places or wording to include": "notes", "names places or wording to include": "notes",
    "_subject": "subject", "subject": "subject",
    # the form's hidden and anti-spam fields: never a value, but they end the one before
    "request": "request", "website": "website", "_gotcha": "website", "leave this empty": "website",
}
SUBJECT_LINE = re.compile(r"(?i)^(?:subject\s*:\s*)?(?:(?:re|fwd?)\s*:\s*)*(proof request\s*:.*)$")
FOOTER = re.compile(r"(?i)^(--|submitted\b|sent (from|via)\b|mark as spam|unsubscribe|view (it|this) )")
LABEL = re.compile(r"^([A-Za-z_][A-Za-z _,()]*?)\s*:\s*(.*)$")


def _field(label):
    key = re.sub(r"\s*\(optional\)\s*", "", label.strip().lower()).strip(" :")
    return FIELDS.get(key)


def _is_label(line):
    """A form label ('Area to map', 'notes: ...'), the subject, or an email footer:
    anything that ends the value before it."""
    m = LABEL.match(line)
    return bool(_field(m.group(1) if m else line) or SUBJECT_LINE.match(line) or FOOTER.match(line))


def parse_request_text(text):
    """Fields from a pasted form email: 'area: ngonghills' lines, or a label line
    followed by its value on the next line, as some mail apps show them. The notes
    keep all their lines; the subject is read with or without 'Subject:'."""
    out, lines = {}, [l.strip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        s = SUBJECT_LINE.match(line)
        if s:
            out.setdefault("subject", s.group(1).strip())
            i += 1
            continue
        m = LABEL.match(line)
        key = _field(m.group(1)) if m else _field(line)
        if key and key not in out:
            value = m.group(2).strip() if m else ""
            if not value and not m:                          # a bare label: the value is on the next line
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines) and not _is_label(lines[j]):
                    value, i = lines[j], j
            if key == "notes" and value:                     # free text: keep its other lines
                more, j = [], i + 1
                while j < len(lines) and not _is_label(lines[j]):
                    more.append(lines[j])
                    j += 1
                while more and not more[-1]:
                    more.pop()
                if more:
                    value, i = "\n".join([value] + more), j - 1
            out[key] = value
        i += 1
    for k in ("request", "website"):                         # the form's own fields
        out.pop(k, None)
    return out


DATE_KEYS = ("_date", "date", "submitted at", "submitted_at", "created_at", "created at", "timestamp")


def _when(r):
    """The submission time of an export row (UTC), or None."""
    for k, v in r.items():
        if k and str(k).strip().lower() in DATE_KEYS and v:
            s = str(v).strip().replace("Z", "+00:00").replace(" UTC", "+00:00")
            try:
                t = dt.datetime.fromisoformat(s)
            except ValueError:
                return None
            return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    return None


def read_request(path, row=None):
    """The request: a pasted email (.txt), or one row of a Formspree export
    (.csv or .json): the row asked for, else the newest by its date, else the last."""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    kind = p.suffix.lower()
    if kind not in (".json", ".csv"):
        return parse_request_text(text)
    if kind == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "submissions" in data:
            data = data["submissions"]
        rows = data if isinstance(data, list) else [data]
    else:
        rows = list(csv.DictReader(io.StringIO(text, newline="")))   # keeps line breaks inside cells
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        raise SystemExit(f"{path}: no rows")
    times = [_when(r) for r in rows]
    if all(times):                                   # oldest first, whatever order the export used
        order = sorted(range(len(rows)), key=lambda i: times[i])
        rows, times = [rows[i] for i in order], [times[i] for i in order]
    if row is None:
        row = len(rows) - 1
    if not -len(rows) <= row < len(rows):
        raise SystemExit(f"{path} has {len(rows)} rows: --row goes from 0 (the oldest) to {len(rows) - 1}"
                         " (the newest), or -1 for the newest.")
    n = row % len(rows)
    r = rows[n]
    when = f", sent {times[n]:%Y-%m-%d %H:%M} UTC" if times[n] else ""
    print(f"Row {n} of {len(rows)} (0 is the oldest){when}")
    return {_field(k) or k: str(v) for k, v in r.items()
            if k and v is not None and _field(k) not in ("request", "website")}


STYLE_WORDS = [                  # first match wins; matched at the start of words
    ("gold", ("gold", "road", "street")),
    ("contours", ("contour", "topographic", "topo")),
    ("population", ("population", "people", "density")),
    ("rivers", ("river", "drainage", "basin")),
    ("own", ("own survey", "own data", "gis data", "my own", "our own")),
    ("relief", ("relief", "terrain", "3d", "ray-traced", "elevation", "mountain")),
    ("unsure", ("not sure", "advise", "any")),
]


def theme_of(subject, area=""):
    """The theme of a print page's subject, 'Proof request: <title>: <theme>', without the
    place name, which can hold a style word itself (Tana *River*: County relief)."""
    s = re.sub(r"(?i)^\s*proof request\s*:\s*", "", subject or "")
    if area:
        s = re.sub(re.escape(area), " ", s, flags=re.I)
    return s.rsplit(":", 1)[-1].strip()


def style_of(text, subject="", area=""):
    """The style from the form's Style field; a print page's form has none, so the theme of
    its subject is used instead."""
    for t in (text, theme_of(subject, area)):
        t = (t or "").lower()
        for key, words in STYLE_WORDS:
            if any(re.search(r"\b" + re.escape(w), t) for w in words):
                return key
    return "unsure"


# ------------------------------------------------------------------ coordinates

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


class Place(dict):
    """name, kind, source; and bbox (w, s, e, n), centre (lon, lat) or region; country."""


def km_box(lon, lat, width_km, height_km):
    dlon = width_km / 2 / (111.32 * math.cos(math.radians(lat)))
    dlat = height_km / 2 / 110.57
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fit_aspect(b, aspect=BOX_MM[0] / BOX_MM[1], min_km=1.0):
    """Grow a box until its shape matches the map box, keeping its centre."""
    w, s, e, n = b
    lat = (s + n) / 2
    wk = max((e - w) * 111.32 * math.cos(math.radians(lat)), min_km)
    hk = max((n - s) * 110.57, min_km)
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


def in_east_africa(lon, lat):
    w, s, e, n = EAST_AFRICA
    return w <= lon <= e and s <= lat <= n


DASHES = dict.fromkeys(map(ord, "−‐‑‒–—﹣－"), "-")
QUOTES = {ord("º"): "°", ord("˚"): "°", ord("′"): "'", ord("’"): "'", ord("‘"): "'",
          ord("″"): '"', ord("”"): '"', ord("“"): '"'}
# numbers that are not coordinates: plot, LR and title numbers, sizes and distances, dates, phones
NOT_COORDS = re.compile(
    r"(?i)\b(?:plots?|l\.?\s?r|title|parcel|block|house|hse|no|number|p\.?\s?o\.?\s?box|"
    r"tel|phone|mobile|whatsapp)\b\.?\s*(?:no\.?\s*)?[\d/.\-\s]*\d"
    r"|[-+]?\d+(?:[.,]\d+)?\s*(?:acres?|ac|ha|hectares?|kms?|kilomet(?:re|er)s?|m|metres?|meters?|ft|feet|"
    r"miles?|mi|sq\w*|%|copies)\b"
    r"|(?<![\d.])\d{1,2}[/.\-]\d{1,2}[/.\-](?:19|20)?\d{2}(?![\d.])|(?<![\d.\-])(?:19|20)\d{2}(?![\d.])"
    r"|\+?\d[\d\s]{8,}\d")
_ANGLE = r"(\d{1,3}(?:\.\d+)?)\s*°?\s*(?:(\d{1,2}(?:\.\d+)?)\s*'\s*)?(?:(\d{1,2}(?:\.\d+)?)\s*(?:\"|'')\s*)?"
_SUFFIX = re.compile(_ANGLE + r"([NSEW])(?:orth|outh|ast|est)?(?![A-Za-z])", re.I)
_PREFIX = re.compile(r"(?<![A-Za-z])([NSEW])(?:orth|outh|ast|est)?\.?\s*" + _ANGLE, re.I)
_MARKED = re.compile(r"°|\d\s*['\"]\s*\d|\d\.\d+\s*[NSEW](?![A-Za-z])|(?<![A-Za-z])[NSEW]\s*\d+\.\d", re.I)
NUM = r"-?\d+(?:\.\d+)?"
RUN = re.compile(rf"(?<![\w.]){NUM}(?:\s*[,;]?\s*{NUM})+(?!\w|\.\d)")   # numbers written together
# degrees, minutes and seconds written with spaces: 1 17 45 S, 36 49 18 E
_SPACED = re.compile(r"(?<![\d.])(\d{1,3})\s+(\d{1,2})(?:\s+(\d{1,2}(?:\.\d+)?))?\s*([NSEW])(?![A-Za-z])", re.I)


def _hemispheres(t):
    """(lon, lat) from '1.112S, 36.650E', 'S 1.112 E 36.650', 1°06'43.2"S 36°39'00.0"E or
    1°06'S 36°39'E; None when the text has no such marks, False when it has marks that do not
    make one point."""
    for rx, suffix in ((_SPACED, True), (_SUFFIX, True), (_PREFIX, False)):
        vals = {}
        for m in rx.finditer(t):
            h, d, mi, se = (m.group(4), *m.group(1, 2, 3)) if suffix else m.group(1, 2, 3, 4)
            if float(mi or 0) >= 60 or float(se or 0) >= 60:
                return False
            axis = "lat" if h.upper() in "NS" else "lon"
            v = float(d) + float(mi or 0) / 60 + float(se or 0) / 3600
            vals.setdefault(axis, -v if h.upper() in "SW" else v)
        if len(vals) == 2:
            if abs(vals["lat"]) > 90 or abs(vals["lon"]) > 180:
                return False
            return vals["lon"], vals["lat"]
    return False if _MARKED.search(t) else None


def _lat_first_kenya(a, b):
    """True when (a, b) reads as a Kenyan lat, lon pair, as Google Maps copies it."""
    return abs(a) <= 5.5 and 33 <= abs(b) <= 42


def coordinates(text):
    """Coordinates in what the customer wrote, as a Place, or None:
    a Google Maps link (the place's pin !3d..!4d, else the map's centre @lat,lon); a point with
    N/S/E/W, in decimal degrees or degrees, minutes and seconds; a point 'lat, lon' as Google
    Maps copies it (or 'lon, lat'); a box 'west, south, east, north' or two corners 'lat, lon,
    lat, lon'. Plot numbers, sizes, distances, dates and phone numbers are not coordinates, and
    plain numbers far from East Africa count only when written precisely; such a point is
    flagged in place['warn']."""
    if not text:
        return None
    t = str(text).translate(DASHES).translate(QUOTES)
    src = "coordinates in the request"
    pin = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", t)
    m = pin or re.search(r"@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", t)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        p = Place(name="Custom area", kind="point", centre=(lon, lat), source=src)
        if not pin:
            p["warn"] = ("The link gave the map's centre, not a pin: check the point is the customer's "
                         "place (a link to a dropped pin is better).")
        return _checked(p, precise=True)
    named = re.search(r"(?i)\blat\w*\.?\s*[:=]?\s*(-?\d+\.\d+)\W{0,4}\s*(?:and\s+)?lo?ng?\w*\.?\s*[:=]?\s*(-?\d+\.\d+)", t)
    if named:
        lat, lon = float(named.group(1)), float(named.group(2))
        if abs(lat) <= 90 and abs(lon) <= 180:
            return _checked(Place(name="Custom area", kind="point", centre=(lon, lat), source=src), precise=True)
    hemi = _hemispheres(t)
    if hemi:
        return _checked(Place(name="Custom area", kind="point", centre=hemi, source=src), precise=True)
    if hemi is False:                   # degrees or N/S/E/W that do not make a point: ask, never guess
        return None
    clean = NOT_COORDS.sub(" | ", t)
    for run in RUN.finditer(clean):
        toks = re.findall(NUM, run.group(0))
        vals = [float(v) for v in toks]
        decimals = [len(v.split(".")[1]) if "." in v else 0 for v in toks]
        if len(vals) == 4:
            a, b, c, d = vals
            if _lat_first_kenya(a, b) and _lat_first_kenya(c, d):      # two Google Maps corners
                a, b, c, d = b, a, d, c
            w, e, s, n = min(a, c), max(a, c), min(b, d), max(b, d)
            if w < e and s < n and abs(s) <= 90 and abs(n) <= 90 and abs(w) <= 180 and abs(e) <= 180:
                p = Place(name="Custom area", kind="box", bbox=(w, s, e, n), source=src,
                          centre=((w + e) / 2, (s + n) / 2))
                return _checked(p, precise=min(decimals) >= 3)
            continue
        if len(vals) == 2 and min(decimals) >= 1:     # a point: two decimals side by side
            a, b = vals
            if abs(a) > 90 >= abs(b) or (33 <= abs(a) <= 42 and abs(b) <= 5.5):   # lon, lat
                lon, lat = a, b
            else:                                     # lat, lon, as Google Maps gives it
                lat, lon = a, b
            if abs(lat) <= 90 and abs(lon) <= 180:
                return _checked(Place(name="Custom area", kind="point", centre=(lon, lat), source=src),
                                precise=min(decimals) >= 3)
    return None


def _checked(p, precise):
    """Keep a point or box near East Africa; far away only when written precisely, and flagged."""
    lon, lat = p["centre"]
    if in_east_africa(lon, lat):
        return p
    if not precise:
        return None
    p["warn"] = (f"FAR FROM KENYA: the coordinates give {lat:.4f}, {lon:.4f}. Check the order (lat, lon) "
                 "and the signs (S and W are negative) before drafting.")
    return p


# ------------------------------------------------------------------ what places are known

@lru_cache(None)
def gazetteer():
    import yaml
    return yaml.safe_load((HERE / "places.yml").read_text(encoding="utf-8")) or []


@lru_cache(None)
def kenya_outline():
    """Kenya as one shape, from the county boundaries; None when they are not fetched."""
    try:
        from common import county_boundaries
        import shapely
        k = shapely.make_valid(county_boundaries().geometry.union_all())
        shapely.prepare(k)
        return k
    except Exception:                                   # noqa: BLE001 - optional
        return None


def country_at(lon, lat):
    """The country a point is in: Kenya from the county boundaries, else Natural Earth's name."""
    import shapely
    k = kenya_outline()
    if k is not None and shapely.contains_xy(k, lon, lat):
        return "Kenya"
    try:
        import warnings
        from shapely.geometry import Point
        from common import countries
        g = countries()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = g.distance(Point(lon, lat))
        return str(g.loc[d.idxmin(), "NAME"]) if d.min() < 0.1 else None
    except Exception:                                   # noqa: BLE001
        return None


@lru_cache(None)
def towns():
    """Named points, best source first: places.yml towns (set up for the gold prints), the
    towns on the county plates, then Natural Earth's populated places, whose country is
    checked against the Kenyan county boundaries (Natural Earth puts Mandera in Somalia)."""
    out = []
    for p in gazetteer():
        if p.get("kind") == "town":
            out.append(dict(name=p["name"], centre=tuple(p["centre"]), pop=0, country="Kenya",
                            radius_km=p.get("radius_km"), source="places.yml"))
    set_up = {norm(t["name"]) for t in out}
    try:
        from relief import COUNTY_LABELS
        for cfg in COUNTY_LABELS.values():
            for name, value, lon, lat, *_ in cfg.get("labels", []):
                if value is None and norm(name) not in set_up:
                    set_up.add(norm(name))
                    out.append(dict(name=name, centre=(lon, lat), pop=0, country="Kenya", source="the county plates"))
    except Exception:                                   # noqa: BLE001 - the list is a convenience
        pass
    try:
        import geopandas as gpd
        import numpy as np
        import shapely
        from common import DATA
        g = gpd.read_file(DATA / "ne" / "ne_10m_populated_places",
                          columns=["NAME", "NAMEASCII", "ADM0NAME", "POP_MAX", "LATITUDE", "LONGITUDE"],
                          ignore_geometry=True)
        k = kenya_outline()
        in_kenya = (shapely.contains_xy(k, g.LONGITUDE.to_numpy(), g.LATITUDE.to_numpy()) if k is not None
                    else np.asarray(g.ADM0NAME == "Kenya"))
        for r, ke in zip(g.itertuples(), in_kenya):
            out.append(dict(name=str(r.NAME), alt=str(r.NAMEASCII), centre=(float(r.LONGITUDE), float(r.LATITUDE)),
                            pop=int(r.POP_MAX or 0), country="Kenya" if ke else str(r.ADM0NAME),
                            source="Natural Earth populated places"))
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


@lru_cache(None)
def country_names():
    """norm(name) -> (Natural Earth ADMIN name for the spec, the name for the title), for every
    country under its ADMIN, NAME and NAME_LONG spellings and regions.ALIASES, in any case."""
    try:
        import regions
        from common import countries
        g = countries()
    except Exception:                                   # noqa: BLE001
        return {}
    out, by_admin = {}, {}
    for admin, short, long_ in zip(g["ADMIN"], g["NAME"], g["NAME_LONG"]):
        title = long_ if "." in str(short) else short           # 'S. Sudan' -> 'South Sudan'
        by_admin[admin] = (admin, title)
        for n in (admin, short, long_):
            if isinstance(n, str) and norm(n):
                out.setdefault(norm(n), (admin, title))
    for alias, admin in regions.ALIASES.items():
        if admin in by_admin:
            out.setdefault(norm(alias), by_admin[admin])
    return out


def keys_for(name):
    """Normalised spellings of a name: 'Mount Kenya' also as 'Mt Kenya'."""
    ks = {norm(name)}
    m = re.match(r"(?i)^(mount|mt\.?)\s+(.*)$", name)
    if m:
        ks |= {norm("mount " + m.group(2)), norm("mt " + m.group(2))}
    return ks


def bare_lake(name):
    return norm(re.sub(r"(?i)^lake\s+", "", name))


# ------------------------------------------------------------------ reading the area text

SETTING = r"(?i)\s+(?:near|in|around|at|of|by|outside|from|off|behind|opposite|along|next to|close to)\s+"
SEPARATORS = r"(?i)\s*(?:[,;/&+]|\band\b)\s*"
LEADING_SETTING = r"(?i)^(?:near|in|around|at|of|by|outside|from|off|behind|opposite|along|next to|close to)(?:\s+|$)"
FILLER = (r"(?i)\b(my|our|the|a|an|family|farm|land|plot|plots|shamba|home|house|estate|area|town|city|county|"
          r"region|centre|center|cbd|downtown|old|forest|reserve|map|print|poster|plate|relief|contours?|"
          r"surroundings|place|village|country|acres?|ac|ha|hectares?|kms?|lr|no)\b")


def unfill(s):
    """A place-name part without filler words ('my farm', 'CBD', 'county'), numbers or units."""
    out = []
    for part in re.split(r"\s*[,;/]\s*", s or ""):
        part = re.sub(r"\S*\d\S*", " ", re.sub(FILLER, " ", part))
        part = re.sub(LEADING_SETTING, "", part.strip())    # 'near Limuru' -> 'Limuru' 
        part = re.sub(r"\s+", " ", part).strip(" .-'")
        if part:
            out.append(part)
    return ", ".join(out)


def split_setting(text):
    """'Ngong Hills in Kajiado' -> ('Ngong Hills', 'Kajiado'): the place and the wider place it
    is in, split at the last 'in / near / at ...'; (text, None) when there is none."""
    parts = re.split(SETTING, f" {text.strip()} ")
    parts = [p.strip() for p in parts]
    if len(parts) < 2:
        return text.strip(), None
    return " ".join(parts[:-1]).strip(), parts[-1]


def candidates(area):
    """What the customer wrote, as (text, role), best first. 'named' is the place itself
    ('Ngong Hills' in 'Ngong Hills near Nairobi', 'Limuru' in 'my farm near Limuru');
    'context' is a wider place it is in ('Nairobi', the 'Siaya' of 'Bondo, Siaya')."""
    text = re.sub(r"\s+", " ", area.strip())
    out = [(text, "named")]
    chunks = [p for p in re.split(SEPARATORS, text) if p.strip()]
    for n, chunk in enumerate([text] + chunks):
        head, tail = split_setting(chunk)
        role = "named" if n <= 1 else "context"              # later list items are usually qualifiers
        if tail is None:
            out.append((chunk, role))
        elif not unfill(head):                               # 'my farm near Limuru': Limuru is the place
            out.append((tail, role))
        else:
            out += [(head, role), (tail, "context")]
    out += [(unfill(c), r) for c, r in list(out)]
    for c, r in list(out):
        words = unfill(c).split()
        if r == "named" and "," not in unfill(c) and len(words) > 1:
            out += [(" ".join(words[:n]), "first words") for n in range(len(words) - 1, 0, -1)]
    texts, roles = {}, {}
    for c, r in out:                                         # a text found as 'named' anywhere is named
        k = norm(c)
        if not k or (c != text and not norm(unfill(c))):    # only filler words or numbers: '1234', 'my farm'
            continue
        texts.setdefault(k, c)
        rank = {"named": 0, "first words": 1, "context": 2}
        roles[k] = min(r, roles.get(k, r), key=rank.get)
    return [(texts[k], role) for role in ("named", "first words", "context") for k in texts if roles[k] == role]


def named_parts(area):
    """The places a request lists one after another: 'Kenya, Uganda and Tanzania', 'Juja, Kiambu'."""
    out = []
    for p in re.split(SEPARATORS, area.strip()):
        head, tail = split_setting(p)
        q = unfill(head if unfill(head) else (tail or ""))
        if q and not re.search(r"\d", q):
            out.append(q)
    return list(dict.fromkeys(out))


def qualifiers(area, counties):
    """Countries and counties named after a comma or 'in' ('Mwanza, Tanzania', 'Bondo, Siaya',
    'Bondo in Siaya'), as (norm name, name, outline buffered by about 5 km)."""
    import shapely
    import regions
    from common import county_boundaries
    parts = []
    for chunk in re.split(SEPARATORS, area.strip()):
        bits = re.split(r"(?i)\s+in\s+", f" {chunk.strip()} ")
        if len(bits) > 1:
            parts.append(bits[-1])
    commas = [p for p in area.split(",") if p.strip()]
    if len(commas) == 2:
        parts.append(commas[1])
    out = []
    cb = None
    for part in dict.fromkeys(unfill(p) for p in parts):
        k = norm(part)
        if not k:
            continue
        geom = None
        hit = [c for c in counties if norm(c) == k]
        try:
            if hit:
                cb = cb if cb is not None else county_boundaries()
                geom = cb[cb["name"] == hit[0]].geometry.iloc[0]
            elif k in country_names():
                geom = regions.region_outline({"countries": [country_names()[k][0]], "keep_islands": True})[0]
        except (SystemExit, Exception):                    # noqa: BLE001
            geom = None
        if geom is not None:
            out.append((k, hit[0] if hit else country_names()[k][1], shapely.buffer(geom, 0.05)))
    return out


def point_of(place):
    if place.get("centre"):
        return tuple(place["centre"])
    if place.get("bbox"):
        w, s, e, n = place["bbox"]
        return ((w + e) / 2, (s + n) / 2)
    return None


def label(p):
    c = p.get("country")
    return f"{p['name']} ({p['kind']}, {c})" if c and c != "Kenya" else f"{p['name']} ({p['kind']})"


def abroad(p):
    return p["kind"] == "town" and p.get("country") not in (None, "", "Kenya")


# ------------------------------------------------------------------ finding the area

def resolve(area, style, online=True, subject=""):
    """Find the area. Returns (Place, candidates tried, list of notes).

    Order: coordinates; the place the customer named, exactly, among Kenyan counties, places.yml,
    towns, lakes, peaks and countries; then (online) OpenStreetMap's search in Kenya; then close
    spellings of Kenyan names; then the wider place it is in; then a town of that name abroad
    (flagged, and only in Kenya's neighbours unless the country is named); then (online)
    OpenStreetMap's search anywhere."""
    notes = []
    pt = coordinates(area)
    if pt:
        if pt.get("warn"):
            notes.append(pt.pop("warn"))
        return pt, [], notes
    import shapely
    from common import county_boundaries
    counties = list(county_boundaries()["name"])
    gaz = gazetteer()
    town_list = towns()
    peak_list = peaks()
    theme = theme_of(subject, area)
    wants_county = "county" in f"{area} {theme}".lower()        # a county page: 'Kirinyaga: County relief'
    wants_town = style == "gold" or bool(re.search(r"(?i)\b(town|city|centre|center|cbd|downtown)\b", area))
    area_n = norm(area)
    quals = qualifiers(area, counties)

    def options(key, key_text, fuzzy):
        """Every place whose name matches `key`, as (preference, Place)."""
        found = []
        if fuzzy and len(key) < 5:
            return found

        def hit(k):
            return k == key or (fuzzy and difflib.SequenceMatcher(None, k, key).ratio() >= 0.86)

        def near(pt):
            return pt is not None and in_east_africa(*pt)

        for c in counties:
            if hit(norm(c)) or hit(norm(c + " county")):
                found.append((0 if wants_county else 2, Place(name=c, kind="county", region={"county": c},
                                                               country="Kenya", source="the county boundaries")))
        for p in gaz:
            if p.get("kind") == "town":
                continue
            names = [p["name"]] + p.get("aliases", [])
            full = {k for n in names for k in keys_for(n)}
            bare = {bare_lake(n) for n in names} - full if p["kind"] == "lake" else set()
            if any(hit(k) for k in full) or any(hit(k) for k in bare):
                pref = 1 if any(hit(k) for k in full) else (5 if wants_town else 2.5)
                found.append((pref, Place(name=p["name"], kind=p["kind"], bbox=tuple(p["bbox"]),
                                          labels=p.get("labels", []), names=p.get("names", []),
                                          source="places.yml")))
        for t in town_list:
            kenyan = t.get("country") == "Kenya"
            if fuzzy and not (kenyan or (t.get("country") in NEAR_KENYA and t.get("pop", 0) >= 100_000)):
                continue                                     # Juja is not Jauja, Peru
            if hit(norm(t["name"])) or (t.get("alt") and hit(norm(t["alt"]))):
                pref = (0 if kenyan else 1) if wants_town else (3 if kenyan else 5)
                found.append((pref, Place(name=t["name"], kind="town", centre=t["centre"], pop=t.get("pop", 0),
                                          country=t.get("country", ""), radius_km=t.get("radius_km"),
                                          source=t["source"])))
        for lk in lakes_ne():
            if fuzzy and not near(point_of(lk)):
                continue
            full = keys_for(lk["name"]) | keys_for("Lake " + lk["name"])
            bare = {bare_lake(lk["name"])} - full
            if any(hit(k) for k in full | bare):
                found.append((1 if any(hit(k) for k in full) else (5 if wants_town else 2.5),
                              Place(name=lk["name"] if lk["name"].lower().startswith("lake") else "Lake " + lk["name"],
                                    kind="lake", bbox=pad(lk["bbox"], 0.08), source="Natural Earth lakes")))
        for pk in peak_list:
            if fuzzy and not near(pk["centre"]):
                continue
            if any(hit(k) for k in keys_for(pk["name"])):
                found.append((4, Place(name=pk["name"], kind="mountain", centre=pk["centre"],
                                       elevation=pk["elevation"], source="Natural Earth peaks")))
        if not fuzzy:
            if key == "africa":
                found.append((3, Place(name="Africa", kind="continent", source="Natural Earth countries",
                                       region={"continent": "Africa"})))
            elif key in country_names():
                admin, title = country_names()[key]
                found.append((3, Place(name=title, kind="country", source="Natural Earth countries",
                                       region={"countries": [admin]}, country=title)))
        # 'Mwanza, Tanzania', 'Bondo, Siaya': towns and peaks inside the country or county named
        q = [g for k, _, g in quals if k != key]
        if q:
            found = [f for f in found if f[1]["kind"] not in ("town", "mountain") or f[1]["source"] == "places.yml"
                     or any(shapely.contains_xy(g, *point_of(f[1])) for g in q)]
        return found

    def rank(f):                                             # curated first; abroad, the largest first
        p = f[1]
        return f[0], p.get("source") != "places.yml", abroad(p), -(p.get("pop") or 0)

    def search(fuzzy, roles):
        for cand, role in candidates(area):
            if role not in roles:
                continue
            tried.append(cand)
            found = options(norm(cand), cand, fuzzy)
            if found:
                found.sort(key=rank)
                if role == "first words":
                    notes.append(f'Only "{cand}" of "{unfill(area)}" was found; check the draft is the place meant.')
                return cand, found
        return None

    def pick(hit, fuzzy=False):
        cand, found = hit
        best = found[0][1]
        others = list(dict.fromkeys(label(p) for _, p in found[1:] if label(p) != label(best)))[:4]
        if fuzzy:
            notes.append(f'"{cand}" was read as {best["name"]} (a close spelling); check that is right.')
        if others:
            notes.append("Also matched: " + "; ".join(others) + ". Change the spec if one of these was meant.")
        return best

    def country_named(p):
        c = norm(p.get("country") or "")
        return bool(c) and (c in area_n or any(norm(n) == c or k == c for k, n, _ in quals))

    def search_osm(kenya_only):
        for term in search_terms(area):
            p = nominatim(term, kenya_only)
            if p is False:                                   # offline or refused: stop asking
                return False
            if p:
                where = "in Kenya" if kenya_only else f"({p.get('country') or 'country not given'})"
                notes.append(f'Found "{term}" by OpenStreetMap search {where}; check the extent carefully.')
                if not kenya_only and p.get("country") not in (None, "", "Kenya"):
                    notes.insert(0, f"OUTSIDE KENYA: {p['name']}, {p.get('country')}. Check it is the place meant.")
                return p
        return None

    tried = []
    whole = several_countries(area)
    if whole:
        return whole, [area], notes
    exact = search(False, {"named", "first words"})
    doubtful = None
    if exact:
        best = exact[1][0][1]
        home = [f for f in exact[1] if not abroad(f[1])]
        if abroad(best) and home and not country_named(best):
            exact = (exact[0], home + [f for f in exact[1] if abroad(f[1])])
            best = home[0][1]
        big = best.get("country") in NEAR_KENYA and (best.get("pop") or 0) >= 250_000   # Kampala, Arusha
        if not abroad(best) or country_named(best) or big:
            place = pick(exact)
            if abroad(place) and not country_named(place):
                notes.insert(0, f"Outside Kenya: {place['name']}, {place['country']}. Check that is the place meant.")
            return place, tried, notes + also_named(area, place, exact[0], quals)
        doubtful = exact                                     # a town abroad: look for a Kenyan one first
    if online:
        p = search_osm(kenya_only=True)
        if p:
            if doubtful:
                b = doubtful[1][0][1]
                notes.append(f"There is also a {b['name']} in {b['country']} (Natural Earth); change the spec "
                             "if that was meant.")
            return p, tried, notes + also_named(area, p, p["name"], quals)
        if p is False:
            online = False
    close = search(True, {"named", "first words"})
    if close:
        place = pick(close, fuzzy=True)
        return place, tried, notes + also_named(area, place, close[0], quals)
    wider = search(False, {"context"})
    if wider and not doubtful:
        place = pick(wider)
        missing = [unfill(c) for c, r in candidates(area) if r == "named" and unfill(c) and norm(c) != norm(area)]
        what = missing[0] if missing else area
        notes.insert(0, f'"{what}" was not found, so the draft is all of {place["name"]} ({place["kind"]}), the wider '
                        "place the request names. Give the place's coordinates (or add it to places.yml) and draft "
                        "again.")
        return place, tried, notes
    if doubtful:
        best = doubtful[1][0][1]
        if best.get("country") in NEAR_KENYA:
            place = pick(doubtful)
            notes.insert(0, f"OUTSIDE KENYA: {place['name']}, {place['country']}. No Kenyan place of that name "
                            "was found; if the customer meant one, give its coordinates or add it to places.yml.")
            return place, tried, notes
    if online:
        p = search_osm(kenya_only=False)
        if p:
            return p, tried, notes
    abroad_hint = ""
    if doubtful:
        b = doubtful[1][0][1]
        abroad_hint = (f"\nThe only {b['name']} found is in {b['country']}; if that is the place, ask for "
                       f"\"{b['name']}, {b['country']}\".")
    raise SystemExit(
        f'Could not find "{area}" in Kenya. Tried: {", ".join(chr(34) + c + chr(34) for c in dict.fromkeys(tried))}.'
        f'{abroad_hint}\n'
        "Give coordinates instead (a point as 'lat, lon' from Google Maps, or a box as 'west, south, east, north'),\n"
        "or add the place to places.yml" + ("." if online else ", or run online so OpenStreetMap's search can help."))


def several_countries(area):
    """'Kenya, Uganda and Tanzania' as one region of those countries; None otherwise."""
    if norm(area) in country_names():                          # 'Trinidad and Tobago' is one country
        return None
    parts = [unfill(p) for p in re.split(SEPARATORS, area.strip()) if unfill(p)]
    if len(parts) < 2 or not all(norm(p) in country_names() for p in parts):
        return None
    hits = [country_names()[norm(p)] for p in parts]
    admins = list(dict.fromkeys(a for a, _ in hits))
    titles = list(dict.fromkeys(t for _, t in hits))
    name = ", ".join(titles[:-1]) + " and " + titles[-1] if len(titles) > 1 else titles[0]
    return Place(name=name, kind="countries", region={"countries": admins}, source="Natural Earth countries")


def also_named(area, place, cand, quals=()):
    """A note when the request lists more places than the draft draws."""
    drawn = {norm(cand), norm(unfill(cand)), norm(place["name"]), norm(place.get("country") or ""), "kenya"}
    drawn |= {k for k, _, _ in quals}
    left = [p for p in named_parts(area) if norm(p) not in drawn and norm(p) not in norm(place["name"])]
    if not left or len(named_parts(area)) < 2:
        return []
    return [f"The request also names {', '.join(left)}; the draft is drawn for {place['name']} alone. If they want "
            "the other places on the sheet too, widen the extent or add them as labels."]


_LAST_SEARCH = [0.0]


def search_terms(area, limit=3):
    """What may be sent to OpenStreetMap: the place-name parts of the area, never the
    customer's sentence. Parts with numbers (plot, LR and phone numbers, distances),
    e-mail addresses or possessives (someone's shop) stay on this computer."""
    terms, seen = [], set()

    def add(part):
        part = re.sub(r"\s+", " ", part).strip(" .-,")
        if (not part or re.search(r"\d|@", part) or re.search(r"(?i)['’]s\b", part)
                or len(part.split()) > 5 or norm(part) in seen):
            return
        seen.add(norm(part))
        terms.append(part)

    commas = [p for p in area.split(",") if p.strip()]
    if len(commas) == 2:                 # 'Bondo, Siaya' is a good query as it is: a place and where it is
        parts = []
        for p in commas:
            head, tail = split_setting(p)
            parts.append(unfill(head) or unfill(tail or ""))
        if all(parts):
            add(", ".join(parts))
    heads, tails = [], []
    for p in re.split(r"[,;/()]|\band\b|&", area):
        head, tail = split_setting(p.strip())                # 'our home in Westlands' -> 'Westlands'
        if unfill(head):
            heads.append(unfill(head))
        if tail and unfill(tail):
            (tails if unfill(head) else heads).append(unfill(tail))
    for part in heads + tails:
        add(part)
    return terms[:limit]


def nominatim(term, kenya_only=True):
    """One OpenStreetMap search for a place name: a Place, None when nothing fits, or False when the
    search cannot be reached. Waits a second between searches, as OpenStreetMap asks."""
    import urllib.parse
    import urllib.request
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&addressdetails=1&q="
           + urllib.parse.quote(term) + ("&countrycodes=ke" if kenya_only else ""))
    wait = 1.0 - (time.time() - _LAST_SEARCH[0])
    if wait > 0:
        time.sleep(wait)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode())
    except Exception as e:                               # noqa: BLE001 - offline, blocked, refused
        print(f"  OpenStreetMap search not available ({type(e).__name__})")
        return False
    finally:
        _LAST_SEARCH[0] = time.time()
    for r in res:                                        # places and landforms, not shops or roads
        if r.get("category") not in ("place", "natural", "boundary", "leisure", "landuse", "tourism", "water",
                                     "waterway", "mountain_pass"):
            continue
        s, n, w, e = (float(v) for v in r["boundingbox"])
        at = r.get("addresstype")
        country = (r.get("address") or {}).get("country")
        if at == "country" and norm(r.get("name", "")) in country_names():
            admin, title = country_names()[norm(r["name"])]
            return Place(name=title, kind="country", region={"countries": [admin]}, country=title,
                         source="OpenStreetMap search (Nominatim)")
        if at in ("city", "town", "village", "suburb", "neighbourhood", "hamlet", "quarter", "city_district"):
            kind = "town"
        elif r.get("type") in ("peak", "volcano", "hill", "ridge", "mountain_range"):
            kind = "mountain"
        elif r.get("type") in ("water", "lake", "reservoir"):
            kind = "lake"
        else:
            kind = "area"
        # a building or a point comes back a few metres across: give it a usable size
        min_km = 30 if kind == "mountain" else 8
        return Place(name=r.get("name") or term, kind=kind, bbox=pad((w, s, e, n), 0.0, min_km=min_km),
                     centre=(float(r["lon"]), float(r["lat"])), country=country or "",
                     source="OpenStreetMap search (Nominatim)")
    return None


# ------------------------------------------------------------------ the draft spec

def num(v):
    """1 761, the house style for numbers of four digits or more."""
    return f"{v:,.0f}".replace(",", " ")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip("-")


def slug_name(place):
    """The name in a draft's file name: the place, or where a coordinate request points."""
    if place["kind"] in ("point", "box") and place["name"] == "Custom area":
        lon, lat = place["centre"]
        return f"point {abs(lat):.3f}{'s' if lat < 0 else 'n'} {abs(lon):.3f}{'e' if lon >= 0 else 'w'}"
    return place["name"]


def extent(place):
    """The box a block region draws for a place, in the map box's shape."""
    if place.get("bbox") and place["kind"] not in ("town", "point"):
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
    """The round interval that gives closest to `lines` contours (40 to 80 read well), never finer than
    5 m: the 30 m model is a surface model, with trees and buildings, and can't support a finer one.
    Every interval here gives a whole-metre index contour at x5."""
    return min((5, 10, 20, 25, 50, 100, 200),
               key=lambda v: abs(math.log(max(relief_m, 1) / v / lines)))


def relief_of(b):
    """Height range of a box from the 30 m model (downloads the tiles if needed)."""
    import fetch_data
    from common import load_dem
    w, s, e, n = b
    fetch_data.dem((math.floor(w), math.floor(s), math.ceil(e), math.ceil(n)), 10, "glo30")
    z, _ = load_dem((round(w, 3), round(s, 3), round(e, 3), round(n, 3)), "glo30")
    z = z[(z != 0) & (z > -100)]     # load_dem fills cells no tile covers (sea, seams between tiles) with 0
    if z.size == 0:
        raise ValueError("no elevation in the box (at sea, or the coordinates swapped?)")
    return float(z.min()), float(z.max())


def label_entries(entries, b):
    return [dict(x) for x in entries if inside(b, x["lon"], x["lat"], 0.02)]


def contour_sheet(centre, scale):
    """The ground box a contour sheet shows at this scale (the map box less the inset)."""
    return km_box(centre[0], centre[1], (BOX_MM[0] - 2 * CONTOUR_INSET_MM) * scale / 1e6,
                  (BOX_MM[1] - 2 * CONTOUR_INSET_MM) * scale / 1e6)


def build_spec(place, style, request):
    """Returns (spec dict, style actually drawn, notes)."""
    notes = []
    name = place["name"]
    number = "01"
    asked = style
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
    if style == "gold" and place["kind"] not in ("town", "point", "box"):
        notes.append(f"Roads in gold need a town; {name} is a {place['kind']}, so the draft is relief. For gold, "
                     "draft again with the town centre's coordinates (lat, lon) as the area.")
        style = "relief"
    if place["kind"] in ("point", "box") and name == "Custom area":
        notes.append("The request gave coordinates, not a name: the title is \"Custom area\" until you set it.")

    if style == "gold":
        pop = place.get("pop") or 0
        if place["kind"] == "box":                           # the circle fits inside their box
            w, s, e, n = place["bbox"]
            lon, lat = (w + e) / 2, (s + n) / 2
            radius = round(max(1.0, min((e - w) * 111.32 * math.cos(math.radians(lat)), (n - s) * 110.57) / 2), 1)
        else:
            lon, lat = place["centre"]
            radius = place.get("radius_km") or (7.0 if pop >= 1_000_000 else 5.5 if pop >= 200_000 else 3.5)
        country = place.get("country") or country_at(lon, lat) or "Kenya"
        spec = {"slug": f"draft-{slugify(slug_name(place))}-gold",
                "city": {"name": name, "country": country, "lon": round(float(lon), 4),
                         "lat": round(float(lat), 4), "radius_km": float(radius)}}
        notes.append(f"The circle reaches {radius:g} km from the centre of {name}; raise radius_km to take in more "
                     "of the town" + ("." if country == "Kenya" else " (the roads are fetched again for a bigger "
                                                                     "circle)."))
        if country != "Kenya":
            notes.append(f"The country line reads {country.upper()}; roads outside Kenya are downloaded from "
                         "Overture Maps on the first render.")
        return spec, style, notes

    slug = f"draft-{slugify(slug_name(place))}-{style}"
    title = name
    if place.get("region"):
        region, b = place["region"], None
    else:
        b = extent(place)
        region = {"bbox": [round(float(v), 4) for v in b]}

    if style == "contours":
        w, s, e, n = b
        centre = [round((w + e) / 2, 4), round((s + n) / 2, 4)]
        wk = (e - w) * 111.32 * math.cos(math.radians((s + n) / 2))
        import regions
        scale = max(10_000, regions.tidy_scale(wk * 1000, (n - s) * 110_570, BOX_MM))
        if scale > 150_000:
            notes.append(f"{name} is large for contours (it needs 1:{num(scale)}); the draft is held at 1:150 000 "
                         "around the centre. Contours read best from 1:10 000 to 1:100 000.")
            scale = 150_000
        sheet = contour_sheet(centre, scale)                 # what the sheet shows at this scale
        labels = label_entries(place.get("labels", []), sheet)
        names = label_entries(place.get("names", []), sheet)
        dropped = ([x["name"] for x in place.get("labels", []) if dict(x) not in labels]
                   + [x["text"] for x in place.get("names", []) if dict(x) not in names])
        if dropped:
            notes.append("Off the sheet at this scale, so left out: " + ", ".join(dropped) + ".")
        try:
            lo, hi = relief_of(sheet)
            interval = nice_interval(hi - lo)
            notes.append(f"Heights on the sheet run from about {num(lo)} m to {num(hi)} m; "
                         f"a {interval:g} m interval gives about {int((hi - lo) / interval)} contours.")
            if (hi - lo) / interval < 25:
                notes.append(f"The sheet is flat for a contour study (only {num(hi - lo)} m of relief): open water "
                             "or plain shows few contours. Move `centre` to a hill or shore, use a closer scale, "
                             "or make the draft relief.")
        except Exception as err:                        # noqa: BLE001 - no elevation data offline
            interval = 10 if scale <= 25_000 else 20 if scale <= 75_000 else 50
            notes.append(f"Could not read the elevation to choose an interval ({err or type(err).__name__}); "
                         f"{interval} m is a guess.")
        spec = {"slug": slug, "title": title, "subtitle": "A contour study", "label": "CUSTOM", "number": number,
                "centre": centre, "scale": int(scale), "interval": interval, "index": interval * 5,
                "labels": labels, "names": names}
        return spec, style, notes

    subtitle = {"relief": "Relief", "population": "Where people live"}[style]
    spec = {"slug": slug, "title": title, "subtitle": subtitle, "label": "CUSTOM", "number": number,
            "region": region}
    if place["kind"] == "county":
        from relief import COUNTY_NUMBERS
        spec["subtitle"] = "County relief" if style == "relief" else "Where the county's people live"
        if name in COUNTY_NUMBERS:
            spec["label"], spec["number"] = "COUNTY", f"{COUNTY_NUMBERS[name]:03d}"
        if style == "relief" and asked in ("relief", "unsure"):
            notes.append(f"This is the shop's {name} County plate. Unless they asked for changes, the print master "
                         f"can be the plate itself: python relief.py \"county:{name}\" 300 40.")
    if style == "relief":
        labels = list(place.get("labels", []))
        if place["kind"] == "county":
            from relief import COUNTY_LABELS
            cl = COUNTY_LABELS.get(name, {})
            labels += [dict(name=x[0], value=x[1], lon=x[2], lat=x[3], side=x[4], snap=x[5])
                       for x in cl.get("labels", [])]
            spec["names"] = [dict(text=x[0], lon=x[1], lat=x[2], angle=x[3], size=x[4]) for x in cl.get("names", [])]
            if not labels:
                labels = county_towns(name)
                notes.append(f"No towns are set up for {name} County's plate yet"
                             + (f"; the draft labels {', '.join(x['name'] for x in labels)} from Natural Earth: check "
                                "them, and add them to COUNTY_LABELS in relief.py if they should stay." if labels
                                else "; add the main towns as labels."))
        elif place.get("elevation") and place.get("centre"):
            lon, lat = place["centre"]
            labels.append(dict(name=name, value=f"{num(place['elevation'])} m", lon=round(lon, 4),
                               lat=round(lat, 4), side="right", snap=3000))
        elif b is not None and not labels:
            labels = [dict(name=t["name"], lon=round(float(t["centre"][0]), 4), lat=round(float(t["centre"][1]), 4),
                           side="right") for t in nearby_towns(b, place, 3)]
        if b is not None:
            labels = label_entries(labels, b)
        spec["labels"] = labels
        if place.get("names"):
            spec["names"] = spec.get("names", []) + (label_entries(place["names"], b) if b else place["names"])
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


def county_towns(county, limit=4):
    """The largest Natural Earth towns inside a county, as relief labels."""
    try:
        import shapely
        from common import county_boundaries
        cb = county_boundaries()
        geom = cb[cb["name"] == county].geometry.iloc[0]
    except Exception:                                           # noqa: BLE001
        return []
    out, seen = [], set()
    for t in sorted(towns(), key=lambda t: -t.get("pop", 0)):
        if t["source"] != "Natural Earth populated places" or norm(t["name"]) in seen:
            continue
        if shapely.contains_xy(geom, *t["centre"]):
            seen.add(norm(t["name"]))
            out.append(dict(name=t["name"], lon=round(t["centre"][0], 4), lat=round(t["centre"][1], 4), side="right"))
            if len(out) == limit:
                break
    return out


def sheet_test(spec):
    """A function (lon, lat) -> True when the point is on the draft's sheet."""
    import shapely
    if spec.get("city"):
        c = spec["city"]
        r = c["radius_km"]
        return lambda lon, lat: math.hypot((lon - c["lon"]) * 111.32 * math.cos(math.radians(c["lat"])),
                                           (lat - c["lat"]) * 110.57) <= r
    if spec.get("centre") and spec.get("scale"):                 # contours
        b = contour_sheet(spec["centre"], spec["scale"])
        return lambda lon, lat: inside(b, lon, lat, 0.0)
    region = spec.get("region") or {}
    if region.get("bbox"):
        return lambda lon, lat: inside(region["bbox"], lon, lat, 0.0)
    try:
        import regions
        geom = regions.region_outline(region)[0]
        return lambda lon, lat: bool(shapely.contains_xy(geom, lon, lat))
    except (SystemExit, Exception):                              # noqa: BLE001
        return lambda lon, lat: False


def notes_point(request_notes, spec):
    """Coordinates in the customer's notes: (label or None, note or None)."""
    pt = coordinates(request_notes or "")
    if not pt or not pt.get("centre"):
        return None, None
    lon, lat = pt["centre"]
    if not sheet_test(spec)(lon, lat):
        return None, (f"Their notes give coordinates ({lat:.5f}, {lon:.5f}) that are not on the draft: check them "
                      "with the customer, or move the extent.")
    if "labels" not in spec:
        return None, (f"Their notes give a point ({lat:.5f}, {lon:.5f}); this style has no point labels, so mark it "
                      "by hand if they want it shown.")
    return (dict(name="Customer's place", lon=round(lon, 5), lat=round(lat, 5), side="right"),
            "The coordinates in their notes are marked \"Customer's place\"; rename the label.")


# ------------------------------------------------------------------ files, render, stamp, notes

SCRIPT = {"relief": "relief.py", "population": "population.py", "contours": "contours.py", "gold": "cities.py"}


def request_key(request):
    return hashlib.sha1("|".join(str(request.get(k) or "") for k in (
        "name", "phone", "email", "area", "style", "subject", "size", "frame", "paper", "notes")).encode()
    ).hexdigest()[:8]


def write_spec(spec, head, replace=False):
    """Write the draft spec without losing another request's draft or your edits: the same request
    run again on an unedited draft reuses its file; anything else takes the next free number.
    Returns (path, the slug it was first given)."""
    import yaml
    DRAFTS.mkdir(parents=True, exist_ok=True)
    first = spec["slug"]
    gold = first.endswith("-gold")
    stem, kind = (first.removesuffix("-gold"), "gold") if gold else first.rsplit("-", 1)
    for n in range(1, 1000):
        spec["slug"] = first if n == 1 else f"{stem}-{n}-{kind}"
        path = DRAFTS / f"{spec['slug']}.yml"
        text = head + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=110)
        if replace or not path.exists():
            break
        if path.read_text(encoding="utf-8").split("\n", 1)[-1] == text.split("\n", 1)[-1]:
            break                                     # the same request, not edited since: nothing is lost
    path.write_text(text, encoding="utf-8")
    return path, first


def why_failed(log):
    """The last line of a failed render's log, and what it most likely means."""
    lines = [l.strip() for l in log.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else "the script printed nothing"
    low = log.lower()
    if ("merge" in low and "indexerror" in last.lower()) or "no elevation" in low:
        hint = ("No elevation tiles cover this extent: open sea, or the coordinates swapped or mistyped. "
                "Check the centre or bbox in the spec.")
    elif "does not cover" in last:
        hint = "The sheet runs off the elevation data: move the centre or use a smaller scale."
    elif "argmax" in last or "empty sequence" in last:
        hint = "A label or name lies outside the sheet: move it inside the extent or delete it from the spec."
    elif "kontur" in low and ("no such file" in low or "not recognized" in low):
        hint = "The Kontur population file for this country is not in $ZP_DATA/kontur: see fetch_data.py."
    elif any(w in log for w in ("ConnectionError", "Max retries", "Temporary failure in name resolution",
                                "URLError", "timed out")):
        hint = "Data could not be downloaded: check the internet connection and render again."
    else:
        hint = "See the full log."
    return last, hint


def output_name(slug, style, dpi):
    """The file a renderer writes, by its own rule (250 dpi and up is a master, without _<dpi>)."""
    from common import OUT
    if style == "gold":
        return OUT / f"{slug.removesuffix('-gold')}-gold_1600.png"
    return OUT / (f"{slug}.png" if dpi >= 250 else f"{slug}_{dpi}.png")


def render(spec_path, style, slug, dpi, spp, log_path):
    """Returns (image, facts, None), or (None, facts, (last line, hint)) when the render fails."""
    rel = spec_path.relative_to(HERE)
    if style == "gold":
        cmd = [sys.executable, "cities.py", f"spec:{rel}", "1600"]
    else:
        cmd = [sys.executable, SCRIPT[style], f"spec:{rel}", str(dpi)] + ([str(spp)] if style != "contours" else [])
    out = output_name(slug, style, dpi)
    print("  " + " ".join(cmd[1:]))
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    log = proc.stdout + proc.stderr
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(" ".join(cmd[1:]) + "\n\n" + log, encoding="utf-8")
    facts = [l.strip().replace(f"spec:{rel}", slug) for l in proc.stdout.splitlines()
             if l.startswith((slug, f"spec:{rel}")) or "left out" in l or l.startswith("  WARNING")]
    if proc.returncode != 0 or not out.exists() or out.stat().st_mtime < t0 - 1:
        return None, facts, why_failed(log)
    return out, facts, None


def stamp(src, dest, when):
    """The proof on extra canvas, with red bands above and below it, a red border, and a faint
    FIRST LOOK across the map, so it is marked even when cropped."""
    from PIL import Image, ImageDraw
    from common import font
    im = Image.open(src).convert("RGB")
    if im.width > 1800:
        im = im.resize((1800, round(im.height * 1800 / im.width)), Image.LANCZOS)
    red = (178, 34, 34)
    edge = max(6, im.width // 160)
    band = max(44, im.width // 24)
    text = f"FIRST LOOK  ·  FOR ZEROPOINT ONLY  ·  NOT FOR THE CLIENT  ·  {when}"
    try:
        f = font("Barlow-600", int(band * 0.42))
        fm = font("Barlow-600", round(im.width * 0.035))
    except Exception:                                    # noqa: BLE001 - fonts not fetched
        from PIL import ImageFont
        f = fm = ImageFont.load_default()
    # a faint diagonal mark across the drawing, as proof_jpeg.py marks a proof
    mark = Image.new("RGBA", (im.width * 2, im.height * 2), (0, 0, 0, 0))
    dm = ImageDraw.Draw(mark)
    step = round(im.width * 0.16)
    for i, y in enumerate(range(0, mark.height, step)):
        dm.text(((i % 2) * step * 2 - step, y), ("FIRST LOOK  ·  NOT FOR THE CLIENT      ") * 4, font=fm,
                fill=(178, 34, 34, 60))
    mark = mark.rotate(30, resample=Image.BICUBIC)
    l, t = (mark.width - im.width) // 2, (mark.height - im.height) // 2
    body = im.convert("RGBA")
    body.alpha_composite(mark.crop((l, t, l + im.width, t + im.height)))
    # bands on extra canvas, so they cover nothing of the drawing
    out = Image.new("RGB", (im.width, im.height + 2 * band), red)
    out.paste(body.convert("RGB"), (0, band))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, out.width - 1, out.height - 1], outline=red, width=edge)
    for y in (band / 2, out.height - band / 2):
        d.text((out.width / 2, y), text, font=f, fill=(255, 255, 255), anchor="mm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, quality=88, optimize=True)
    return dest


def write_notes(path, request, place, style, spec_path, spec, notes, facts, image, dpi, spp,
                failed=None, log=None):
    rel = spec_path.relative_to(HERE)
    script = SCRIPT[style]
    again = (f"python cities.py spec:{rel} 1600" if style == "gold" else
             f"python {script} spec:{rel} {dpi}" + ("" if style == "contours" else f" {spp}"))
    master = (f"python cities.py spec:{rel} 6744" if style == "gold" else
              f"python {script} spec:{rel} 300" + ("" if style == "contours" else " 40"))
    proof_src = "$ZP_OUT/" + output_name(spec["slug"], style, dpi).name
    where = place.get("region") or (spec.get("region") or {}).get("bbox") or spec.get("centre") or spec.get("city")
    if style == "contours":
        where = (f"centre {spec['centre'][1]:.4f}, {spec['centre'][0]:.4f} (lat, lon) at "
                 + f"1:{num(spec['scale'])}")
    order = ", ".join(v for v in (request.get("size"), request.get("frame"), request.get("paper")) if v)
    asked = request.get("style") or theme_of(request.get("subject"), request.get("area", "")) or "not given"
    country = place.get("country")
    lines = [
        f"# First look: {spec.get('title') or spec['city']['name']}, {style}",
        "",
        f"Made {dt.datetime.now():%Y-%m-%d %H:%M}. For ZeroPoint only: do not send this draft to the customer.",
        "",
        "## The request",
        "",
        f"- Area: \"{request.get('area', '')}\"",
        f"- Style: \"{asked}\"",
    ]
    if order:
        lines.append(f"- Order: {order}")
    if request.get("name"):
        lines.append(f"- From: {request['name']} (contact details are in the request email)")
    if request.get("notes"):
        quoted = request["notes"].replace("\n", "\n  > ")
        lines.append(f"- Their notes:\n  > {quoted}")
    lines += [
        "",
        "## What the draft assumed",
        "",
        f"- Place: {place['name']} ({place['kind']}{', ' + country if country and country != place['name'] else ''}),"
        f" from {place['source']}.",
        f"- Drawn: {where}",
        f"- Style: {style}.",
    ]
    lines += [f"- {n}" for n in notes]
    if facts:
        lines += ["", "## From the render", ""] + [f"    {f}" for f in facts]
    if failed:
        lines += ["", "## The render failed", "",
                  f"- {failed[1]}", f"- The last line: `{failed[0]}`", f"- The full log: {log}",
                  "- Fix the spec, then render again with the command under \"Next\"."]
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
    if style != "gold":
        lines.append(f"- [ ] The plate number (now \"{spec.get('label', 'CUSTOM')} {spec.get('number', '01')}\").")
    lines += [
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
        f"Draft image: {image}" if image else
        ("Not rendered: the render failed (above)." if failed else "Not rendered (--no-render)."),
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
    ap.add_argument("--row", type=int, default=None,
                    help="which row of a CSV or JSON export, 0 the oldest (default: the newest)")
    ap.add_argument("--dpi", type=int, default=100, help="draft resolution, 50 to 249 (default 100)")
    ap.add_argument("--spp", type=int, default=16, help="ray-tracing samples for the draft (default 16)")
    ap.add_argument("--offline", action="store_true", help="never use OpenStreetMap's search")
    ap.add_argument("--no-render", action="store_true", help="write the spec and notes only")
    ap.add_argument("--replace", action="store_true",
                    help="write over an existing draft of the same name (your edits to it are lost)")
    args = ap.parse_args()
    if not 50 <= args.dpi < 250:
        ap.error("--dpi is for the first-look draft (50 to 249); make the print master with the command in the notes")

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
    style = style_of(request.get("style"), request.get("subject"), area)
    print(f"Request: \"{area}\", style {style}")

    try:
        place, _, notes = resolve(area, style, online=not args.offline, subject=request.get("subject", ""))
    except SystemExit as missing:
        pt = coordinates(request.get("notes", ""))
        if not pt:
            raise
        notes = [f'"{area}" was not found, so the draft is centred on the coordinates in their notes. '
                 "Set the title to the place's name."]
        if pt.get("warn"):
            notes.append(pt.pop("warn"))
        place = pt
        print(f"  {str(missing).splitlines()[0]} Using the coordinates in the notes.")
    print(f"  found {label(place)} in {place['source']}")
    spec, style, more = build_spec(place, style, request)
    notes += more
    mark, note = notes_point(request.get("notes"), spec)
    if mark:
        spec["labels"] = spec["labels"] + [mark]
    if note:
        notes.append(note)
    elif request.get("notes") and not mark:
        notes.append("Their notes are not on the draft yet: add the names they asked for by hand.")

    head = (f"# First-look draft from a proof request, {dt.date.today():%Y-%m-%d}. Edit freely; see maps/README.md.\n"
            f"# Request {request_key(request)}: area \"{area}\", style \"{request.get('style') or theme_of(request.get('subject'), area)}\"\n")
    spec_path, first = write_spec(spec, head, args.replace)
    if spec["slug"] != first:
        notes.append(f"maps/drafts/{first}.yml already holds another request or your edits, so this draft is "
                     f"{spec['slug']}.yml (--replace writes over the old one).")
    print(f"  spec: {spec_path.relative_to(HERE)}")

    from common import OUT
    folder = OUT / "first-look"
    folder.mkdir(parents=True, exist_ok=True)
    image, facts, failed = None, [], None
    log = folder / f"{spec['slug']}_render.log"
    if not args.no_render:
        src, facts, failed = render(spec_path, style, spec["slug"], args.dpi, args.spp, log)
        if not failed:
            image = stamp(src, folder / f"{spec['slug']}_FIRST-LOOK.jpg", f"{dt.date.today():%d %b %Y}".upper())
            print(f"  draft: {image}")
    path = write_notes(folder / f"{spec['slug']}_notes.md", request, place, style, spec_path, spec, notes,
                       facts, image, args.dpi, args.spp, failed, log)
    print(f"  notes: {path}")
    for n in notes:
        print(f"  - {n}")
    if failed:
        print(f"The render failed: {failed[1]}\n  ({failed[0]}; full log {log})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
