"""Check a built site: internal links, anchors, images, ids, alt text, JSON-LD."""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, unquote

root = Path(sys.argv[1])
pages = sorted(root.rglob("*.html"))
problems, stats = [], {"pages": len(pages), "links": 0, "images": 0, "external": set()}

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]; self.imgs=[]; self.h=[]; self.ld=[]; self._ld=False; self.title=None; self._t=False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a: self.ids.append(a["id"])
        for k in ("href", "src"):
            if k in a and a[k] is not None: self.links.append((tag, k, a[k]))
        if tag == "img":
            self.imgs.append(a)
            for part in (a.get("srcset") or "").split(","):
                if part.strip(): self.links.append(("img", "srcset", part.strip().split()[0]))
            if a.get("data-src"): self.links.append(("img", "data-src", a["data-src"]))
        if tag in ("h1","h2","h3","h4"): self.h.append(tag)
        if tag == "script" and a.get("type") == "application/ld+json": self._ld=True; self.ld.append("")
        if tag == "title": self._t=True; self.title=""
    def handle_endtag(self, tag):
        if tag == "script": self._ld=False
        if tag == "title": self._t=False
    def handle_data(self, d):
        if self._ld: self.ld[-1]+=d
        if self._t: self.title+=d

parsed = {}
for p in pages:
    x = P(); x.feed(p.read_text()); parsed[p] = x

def target(p, url):
    path = (p.parent / unquote(url)).resolve() if not url.startswith("/") else None
    return path

for p, x in parsed.items():
    rel = p.relative_to(root)
    dup = {i for i in x.ids if x.ids.count(i) > 1}
    if dup: problems.append(f"{rel}: duplicate ids {sorted(dup)}")
    if x.h.count("h1") != 1 and rel.name not in ("prints-shop.html",): problems.append(f"{rel}: {x.h.count('h1')} h1 elements")
    for a in x.imgs:
        stats["images"] += 1
        if "alt" not in a: problems.append(f"{rel}: img without alt {a.get('src')}")
        if not (a.get("width") and a.get("height")): problems.append(f"{rel}: img without width/height {a.get('src')}")
    for block in x.ld:
        try: json.loads(block)
        except Exception as e: problems.append(f"{rel}: invalid JSON-LD ({e})")
    for tag, k, url in x.links:
        if url.startswith(("http://", "https://")):
            stats["external"].add(re.sub(r"^(https?://[^/]+).*", r"\1", url)); continue
        if url.startswith(("mailto:", "tel:", "data:")): continue
        stats["links"] += 1
        u, frag = urldefrag(url)
        u = u.split("?")[0]
        t = p if u == "" else (p.parent / unquote(u)).resolve()
        if t.is_dir(): t = t / "index.html"
        if not t.exists():
            problems.append(f"{rel}: broken {k} -> {url}"); continue
        if frag and t.suffix == ".html":
            if frag not in parsed.get(t, P()).ids: problems.append(f"{rel}: missing anchor -> {url}")

print(f"{stats['pages']} pages, {stats['links']} internal references, {stats['images']} images checked")
print("external hosts:", ", ".join(sorted(stats["external"])))
print("titles:"); [print("  ", p.relative_to(root), "|", x.title.strip()) for p, x in parsed.items() if x.title]
print("PROBLEMS:" if problems else "no problems found")
for pr in problems: print("  ", pr)
