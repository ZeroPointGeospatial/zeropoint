"""First look: turn a proof request from the website into a draft for you, not the client.

    python first_look.py "Ngong Hills"                       # relief, the default for a place
    python first_look.py "ngonghills" --style "Relief, ray-traced like the county plates"
    python first_look.py "Kisumu" --style gold
    python first_look.py "my farm near Limuru" --style contours --notes "-1.112, 36.650"
    python first_look.py --request request.txt     # the proof-request email, pasted into a file
    python first_look.py --request export.csv      # a Formspree CSV or JSON export: the newest row
    python first_look.py "Lake Naivasha" --style "Lakes and water, 1984 to 2021"   # land cover, forest loss,
                                                   # water and true colour are relief with a drape (drapes.py)
    python first_look.py ... --no-render           # write the spec and notes only

What it does:

1. Reads the request: area, style, notes, and the size, frame and paper, from a
   pasted email (also a copied table, a quoted reply or a WhatsApp paste) or a
   Formspree export.
2. Finds the area, in this order: coordinates (a map link, a plus code, UTM,
   decimal degrees, degrees and minutes, N/S/E/W, a box); several countries; a
   Kenyan county, a landmark in places.yml, a town, a lake, a peak or a country,
   inside the county or country the request puts it in (Swahili place words are
   read too); then, when the computer is online, OpenStreetMap's search in Kenya;
   then close spellings of Kenyan names; then the wider place the request names
   (never a whole country for a place not found); then a town of that name in a
   neighbouring country, flagged; then the first words of a longer name.
3. Picks the style (relief, contours, population, roads in gold, or relief with a
   drape: land cover, forest loss, water, true colour) and writes a map spec,
   maps/drafts/<slug>.yml, in the house style. Another request's draft is never
   written over, nor your edits to this one: the new draft gets the next number.
   --replace writes over this request's own draft only.
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
OpenStreetMap's search is sent only the parts of the area that may be place
names: never numbers, e-mail addresses, links, possessives, the customer's own
name, the sender of a pasted WhatsApp chat, or a part with a kinship word or
title (Mzee, grandfather, Mr), a first name and surname just before "farm" or
"plot" ("Jane Wanjiku farm"), or a Swahili possessive ("shamba la Wanjiku",
"kwa Mama Wanjiru"). One word before "farm" is taken as where the land is
("Juja farm"), so a lone surname there ("Kamau plot") may be searched for, as
may a bare name given for the land ("Kamau Njoroge, Kiambu"): neither can be
told from a place name. A style written into the area ("Kenya land cover",
"Magadi true colour") is used when the request gives none, and a request for
one of the shop's own plates (a county, or plate 22 to 26) says so in the notes
with the master's command. Run from tools/prints with ZP_DATA and ZP_OUT set, as for every other
script. A southern point typed on the command line without a space
("-1.112,36.650") is read as a value, not an option.
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
import urllib.parse
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
# an email's foot: the signature delimiter alone on its line, a run of dashes ("---------- Forwarded
# message"), Formspree's own lines; not a customer's "-- and our family name"
FOOTER = re.compile(r"(?i)^(--\s*$|-{3,}|submitted\b|sent (from|via)\b|mark as spam|unsubscribe|view (it|this) )")
LABEL = re.compile(r"^([A-Za-z_][A-Za-z _,()]*?)(?:\s*:|\t)\s*(.*)$")   # 'area: x', or 'area<TAB>x' from a table
BARE_LABEL = re.compile(r"^[A-Za-z_][\w ]{0,30}:$")          # an unknown 'Message:' line ends a value too
FORM_TAIL = ("request", "website")                           # the form's own fields, after the customer's
# How a request may have been pasted: a reply's '> ', a WhatsApp line's time and sender
# ('[20/11/2026, 08:41:30] Name: ', '20/11/2026, 08:41 - Name: '), and, around a label only, a
# bullet or *bold*. A dash is a bullet only with a space after it, so '-1.112, 36.650' keeps its sign.
QUOTED = re.compile(r"^(?:>(?=[ \t>]|$)[ \t]?)+")
CHAT = re.compile("^(?:\\[[\\d/.,:\\- \u00a0\u202fAPMapm]{8,30}\\]"
                  "|\\d{1,4}[/.-]\\d{1,2}[/.-]\\d{2,4},? \\d{1,2}:\\d{2}(?::\\d{2})?(?:[ \u202f]?[APap]\\.?[Mm]\\.?)? -)"
                  "[ \u00a0\u202f]*(?P<who>[^:\\[\\]]{1,60}?):[ \t]+")
BULLET = re.compile("^[\u2022\u00b7\u25aa\u25e6\u2023\u25cf\u25cb\u25a0\u27a2\u27a4*+\\-\u2013\u2014][ \t]+")
BOLD = re.compile(r"^(\*{1,2})([^*\n]+?)\1(?=[\s:]|$)")


def _field(label):
    key = re.sub(r"\s*\(optional\)\s*", "", label.strip().lower()).strip(" :")
    return FIELDS.get(key)


def _unquote(line):
    """A pasted line without a reply's quote marks or a chat message's time and sender."""
    return CHAT.sub("", QUOTED.sub("", line.strip())).strip()


def _label(line):
    """(field, match) for a label line, read without a bullet or bold around the label."""
    line = BOLD.sub(r"\2", BULLET.sub("", line)).strip()
    m = LABEL.match(line)
    return _field(m.group(1) if m else line), m


def _is_label(line):
    """A form label ('Area to map', 'notes: ...'), the subject, or an email footer:
    anything that ends the value before it."""
    return bool(_label(line)[0] or SUBJECT_LINE.match(line) or FOOTER.match(line) or BARE_LABEL.match(line))


def _ends_notes(line, out):
    """Inside the notes, only the form's own fields, a field not read yet, the subject or the
    footer end them: a customer's 'Name: The Test Family' line is part of their notes."""
    if SUBJECT_LINE.match(line) or FOOTER.match(line):
        return True
    key, _ = _label(line)
    if key == "style" and _print_page(out.get("subject")):
        return False                       # a print page's form has no Style field: the customer's own line
    return bool(key) and (key in FORM_TAIL or (key not in out and key != "notes"))


def _print_page(subject):
    """A shop print page's form ('Proof request: <title>: <theme>') has no Style field; the custom
    page's subject is 'Proof request: custom map print'."""
    return bool(subject) and theme_of(subject).lower() != "custom map print"


def parse_request_text(text):
    """Fields from a pasted form email: 'area: ngonghills' lines, or a label line followed by its
    value on the next line, as some mail apps show them; also a copied table (label, tab, value),
    a quoted reply and a WhatsApp paste. The notes keep all their lines, labels inside them
    included; the subject is read with or without 'Subject:'."""
    out, lines = {}, [_unquote(l) for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        s = SUBJECT_LINE.match(line)
        if s:
            if not out.get("subject"):             # also fills a bare 'Subject' / '_subject' label
                out["subject"] = s.group(1).strip()
            i += 1
            continue
        key, m = _label(line)
        if key and key not in out:
            value = m.group(2).strip() if m else ""
            ends = (lambda l: _ends_notes(l, out)) if key == "notes" else _is_label
            if not value:                          # the value is on the next line
                j = i + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                if j < len(lines) and not ends(lines[j]):
                    value, i = lines[j], j
            if key == "notes" and value:           # free text: keep its other lines
                more, j = [], i + 1
                while j < len(lines) and not ends(lines[j]):
                    more.append(lines[j])
                    j += 1
                while more and not more[-1]:
                    more.pop()
                if more:
                    value, i = "\n".join([value] + more), j - 1
            if key == "subject" and not value:     # the subject line itself comes next
                i += 1
                continue
            out[key] = value
        i += 1
    for k in FORM_TAIL:
        out.pop(k, None)
    senders = _chat_senders(text)
    if senders and not out.get("name"):      # a WhatsApp paste: its sender is the customer
        out["name"] = ", ".join(senders)
    return out


def _chat_senders(text):
    """The senders of a WhatsApp paste, in order of their first message: the customer, and the
    owner when their own messages were copied too."""
    who = []
    for line in text.splitlines():
        m = CHAT.match(QUOTED.sub("", line.strip()))
        if m and m.group("who").strip() and m.group("who").strip() not in who:
            who.append(m.group("who").strip())
    return who


DATE_KEYS = ("_date", "date", "submitted at", "submitted_at", "created_at", "created at", "timestamp")


DATE_FORMATS = ("%b %d, %Y %I:%M %p", "%b %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d, %Y",
                "%d %b %Y %H:%M", "%d %B %Y %H:%M", "%a, %d %b %Y %H:%M:%S %z")
SLASH_DATE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:[ ,T]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?")


def _parse_time(v):
    """A submission time (UTC) from ISO, epoch seconds or milliseconds, 'Nov 20, 2026 8:41 AM', or
    '20/11/2026 08:41' when the day and month cannot be swapped; else None."""
    s = str(v).strip()
    if re.fullmatch(r"\d{9,13}(\.\d+)?", s):
        x = float(s)
        return dt.datetime.fromtimestamp(x / 1000 if x > 1e11 else x, dt.timezone.utc)
    m = SLASH_DATE.fullmatch(s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a != b and a <= 12 and b <= 12:
            return None                            # 05/11: May or November? don't guess
        d, mo = (a, b) if a > 12 or a == b else (b, a)
        h, mi, sec = int(m[4] or 0), int(m[5] or 0), int(m[6] or 0)
        if m[7]:
            h = h % 12 + (12 if m[7].lower() == "pm" else 0)
        try:
            return dt.datetime(y, mo, d, h, mi, sec, tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    s = s.replace("Z", "+00:00").replace(" UTC", "+00:00")
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        for f in DATE_FORMATS:
            try:
                t = dt.datetime.strptime(s, f)
                break
            except ValueError:
                pass
        else:
            return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _when(r):
    """The submission time of an export row (UTC), or None: every date column is tried."""
    for k, v in r.items():
        if k and str(k).strip().lower() in DATE_KEYS and v:
            t = _parse_time(v)
            if t:
                return t
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
    dated = all(times)
    if dated:                                        # oldest first, whatever order the export used
        order = sorted(range(len(rows)), key=lambda i: times[i])
        rows, times = [rows[i] for i in order], [times[i] for i in order]

    def fields(r):
        return {_field(k) or k: str(v) for k, v in r.items()
                if k and v is not None and _field(k) not in FORM_TAIL}

    def who(f):
        return ", ".join(x for x in (f.get("name"), f'"{f["area"]}"' if f.get("area") else None) if x)

    if not dated and len(rows) > 1 and row is None:   # never guess which request is the newest
        listing = "\n".join(f"  row {i}: {who(fields(r))}" for i, r in enumerate(rows))
        raise SystemExit(f"{path}: the dates of {len(rows) - sum(map(bool, times))} of the {len(rows)} rows could "
                         "not be read, so the newest request is not known. Pick one with --row (0 is the first in "
                         f"the file):\n{listing}")
    first, last = ("the oldest", "the newest") if dated else ("the first in the file", "the last in the file")
    if row is None:
        row = len(rows) - 1
    if not -len(rows) <= row < len(rows):
        raise SystemExit(f"{path} has {len(rows)} rows: --row goes from 0 ({first}) to {len(rows) - 1} ({last}), "
                         "or -1 for the last.")
    n = row % len(rows)
    out = fields(rows[n])
    if dated:
        print(f"Row {n} of {len(rows)} (0 is the oldest), sent {times[n]:%Y-%m-%d %H:%M} UTC: {who(out)}")
    else:
        print(f"Row {n} of {len(rows)}, counted in file order: {who(out)}")
    return out


STYLE_WORDS = [                  # first match wins; matched at the start of words
    ("gold", ("gold", "road", "street")),
    ("contours", ("contour", "topographic", "topo")),
    ("population", ("population", "people", "density")),
    ("landcover", ("land cover", "landcover", "land use", "vegetation")),
    ("forestloss", ("forest", "deforest", "tree cover", "trees")),
    ("truecolour", ("true colour", "true color", "satellite", "imagery", "photo")),
    ("water", ("lakes and water", "water", "flood", "lake level")),
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


# a style written into the area itself ('Kenya land cover', 'land cover of Kenya', 'Kampala in gold'):
# only at the end, or at the start before 'of' or 'for', and never a bare 'forest', 'water' or
# 'satellite' ('Riruta Satellite' is a Nairobi estate)
AREA_STYLES = [
    ("landcover", r"land\s*cover|land\s+use|vegetation"),
    ("forestloss", r"forest\s+loss|deforestation|tree\s+cover(?:\s+loss)?"),
    ("truecolour", r"(?:in\s+)?true\s+colou?r|from\s+(?:the\s+)?satellite|satellite\s+(?:image(?:ry)?|view|photo)"),
    ("water", r"surface\s+water|water\s+levels?|lake\s+levels?|lakes?\s+and\s+water|floods?|flooding"),
    ("population", r"population(?:\s+density)?"),
    ("contours", r"contours?|topographic(?:al)?"),
    ("gold", r"(?:in\s+)?gold|roads|streets"),
    ("rivers", r"rivers|drainage"),
    ("relief", r"relief|terrain|3d"),
]


def style_in_area(area):
    """'Kenya land cover' -> ('Kenya', 'landcover', 'land cover'); (area, None, None) when the
    area names no style, or nothing but one."""
    for key, pat in AREA_STYLES:
        for rx in (rf"(?i)[\s,;:-]+(?P<s>{pat})(?:\s+(?:map|print))?\s*$",
                   rf"(?i)^\s*(?:(?:a|the)\s+)?(?P<s>{pat})(?:\s+(?:map|print))?\s+(?:of|for)\s+"):
            m = re.search(rx, area)
            if m:
                rest = re.sub(r"\s+", " ", area[:m.start()] + " " + area[m.end():]).strip(" ,;:-")
                if unfill(rest):
                    return rest, key, m.group("s")
    return area, None, None


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
# numbers that are not coordinates: plot, LR and title numbers, sizes and distances, dates, phones.
# A plot or phone number is one number (with slashes, hyphens, or spaces only between digit groups):
# it never runs over a space into a signed or decimal number ('Plot 209/12 -1.112, 36.650').
NOT_COORDS = re.compile(
    r"(?i)\b(?:plots?|l\.?\s?r|title|parcel|block|house|hse|no|number|p\.?\s?o\.?\s?box|"
    r"tel|phone|mobile|whatsapp)\b\.?\s*(?:no\.?\s*)?\d+(?:(?:\s*/\s*|[.\-]|\s+(?!-|\d+\.\d))\d+)*"
    r"|[-+]?\d+(?:[.,]\d+)?\s*(?:acres?|ac|ha|hectares?|kms?|kilomet(?:re|er)s?|m|metres?|meters?|ft|feet|"
    r"miles?|mi|sq\w*|%|copies)\b"
    r"|(?<![\d.])\d{1,2}[/.\-]\d{1,2}[/.\-](?:19|20)?\d{2}(?![\d.])|(?<![\d.\-])(?:19|20)\d{2}(?![\d.])"
    r"|\+?\d[\d\s]{8,}\d")
# house, flat, plot and block numbers, often with a letter (House 12E, Block 5S): not N/S/E/W
ADDRESS = re.compile(
    r"(?i)\b(?:plots?|parcel|blo?c?k|house|hse|flat|apartment|apt|unit|room|door|court|phase|section|"
    r"stage|gate|no|number)\b\.?\s*(?:no\.?\s*)?[A-Z]?[\d/\-]*\d[A-Z]?\b")
# degrees stand alone: never the tail of a longer number (the 123 of 256123E)
_ANGLE = (r"(?<![\d.])(\d{1,3}(?:\.\d+)?)(?!\d)\s*°?\s*(?:(\d{1,2}(?:\.\d+)?)\s*'\s*)?"
          r"(?:(\d{1,2}(?:\.\d+)?)\s*(?:\"|'')\s*)?")
_SUFFIX = re.compile(_ANGLE + r"([NSEW])(?:orth|outh|ast|est)?(?![A-Za-z])", re.I)
_PREFIX = re.compile(r"(?<![A-Za-z])([NSEW])(?:orth|outh|ast|est)?\.?\s*" + _ANGLE, re.I)
# degrees, then minutes without a minute mark (as GPS units show them: S01 06.720, 1°06.720), then
# optional seconds: '1 06.720 S', '1°06.720S', 'S01 06.720', '1 17 45 S'. Decimal minutes after a
# plain space need two digits (06.720), so 'Plot 12 1.112S' is not read as 12°1.112'.
_MIN = r"(\d{1,2}(?![.\d])|\d{2}\.\d+|(?<=°)\d\.\d+|(?<=°\s)\d\.\d+)"
_SEC = r"\s*'?(?:\s+(\d{1,2}(?:\.\d+)?)\s*(?:\"|'')?)?"
_SPACED = re.compile(r"(?<![\d.])(\d{1,3})(?:\s*°\s*|\s+)" + _MIN + _SEC + r"\s*([NSEW])(?![A-Za-z])", re.I)
# after a leading letter one-digit decimal minutes are plain: 'S1 6.72' is 1°6.72'
_MIN_PRE = r"(\d{1,2}(?![.\d])|\d{1,2}\.\d+)"
# degrees, one-digit decimal minutes, then a letter ('1 6.72 S'): 1°6.72'S, or 6.72°S after a stray
# number. Not after / or - (the 123 of 'LR 209/123 1.112S'): ask, never guess
_AMBIG_MIN = re.compile(r"(?<![\w./\-])\d{1,3}\s+\d\.\d+\s*[NSEW](?![A-Za-z])", re.I)
_SPACED_PRE = re.compile(r"(?<![A-Za-z])([NSEW])(?:orth|outh|ast|est)?\.?\s*(\d{1,3})(?:\s*°\s*|\s+)" + _MIN_PRE + _SEC
                         + r"(?![\d.'\"°])", re.I)
# marks that say 'these are coordinates': a degree mark on a decimal or before minutes, minutes or
# seconds marks, a hemisphere letter on a decimal ('a 15° slope' is not one)
_MARKED = re.compile(r"\d\.\d+\s*°|\d\s*°\s*\d|\d\s*['\"]\s*\d|\d\.\d+\s*[NSEW](?![A-Za-z])|"
                     r"(?<![A-Za-z])[NSEW]\s*\d+\.\d", re.I)
NUM = r"-?\d+(?:\.\d+)?"
RUN = re.compile(rf"(?<![\w.]){NUM}(?:\s*[,;]?\s*{NUM})+(?!\w|\.\d)")   # numbers written together
# '1.112 deg S' is '1.112° S' (only before a hemisphere letter: '12 degrees warmer' is not a coordinate)
_DEG_WORD = re.compile(r"(?i)(?<=\d)\s*deg(?:ree)?s?\.?(?=\s*[NSEW](?:orth|outh|ast|est)?(?![A-Za-z]))")
# two decimals with degree marks and no N/S/E/W: '-1.112°, 36.650°'
_DEG_PAIR = re.compile(rf"(?<![\w.])({NUM})\s*°\s*[,;/]?\s*({NUM})\s*°?(?!\s*[\d'\"°]|\s*[NSEW](?![A-Za-z]))", re.I)
# lat and lon named, in either order: 'Latitude: -1.2921, Longitude: 36.8219', 'Long 36.65 Lat -1.11'
_LAT = r"\blat\w*\.?\s*[:=]?\s*(-?\d+\.\d+)\s*°?"
_LON = r"\bl(?:o?ng|on)\w*\.?\s*[:=]?\s*(-?\d+\.\d+)\s*°?"
_NAMED = re.compile(rf"(?i){_LAT}\W{{0,4}}\s*(?:and\s+)?{_LON}|{_LON}\W{{0,4}}\s*(?:and\s+)?{_LAT}")
# a point or two corners joined by '/', 'and' or 'to'
_PAIRS = re.compile(rf"(?i)(?<![\w.])({NUM}(?:\s*[,;]?\s*{NUM})?)\s*(?:/|\band\b|\bto\b)\s*({NUM}(?:\s*[,;]?\s*{NUM})?)"
                    r"(?!\w|\.\d)")
# a box written as one range per axis, lat and lon in either order, labelled or not
_AXIS = r"(?:\b(lat\w*|l(?:o?ng|on)\w*)\.?\s*[:=]?\s*)?(?:(?:between|from)\s+)?"
_SPAN = rf"({NUM})\s*(?:/|\band\b|\bto\b)\s*({NUM})"
_RANGES = re.compile(rf"(?i)(?<![\w.]){_AXIS}{_SPAN}\s*[,;]?\s*(?:and\s+)?{_AXIS}{_SPAN}(?!\w|\.\d)")
# one end of a range: a decimal joined to the run by 'to', 'and' or '/'
_RANGE_BEFORE = re.compile(r"(?i)(-?\d+\.\d+)\s*(?:/|\band\b|\bto\b)\s*$")
_RANGE_AFTER = re.compile(r"(?i)\s*(?:/|\band\b|\bto\b)\s*(-?\d+\.\d+)")
# a hemisphere letter written once for a range: '1.10 to 1.12S', 'S 1.10 to 1.12'
_SHARED_SUFFIX = re.compile(r"(?i)(?<![\w.])-?(\d{1,3}\.\d+)\s*(?:\bto\b|/|\band\b|-)\s*-?(\d{1,3}\.\d+)\s*([NSEW])"
                            r"(?:orth|outh|ast|est)?(?![A-Za-z])")
_SHARED_PREFIX = re.compile(r"(?i)(?<![A-Za-z])([NSEW])\.?\s*(\d{1,3}\.\d+)\s*(?:\bto\b|/|\band\b|-)\s*(\d{1,3}\.\d+)"
                            r"(?![\d.]|\s*[NSEW](?![A-Za-z]))")
# UTM as survey plans give it: zone 36 or 37 (band letter optional), six-figure easting, northing
_UTM = re.compile(
    r"(?i)(?:\butm\b|\bzone\b)\D{0,12}?(3[67])\s*[C-X]?\b\D{0,24}?(?<![\d.])(\d{6}(?:\.\d+)?)(?![\d.])"
    r"\D{0,12}?(?<![\d.])(\d{6,7}(?:\.\d+)?)(?![\d.])")
_UTM_WORD = re.compile(r"(?i)\butm\b|\bzone\s*3[67]")
# the zone alone, before or after the numbers: 'UTM 37M', 'zone 36 North', 'UTM zone 37S'
_UTM_ZONE = re.compile(r"(?i)\b(?:utm|zone)\b\D{0,12}?(?<![\d.])(3[67])(?!\d)\s*(?:[C-X](?![A-Za-z])|north\b|south\b)?")
# an easting or northing: 6 or 7 figures (a GPS unit pads the easting to 7: 0256123), labelled
# before it ('E 256123', 'Easting: 256123', 'N=9876543') or after it ('256123E', '9876543 N')
_UTM_FIG = r"(?<![\d.])(\d{6,7}(?:\.\d+)?)(?![\d.])"
_UTM_PRE = re.compile(r"(?i)(?<![A-Za-z0-9])([EN])(?:ast|orth)?(?:ings?)?\b\.?\s*[:=]?\s*" + _UTM_FIG)
_UTM_SUF = re.compile(_UTM_FIG + r"\s*([EN])(?![A-Za-z])", re.I)
# links: a map link carries its coordinates in the URL, a short link does not
URL = re.compile(r"(?i)(?:\bhttps?://|\bwww\.)\S+|\b(?:maps\.app\.goo\.gl|goo\.gl|g\.co|osm\.org)/\S*")
# Google Maps plus codes: full ('6GCRPR6C+24') or short ('PR6C+24 Nairobi')
OLC = "23456789CFGHJMPQRVWX"
PLUS_CODE = re.compile(r"(?<![0-9A-Za-z])((?:[2-9CFGHJMPQRVWX]{2}){2,4})\+([2-9CFGHJMPQRVWX]{2,3})(?![0-9A-Za-z])", re.I)


def _olc_cell(code):
    """(lat, lon) centre of a full plus code: 8 digits, '+', then 2 or 3."""
    d = code.upper().replace("+", "")
    lat, lon, res = -90.0, -180.0, 20.0
    hl = hw = res
    for i in range(0, min(len(d), 10), 2):
        lat += OLC.index(d[i]) * res
        lon += OLC.index(d[i + 1]) * res
        hl = hw = res
        res /= 20
    if len(d) > 10:                                    # 11th digit: a 4 x 5 grid
        hl, hw = hl / 5, hw / 4
        lat += OLC.index(d[10]) // 4 * hl
        lon += OLC.index(d[10]) % 4 * hw
    return lat + hl / 2, lon + hw / 2


def _olc_prefix(lat, lon, n):
    lat, lon, res, out = lat + 90, lon + 180, 20.0, ""
    for _ in range(n // 2):
        a, b = int(lat // res), int(lon // res)
        out += OLC[a] + OLC[b]
        lat, lon, res = lat - a * res, lon - b * res, res / 20
    return out


def plus_code(text, near=None):
    """(lon, lat) of a Google Maps plus code: a full one, or a short one recovered nearest `near`
    (lon, lat); None when there is none, False when a short code has nothing to place it by."""
    m = PLUS_CODE.search(text or "")
    if not m:
        return None
    code, missing = m.group(0).upper(), 8 - len(m.group(1))
    if not missing:
        lat, lon = _olc_cell(code)
        return lon, lat
    if near is None:
        return False
    rlon, rlat = near
    res = 20.0 ** (2 - missing // 2)
    lat, lon = _olc_cell(_olc_prefix(rlat, rlon, missing) + code)
    if rlat + res / 2 < lat and lat - res >= -90:
        lat -= res
    elif rlat - res / 2 > lat and lat + res <= 90:
        lat += res
    if rlon + res / 2 < lon:
        lon -= res
    elif rlon - res / 2 > lon:
        lon += res
    return lon, lat


def utm_point(t):
    """(lon, lat), as WGS 84, from UTM as survey plans and GPS units give it: 'UTM 37S 256123E 9876543N',
    'Zone 37M, E 256123, N 9876543', 'Easting 256123 Northing 9876543 (UTM 37S)', labelled northing
    first, a padded easting (0256123); the zone before or after the numbers."""
    z = _UTM_ZONE.search(t)
    if not z:
        return None
    zone, e, n = int(z.group(1)), None, None
    for rx, lab, fig in ((_UTM_PRE, 1, 2), (_UTM_SUF, 2, 1)):     # labelled: E and N, in either order
        got = [(g.group(lab).upper(), float(g.group(fig))) for g in rx.finditer(t)]
        es, ns = [v for k, v in got if k == "E"], [v for k, v in got if k == "N"]
        if len(es) == len(ns) == 1:
            e, n = es[0], ns[0]
            break
    else:
        m = _UTM.search(t)
        if m:                                                      # unlabelled, easting first
            zone, e, n = int(m.group(1)), float(m.group(2)), float(m.group(3))
        else:
            figs = [float(v) for v in re.findall(_UTM_FIG, t)]
            if len(figs) != 2:
                return None
            e, n = figs if not figs[0] >= 1_000_000 > figs[1] else figs[::-1]   # only a southern northing has 7 figures
    if not (100_000 <= e <= 900_000 and (n <= 1_000_000 or 9_000_000 <= n <= 10_000_000)):
        return None
    from pyproj import Transformer
    epsg = (32700 if n >= 5_000_000 else 32600) + zone   # southern northings start from 10 000 km
    return Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform(e, n)


def _hemispheres(t):
    """Coordinates written with N/S/E/W, in decimal degrees, degrees and decimal minutes, or degrees,
    minutes and seconds: (lon, lat) for one point, (w, s, e, n) for two corners; None when the text
    has no such marks, False when it has marks that do not make one point or two corners (ask,
    never guess)."""
    for rx, suffix in ((_SPACED, True), (_SPACED_PRE, False), (_SUFFIX, True), (_PREFIX, False)):
        if rx is _SUFFIX and _AMBIG_MIN.search(t):
            return False                # '1 6.72 S' and the spaced readings made no point: ask
        lats, lons, used = [], [], []
        for m in rx.finditer(t):
            h, d, mi, se = (m.group(4), *m.group(1, 2, 3)) if suffix else m.group(1, 2, 3, 4)
            if float(mi or 0) >= 60 or float(se or 0) >= 60:
                return False
            v = float(d) + float(mi or 0) / 60 + float(se or 0) / 3600
            (lats if h.upper() in "NS" else lons).append(-v if h.upper() in "SW" else v)
            used.append(m.span())
        if not (lats and lons):
            continue                    # 'S 1.1 E 36.6' read as suffixes gives one lon only: try prefixes
        if len(lats) != len(lons) or len(lats) > 2:
            return False
        if any(abs(v) > 90 for v in lats) or any(abs(v) > 180 for v in lons):
            return False
        # degrees the reading did not use (the 1° of '1°06.720S'): the marks do not make one point
        for k in re.finditer(r"\d\s*°\s*\d", t):
            if not any(a <= k.start() < b for a, b in used):
                return False
        w, e, s, n = min(lons), max(lons), min(lats), max(lats)
        if (e - w) < 0.005 and (n - s) < 0.005:
            return (w + e) / 2, (s + n) / 2
        return w, s, e, n
    return False if _MARKED.search(t) else None


def _lat_first_kenya(a, b):
    """True when (a, b) reads as a Kenyan lat, lon pair, as Google Maps copies it."""
    return abs(a) <= 5.5 and 33 <= abs(b) <= 42


def _axis_ranges(t):
    """(w, s, e, n, decimals) for a box written as one range per axis; None when there is none or
    which range is the latitude is not clear (labels, else Kenya's latitudes and longitudes)."""
    for m in _RANGES.finditer(t):
        l1, a1, a2, l2, b1, b2 = m.groups()
        toks = (a1, a2, b1, b2)
        if not all("." in v for v in toks):
            continue
        p, q = (float(a1), float(a2)), (float(b1), float(b2))
        k1 = l1 and ("lat" if l1.lower().startswith("lat") else "lon")
        k2 = l2 and ("lat" if l2.lower().startswith("lat") else "lon")
        if k1 or k2:
            if k1 == k2 or not (k1 and k2):
                continue                       # both lat, or only one labelled: ask
            lats, lons = (p, q) if k1 == "lat" else (q, p)
        elif all(abs(v) <= 5.5 for v in p) and all(33 <= abs(v) <= 42 for v in q):
            lats, lons = p, q
        elif all(abs(v) <= 5.5 for v in q) and all(33 <= abs(v) <= 42 for v in p):
            lats, lons = q, p
        else:
            continue
        w, e, s, n = min(lons), max(lons), min(lats), max(lats)
        if w < e and s < n and abs(s) <= 90 and abs(n) <= 90 and abs(w) <= 180 and abs(e) <= 180:
            return w, s, e, n, min(len(v.split(".")[1]) for v in toks)
    return None


def _range_end(clean, run, vals):
    """True when a run of two numbers is one end of a one-axis range ('-1.12, 36.64' in
    '-1.10 to -1.12, 36.64')."""
    def same_axis(x, y):
        return not (_lat_first_kenya(x, y) or _lat_first_kenya(y, x))
    before = _RANGE_BEFORE.search(clean[:run.start()])
    after = _RANGE_AFTER.match(clean, run.end())
    return bool(before and same_axis(float(before.group(1)), vals[0])
                or after and same_axis(float(after.group(1)), vals[-1]))


def _shared_hemisphere(t):
    """'1.10 to 1.12S' -> '1.10S to 1.12S', 'S 1.10 to 1.12' -> 'S 1.10 to S 1.12'."""
    t = _SHARED_SUFFIX.sub(lambda m: f"{m.group(1)}{m.group(3)} to {m.group(2)}{m.group(3)}", t)
    return _SHARED_PREFIX.sub(lambda m: f"{m.group(1)} {m.group(2)} to {m.group(1)} {m.group(3)}", t)


def _signed_degrees(t):
    """'-1.112°, 36.650°' -> '-1.112, 36.650': the minus sign gives the hemisphere. Unsigned stays."""
    return _DEG_PAIR.sub(lambda m: f"{m.group(1)}, {m.group(2)}" if "-" in m.group(1) + m.group(2)
                         else m.group(0), t)


def _joined(t):
    """A point or two corners joined by '/', 'and' or 'to' -> joined by a comma."""
    def join(m):
        a, b = re.findall(NUM, m.group(1)), re.findall(NUM, m.group(2))
        if not all("." in v for v in a + b):
            return m.group(0)
        if len(a) == len(b) == 2 or (len(a) == len(b) == 1 and (
                _lat_first_kenya(float(a[0]), float(b[0])) or _lat_first_kenya(float(b[0]), float(a[0])))):
            return f"{m.group(1)}, {m.group(2)}"
        return m.group(0)
    return _PAIRS.sub(join, t)


def coordinates(text, rough=None):
    """Coordinates in what the customer wrote, as a Place, or None:
    a map link (Google Maps: the pin !3d..!4d, else the map's centre @lat,lon or query=lat,lon;
    OpenStreetMap: mlat/mlon, else #map=z/lat/lon); a full plus code; 'lat .. lon ..' in either
    order; UTM as on a survey plan; a point or two corners with N/S/E/W, in decimal degrees,
    degrees and decimal minutes, or degrees, minutes and seconds; a point 'lat, lon' as Google Maps
    copies it (or 'lon, lat', or with degree marks and signs); a box 'west, south, east, north' or
    two corners 'lat, lon, lat, lon' (joined by commas, '/', 'and' or 'to'). Plot, house and phone
    numbers, sizes, distances and dates are not coordinates, and plain numbers far from East
    Africa count only when written precisely; such a point is flagged in place['warn']. When
    `rough` is a list, a far point dropped for being written roughly is explained in it."""
    if not text:
        return None
    t = str(text).translate(DASHES).translate(QUOTES)
    t = URL.sub(lambda m: urllib.parse.unquote(m.group(0)), t)       # query=-1.112%2C36.650
    t = _signed_degrees(_DEG_WORD.sub("°", t))
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
    mlat = re.search(r"[?&;]mlat=(-?\d+(?:\.\d+)?)", t)
    mlon = re.search(r"[?&;]mlon=(-?\d+(?:\.\d+)?)", t)
    view = re.search(r"#map=\d+(?:\.\d+)?/(-?\d+(?:\.\d+)?)/(-?\d+(?:\.\d+)?)", t)
    if (mlat and mlon) or view:                                       # OpenStreetMap links
        lat, lon = ((float(mlat.group(1)), float(mlon.group(1))) if mlat and mlon
                    else (float(view.group(1)), float(view.group(2))))
        if abs(lat) <= 90 and abs(lon) <= 180:
            p = Place(name="Custom area", kind="point", centre=(lon, lat), source=src)
            if not (mlat and mlon):
                p["warn"] = ("The link gave the map's centre, not a marker: check the point is the "
                             "customer's place (a link with a marker is better).")
            return _checked(p, precise=True)
    pc = plus_code(t)
    if pc:                                                            # a full plus code
        return _checked(Place(name="Custom area", kind="point", centre=pc, source="the plus code in the request"),
                        precise=True)
    named = _NAMED.search(t)
    if named:
        g = named.groups()
        lat, lon = (float(g[0]), float(g[1])) if g[0] is not None else (float(g[3]), float(g[2]))
        if abs(lat) <= 90 and abs(lon) <= 180:
            return _checked(Place(name="Custom area", kind="point", centre=(lon, lat), source=src), precise=True)
    if _UTM_WORD.search(t):
        u = utm_point(t)
        if u:
            p = Place(name="Custom area", kind="point", centre=u, source="UTM coordinates in the request")
            p["warn"] = (f"The request gave UTM coordinates, read as WGS 84 ({u[1]:.5f}, {u[0]:.5f}); a survey "
                         "plan in Arc 1960 sits a few hundred metres from that: check the point.")
            return _checked(p, precise=True)
        # UTM only named, or written some other way: read the rest ('-1.112, 36.650 (UTM 37M)'), with the
        # zone taken out so its letter is not read as a hemisphere; 6- and 7-figure numbers are never
        # degrees, so unread UTM still ends in None and the ask
        t = _UTM_ZONE.sub(" | ", t)
    bounds = {k[0].lower(): float(v) for k, v in
              re.findall(r"(?i)\b(north|south|east|west)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)", t)}
    if len(bounds) == 4 and bounds["w"] < bounds["e"] and bounds["s"] < bounds["n"]:   # 'North -1.30 South ...'
        w, s, e, n = bounds["w"], bounds["s"], bounds["e"], bounds["n"]
        return _checked(Place(name="Custom area", kind="box", bbox=(w, s, e, n), centre=((w + e) / 2, (s + n) / 2),
                              source=src), precise=True)
    hemi = _hemispheres(_shared_hemisphere(ADDRESS.sub(" | ", t)))
    if hemi and len(hemi) == 4:
        w, s, e, n = hemi
        return _checked(Place(name="Custom area", kind="box", bbox=hemi, centre=((w + e) / 2, (s + n) / 2),
                              source=src), precise=True)
    if hemi:
        return _checked(Place(name="Custom area", kind="point", centre=hemi, source=src), precise=True)
    if hemi is False:                   # degrees or N/S/E/W that do not make a point: ask, never guess
        return None
    clean = NOT_COORDS.sub(" | ", t)
    box = _axis_ranges(clean)
    if box:                                      # '-1.10 to -1.12, 36.64 to 36.66'
        w, s, e, n, dec = box
        got = _checked(Place(name="Custom area", kind="box", bbox=(w, s, e, n), centre=((w + e) / 2, (s + n) / 2),
                             source=src), precise=dec >= 3, rough=rough)
        if got:
            return got
    clean = _joined(clean)
    for run in RUN.finditer(clean):
        toks = re.findall(NUM, run.group(0))
        vals = [float(v) for v in toks]
        if len(vals) == 2 and _range_end(clean, run, vals):
            continue        # the end of a range ('-1.10 to -1.12, 36.64'): not a point, ask
        decimals = [len(v.split(".")[1]) if "." in v else 0 for v in toks]
        if len(vals) == 4:
            a, b, c, d = vals
            if _lat_first_kenya(a, b) and _lat_first_kenya(c, d):      # two Google Maps corners
                a, b, c, d = b, a, d, c
            w, e, s, n = min(a, c), max(a, c), min(b, d), max(b, d)
            if w < e and s < n and abs(s) <= 90 and abs(n) <= 90 and abs(w) <= 180 and abs(e) <= 180:
                p = Place(name="Custom area", kind="box", bbox=(w, s, e, n), source=src,
                          centre=((w + e) / 2, (s + n) / 2))
                got = _checked(p, precise=min(decimals) >= 3, rough=rough)
                if got:
                    return got
            continue
        if len(vals) == 2 and min(decimals) >= 1:     # a point: two decimals side by side
            a, b = vals
            if abs(a) > 90 >= abs(b) or (33 <= abs(a) <= 42 and abs(b) <= 5.5):   # lon, lat
                lon, lat = a, b
            else:                                     # lat, lon, as Google Maps gives it
                lat, lon = a, b
            if abs(lat) <= 90 and abs(lon) <= 180:
                got = _checked(Place(name="Custom area", kind="point", centre=(lon, lat), source=src),
                               precise=min(decimals) >= 3, rough=rough)
                if got:
                    return got
    return None


def _checked(p, precise, rough=None):
    """Keep a point or box near East Africa; far away only when written precisely, and flagged.
    A far one written roughly is dropped, and said in `rough` when it is a list."""
    lon, lat = p["centre"]
    if in_east_africa(lon, lat):
        return p
    if not precise:
        if rough is not None:
            what = (f"the point {lat:g}, {lon:g} (lat, lon)" if p["kind"] == "point" else
                    "the box {:g}, {:g}, {:g}, {:g} (west, south, east, north)".format(*p["bbox"]))
            rough.append(f"The numbers in the area read as {what}, which is far from Kenya, and are written "
                         "with fewer than 3 decimals, so they were not used. Check the order (lat, lon) and the "
                         "signs (S and W are negative), or give them with 3 or more decimals.")
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
    """Named lakes from Natural Earth: bounds, a point on the water, whether the lake touches Kenya."""
    try:
        import geopandas as gpd
        import shapely
        from common import DATA
        g = gpd.read_file(DATA / "ne" / "ne_10m_lakes", columns=["name"])
        g = g[g["name"].apply(lambda v: isinstance(v, str))]
        k = kenya_outline()
        ke = shapely.intersects(k, g.geometry.values) if k is not None else [False] * len(g)
        return [dict(name=str(r.name), bbox=tuple(float(v) for v in r.geometry.bounds), kenya=bool(x),
                     at=tuple(r.geometry.representative_point().coords[0]))
                for r, x in zip(g.itertuples(), ke)]
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

# where a plot sits relative to a known place: 'near Limuru', '3 km past Limuru', 'on the road to
# Nanyuki', 'north of Nanyuki' (long phrases first, so 'along the road to' is taken whole)
_WHERE = (r"(?:on|along|off)\s+(?:the\s+)?(?:road|way|highway)\s+to|"
          r"(?:north|south|east|west)(?:[\s-]*(?:north|south|east|west))?\s+of|"
          r"near|in|around|at|of|by|outside|from|off|behind|opposite|along|next to|close to|"
          r"past|beyond|after|before|towards?|via|beside|above|below|between")
SETTING = rf"(?i)\s+(?:{_WHERE})\s+"
SEPARATORS = r"(?i)\s*(?:[,;/&+]|\band\b)\s*"
LEADING_SETTING = rf"(?i)^(?:{_WHERE})(?:\s+|$)"
# setting words that only ever lead to a place: what follows a person's land 'in' or 'near' is searched
# as the place; what follows 'from', 'by', 'next to' or 'with' may be another person
AT_PLACE = (r"(?i)in|near|at|around|outside|close to|past|beyond|"
            r"(?:north|south|east|west)(?:[\s-]*(?:north|south|east|west))?\s+of|"
            r"(?:on|along|off)\s+(?:the\s+)?(?:road|way|highway)\s+to")
# a comma part with one of these is near the place, not the county it is in ('Thika, near Nairobi')
NOT_IN = r"(?i)\b(?:near|around|at|by|outside|from|off|behind|opposite|along|next to|close to|past|beyond)\b"
# words that say what kind of map or land it is, never which place; a filler word after an
# apostrophe inside a word is part of a name (the 'a' of Murang'a)
FILLER = (r"(?i)(?<!\w['’])\b(just|right|about|my|our|the|a|an|all|whole|entire|entirety|full|complete|extent|"
          r"family|farms?|lands?|plots?|shambas?|homes?|house|estates?|area|town|city|county|it|them|there|"
          r"region|centre|center|cbd|downtown|old|forest|reserve|map|print|poster|plate|relief|contours?|"
          r"surroundings|place|village|country|acres?|ac|ha|hectares?|kms?|lr|no|"
          r"wall|big|large|huge|topographic(?:al)?|topo|elevation|aerial\s+view|satellite\s+view|"
          r"approx(?:imately)?|roughly|foot|slopes?|shores?|banks?|edge|heart|middle|"
          r"tea\s+country|coffee\s+country)\b")
# filler words that name a feature: dropping one is said in the notes ('Kakamega forest')
FEATURE_WORDS = ("forest", "reserve", "estate", "village")
# a road is not the town it is named after ('Mombasa Road', 'Thika Road Mall')
ROAD_WORDS = r"(?i)^(?:road|rd|street|st|avenue|ave|highway|hwy|superhighway|bypass|by-pass|way|drive|lane|crescent)\.?$"
# parts of a list that are not more places to draw: a bare feature, an old province
LIST_FEATURES = {"lake", "river", "hill", "hills", "mountain", "mountains", "beach", "coast", "valley", "falls"}
OLD_PROVINCES = {"western", "eastern", "central", "coast", "coastal", "nyanza", "riftvalley", "northeastern"}
# areas that are a whole country or continent
BROAD = ("country", "countries", "continent")
OWN_LAND = r"(?i)\b(farm|land|plot|plots|shamba|home|house|estate)\b"
THEME = (r"(?i)\b(population|people|density|roads?|streets?|rivers?|drainage|basins?|relief|terrain|elevation|"
         r"3d|ray-traced|topo\w*|contours?|hillshade|shaded|land|cover|landcover|forests?|loss|water|surface|"
         r"true|colou?r|satellite|gold)\b")
# Swahili as the English the lookups know: 'shamba langu karibu na Limuru' -> 'farm my near Limuru',
# 'Mlima Kenya' -> 'Mount Kenya', 'Ziwa Victoria' -> 'Lake Victoria', 'Kaunti ya Nyeri' -> 'Nyeri County'.
# Never 'kwa' or a bare 'ya / la / wa': they are parts of names ('Kwa Njenga', 'Mto wa Mbu', 'La Paz').
SWAHILI = [
    # a relative with no name ('shamba ya baba yangu'): the family's land, a filler word
    (r"(?i)\b(?:ya|la|wa|kwa)\s+(?:baba|mama|babu|bibi|cucu|shosho|guka|nyanya|mzee)\b(?!\s+(?-i:[A-Z]))", " family"),
    (r"(?i)\bkaunti\s+ya\s+([^,;/()&]+?)\s*(?=[,;/()&]|$)", r"\1 County"),
    (r"(?i)\bmilima\s+ya\s+([\w']+)", r"\1 Hills"),
    (r"(?i)\bmlima\s+", "Mount "),
    (r"(?i)\bziwa\s+(?:la\s+)?", "Lake "),
    (r"(?i)\bkisiwa\s+cha\s+([\w']+)", r"\1 Island"),
    (r"(?i)\bmji\s+wa\s+", "town of "),
    (r"(?i)(?:^|\s+)karibu\s+na\s+", " near "),
    (r"(?i)(?:^|\s+)(?:katika|ndani\s+ya)\s+", " in "),
    (r"(?i)\s+nje\s+ya\s+", " outside "),
    (r"(?i)\bmjini\b", "town"),
    (r"(?i)\b(?:ma)?shamba\b", "farm"),
    (r"(?i)\bkiwanja\b", "plot"),
    (r"(?i)\bnyumbani\b", "home"),
    (r"(?i)\b(?:yangu|langu|wangu|changu|kwangu|zangu|yetu|letu|wetu|chetu|kwetu|zetu)\b", "my"),
]
# parts that point at a person rather than a place: never sent to OpenStreetMap
PERSONAL = re.compile(
    r"(?i)\b(mzee|cucu|shosho|guka|nyanya|babu|bibi|grand(?:father|mother|pa|ma|parents?)|granny|"
    r"dad|daddy|father|mum|mom|mother|parents?|uncle|aunt|auntie|brother|sister|son|daughter|wife|husband|"
    r"late|mr|mrs|ms|dr|rev|pastor|shop|kiosk|duka|left|gave|bought|lives?|lived|"
    r"us|we|me|him|her|his|their|who|where|for)\b")
NAME_WORD = r"[A-Z][\w'’-]*"
KIN = r"(?i:mama|baba|mzee|cucu|shosho|guka|nyanya|babu|bibi)"
PEOPLE = (                                 # people's names written in tell-tale patterns
    rf"(?i:\b(?:farm|land|plots?|home|house|shamba|property|homestead)\s+of)\s+(?:(?i:the)\s+)?(?:{NAME_WORD}\s*){{1,3}}",
    rf"(?:\b(?i:the)\s+)?(?:{NAME_WORD}\s+){{1,2}}(?i:family)\b",
    rf"(?i:\b(?:mr|mrs|ms|miss|dr|mzee)\b\.?)\s+(?:{NAME_WORD}\s*){{1,3}}",
    # 'Jane Wanjiku farm': a first name and surname just before the land they own. Not one word:
    # 'Juja farm', 'Ruai plot' and 'Mwea farm' are where the land is, written the Kenyan way
    rf"(?:(?!(?i:my|our|the|their|his|her|this|that|an?)\b){NAME_WORD}\s+){{2,3}}"
    r"(?=(?i:farm|land|plots?|shamba|home|house|homestead|property)\b)",
    # 'shamba la Wanjiku', 'plot ya Kamau', 'nyumbani kwa Mama Wanjiru': a Swahili possessive
    rf"(?i:\b(?:farm|land|plots?|home|house|homestead|property)\s+(?:la|ya|wa|cha|kwa))\s+(?:{KIN}\s+)?(?:{NAME_WORD}\s*){{1,3}}",
    # 'kwa Mama Wanjiru': at Mama Wanjiru's (a bare 'Kwa Njenga' is a place and is kept)
    rf"(?i:\bkwa)\s+{KIN}\s+(?:{NAME_WORD}\s*){{1,2}}",
)


def english(area):
    """The area with Swahili place words in English; unchanged when that leaves only filler
    ('Nyumbani Village' is a place)."""
    out = area
    for pat, rep in SWAHILI:
        out = re.sub(pat, rep, out)
    out = re.sub(r"\s+", " ", out).strip()
    return out if unfill(out) else area


# a home's own number, and whose land it is or what grows on it, are never part of a place name
DWELLING = re.compile(r"(?i)\b(?:plots?|parcel|blo?c?k|house|hse|flat|apartment|apt|unit|room|door)\b\.?\s*"
                      r"(?:no\.?\s*)?[A-Z]?[\d/\-]*\d[A-Z]?\b")
LAND_OF = (r"(?i)\b(?:[\w-]+['’]s|tea|coffee|dairy|maize|avocado|flower|fruit|sugar(?:cane)?|wheat|cattle)\s+"
           r"(?=(?:farm|land|plot|shamba|home|house)s?\b)")


def unfill(s):
    """A place-name part without filler words ('my farm', 'CBD', 'county'), numbers or units."""
    out = []
    for part in re.split(r"\s*[,;/]\s*", s or ""):
        part = re.sub(LAND_OF, " ", DWELLING.sub(" ", part))
        part = re.sub(r"\S*\d\S*", " ", re.sub(FILLER, " ", part))
        part = re.sub(LEADING_SETTING, "", part.strip())    # 'near Limuru' -> 'Limuru'
        part = re.sub(r"\s+", " ", part).strip(" .-'–—:")
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


def private_words(*values):
    """Words of the customer's name and e-mail: a search part with one of them stays here."""
    out = set()
    for v in values:
        v = (v or "").split("@")[0]
        out |= {w for w in re.findall(r"[a-z]+", unicodedata.normalize("NFKD", v).lower()) if len(w) >= 3}
    return out


def without_people(area, private=()):
    """The area without people's names: the customer's own, and names in tell-tale patterns
    ('the Kamau family', 'Mr Otieno', 'farm of Peter Otieno'); the area itself when that leaves
    nothing."""
    s = area
    for pat in PEOPLE:
        s = re.sub(pat, " ", s)
    for w in private:
        s = re.sub(rf"(?i)\b{re.escape(w)}\b", " ", s)
    s = re.sub(r"(?i)\bfor\s*(?=,|$)", "", re.sub(r"\s+", " ", s))
    s = re.sub(r"\s*,\s*(?=,|$)|^\s*,\s*", "", s).strip(" ,")
    # a Swahili connector left alone once its name is gone ('kwa, Bondo'): never a place
    s2 = re.sub(r"\s+", " ", re.sub(r"(?i)(?:^|(?<=[\s,]))(?:la|ya|wa|cha|kwa)\s*(?=,|$)", " ", s)).strip(" ,")
    s = s2 if unfill(s2) else s
    return s if unfill(s) else area


def people_in(area, private=()):
    """The parts of the area that without_people() leaves out, as written ('Jane Wanjiku')."""
    found = [m.group(0).strip(" ,") for pat in PEOPLE for m in re.finditer(pat, area)]
    for w in private:
        found += [m.group(0) for m in re.finditer(rf"(?i)\b{re.escape(w)}\b", area)
                  if not any(m.group(0).lower() in f.lower() for f in found)]
    return list(dict.fromkeys(f for f in found if f))


def candidates(area):
    """What the customer wrote, as (text, role), best first. 'named' is the place itself
    ('Ngong Hills' in 'Ngong Hills near Nairobi', 'Limuru' in 'my farm near Limuru');
    'first words' are the leading words of a longer name ('Kericho' of 'Kericho tea estate'),
    tried only when nothing else is found; 'context' is a wider place it is in ('Nairobi', the
    'Siaya' of 'Bondo, Siaya', the 'Ruiru' of 'off Thika Road, Ruiru')."""
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
            road = next((i for i, w in enumerate(words) if re.match(ROAD_WORDS, w)), None)
            if road is None:
                out += [(" ".join(words[:k]).strip(" -–—,;:/."), "first words") for k in range(len(words) - 1, 0, -1)]
            elif road + 1 < len(words):              # 'Kenyatta Avenue Nakuru': Nakuru is where the road is
                out.append((unfill(" ".join(words[road + 1:])), "context"))
            # 'Mombasa Road' is a road in Nairobi, not Mombasa: no 'first words' before a road word
    texts, roles = {}, {}
    rank = {"named": 0, "first words": 1, "context": 2}
    for c, r in out:                                         # a text found as 'named' anywhere is named
        k = norm(c)
        if not k or (c != text and not norm(unfill(c))):    # only filler words or numbers: '1234', 'my farm'
            continue
        texts.setdefault(k, c)
        roles[k] = min(r, roles.get(k, r), key=rank.get)
    return [(texts[k], role) for role in ("named", "first words", "context") for k in texts if roles[k] == role]


def named_parts(area):
    """The places a request lists one after another: 'Kenya, Uganda and Tanzania', 'Juja, Kiambu';
    not a bare feature ('by the lake') or an old province ('Embu, Eastern')."""
    out = []
    for p in re.split(SEPARATORS, area.strip()):
        head, tail = split_setting(p)
        q = unfill(head if unfill(head) else (tail or ""))
        bare = norm(re.sub(r"(?i)\b(province|kenya)\b", " ", q))
        if q and not re.search(r"\d", q) and norm(q) not in LIST_FEATURES and bare not in OLD_PROVINCES:
            out.append(q)
    return list(dict.fromkeys(out))


def qualifiers(area, counties):
    """Countries and counties the request puts the place in ('Mwanza, Tanzania', 'Bondo, Siaya',
    'Bondo in Siaya'), as (norm name, name, outline buffered by about 5 km, Kenyan?). A comma part
    that says 'near' or 'from' is not one ('Thika, near Nairobi')."""
    import shapely
    import regions
    from common import county_boundaries
    parts = []
    for chunk in re.split(SEPARATORS, area.strip()):
        bits = re.split(r"(?i)\s+in\s+", f" {chunk.strip()} ")
        if len(bits) > 1:
            parts.append(bits[-1])
    commas = [p for p in area.split(",") if p.strip()]
    if len(commas) == 2 and not re.search(NOT_IN, commas[1]):
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
            name = hit[0] if hit else country_names()[k][1]
            kenyan = bool(hit) or country_names()[k][0] == "Kenya"
            out.append((k, name, shapely.buffer(geom, 0.05), kenyan))
    return out


def point_of(place):
    if place.get("centre"):
        return tuple(place["centre"])
    if place.get("bbox"):
        w, s, e, n = place["bbox"]
        return ((w + e) / 2, (s + n) / 2)
    return None


def county_shape(name):
    from common import county_boundaries
    cb = county_boundaries()
    rows = cb[cb["name"] == name]
    return rows.geometry.iloc[0] if len(rows) else None


def within(p, g):
    """Whether place p lies in the qualifier g: a point inside it, a county mostly inside it, a
    lake, range or park whose box overlaps it."""
    import shapely
    if p["kind"] in BROAD:
        return True
    if p["kind"] == "county":                  # g is buffered 5 km, so neighbouring counties touch it
        c = county_shape(p["name"])
        return c is None or shapely.intersection(c, g).area >= 0.5 * c.area
    if p.get("bbox") and p["kind"] not in ("town", "point"):
        return bool(shapely.intersects(g, shapely.box(*p["bbox"])))
    pt = point_of(p)
    return pt is None or bool(shapely.contains_xy(g, *pt))


def ref_point(place):
    """A point in the place a short plus code names; None for a country or anything over a degree."""
    if place.get("kind") in BROAD:
        return None
    if place.get("region"):
        import regions
        g = regions.region_outline(place["region"])[0]
        w, s, e, n = g.bounds
        if max(e - w, n - s) > 2:
            return None
        rp = g.representative_point()
        return rp.x, rp.y
    return point_of(place)


def label(p):
    c = p.get("country")
    return f"{p['name']} ({p['kind']}, {c})" if c and c != "Kenya" else f"{p['name']} ({p['kind']})"


def abroad(p):
    """A place outside Kenya: a town, lake or peak with another country (a country is what it is)."""
    return p["kind"] not in BROAD and p.get("country") not in (None, "", "Kenya")


def own_land_only(area):
    """'our farm in Kenya', 'my plot, Kenya': the customer's own land, and no place named but the
    wider one ('a map of Kenya' and 'Kenya land cover' are not)."""
    head, _ = split_setting(re.split(r"\s*[,;/]\s*", area.strip())[0])
    return bool(re.search(OWN_LAND, head) or DWELLING.search(head)) and not unfill(head)


def theme_only(text):
    """'population', 'land cover', 'roads': what they want drawn, not a place."""
    return bool(unfill(text)) and not re.sub(THEME, " ", unfill(text)).strip(" ,.-")


def left_out(area, cand):
    """Feature words just after the name that matched: 'forest' of 'Kakamega forest', not the
    'estate' of 'my family estate in Limuru'."""
    name = r"\s+".join(map(re.escape, cand.split()))
    m = re.search(r"(?i)\b" + name + r"\b((?:\s+[\w'-]+){1,3})", area)
    words = re.findall(r"(?i)\b(?:" + "|".join(FEATURE_WORDS) + r")\b", m.group(1)) if m else []
    return list(dict.fromkeys(w.lower() for w in words))


# ------------------------------------------------------------------ finding the area

def resolve(area, style, online=True, subject="", private=()):
    """Find the area. Returns (Place, candidates tried, list of notes).

    Order: coordinates (a link, a plus code, numbers); several countries; the place the customer
    named, exactly, among Kenyan counties, places.yml, towns, lakes, peaks and countries, inside
    the county or country the request puts it in; the same without people's names; then (online)
    OpenStreetMap's search in Kenya; then close spellings of Kenyan names; then the wider place it
    is in (never a whole country for a place not found); then a town of that name in a
    neighbouring country (flagged); then the first words of a longer name; then (online)
    OpenStreetMap's search anywhere. `private` holds the words of the customer's name and e-mail,
    which are never searched for."""
    notes, rough = [], []
    pt = coordinates(area, rough)
    if pt:
        if pt.get("warn"):
            notes.append(pt.pop("warn"))
        return pt, [], notes
    asked = area
    links = URL.findall(area)
    if links:                       # a link with no coordinates in it: never search for its parts
        advice = (f"The area is given as a map link with no coordinates in it ({links[0]}). Open it, copy the "
                  "pin's coordinates ('lat, lon') and draft again with them.")
        area = re.sub(r"\s+", " ", URL.sub(" ", area)).strip(" ,;:-")
        if not unfill(area):
            raise SystemExit(advice)                       # main() still falls back to coordinates in the notes
        notes.append(advice)
    pc = PLUS_CODE.search(area)
    if pc:                          # a short plus code ('PR6C+24 Nairobi'): placed by the town it names
        rest = re.sub(r"\s+", " ", area[:pc.start()] + " " + area[pc.end():]).strip(" ,;:-")
        if not unfill(rest):
            raise SystemExit(f"The plus code {pc.group(0)} is a short one: it needs the town it is in, or the full "
                             "code (e.g. 6GCRPR6C+24), or the point as 'lat, lon'.")
        ref, _, _ = resolve(rest, style, online=online, subject=subject, private=private)
        near = ref_point(ref)
        if near is None:
            raise SystemExit(f"The plus code {pc.group(0)} is a short one, and {ref['name']} is too large to place "
                             "it by: give the full code or the point as 'lat, lon'.")
        lon, lat = plus_code(pc.group(0), near)
        return (Place(name="Custom area", kind="point", centre=(lon, lat), source="the plus code in the request"),
                [], [f"Read the plus code {pc.group(0).upper()} near {ref['name']} as {lat:.5f}, {lon:.5f}; check it "
                     "is the customer's place."])
    if rough:
        if not re.sub(r"[\d\s.,;+\-°]", "", area):         # nothing but the numbers: no name to look for
            raise SystemExit(rough[0])
        notes.insert(0, rough[0])
    unsigned = None
    deg = _DEG_PAIR.search(area)
    if deg and "-" not in deg.group(1) + deg.group(2) and "." in deg.group(1) and "." in deg.group(2):
        a, b = deg.group(1), deg.group(2)                  # '1.112°, 36.650°': coordinates() will not guess
        unsigned = (f'The area gives "{deg.group(0).strip()}": degrees with no minus sign or N/S, so north or '
                    f"south of the equator would be a guess. Ask the customer, then give it as '-{a}, {b}' or "
                    f"'{a} S, {b} E' (or '{a} N, {b} E').")
        if not re.sub(r"[\d\s.,;/+\-°]", "", area):       # nothing but the numbers: no name to look for
            raise SystemExit(unsigned)                     # main() still falls back to coordinates in the notes
        notes.insert(0, unsigned)
    area = english(area)
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
    # the county a request puts its place in ('Mwea, Kirinyaga', 'my farm in Kirinyaga') is that county,
    # not a landmark that shares its name (Kirinyaga is also Mount Kenya)
    named_county = {k for k, n, _, _ in quals if n in counties}

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
            first = norm(re.split(r"[\s-]+", c)[0])
            if hit(norm(c)) or hit(norm(c + " county")) or hit(norm(c + " city county")):
                found.append((0 if wants_county else 0.5 if key in named_county else 2,
                              Place(name=c, kind="county", region={"county": c},
                                                               country="Kenya", source="the county boundaries")))
            elif not fuzzy and first != norm(c) and first not in ("west", "trans") and key == first:
                found.append((2.2, Place(name=c, kind="county", region={"county": c}, country="Kenya",
                                         source="the county boundaries")))   # 'Tana' is Tana River
        for p in gaz:
            if p.get("kind") == "town":
                continue
            names = [p["name"]] + p.get("aliases", [])
            full = {k for n in names for k in keys_for(n)}
            bare = {bare_lake(n) for n in names} - full if p["kind"] == "lake" else set()
            if any(hit(k) for k in full) or any(hit(k) for k in bare):
                pref = 1 if any(hit(k) for k in full) else (5 if wants_town else 2.5)
                b = tuple(p["bbox"])
                found.append((pref, Place(name=p["name"], kind=p["kind"], bbox=b,
                                          labels=p.get("labels", []), names=p.get("names", []),
                                          country=country_at((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) or "",
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
            if fuzzy and not near(lk["at"]):
                continue
            full = keys_for(lk["name"]) | keys_for("Lake " + lk["name"])
            bare = {bare_lake(lk["name"])} - full
            if any(hit(k) for k in full | bare):
                pref = 1 if any(hit(k) for k in full) else (5 if wants_town else 2.5 if lk["kenya"] else 3.5)
                found.append((pref, Place(name=lk["name"] if lk["name"].lower().startswith("lake") else
                                          "Lake " + lk["name"], kind="lake", bbox=pad(lk["bbox"], 0.08), at=lk["at"],
                                          country="Kenya" if lk["kenya"] else (country_at(*lk["at"]) or ""),
                                          source="Natural Earth lakes")))
        for pk in peak_list:
            if fuzzy and not near(pk["centre"]):
                continue
            if any(hit(k) for k in keys_for(pk["name"])):
                found.append((4, Place(name=pk["name"], kind="mountain", centre=pk["centre"],
                                       elevation=pk["elevation"], country=country_at(*pk["centre"]) or "",
                                       source="Natural Earth peaks")))
        if not fuzzy:
            if key == "africa":
                found.append((3, Place(name="Africa", kind="continent", source="Natural Earth countries",
                                       region={"continent": "Africa"})))
            elif key in country_names():
                admin, title = country_names()[key]
                found.append((3, Place(name=title, kind="country", source="Natural Earth countries",
                                       region={"countries": [admin]}, country=title)))
        # 'Mwanza, Tanzania', 'Bondo, Siaya', 'Victoria, Seychelles': the places in the county or
        # country named come first; with none there, a Kenyan place stays when only Kenyan places
        # were named ('Thika, Nairobi': Thika is in Kiambu) and the notes say so
        q = [(g, ke) for k, _, g, ke in quals if k != key]
        if q and found:
            ins = [f for f in found if any(within(f[1], g) for g, _ in q)]
            if ins:
                found = [(r if f in ins else r + 10, p) for f in found for r, p in [f]]
            elif all(ke for _, ke in q):
                found = [(r, p) for r, p in found if p.get("country") == "Kenya" or p["kind"] == "county"]
                for _, p in found:
                    p["outside_named"] = True
            else:
                found = []
        return found

    def rank(f):                                             # curated first; abroad, the largest first
        p = f[1]
        return f[0], p.get("source") != "places.yml", abroad(p), -(p.get("pop") or 0)

    def search(fuzzy, roles, text=None, accept=None):
        for cand, role in candidates(text or area):
            if role not in roles:
                continue
            tried.append(cand)
            found = options(norm(cand), cand, fuzzy)
            if found:
                found.sort(key=rank)
                if accept and not accept(found):
                    continue                                 # 'Nakuru' of 'Nakuru Athletic Club, Mombasa'
                lost = left_out(asked, cand)
                if role == "first words" or lost:
                    why = f' ("{", ".join(lost)}" was left out)' if lost else ""
                    notes.append(f'Only "{cand}" of "{asked}" was found{why}; check the draft is the place meant, '
                                 "or give the coordinates of the place they named.")
                    for _, p in found:
                        p["inside_of"] = True                # the place named may be only part of this one
                return cand, found
        return None

    def inside_named(found):
        """The best match lies inside the county or country the request names: 'Kitengela' of
        'Kitengela Hot Glass, Kajiado'; not 'Nakuru' of 'Nakuru Athletic Club, Mombasa'."""
        r, p = found[0]
        if r >= 10 or p.get("outside_named") or p["kind"] in BROAD or (abroad(p) and not country_named(p)):
            return False
        pt = point_of(p)
        if pt is None:                                       # a county: options() checked it lies there
            return p["kind"] == "county"
        shapes = [county_shape(n) if n in counties else g for _, n, g, _ in quals]
        return any(s is not None and shapely.contains_xy(s, *pt) for s in shapes)

    def country_named(p):
        c = norm(p.get("country") or "")
        return bool(c) and (c in area_n or any(norm(n) == c or k == c for k, n, _, _ in quals))

    def pick(hit, fuzzy=False, flag_abroad=True):
        cand, found = hit
        best = found[0][1]
        others = list(dict.fromkeys(label(p) for _, p in found[1:] if label(p) != label(best)
                                    and (not abroad(p) or p.get("country") in NEAR_KENYA or country_named(p))))[:4]
        if fuzzy:
            notes.append(f'"{cand}" was read as {best["name"]} (a close spelling); check that is right.')
        if others:
            notes.append("Also matched: " + "; ".join(others) + ". Change the spec if one of these was meant.")
        if flag_abroad and abroad(best) and not country_named(best) and best.get("source") != "places.yml":
            notes.insert(0, f"Outside Kenya: {label(best)}. Check that is the place meant.")
        if best.pop("outside_named", False):
            notes.append(outside_named_note(best))
        return best

    def outside_named_note(place):
        pt = ref_point(place) if place.get("region") else point_of(place)
        q = [n for k, n, _, _ in quals if k != norm(place["name"])]
        at = None
        if pt is not None:
            cb = county_boundaries()
            hits = [c for c, g in zip(cb["name"], cb.geometry) if shapely.contains_xy(g, *pt)]
            at = f"{hits[0]} County" if hits else country_at(*pt)
        return (f'{place["name"]} is in {at or "another place"}, not in {" or ".join(q) or "the place named"} as '
                "the request says; check which place the customer meant.")

    def known_here(term):
        try:
            return any(not abroad(p) for _, p in options(norm(term), term, False))
        except Exception:                                    # noqa: BLE001
            return False

    def search_osm(kenya_only, roles=("named", "bare")):
        within_g = [g for _, _, g, _ in quals]
        for term, role in search_terms(area, private=private):
            if role not in roles or (role == "bare" and not within_g):
                continue                                     # a bare 'Majengo' that cannot be checked
            if known_here(term):
                continue                                     # 'Ruiru' is known here: the wider-place step has it
            p = nominatim(term, kenya_only, within=within_g)
            if p is False:                                   # offline or refused: stop asking
                return False
            if not p or p["kind"] in BROAD:                  # 'Kenya' of 'Nyahururu, Kenya' is not the place
                continue
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
    exact = search(False, {"named"})
    clean = without_people(area, private)
    if not exact and clean != area:             # the place as written was not found: try it without the names
        exact = search(False, {"named"}, clean)
        if exact:
            skipped = " and ".join(f'"{p}"' for p in people_in(area, private)) or "the rest"
            notes.append(f'"{asked}" was read as {exact[0]}: {skipped} was not searched for, in case it is a '
                         "person's name. If it is a place, give its coordinates and draft again.")
    if exact and exact[1][0][1]["kind"] in BROAD and own_land_only(area):
        raise SystemExit(f'"{asked}" places their land only in {exact[1][0][1]["name"]}. Ask for its coordinates '
                         "(a point as 'lat, lon' from Google Maps, or a box as 'west, south, east, north') "
                         "or the nearest town.")
    doubtful = None
    if exact:
        best = exact[1][0][1]
        home = [f for f in exact[1] if not abroad(f[1])]
        if abroad(best) and home and not country_named(best):
            exact = (exact[0], home + [f for f in exact[1] if abroad(f[1])])
            best = home[0][1]
        big = best.get("country") in NEAR_KENYA and (best.get("pop") or 0) >= 250_000   # Kampala, Arusha
        if not abroad(best) or country_named(best) or big or best["kind"] != "town":
            place = pick(exact)
            return place, tried, notes + also_named(clean, place, exact[0], quals)
        doubtful = exact                                     # a town abroad: look for a Kenyan one first
    if online:
        p = search_osm(kenya_only=True)
        if p:
            if doubtful:
                b = doubtful[1][0][1]
                notes.append(f"There is also a {b['name']} in {b['country']} (Natural Earth); change the spec "
                             "if that was meant.")
            return p, tried, notes + also_named(clean, p, p["name"], quals)
        if p is False:
            online = False
    close = search(True, {"named"})
    if close:
        place = pick(close, fuzzy=True)
        return place, tried, notes + also_named(clean, place, close[0], quals)
    if quals:                                    # 'Kitengela Hot Glass, Kajiado': Kitengela, not all of Kajiado
        part = search(False, {"first words"}, accept=inside_named)
        if part:
            place = pick(part)
            return place, tried, notes + also_named(clean, place, part[0], quals)
    wider = search(False, {"context"})
    missing = [c.strip(" ,;:.-") for c, r in candidates(clean) if r == "named" and unfill(c) and norm(c) != norm(clean)]
    what = missing[0] if missing else asked
    if wider and wider[1][0][1]["kind"] in BROAD:
        if theme_only(what):                                 # 'population of Kenya': the theme, not a place
            return pick(wider), tried, notes
        wider = None                                         # 'Nyahururu, Kenya': ask, never draw all of Kenya
    if wider and not doubtful:
        home = [f for f in wider[1] if not abroad(f[1])]
        if home and abroad(wider[1][0][1]) and not country_named(wider[1][0][1]):
            wider = (wider[0], home + [f for f in wider[1] if abroad(f[1])])   # Nandi County, not Nandi, Fiji
        best = wider[1][0][1]
        if abroad(best) and not country_named(best) and best["kind"] == "town":
            doubtful = wider                                 # 'Otieno farm in Luanda': as for a bare 'Luanda'
            notes.append(f'"{what}" was not found, and the only {best["name"]} found is in {best["country"]}.')
        else:
            place = pick(wider)
            place["inside_of"] = True
            if (re.search(r"(?i)['’]s\b", what) or PERSONAL.search(what)
                    or {norm(w) for w in what.split()} & set(private)):     # 'dad's farm near Limuru'
                notes.insert(0, f'"{asked}" was read as {label(place)}; the rest is about a person, so the draft is '
                                "all of it. Ask for the coordinates of the place itself to centre the draft on it.")
            else:
                notes.insert(0, f'"{what}" was not found, so the draft is all of {label(place)}, the wider place the '
                                "request names. Give the place's coordinates (or add it to places.yml) and draft "
                                "again.")
            return place, tried, notes
    if doubtful:
        best = doubtful[1][0][1]
        if best.get("country") in NEAR_KENYA:
            place = pick(doubtful, flag_abroad=False)       # the note below says it is abroad
            notes.insert(0, f"OUTSIDE KENYA: {place['name']}, {place['country']}. No Kenyan place of that name "
                            "was found; if the customer meant one, give its coordinates or add it to places.yml.")
            return place, tried, notes
    part = search(False, {"first words"})                    # last local try: 'Kericho tea estate' -> Kericho
    if part:
        home = [f for f in part[1] if not abroad(f[1])]
        if home and abroad(part[1][0][1]) and not country_named(part[1][0][1]):
            part = (part[0], home + [f for f in part[1] if abroad(f[1])])   # 'Nandi Hills': Nandi County
        best = part[1][0][1]
        if not (abroad(best) and best["kind"] == "town" and not country_named(best)
                and best.get("country") not in NEAR_KENYA):
            place = pick(part)
            return place, tried, notes + also_named(clean, place, part[0], quals)
    if online:
        p = search_osm(kenya_only=False, roles=("named", "bare"))
        if p:
            return p, tried, notes
    abroad_hint = ""
    if doubtful:
        b = doubtful[1][0][1]
        abroad_hint = (f"\nThe only {b['name']} found is in {b['country']}; if that is the place, ask for "
                       f"\"{b['name']}, {b['country']}\".")
    road = any(re.match(ROAD_WORDS, w) for w in unfill(asked).split())
    if unsigned:
        abroad_hint = "\n" + unsigned + abroad_hint
    elif _MARKED.search(asked):                            # e.g. unsigned DMS 1°06'43", 36°39'00"
        abroad_hint = ("\nIt looks like coordinates that could not be read as one point or box (degree marks with "
                       "no N/S/E/W or minus sign, or an unusual layout): ask the customer, or write them as "
                       "'-1.112, 36.650' or '1.112 S, 36.650 E'." + abroad_hint)
    raise SystemExit(
        f'Could not find "{asked}" in Kenya. Tried: {", ".join(chr(34) + c + chr(34) for c in dict.fromkeys(tried))}.'
        f'{abroad_hint}\n' + ("It names a road: give a point on it as 'lat, lon'.\n" if road else "") +
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
    drawn |= {q[0] for q in quals}
    parts = named_parts(area)
    left = [p for p in parts if norm(p) not in drawn and norm(p) not in norm(place["name"])]
    if not left or len(parts) < 2:
        return []
    return [f"The request also names {', '.join(left)}; the draft is drawn for {place['name']} alone. If they want "
            "the other places on the sheet too, widen the extent or add them as labels."]


_LAST_SEARCH = [0.0]


def search_terms(area, limit=3, private=()):
    """What may be sent to OpenStreetMap, as (term, role): the place-name parts of the area, never
    the customer's sentence. Parts with numbers (plot, LR and phone numbers, distances), e-mail
    addresses, links, possessives (someone's shop), the customer's own name, or a word that points
    at a person (Mzee, grandfather, Mr) stay on this computer. 'X in Y' is sent as 'X, Y' first;
    X alone is 'bare' and is kept only when the answer can be checked against Y; Y is 'context'."""
    area = URL.sub(" ", english(area))
    terms, seen = [], set()

    def personal(part):
        words = {norm(w) for w in re.split(r"[\s,]+", part)}
        return bool(re.search(r"(?i)['’]s\b", part) or PERSONAL.search(part) or words & set(private))

    def add(part, role="named"):
        part = re.sub(r"\s+", " ", part).strip(" .-,")
        if (not part or re.search(r"\d|@|://|[#?=&~%]", part) or re.search(r"(?i)\.(?:com|org|net|gl|app)\b", part)
                or personal(part) or len(part.split()) > 5 or norm(part) in seen):
            return
        seen.add(norm(part))
        terms.append((part, role))

    area = without_people(area, private)
    commas = [p for p in area.split(",") if p.strip()]
    if len(commas) == 2:                 # 'Bondo, Siaya' is a good query as it is: a place and where it is
        parts = []
        for p in commas:
            head, tail = split_setting(p)
            parts.append(unfill(head) or unfill(tail or ""))
        if all(parts):
            add(", ".join(parts))
    named, bare, context = [], [], []
    chunks = [c for c in re.split(r"[,;/()]|\band\b|&", area) if unfill(c)]
    for n, p in enumerate(chunks):
        head, tail = split_setting(p.strip())
        h, tl = unfill(head), unfill(tail or "")
        word = (re.findall(SETTING, f" {p.strip()} ") or [""])[-1]
        if n == 0 and h and tl and personal(head) and re.fullmatch(AT_PLACE, word.strip()):
            named.append(tl)          # 'my mother's shamba in Kiserian': as for 'our land in Kiserian'
        elif h and tl:                            # 'Majengo in Nyeri' -> 'Majengo, Nyeri'
            add(f"{h}, {tl}")
            (bare if n == 0 else context).append(h)
            context.append(tl)
        elif n == 0:
            named.append(h or tl)                 # 'our home in Westlands' -> 'Westlands'
        else:
            context.append(h or tl)               # 'Juja, Kiambu': Kiambu is where Juja is
    for part in named:
        add(part)
    for part in bare:
        add(part, "bare")
    for part in context:
        add(part, "context")
    first = [x for x in terms if x[1] != "context"][:limit]
    return first + [x for x in terms if x[1] == "context"][:1]


def nominatim(term, kenya_only=True, within=()):
    """One OpenStreetMap search for a place name: a Place, None when nothing fits, or False when the
    search cannot be reached. `within`: outlines the answer must lie in (the search is limited to
    their box). Asks for English names. Waits a second between searches, as OpenStreetMap asks."""
    import urllib.request
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&addressdetails=1&accept-language=en&q="
           + urllib.parse.quote(term) + ("&countrycodes=ke" if kenya_only else ""))
    if within:
        import shapely
        w, s, e, n = shapely.union_all(within).bounds
        url += f"&viewbox={w:.3f},{n:.3f},{e:.3f},{s:.3f}&bounded=1"
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
        if within:
            import shapely
            if not any(shapely.contains_xy(g, float(r["lon"]), float(r["lat"])) for g in within):
                continue                                 # 'Majengo' in Mombasa is not 'Majengo in Nyeri'
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
        name = r.get("name") or term
        if not slugify(name):                            # no English name in OpenStreetMap: the request's
            name = term
        # a building or a point comes back a few metres across: give it a usable size
        min_km = 30 if kind == "mountain" else 8
        return Place(name=name, kind=kind, bbox=pad((w, s, e, n), 0.0, min_km=min_km),
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
    """The name in a draft's file name: the place, or where a coordinate request points (also for a
    name with no Latin letters)."""
    pt = point_of(place)
    if pt and ((place["kind"] in ("point", "box") and place["name"] == "Custom area")
               or not slugify(place["name"])):
        lon, lat = pt
        kind = place["kind"] if place["kind"] in ("point", "box") else "point"
        return f"{kind} {abs(lat):.3f}{'s' if lat < 0 else 'n'} {abs(lon):.3f}{'e' if lon >= 0 else 'w'}"
    return place["name"]


def is_kind(place, whole=False):
    """'is a county', 'is an area', 'are whole countries'."""
    k = place["kind"]
    if k == "countries":
        return "are " + ("whole countries" if whole else "several countries")
    w = "whole " + k if whole else k
    return ("is an " if w[0] in "aeiou" else "is a ") + w


# the drape styles: the style word -> (drape name in a spec, subtitle)
DRAPE_STYLES = {"landcover": ("landcover", "Land cover"),
                "forestloss": ("forest-loss", "Forest loss mapped, 2001 to 2023"),
                "water": ("water", "Surface water, 1984 to 2021"),
                "truecolour": ("true-colour", "In true colour")}


# The shop's plates of a place a request can name, other than the counties: (place found, drape
# or style drawn) -> (plate number, plate name, the master's command, the plate's spec to start from)
SHOP_PLATES = {
    ("Kenya", "landcover"): ("22", "Kenya, land cover", "relief.py kenya-landcover 300 40", None),
    ("Mau Forest", "forest-loss"): ("23", "The Mau Forest, forest loss",
                                    "relief.py spec:maps/mau-forest-loss.yml 300 40", "maps/mau-forest-loss.yml"),
    ("Lake Baringo", "water"): ("24", "Baringo & Bogoria", "relief.py spec:maps/baringo-bogoria-water.yml 300 40",
                                None),
    ("Lake Bogoria", "water"): ("24", "Baringo & Bogoria", "relief.py spec:maps/baringo-bogoria-water.yml 300 40",
                                None),
    ("Lake Victoria", "population"): ("25", "Lake Victoria, where people live",
                                      "population.py spec:maps/lake-victoria-population.yml 300 40",
                                      "maps/lake-victoria-population.yml"),
    ("Lake Magadi", "true-colour"): ("26", "Lake Magadi in true colour",
                                     "relief.py spec:maps/magadi-true-colour.yml 300 40", "maps/magadi-true-colour.yml"),
}
# what a draft takes from the plate's spec when it starts from it
PLATE_KEYS = ("region", "scale", "zex", "h3_res", "model_width", "drape_options", "labels", "names", "towns", "credit")
# the drape's name in the notes
DRAPE_NAMES = {"landcover": "land cover", "forest-loss": "forest loss", "water": "surface water",
               "true-colour": "true colour"}


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


def truecolour_tiles(place):
    """The Sentinel-2 tiles the true colour drape would read for the place, counted offline."""
    import truecolour
    if place.get("region"):
        import regions
        w, s, e, n = regions.region_outline(place["region"])[0].bounds
    else:
        w, s, e, n = extent(place)
    pad = 0.05                 # relief.py's margin round the outline and the drape's own 0.01
    return truecolour.tiles_needed((w - pad, s - pad, e + pad, n + pad))


def plate_for(place_name, drawn, area):
    """The shop plate a request is simply asking for: the place itself, not land in or near it."""
    if re.search(OWN_LAND, area or "") or re.search(NOT_IN, area or ""):
        return None
    return SHOP_PLATES.get((place_name, drawn))


def build_spec(place, style, request):
    """Returns (spec dict, style actually drawn, notes)."""
    notes = []
    name = place["name"]
    number = "01"
    asked = style
    part_of = place.pop("inside_of", False)                  # only part of the request was found (resolve)
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
        given = request.get("style") or theme_of(request.get("subject"), request.get("area", ""))
        notes.append(f"{'The customer was not sure' if given else 'No style was given'}: the draft is "
                     f"{'roads in gold' if style == 'gold' else 'relief'}, "
                     "the usual choice for " + ("a town." if style == "gold" else
                                                {"county": "a county.", "country": "a country.",
                                                 "countries": "a group of countries.",
                                                 "continent": "a continent."}.get(place["kind"], "a natural area.")))
    if style == "contours" and place.get("region"):
        notes.append(f"{name} {is_kind(place, whole=True)}: too big for a contour study (they read best from "
                     "1:10 000 to 1:100 000), so the draft is relief. Ask which mountain, crater or farm they mean.")
        style = "relief"
    if style == "gold" and place["kind"] not in ("town", "point", "box"):
        notes.append(f"Roads in gold need a town; {name} {is_kind(place)}, so the draft is relief. For gold, "
                     "draft again with the town centre's coordinates (lat, lon) as the area.")
        style = "relief"
    drape = drape_sub = None
    if style in DRAPE_STYLES:
        if style == "truecolour":
            import truecolour
            tiles = None if place["kind"] in BROAD else truecolour_tiles(place)
            if tiles is None or tiles > truecolour.MAX_TILES:
                notes.append("True colour is for areas up to a few hundred kilometres across (at most "
                             f"{truecolour.MAX_TILES} Sentinel-2 tiles of about 110 km); {name} {is_kind(place)}"
                             + (f" and needs {tiles}" if tiles else "") + ", so the draft is land cover instead. "
                             "For true colour, ask which part they mean and draft that.")
                style = "landcover"
        drape, drape_sub = DRAPE_STYLES[style]
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
        where = ({"point": "the point they gave", "box": "the centre of their box"}[place["kind"]]
                 if name == "Custom area" else f"the centre of {name}")
        notes.append(f"The circle reaches {radius:g} km from {where}; raise radius_km to take in more"
                     + (" of the town" if place["kind"] == "town" else "")
                     + ("." if country == "Kenya" else " (the roads are fetched again for a bigger circle)."))
        if country != "Kenya":
            notes.append(f"The country line reads {country.upper()}; roads outside Kenya are downloaded from "
                         "Overture Maps on the first render.")
        return spec, style, notes

    slug = f"draft-{slugify(slug_name(place))}-{drape or style}"
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

    subtitle = drape_sub or {"relief": "Relief", "population": "Where people live"}[style]
    spec = {"slug": slug, "title": title, "subtitle": subtitle, "label": "CUSTOM", "number": number,
            "region": region}
    if drape:
        spec["drape"] = drape
        if drape == "water":
            lake = place.get("at") or point_of(place) if place["kind"] == "lake" else None
            if lake:
                spec["drape_options"] = {"lakes": [{"name": name, "lon": round(float(lake[0]), 4),
                                                    "lat": round(float(lake[1]), 4)}]}
                notes.append(f"{name} is measured at the start and in 2021 in the facts row; check the point in "
                             "drape_options.lakes lies on the water.")
            else:
                notes.append("Name the lakes to measure in drape_options.lakes ({name, lon, lat} on the water); "
                             "without them the facts row gives the sheet's own water totals.")
        elif drape == "true-colour" and not (plate_for(name, drape, request.get("area")) or (0, 0, 0, None))[3]:
            notes.append("The draft takes the most recent clear Sentinel-2 day; once the scene suits, pin it with "
                         "drape_options: {date: YYYY-MM-DD} so the master matches the proof.")
        elif drape == "forest-loss":
            notes.append("Forest loss reads Hansen tiles: Kenya's are on disk; elsewhere a large area needs "
                         "drape_options: {allow_download: true}. Say 'loss mapped', not 'deforestation'.")
    if place["kind"] == "county":
        from relief import COUNTY_NUMBERS
        if not drape:
            spec["subtitle"] = "County relief" if style == "relief" else "Where the county's people live"
        if name in COUNTY_NUMBERS:
            spec["label"], spec["number"] = "COUNTY", f"{COUNTY_NUMBERS[name]:03d}"
        if style == "relief" and not drape and asked in ("relief", "unsure"):
            if part_of:                                      # 'Kakamega forest', 'Isecheno, Kakamega'
                notes.append(f"The shop has a {name} County plate, but the request names a place in it: print "
                             f"the plate (python relief.py \"county:{name}\" 300 40) only if they want the whole "
                             "county.")
            else:
                notes.append(f"This is the shop's {name} County plate. Unless they asked for changes, the print "
                             f"master can be the plate itself: python relief.py \"county:{name}\" 300 40.")
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
                it, they = ("them", "they") if len(labels) > 1 else ("it", "it")
                notes.append(f"No towns are set up for {name} County's plate yet"
                             + (f"; the draft labels {', '.join(x['name'] for x in labels)} from Natural Earth: check "
                                f"{it}, and add {it} to COUNTY_LABELS in relief.py if {they} should stay." if labels
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
    plate = None if part_of else plate_for(name, drape or style, request.get("area"))
    if plate:
        number, plate_name, command, source = plate
        if source:                    # start from the plate: its box, scale, names, credit and scene
            import yaml
            ps = yaml.safe_load((HERE / source).read_text(encoding="utf-8"))
            spec.update({k: ps[k] for k in PLATE_KEYS if ps.get(k) is not None})
        notes.append(f"This is the shop's plate {number}, {plate_name}"
                     + (" (the draft starts from its spec)" if source else "")
                     + f". Unless they asked for changes, the print master can be the plate itself: python {command}.")
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


def notes_point(request_notes, spec, near=None):
    """Coordinates in the customer's notes: (label or None, note or None). A short plus code in the
    notes is placed by `near`, the draft's own place."""
    pt = coordinates(request_notes or "")
    if not pt and near is not None:
        pc = plus_code(request_notes or "", near)
        if pc:
            pt = Place(name="Custom area", kind="point", centre=pc, source="the plus code in the notes")
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


def one_line(s):
    """Text on one line, for a comment in the spec's header: line breaks and other unprintable
    characters become spaces."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(s or "")).split())


def draft_key(path):
    """The request key in a draft's header ('# Request 3a925fa0: ...'), or None."""
    try:
        with path.open(encoding="utf-8") as f:
            for _, line in zip(range(3), f):
                m = re.match(r"# Request ([0-9a-f]{8}):", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def write_spec(spec, head, key, replace=False):
    """Write the draft without losing another request's draft or your edits. This request's own
    unedited draft is reused; with --replace its own draft is written over even if edited; another
    request's draft is never written over. Anything else takes the next free number.
    Returns (path, first slug, other requests' drafts in the way, this request's edited drafts)."""
    import yaml
    DRAFTS.mkdir(parents=True, exist_ok=True)
    first = spec["slug"]
    # the style suffix build_spec put on the slug ('-forest-loss', '-true-colour', '-gold'): the number goes before it
    kinds = sorted({*SCRIPT, *(d for d, _ in DRAPE_STYLES.values())}, key=len, reverse=True)
    kind = next((k for k in kinds if first.endswith("-" + k)), first.rsplit("-", 1)[-1])
    stem = first[:-len(kind) - 1]
    others, mine = [], []
    for n in range(1, 1000):
        spec["slug"] = first if n == 1 else f"{stem}-{n}-{kind}"
        path = DRAFTS / f"{spec['slug']}.yml"
        text = head + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=110)
        if not path.exists():
            break
        if draft_key(path) != key:
            others.append(path.name)                  # another request's draft: never written over
            continue
        if replace or path.read_text(encoding="utf-8").split("\n", 1)[-1] == text.split("\n", 1)[-1]:
            break                                     # this request's own draft
        mine.append(path.name)                        # this request's draft, with your edits
    yaml.safe_load(text)                              # never write a spec that will not load
    path.write_text(text, encoding="utf-8")
    return path, first, others, mine


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


# the drapes' own headline figures in a render log: the scene used, the shares, the totals
DRAPE_FACT = re.compile(r"  (true colour: (\d{4}-\d{2}-\d{2}|clearest)|land cover shares:|"
                        r"forest loss: forest in|transitions on the sheet|[^:]+: water at the start)")
SCENE = re.compile(r"^  true colour: (\d{4}-\d{2}-\d{2})((?:, \d{4}-\d{2}-\d{2})*) \(", re.M)


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
             if l.startswith((slug, f"spec:{rel}")) or DRAPE_FACT.match(l)
             or "left out" in l or l.startswith("  WARNING")]
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
    drawn = f"relief with the {DRAPE_NAMES.get(spec['drape'], spec['drape'])} drape" if spec.get("drape") else style
    lines = [
        f"# First look: {spec.get('title') or spec['city']['name']}, {drawn}",
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
        f"- Style: {drawn}.",
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
    VALUE_OPTS = ("--notes", "--style", "--request", "--row", "--dpi", "--spp")
    ap.add_argument("area", nargs="?", help="the area, as the customer wrote it")
    ap.add_argument("--style", default="", help="relief, contours, population, gold, or the form's wording")
    ap.add_argument("--notes", default="", help='the customer\'s notes (names, places, coordinates); '
                    'coordinates such as "-1.112,36.650" are fine, quoted')
    ap.add_argument("--request", help="a pasted request email (.txt), a Formspree export (.csv or .json)")
    ap.add_argument("--row", type=int, default=None,
                    help="which row of a CSV or JSON export, 0 the oldest (default: the newest)")
    ap.add_argument("--dpi", type=int, default=100, help="draft resolution, 50 to 249 (default 100)")
    ap.add_argument("--spp", type=int, default=16, help="ray-tracing samples for the draft (default 16)")
    ap.add_argument("--offline", action="store_true", help="never use OpenStreetMap's search")
    ap.add_argument("--no-render", action="store_true", help="write the spec and notes only")
    ap.add_argument("--replace", action="store_true",
                    help="write over an existing draft of the same name (your edits to it are lost)")
    # A southern point typed without a space, "-1.112,36.650", is a value, not an option: argparse
    # only lets a bare number through, so such a value is attached to its option or taken as the area.
    argv, point = [], None
    for tok in sys.argv[1:]:
        if re.match(r"-\.?\d", tok) and not re.fullmatch(r"-\d+", tok):
            if argv and argv[-1] in VALUE_OPTS:
                argv[-1] += "=" + tok                 # --notes -1.112,36.650 -> --notes=-1.112,36.650
                continue
            if point is None:
                point = tok
                continue
        argv.append(tok)
    args = ap.parse_args(argv)
    if point is not None:
        if args.area:
            ap.error(f"two areas given: {args.area!r} and {point!r}")
        args.area = point
    if not 50 <= args.dpi < 250:
        ap.error("--dpi is for the first-look draft (50 to 249); make the print master with the command in the notes")

    request = read_request(args.request, args.row) if args.request else {}
    if args.request and not any(request.get(k) for k in ("area", "style", "notes")):
        raise SystemExit(f"Nothing was read from {args.request}: no 'area:', 'style:' or 'notes:' lines. Paste the "
                         "email as it came, or give the area with --style and --notes.")
    if args.area:
        request["area"] = args.area
    if args.style:
        request["style"] = args.style
    if args.notes:
        request["notes"] = args.notes
    area = one_line(request.get("area"))
    if not area:
        raise SystemExit("No area: give it as the first argument or in the request file.")
    style = style_of(request.get("style"), request.get("subject"), area)
    where, in_area, phrase = style_in_area(area)     # 'Kenya land cover': Kenya, in land cover
    forests = {norm(n) for p in gazetteer() if p.get("kind") == "forest" for n in [p["name"], *p.get("aliases", [])]}
    if in_area == "forestloss" and norm(where + " forest") in forests:
        where += " Forest"                           # 'Mau forest loss': the Mau Forest, not the escarpment
    early = []
    if in_area and style == "unsure":
        style = in_area
        early.append(f'{"They were not sure of the style" if request.get("style") else "No style was given"}; '
                     f'the style is read from the area ("{phrase}"). Check that is what they meant.')
    print(f"Request: \"{area}\", style {style}")

    try:
        place, _, notes = resolve(where, style, online=not args.offline, subject=request.get("subject", ""),
                                  private=private_words(request.get("name"), request.get("email")))
        notes = early + notes
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
    try:
        near = ref_point(place)
    except (SystemExit, Exception):                  # noqa: BLE001
        near = None
    mark, note = notes_point(request.get("notes"), spec, near)
    if mark:
        spec["labels"] = spec["labels"] + [mark]
    if note:
        notes.append(note)
    elif request.get("notes") and not mark:
        notes.append("Their notes are not on the draft yet: add the names they asked for by hand.")

    key = request_key(request)
    head = (f"# First-look draft from a proof request, {dt.date.today():%Y-%m-%d}. Edit freely; see maps/README.md.\n"
            f"# Request {key}: area \"{one_line(area)}\", "
            f"style \"{one_line(request.get('style') or theme_of(request.get('subject'), area))}\"\n")
    spec_path, first, others, mine = write_spec(spec, head, key, args.replace)
    if others:
        many = len(others) > 1
        notes.append(f"{', '.join(others)} in maps/drafts {'hold other requests' if many else 'holds another request'} "
                     f"for the same place and style; {'they are' if many else 'it is'} left as {'they are' if many else 'it is'}, "
                     f"and this draft is {spec['slug']}.yml.")
    if mine:
        notes.append(f"{', '.join(mine)} {'are' if len(mine) > 1 else 'is'} this request's earlier draft with your "
                     f"edits, kept; this draft is {spec['slug']}.yml (--replace writes over this request's own "
                     "draft).")
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
        m = SCENE.search(log.read_text(encoding="utf-8")) if spec.get("drape") == "true-colour" and not failed else None
        if m and not (spec.get("drape_options") or {}).get("date"):
            notes = [n for n in notes if not n.startswith("The draft takes the most recent clear Sentinel-2 day")]
            if not m.group(2):
                notes.append(f"Scene used: {m.group(1)}. Before the proof, pin it: add "
                             f"`drape_options: {{date: '{m.group(1)}'}}` to {spec_path.name}, so the proof and the "
                             "master use this day and not a newer one.")
            else:
                notes.append(f"No single day was clear: the draft is {m.group(1)} filled from {m.group(2)[2:]}. "
                             f"Pinning `date` takes {m.group(1)} alone, clouds included.")
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
