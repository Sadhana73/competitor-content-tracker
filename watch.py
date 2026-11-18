#!/usr/bin/env python3
"""
Page watch
----------
Watches only the pages you add (e.g. a competitor's home page). On each check it
saves what matters on the page (title, description, H1/H2, menu, footer, buttons,
AI-related signals) and compares it with:
  - the previous check, and
  - an older copy from the Wayback Machine (about 30 days, 90 days and 1 year ago).
The dashboard turns the differences into plain sentences.

Files:
  data/watch.json                the pages you are watching
  data/watch-snapshots/*.json    what was found on each page, per check
"""
import os, re, json, html, hashlib, datetime, urllib.parse, time
import collect

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(HERE, "data", "watch.json")
SNAPS = os.path.join(HERE, "data", "watch-snapshots")
WAYBACK_AGES = {"wb30": 30, "wb90": 90, "wb365": 365}
AI_HINTS = re.compile(r"llms?(-full)?\.txt|ai[-_ ]?(info|instructions|policy|usage|crawler)|for ai|for llms|"
                      r"\bllm\b|ai agents? (policy|instructions)|machine[- ]readable|/ai\.txt", re.I)


# ---------------------------------------------------------------- the watch list
def load_list():
    if os.path.exists(LIST): return json.load(open(LIST, encoding="utf-8"))
    return {"pages": []}

def save_list(w):
    os.makedirs(os.path.dirname(LIST), exist_ok=True)
    json.dump(w, open(LIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def clean_url(u):
    u = u.strip()
    if not re.match(r"^https?://", u): u = "https://" + u
    p = urllib.parse.urlparse(u)
    if not p.netloc or "." not in p.netloc: raise ValueError("That doesn't look like a web address.")
    return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path or "/", "", p.query, ""))

def add_page(url, name=""):
    w = load_list(); url = clean_url(url)
    if any(x["url"] == url for x in w["pages"]): return url, False
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    w["pages"].append({"url": url, "name": name.strip() or host + (urllib.parse.urlparse(url).path if urllib.parse.urlparse(url).path != "/" else " home page"),
                       "added": collect.today_ist()})
    save_list(w); return url, True

def remove_page(url):
    w = load_list(); before = len(w["pages"])
    w["pages"] = [x for x in w["pages"] if x["url"] != url]
    save_list(w); return len(w["pages"]) < before


# ---------------------------------------------------------------- reading a page
def _strip(doc):
    return re.sub(r"<(script|style|noscript|svg|template)[\s>].*?</\1>", " ", doc, flags=re.S | re.I)

def _texts(part, tag):
    return [t for t in (collect.clean(m) for m in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", part, flags=re.S | re.I)) if t]

def _links(part):
    out = []
    for href, inner in re.findall(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', part, flags=re.S | re.I):
        t = collect.clean(inner) or collect.clean(" ".join(re.findall(r'(?:alt|aria-label|title)="([^"]*)"', inner + href, flags=re.I)))
        if t: out.append((t[:80], href))
    return out

def _uniq(xs, n):
    seen, out = set(), []
    for x in xs:
        k = x.lower()
        if k not in seen: seen.add(k); out.append(x)
        if len(out) >= n: break
    return out

def extract(doc, cfg):
    """Pull out the parts of a page worth comparing."""
    raw = doc
    doc = _strip(doc)
    region = lambda tag: " ".join(re.findall(rf"<{tag}[\s>].*?</{tag}>", doc, flags=re.S | re.I))
    nav = region("nav") or region("header")
    foot = region("footer")
    body = re.search(r"<body[\s>].*?</body>", doc, flags=re.S | re.I)
    text = collect.clean(body.group(0) if body else doc)
    words = {w for c in cfg.get("ctaTypes", []) for w in c["words"]}
    all_links = _links(doc)
    buttons = [t for t in _texts(doc, "button")] + [t for t, h in all_links if any(w in t.lower() for w in words)]
    ai = [f"{t} ({h})" for t, h in all_links if AI_HINTS.search(t + " " + h)]
    ai += [f'<link> {h}' for h in re.findall(r'<link[^>]+href="([^"]*llms?[^"]*\.txt)"', raw, flags=re.I)]
    jsonld = re.findall(r'"@type"\s*:\s*"([^"]+)"', raw)
    return {
        "title": collect.clean((re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.S | re.I) or [None, ""])[1])[:200],
        "description": collect.meta(raw, "description", "og:description")[:300],
        "h1": _uniq(_texts(doc, "h1"), 5),
        "h2": _uniq(_texts(doc, "h2"), 15),
        "menu": _uniq([t for t, _ in _links(nav)], 40),
        "footer": _uniq([t for t, _ in _links(foot)], 80),
        "buttons": _uniq(buttons, 25),
        "ai": _uniq(ai, 15),
        "schema": sorted(set(jsonld))[:20],
        "words": len(text.split()),
    }


# ---------------------------------------------------------------- checking
def _key(url): return hashlib.md5(url.encode()).hexdigest()[:12]

def _load_snaps(url):
    f = os.path.join(SNAPS, _key(url) + ".json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {"url": url, "live": [], "wayback": {}}

def _save_snaps(url, s):
    os.makedirs(SNAPS, exist_ok=True)
    json.dump(s, open(os.path.join(SNAPS, _key(url) + ".json"), "w", encoding="utf-8"), ensure_ascii=False)

def wayback_copy(url, days_ago):
    """Closest Wayback Machine copy to N days ago: (date, html) or (None, reason)."""
    target = (datetime.date.today() - datetime.timedelta(days=days_ago)).strftime("%Y%m%d")
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="") + "&timestamp=" + target
    txt, info = collect.fetch(api, timeout=30)
    if txt is None: return None, "Wayback Machine not reachable"
    try: snap = json.loads(txt).get("archived_snapshots", {}).get("closest")
    except Exception: snap = None
    if not snap or not snap.get("available"): return None, "no copy in the Wayback Machine"
    ts = snap["timestamp"]
    doc, info = collect.fetch(f"https://web.archive.org/web/{ts}id_/{url}", timeout=40)   # id_ = the original page, without Wayback's toolbar
    if doc is None: return None, "couldn't open the Wayback copy"
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", doc

def check_all():
    cfg = collect.load_config()
    pages = load_list()["pages"]
    if not pages: print("Page watch: no pages added yet."); return
    print(f"Page watch: checking {len(pages)} page(s)…", flush=True)
    today = collect.today_ist()
    for w in pages:
        s = _load_snaps(w["url"])
        doc, info = collect.fetch(w["url"], timeout=25)
        if doc is None:
            s["lastError"] = {"date": today, "note": "couldn't open the page"}; _save_snaps(w["url"], s)
            print(f"  {w['name']}: couldn't open the page ({info[:60]})", flush=True); continue
        s.pop("lastError", None)
        fields = extract(doc, cfg)
        s["live"] = [x for x in s["live"] if x["date"] != today] + [{"date": today, "fields": fields}]
        s["live"] = s["live"][-30:]
        for k, days in WAYBACK_AGES.items():
            old = s["wayback"].get(k)
            if old and old.get("checked") == today: continue         # at most once a day
            d, got = wayback_copy(w["url"], days)
            if d: s["wayback"][k] = {"date": d, "checked": today, "fields": extract(got, cfg)}
            else: s["wayback"][k] = {"date": None, "checked": today, "note": got}
            time.sleep(1)
        _save_snaps(w["url"], s)
        print(f"  {w['name']}: checked", flush=True)

def for_dashboard():
    """What the dashboard needs: each watched page with its latest, previous and Wayback snapshots."""
    out = []
    for w in load_list()["pages"]:
        s = _load_snaps(w["url"])
        live = s.get("live", [])
        out.append({**w, "now": live[-1] if live else None, "prev": live[-2] if len(live) > 1 else None,
                    "wayback": s.get("wayback", {}), "lastError": s.get("lastError")})
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "add": print(add_page(sys.argv[2], " ".join(sys.argv[3:])))
    elif len(sys.argv) > 2 and sys.argv[1] == "add-from-text":          # used by GitHub Actions (issue title + body)
        text = " ".join(sys.argv[2:])
        m = re.search(r"https?://[^\s<>\"')]+", text)
        if not m: print("No web address found in the request."); sys.exit(1)
        name = re.search(r"Name:\s*(.+)", text)
        print(add_page(m.group(0), name.group(1).strip() if name else ""))
    elif len(sys.argv) > 2 and sys.argv[1] == "remove": print(remove_page(sys.argv[2]))
    else: check_all()
