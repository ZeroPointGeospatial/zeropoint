"""Write one field note for the blog when one is due.

    python tools/blog/autopost.py              # write a post if the last one is old enough
    python tools/blog/autopost.py --force      # write one now
    python tools/blog/autopost.py --check-feeds
    python tools/blog/autopost.py --dry-run    # everything but the API call (a canned draft)

Run from the repository root. GitHub Actions runs it weekly
(.github/workflows/field-notes.yml) and commits the post it writes.

Each post is one of two kinds, taken in turn:

  news   a recent article from the feeds in sources.yml, read in full and
         explained for clients in Kenya, with the article cited as a source
  guide  one of the evergreen guides in sources.yml, written from its brief

Every draft goes through a second, separate review that checks it against its
sources and removes anything it cannot support, then through local checks
(length, headings, links, filler phrases). A draft that fails is not
published; the job log says why, and the source is noted in history.yml so
later runs move on to another. A run tries at most three drafts.

Needs ANTHROPIC_API_KEY in the environment.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
POSTS = ROOT / "_posts"
HISTORY = HERE / "history.yml"           # sources tried and not published, so they are not tried again
MAX_DRAFTS = 3                           # drafts per run, at two requests each
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
UA = "Mozilla/5.0 (compatible; ZeroPointFieldNotes/1.0; +https://zeropointgeospatial.pages.dev/blog/)"
TODAY = dt.date.today()

# Phrases that mark filler writing. A draft containing any of them is sent back.
# Matched as whole words; a trailing * also matches longer forms ("unlock*": unlocks, unlocking).
BANNED = [
    "delve*", "delving", "in today's", "fast-paced", "ever-evolving", "ever-changing", "game-changer*", "game changer*",
    "unlock*", "unleash*", "revolutioniz*", "revolutionis*", "landscape of", "tapestry", "navigate the",
    "navigating the", "it's important to note", "it is important to note", "in conclusion", "in summary",
    "seamless*", "cutting-edge", "cutting edge", "harness the power", "elevate", "elevates", "elevating",
    "embark*", "realm", "realms", "paradigm*", "synergy", "synergies", "robust solution*", "a testament to",
    "plays a crucial role", "plays a vital role", "whether you're", "look no further", "dive into",
    "deep dive", "stay tuned", "as an ai",
]


def has(term, text):
    """True if `term` is in `text` as whole words, ignoring case; "survey*" also matches surveys, surveyor."""
    t = term.lower()
    stem = t.endswith("*")
    pat = r"(?<![a-z0-9])" + re.escape(t.rstrip("*")) + ("" if stem else r"(?![a-z0-9])")
    return re.search(pat, text.lower()) is not None


def banned_in(text):
    return [b.rstrip("*") for b in BANNED if has(b, text)]


# ---------------------------------------------------------------- the blog so far

def front_matter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    try:
        return yaml.safe_load(text.split("---", 2)[1]) or {}
    except yaml.YAMLError:
        return {}


def existing_posts():
    posts = []
    for p in sorted(POSTS.glob("*.md")):
        fm = front_matter(p)
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.md$", p.name)
        if not m:
            continue
        fm["_date"] = dt.date.fromisoformat(m.group(1))
        fm["_slug"] = m.group(2)
        posts.append(fm)
    return posts


def history():
    if not HISTORY.exists():
        return []
    return yaml.safe_load(HISTORY.read_text(encoding="utf-8")) or []


def note(kind, item, guide, result, reason=""):
    """Add a source to history.yml: `rejected` (its draft failed) or `proposed` (sent for review)."""
    entry = {"date": TODAY.isoformat(), "kind": kind, "result": result}
    if kind == "news":
        entry.update(url=item["url"], title=item["title"])
    else:
        entry.update(guide=guide["id"])
    if reason:
        entry["reason"] = reason[:300]
    head = ("# Written by autopost.py: sources that were tried and not published, and drafts sent for\n"
            "# review. They are not tried again. Delete an entry to let the script try it once more.\n")
    entries = history() + [entry]
    HISTORY.write_text(head + yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=1000),
                       encoding="utf-8")


# ---------------------------------------------------------------- reading the web

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000)
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


class TextOf(HTMLParser):
    """The paragraphs of an article page, without navigation, scripts or footers."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "figure"}

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.inside = None
        self.buf, self.paras = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "li", "h2", "h3") and not self.depth:
            self.inside, self.buf = tag, []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag == self.inside:
            text = " ".join("".join(self.buf).split())
            if len(text) > 40 or tag in ("h2", "h3"):
                self.paras.append(("## " if tag in ("h2", "h3") else "") + text)
            self.inside = None

    def handle_data(self, data):
        if self.inside and not self.depth:
            self.buf.append(data)


def article_text(url):
    parser = TextOf()
    parser.feed(fetch(url))
    return "\n\n".join(parser.paras)


def strip_tags(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def read_feeds(cfg, verbose=False):
    import feedparser
    items, cutoff = [], TODAY - dt.timedelta(days=cfg.get("lookback_days", 35))
    for feed in cfg["feeds"]:
        try:
            parsed = feedparser.parse(fetch(feed["url"]))
            if not parsed.entries:
                raise ValueError("no entries")
        except Exception as e:                                   # noqa: BLE001 - any failure skips the feed
            print(f"  feed failed: {feed['name']} ({type(e).__name__}: {str(e)[:80]})")
            continue
        n = 0
        for e in parsed.entries:
            when = e.get("published_parsed") or e.get("updated_parsed")
            date = dt.date(*when[:3]) if when else None
            if not date or date < cutoff or not e.get("link"):
                continue
            items.append(dict(publisher=feed["name"], title=strip_tags(e.get("title")), url=e["link"],
                              date=date, summary=strip_tags(e.get("summary"))[:1200]))
            n += 1
        if verbose:
            print(f"  ok: {feed['name']}, {len(parsed.entries)} entries, {n} recent")
    return items


def score(item, cfg):
    text = f"{item['title']} {item['summary']}"
    title = item["title"]
    if any(has(x, text) for x in cfg.get("exclude", [])):
        return 0
    s = 0
    for w in cfg["keywords"]["strong"]:
        if has(w, text):
            s += 3 + (2 if has(w, title) else 0)
    for w in cfg["keywords"]["normal"]:
        if has(w, text):
            s += 1 + (1 if has(w, title) else 0)
    return s


def news_items(cfg, used_urls):
    """The best recent articles not yet used, each read in full, best first."""
    items = [i for i in read_feeds(cfg) if i["url"] not in used_urls]
    for i in items:
        i["score"] = score(i, cfg)
    items = sorted((i for i in items if i["score"] >= 2), key=lambda i: (i["score"], i["date"]), reverse=True)
    print(f"  {len(items)} candidate articles")
    for item in items[:8]:
        try:
            text = article_text(item["url"])
        except Exception as e:                                   # noqa: BLE001
            print(f"  could not read {item['url']}: {type(e).__name__}")
            continue
        if len(text) < 1500:                                     # not enough to write from without guessing
            print(f"  too little text in {item['url']} ({len(text)} characters)")
            continue
        item["text"] = text[:24000]
        yield item


# ---------------------------------------------------------------- writing

STYLE = """You write field notes for the website of ZeroPoint Geospatial, a land surveying and GIS firm in
Nairobi, Kenya. Its clients are landowners and buyers, developers, contractors, architects and planners,
county and public agencies, and banks. It also sells map prints made from open data.

How the notes read:
- Plain, exact British English, as a careful engineer would explain something to a client. Short
  paragraphs. Concrete nouns and verbs. No hype, no filler, no rhetorical questions, no exclamation marks.
- Never use these words or phrases: {banned}.
- Do not open by restating the title or with a sweeping statement about the world or the industry. Start
  with the specific thing the reader needs to know.
- Explain why it matters to someone in Kenya: a land buyer, a contractor, a county team. If it does not
  matter to them, say less rather than inventing a connection.
- 700 to 1 200 words. Markdown body with three to six `##` headings. No `#` title heading, no front matter,
  no table of contents, no closing summary section, no sign-off.
- Lists only where the content is a real list or a sequence of steps.

Accuracy rules, which matter more than anything above:
- Every specific fact (a number, a date, a name, a product, an organisation, a law or regulation, a price,
  a result) must come from the SOURCE MATERIAL you are given. General, long-established survey and GIS
  knowledge may be explained in your own words, but nothing that a reader would need to look up.
- Do not state Kenyan fees, timelines, procedures or section numbers of laws unless they are in the source
  material. Where a reader would need them, tell them to confirm with the relevant office or a licensed
  professional instead.
- Do not claim that ZeroPoint Geospatial has done, owns or offers anything beyond survey, GIS and mapping
  work and map prints. Do not invent clients, projects or quotes.
- Attribute news to its publisher in the text ("GPS World reports that..."). Do not quote more than one
  short sentence from any source.
- If the source material is too thin for a useful note, set "usable" to false and explain in "reason".
"""

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "reason": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "topic": {"type": "string"},
        "slug": {"type": "string"},
        "body_markdown": {"type": "string"},
    },
    "required": ["usable", "reason", "title", "description", "topic", "slug", "body_markdown"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "publish": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "body_markdown": {"type": "string"},
    },
    "required": ["publish", "problems", "title", "description", "body_markdown"],
    "additionalProperties": False,
}

REVIEW = """You are the fact checker for a land surveying firm's website. You are given SOURCE MATERIAL and a
DRAFT field note written from it. Check the draft sentence by sentence.

1. Remove or correct every specific claim (number, date, name, product, organisation, law, price, result)
   that the source material does not support. Do not add new facts.
2. Remove any statement of Kenyan fees, timelines, legal procedures or section numbers that is not in the
   source material.
3. Remove any claim that ZeroPoint Geospatial did, owns or offers something not stated in the source.
4. Rewrite any sentence that uses these words or phrases: {banned}. Cut filler and repetition.
5. Keep the structure: Markdown body, three to six `##` headings, no `#` heading, 700 to 1 200 words.

Return the corrected title, description and body. Set "publish" to false only if, after correction, the note
is no longer accurate and useful to a client in Kenya; list what you changed or why it fails in "problems".
"""


def call(client, system, user, schema):
    """One request; returns the parsed JSON, or None if the model declined."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                  # retry on another model if a safety classifier declines
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    u = response.usage
    print(f"  {response.model}: {u.input_tokens} tokens in, {u.output_tokens} out")
    if response.stop_reason == "refusal":
        print("  the model declined this request; nothing is published")
        return None
    if response.stop_reason == "max_tokens":
        print("  the response was cut off; nothing is published")
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    return json.loads(text) if text else None


def source_block(kind, item, guide):
    if kind == "news":
        return (f"SOURCE MATERIAL\n\nPublisher: {item['publisher']}\nTitle: {item['title']}\n"
                f"Date: {item['date'].isoformat()}\nURL: {item['url']}\n\nText of the article:\n{item['text']}")
    return (f"SOURCE MATERIAL\n\nGuide: {guide['title']}\nWritten for: {guide['reader']}\n"
            f"Brief (the only specific facts you may use):\n{guide['brief']}")


def write_post(client, kind, item, guide, topics):
    banned = ", ".join(f'"{b.rstrip("*")}"' for b in BANNED)
    system = STYLE.format(banned=banned)
    src = source_block(kind, item, guide)
    if kind == "news":
        task = ("Write a field note about this article for our clients in Kenya: what happened, what it means "
                "in practice, and what, if anything, a client here should do differently. Cite the publisher.")
    else:
        task = f"Write the field note \"{guide['title']}\" from the brief."
    task += (f"\n\n`topic` must be one of: {', '.join(topics)}. `slug`: 3 to 7 lowercase words joined by hyphens. "
             "`description`: one sentence of at most 160 characters saying what the reader will learn.")
    draft = call(client, system, f"{src}\n\nTASK\n{task}", DRAFT_SCHEMA)
    if not draft:
        return None, "the writer returned nothing"
    if not draft["usable"]:
        print(f"  writer: not usable ({draft['reason']})")
        return None, f"writer: {draft['reason']}"
    review = call(client, REVIEW.format(banned=banned),
                  f"{src}\n\nDRAFT\n\nTitle: {draft['title']}\nDescription: {draft['description']}\n\n"
                  f"{draft['body_markdown']}", REVIEW_SCHEMA)
    if not review:
        return None, "the review returned nothing"
    for p in review["problems"]:
        print(f"  review: {p}")
    if not review["publish"]:
        print("  review: not publishable")
        return None, "review: " + "; ".join(review["problems"])
    draft.update(title=review["title"], description=review["description"], body_markdown=review["body_markdown"])
    if kind == "guide" and guide.get("topic") in topics:
        draft["topic"] = guide["topic"]           # the guide's own topic, not the writer's choice
    return draft, ""


# ---------------------------------------------------------------- checks and output

def check(draft, topics, allowed_links):
    body, problems = draft["body_markdown"], []
    words = len(re.findall(r"\b\w+\b", body))
    if not 550 <= words <= 1500:
        problems.append(f"{words} words")
    heads = re.findall(r"^## ", body, re.M)
    if not 2 <= len(heads) <= 8:
        problems.append(f"{len(heads)} section headings")
    if re.search(r"^# ", body, re.M):
        problems.append("a top-level heading in the body")
    low = f"{draft['title']} {draft['description']} {body}".lower()
    found = banned_in(low)
    if found:
        problems.append("filler phrases: " + ", ".join(found))
    if draft["topic"] not in topics:
        problems.append(f"unknown topic {draft['topic']!r}")
    if len(draft["description"]) > 170:
        problems.append("description too long")
    for url in re.findall(r"\]\((https?://[^)\s]+)\)", body):
        if url not in allowed_links:
            problems.append(f"link not among the sources: {url}")
    return problems


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return "-".join(s.split("-")[:8]) or "field-note"


def save(draft, kind, item, guide, folder=None):
    folder = folder or POSTS
    # Posts are served at /blog/<slug>/ whatever their date, so the slug must be new to the whole blog.
    taken = {p["_slug"] for p in existing_posts()}
    taken |= {m.group(1) for f in folder.glob("*.md") if (m := re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", f.name))}
    base = slug = slugify(draft["slug"] or draft["title"])
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    path = folder / f"{TODAY.isoformat()}-{slug}.md"
    fm = {"layout": "post", "title": draft["title"], "description": draft["description"],
          "topic": draft["topic"], "auto": True, "kind": kind}
    if kind == "news":
        fm["sources"] = [{"title": item["title"], "publisher": item["publisher"], "url": item["url"],
                          "date": item["date"].isoformat()}]
    else:
        fm["guide"] = guide["id"]
    text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n"
    text += draft["body_markdown"].strip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path


class Canned:
    """Stands in for the API client in --dry-run, so the rest of the pipeline can be tested for free."""
    class _Messages:
        def create(self, **kw):
            schema = kw["output_config"]["format"]["schema"]
            para = ("Survey control points are the fixed references every later measurement on a site is "
                    "taken from, and keeping them intact is what lets a project stay in one coordinate "
                    "system from the first survey to the last as-built check. ") * 3
            body = "\n\n".join(f"## Part {i}\n\n{para}\n\n{para}" for i in range(1, 5))
            out = {"usable": True, "reason": "", "publish": True, "problems": [],
                   "title": "Why survey control points matter on long projects",
                   "description": "What control points are, why long projects depend on them, and how to keep them.",
                   "topic": "Survey methods", "slug": "survey-control-points-long-projects",
                   "body_markdown": body}
            text = json.dumps({k: out[k] for k in schema["properties"]})

            class R:
                model, stop_reason = "dry-run", "end_turn"
                usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()
                content = [type("B", (), {"type": "text", "text": text})()]
            return R()

    class _Beta:
        def __init__(self):
            self.messages = Canned._Messages()

    def __init__(self):
        self.beta = Canned._Beta()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="write a post even if one is not due")
    ap.add_argument("--check-feeds", action="store_true", help="load every feed and report")
    ap.add_argument("--dry-run", action="store_true", help="use a canned draft instead of the API")
    ap.add_argument("--kind", choices=["news", "guide"], help="write this kind of post")
    args = ap.parse_args()

    cfg = yaml.safe_load((HERE / "sources.yml").read_text(encoding="utf-8"))
    topics = yaml.safe_load((ROOT / "_data" / "topics.yml").read_text(encoding="utf-8"))
    if args.check_feeds:
        read_feeds(cfg, verbose=True)
        return 0

    posts = existing_posts()
    auto = sorted((p for p in posts if p.get("auto")), key=lambda p: p["_date"])
    last = auto[-1] if auto else None
    if last and not args.force:
        age = (TODAY - last["_date"]).days
        if age < cfg.get("cadence_days", 12):
            print(f"Not due: the last automatic post is {age} days old.")
            return 0

    tried = history()
    used_urls = {x.get("url") for p in posts for x in (p.get("sources") or [])}
    used_urls |= {e["url"] for e in tried if e.get("url")}
    used_guides = {p.get("guide") for p in posts if p.get("guide")}
    used_guides |= {e["guide"] for e in tried if e.get("guide")}
    guides = [g for g in cfg["guides"] if g["id"] not in used_guides]
    review_mode = os.environ.get("FIELD_NOTES_REVIEW", "").lower() == "true"

    # Alternate with the last automatic post, and fall back to the other kind.
    if args.kind:
        kinds = [args.kind]
    elif args.dry_run:
        kinds = ["guide"]
    else:
        first = "guide" if last and last.get("kind") == "news" else "news"
        kinds = [first, "news" if first == "guide" else "guide"]

    if args.dry_run:
        client = Canned()
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set; add it as a repository secret.")
            return 1
        import anthropic
        client = anthropic.Anthropic()

    def candidates():
        """(kind, news item, guide) in the order to try them."""
        for kind in kinds:
            if kind == "news":
                print("Looking for news")
                for item in news_items(cfg, used_urls):
                    yield "news", item, None
                print("  no more usable articles")
            else:
                if not guides:
                    print("Every guide in sources.yml has been written; add more to keep them coming.")
                for guide in guides:
                    yield "guide", None, guide

    drafts = 0
    for kind, item, guide in candidates():
        if drafts == MAX_DRAFTS:
            print(f"Tried {MAX_DRAFTS} drafts; stopping until the next run.")
            break
        drafts += 1
        if kind == "guide":
            print(f"Writing guide: {guide['title']}")
        else:
            print(f"Writing about: {item['title']} ({item['publisher']}, {item['date']})")
        draft, reason = write_post(client, kind, item, guide, topics)
        if draft:
            problems = check(draft, topics, {item["url"]} if item else set())
            if problems and not args.dry_run:
                reason = "failed the checks: " + "; ".join(problems)
                print("  draft " + reason)
                draft = None
        if not draft:
            if not args.dry_run:
                note(kind, item, guide, "rejected", reason)
            continue
        if args.dry_run:                   # never into _posts, so a test cannot be published by mistake
            import tempfile
            path = save(draft, kind, item, guide, Path(tempfile.mkdtemp(prefix="field-note-")))
            print(f"Wrote {path} (dry run)")
            if problems:
                print("  checks: " + "; ".join(problems))
        else:
            path = save(draft, kind, item, guide)
            if review_mode:                # a closed pull request must not bring the same source back
                note(kind, item, guide, "proposed")
            print(f"Wrote {path.relative_to(ROOT)}")
        return 0
    print("Nothing published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
