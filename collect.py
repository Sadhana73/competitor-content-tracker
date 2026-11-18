#!/usr/bin/env python3
"""
Competitor Content Tracker — collector
--------------------------------------
Reads every company's feeds (from config.js), finds pages we have not seen
before, and saves them to data/pages.json. Uses only Python's built-in tools,
so nothing needs installing.

Steps (run in this order; each one is safe to run again):
  python3 collect.py feeds            read all feeds, add new pages
  python3 collect.py enrich [N|all]   open up to N new pages (default 25) to read their
                                      publish date, description, first paragraph and calls to action
  python3 collect.py status           show what is stored

Rules (from the build spec):
  - a page's URL is its unique key; the same page is never stored twice
  - every date is stored in IST
  - if a page has no publish date, the date collected is used and it is flagged
"""
import sys, os, re, json, html, time, datetime, urllib.request, urllib.parse, email.utils

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.js")
STORE = os.path.join(HERE, "data", "pages.json")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


# ---------------------------------------------------------------- settings
def load_config():
    """config.js is JavaScript (so the dashboard can read it); turn it into JSON here."""
    src = open(CONFIG, encoding="utf-8").read()
    src = src[src.index("{"): src.rindex("}") + 1]
    out, i, in_str, q = [], 0, False, ""
    while i < len(src):                      # drop // comments that are outside strings
        ch = src[i]
        if in_str:
            out.append(ch)
            if ch == "\\": out.append(src[i + 1]); i += 2; continue
            if ch == q: in_str = False
        elif ch in "\"'":
            in_str, q = True, ch; out.append(ch)
        elif src.startswith("//", i):
            while i < len(src) and src[i] != "\n": i += 1
            continue
        else:
            out.append(ch)
        i += 1
    text = "".join(out)
    parts = re.split(r'("(?:[^"\\]|\\.)*")', text)   # quote bare keys outside strings
    for k in range(0, len(parts), 2):
        parts[k] = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', parts[k])
        parts[k] = re.sub(r',(\s*[}\]])', r'\1', parts[k])
    return json.loads("".join(parts))


def load_store():
    if os.path.exists(STORE):
        return json.load(open(STORE, encoding="utf-8"))
    return []


def save_store(pages):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    pages.sort(key=lambda p: (p.get("published") or "", p["url"]), reverse=True)
    tmp = STORE + ".tmp"
    json.dump(pages, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    os.replace(tmp, STORE)


# ---------------------------------------------------------------- helpers
def fetch(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(4_000_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, "replace"), r.geturl()
    except Exception as e:
        return None, str(e)


def clean(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(s)))
    return re.sub(r"\s+", " ", s).strip()


TRACKING = re.compile(r"^(utm_|_?hs|hubs|mc_|fbclid|gclid|ref$|source$|oc$)")
def norm_url(u):
    """Same page, same key: drop tracking codes, #anchors, trailing slash; lowercase host."""
    u = html.unescape(u.strip())
    if "bing.com" in u and "url=" in u:                       # unwrap Bing tracking links
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        if q.get("url"): u = q["url"][0]
    p = urllib.parse.urlparse(u)
    query = "&".join(x for x in p.query.split("&") if x and not TRACKING.match(x.split("=")[0]))
    path = p.path.rstrip("/") or "/"
    if "news.google.com" in p.netloc: query = ""              # keep Google News article id only
    return urllib.parse.urlunparse((p.scheme or "https", p.netloc.lower(), path, "", query, ""))


def to_ist_date(s):
    """RSS (RFC 822) or ISO date -> YYYY-MM-DD in IST, or None."""
    if not s: return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        d = None
    if d is None:
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
            return m.group(1) if m else None
    if d.tzinfo is None: d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(IST).date().isoformat()


def today_ist():
    return datetime.datetime.now(IST).date().isoformat()


def parse_feed(xml):
    """Return list of {title, link, published, description} from RSS or Atom."""
    items = []
    blocks = re.findall(r"<item[\s>].*?</item>", xml, flags=re.S | re.I) or \
             re.findall(r"<entry[\s>].*?</entry>", xml, flags=re.S | re.I)
    for b in blocks:
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", b, flags=re.S | re.I)
            return m.group(1) if m else ""
        link = clean(tag("link"))
        if not link:
            m = re.search(r'<link[^>]+href="([^"]+)"', b, flags=re.I)
            link = m.group(1) if m else ""
        if not link: continue
        items.append({
            "title": clean(tag("title")),
            "link": link,
            "published": to_ist_date(clean(tag("pubDate")) or clean(tag("published")) or clean(tag("updated")) or clean(tag("dc:date"))),
            "description": clean(tag("description")) or clean(tag("summary")),
            "source": clean(tag("source")),
        })
    return items


def page_type(url):
    u = url.lower()
    if "template" in u or "/kit" in u: return "Template"
    if "/tools/" in u or "calculator" in u or "generator" in u: return "Tool"
    if "/case-stud" in u or "/customers/" in u: return "Case study"
    return "Blog"


# ---------------------------------------------------------------- rule-based first guess
# Quick keyword guess so pages are never left empty. Always marked Low confidence,
# so the AI step (or a person) can confirm it.
RULES = [
    ("AI in sales", ["ai ", " ai", "artificial intelligence", "agent", "chatgpt", "genai", "machine learning", "copilot", "llm"]),
    ("Sales templates and resources", ["template", "script", "checklist", "free download", "kit", "examples"]),
    ("CRM basics and comparisons", ["what is a crm", "crm software", "best crm", " vs ", "alternative", "choosing a crm", "crm for"]),
    ("Lead management", ["lead gen", "lead scoring", "leads", "prospect", "nurtur", "lead magnet"]),
    ("Pipeline and deals", ["pipeline", "deal", "closing", "forecast", "quota", "win rate"]),
    ("Marketing and email", ["email", "marketing", "newsletter", "social media", "seo", "campaign", "content", "brand", "instagram", "linkedin", "tiktok", "ads"]),
    ("Customer service and retention", ["customer service", "support", "retention", "churn", "loyalty", "customer success", "help desk", "nps"]),
    ("Automation and integrations", ["automation", "automate", "workflow", "integration", "no-code", "api", "zapier"]),
    ("Customer stories", ["case study", "customer story", "how ", "success story"]),
    ("Sales process and productivity", ["sales", "selling", "cold call", "objection", "rep", "kpi", "coaching", "productivity"]),
    ("Small business growth", ["small business", "startup", "entrepreneur", "founder", "grow your business", "smb", "side hustle"]),
]
def guess_category(title, desc):
    t = " " + (title + " " + (desc or "")).lower() + " "
    for cat, words in RULES:
        if cat == "Customer stories":
            if any(w in t for w in ["case study", "customer story", "success story"]): return cat
            continue
        if any(w in t for w in words): return cat
    return "Other"



# ---------------------------------------------------------------- sitemaps
SEEN = os.path.join(HERE, "data", "sitemap-seen.json")

def read_sitemap(url, depth=0, child_include=None):
    """Return list of (loc, lastmod-date or None). Follows a sitemap index one level down."""
    xml, info = fetch(url, timeout=30)
    if xml is None: return None, info
    if "<sitemapindex" in xml and depth == 0:
        out = []
        for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml):
            loc = html.unescape(loc)
            if child_include and not re.search(child_include, loc): continue
            got, _ = read_sitemap(loc, 1)
            out += got or []
        return out, "index"
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml, flags=re.S):
        m = re.search(r"<loc>\s*(.*?)\s*</loc>", block)
        if not m: continue
        lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block)
        out.append((html.unescape(m.group(1)), to_ist_date(lm.group(1)) if lm else None))
    return out, "urls"


def sitemap_candidates(co, sm, known, seen, lookback, today):
    """New or recently changed pages from one sitemap, to be checked by their real publish date."""
    entries, info = read_sitemap(sm["url"], child_include=sm.get("childInclude"))
    if entries is None: return [], f"{sm['url']} → {info[:80]}"
    inc = [re.compile(x) for x in sm.get("include", [])]
    exc = [re.compile(x) for x in sm.get("exclude", [])]
    entries = [(u, d) for u, d in entries if (not inc or any(r.search(u) for r in inc)) and not any(r.search(u) for r in exc)]
    key = co["name"] + " | " + sm["url"]
    first_scan = key not in seen
    before = set(seen.get(key, []))
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=lookback)).isoformat()
    cands = []
    for u, lm in entries:
        nu = norm_url(u)
        if nu in known: continue
        is_new_url = (not first_scan) and nu not in before
        recently_changed = lm is not None and lm >= since
        if is_new_url or recently_changed:
            cands.append((nu, lm, is_new_url))
    seen[key] = sorted({norm_url(u) for u, _ in entries} | before)
    cands.sort(key=lambda x: x[1] or "", reverse=True)
    return cands[: sm.get("maxPerRun", 150)], None


def title_from_url(u):
    slug = urllib.parse.urlparse(u).path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.(html?|php)$", "", slug)
    return slug.replace("-", " ").strip().capitalize() or u


def dedupe(pages):
    """The same article can arrive from two sources (e.g. Google News and a sitemap). Count it once,
    keeping the copy with the real page address."""
    groups = {}
    for p in pages:
        if p.get("exclude") or p.get("needsDate"): continue
        key = (p["company"], re.sub(r"\W+", " ", p["title"].lower()).strip())
        groups.setdefault(key, []).append(p)
    n = 0
    for ps in groups.values():
        if len(ps) < 2: continue
        ps.sort(key=lambda p: ("news.google.com" in p["url"], p["collected"]))
        for extra in ps[1:]:
            extra["exclude"] = "duplicate of " + ps[0]["url"]; n += 1
    return n

# ---------------------------------------------------------------- step 1: feeds
def step_feeds():
    cfg = load_config()
    pages = load_store()
    known = {p["url"] for p in pages}
    known_titles = {(p["company"], p["title"].lower()) for p in pages}
    today = today_ist()
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
    report = []
    for co in cfg["companies"]:
        found, used, errors = [], "feeds", []
        for url in co.get("feeds", []):
            xml, info = fetch(url)
            if xml is None: errors.append(f"{url} → {info[:80]}"); continue
            found += parse_feed(xml)
        sm_added = 0
        for sm in co.get("sitemaps", []):
            cands, err = sitemap_candidates(co, sm, known, seen, cfg.get("sitemapLookbackDays", 45), today)
            if err: errors.append(err); continue
            used = "feeds + sitemap" if found else "sitemap"
            for nu, lm, is_new_url in cands:
                pages.append({
                    "url": nu, "title": title_from_url(nu), "company": co["name"],
                    "published": lm or today, "dateMissing": True, "needsDate": True, "newInSitemap": is_new_url,
                    "category": "Other", "confidence": "Low", "setBy": "Rules",
                    "meta": "", "firstParagraph": "", "pageType": page_type(nu),
                    "ctas": None, "collected": today, "viaNews": False, "enriched": False, "source": "sitemap",
                })
                known.add(nu); sm_added += 1
        if not found and not sm_added and not co.get("sitemaps"):
            used = "backup"
            for url in co.get("backupFeeds", []):
                xml, info = fetch(url)
                if xml is None: errors.append(f"{url} → {info[:80]}"); continue
                got = parse_feed(xml)
                if got: found += got; break
        added = 0
        for it in found:
            url = norm_url(it["link"])
            title = it["title"]
            if " - " in title and it.get("source") and title.endswith(it["source"]):
                title = title[: -len(it["source"])].rstrip(" -")        # Google News adds " - Source"
            if "/author/" in url or not title: continue
            if it.get("source") and (re.search(r",\s*Author$", title) or len(title.split()) <= 2):
                continue                                   # Google News author or topic page, not an article
            if url in known or (co["name"], title.lower()) in known_titles: continue
            pub = it["published"]
            if "news.google.com" in url and pub:
                since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=cfg.get("sitemapLookbackDays", 45))).isoformat()
                if pub < since: continue                   # Google News also returns old pages; only recent ones are new
            pages.append({
                "url": url, "title": title, "company": co["name"],
                "published": pub or today, "dateMissing": not pub,
                "category": guess_category(title, it["description"]), "confidence": "Low", "setBy": "Rules",
                "meta": it["description"][:300], "firstParagraph": "", "pageType": page_type(url),
                "ctas": None, "collected": today, "viaNews": "news.google.com" in url, "enriched": False,
            })
            known.add(url); known_titles.add((co["name"], title.lower())); added += 1
        line = f"{co['name']:<12} {len(found):>3} in feed · {added:>3} new" + (f" · {sm_added} sitemap pages to check" if co.get("sitemaps") else "") + f" · source: {used}" + \
               (f" · problems: {'; '.join(errors)}" if errors else "")
        report.append(line); print(line, flush=True)
    save_store(pages)
    json.dump(seen, open(SEEN, "w"))
    print(f"\nTotal pages stored: {len(pages)}")


# ---------------------------------------------------------------- step 2: enrich
def region(doc):
    """The article itself, not the site menu/footer (so site-wide buttons don't count)."""
    for pat in (r"<article[\s>].*?</article>", r"<main[\s>].*?</main>"):
        m = re.search(pat, doc, flags=re.S | re.I)
        if m: return m.group(0)
    body = re.search(r"<body[\s>].*?</body>", doc, flags=re.S | re.I)
    b = body.group(0) if body else doc
    b = re.sub(r"<(nav|header|footer)[\s>].*?</\1>", " ", b, flags=re.S | re.I)
    return b


def find_ctas(doc, cta_types):
    part = region(doc)
    texts = []
    for m in re.finditer(r"<(a|button)[^>]*>(.*?)</\1>", part, flags=re.S | re.I):
        inner = m.group(2)
        alt = " ".join(re.findall(r'alt="([^"]*)"', inner, flags=re.I))
        texts.append(clean(inner) + " " + alt)
    texts += re.findall(r'class="[^"]*hs-cta[^"]*"[^>]*>(.*?)</', part, flags=re.S | re.I)
    blob = " | ".join(t.lower() for t in texts)
    return [c["name"] for c in cta_types if any(w in blob for w in c["words"])]


def meta(doc, *names):
    for n in names:
        m = re.search(rf'<meta[^>]+(?:name|property|itemprop)="{re.escape(n)}"[^>]+content="([^"]*)"', doc, flags=re.I) or \
            re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:name|property|itemprop)="{re.escape(n)}"', doc, flags=re.I)
        if m: return html.unescape(m.group(1)).strip()
    return ""


def step_enrich(limit=25, budget=150):
    if limit == 0: limit, budget = 10**6, 10**9        # "enrich all": no limits (used by Update tracker.command)
    cfg = load_config()
    pages = load_store()
    todo = [p for p in pages if not p.get("enriched") and not p.get("viaNews")]
    todo.sort(key=lambda p: p.get("source") != "sitemap")      # check sitemap pages first
    start, done = time.time(), 0
    for p in todo[:limit]:
        if time.time() - start > budget: break
        doc, final = fetch(p["url"], timeout=15)
        time.sleep(0.4)                                   # be polite to the websites
        p["enriched"] = True
        if doc is None:
            p["fetchError"] = final[:120]; continue
        desc = meta(doc, "description", "og:description")
        if desc: p["meta"] = desc[:300]
        pub = meta(doc, "article:published_time", "datePublished", "og:published_time")
        if not pub:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', doc)
            pub = m.group(1) if m else ""
        d = to_ist_date(pub)
        if p.get("source") == "sitemap":
            t = meta(doc, "og:title") or clean((re.search(r"<title[^>]*>(.*?)</title>", doc, flags=re.S | re.I) or [None, ""])[1])
            if t: p["title"] = re.split(r"\s[|–-]\s(?=[^|–-]*$)", t)[0].strip()[:200]
            since = (datetime.date.fromisoformat(today_ist()) - datetime.timedelta(days=cfg.get("sitemapLookbackDays", 45))).isoformat()
            if d:
                p["published"], p["dateMissing"] = d, False
                if d < since and not p.get("newInSitemap"):
                    p["exclude"] = "old page updated, not new"        # sitemap 'last modified' never counts as new
            elif p.get("newInSitemap"):
                p["published"], p["dateMissing"] = p["collected"], True  # first seen today, no publish date on the page
            else:
                p["exclude"] = "no publish date on the page"
            p["needsDate"] = False
        elif d:
            p["published"], p["dateMissing"] = d, False
        art = region(doc)
        for m in re.finditer(r"<p[^>]*>(.*?)</p>", art, flags=re.S | re.I):
            t = clean(m.group(1))
            if len(t) > 80: p["firstParagraph"] = t[:500]; break
        p["ctas"] = find_ctas(doc, cfg.get("ctaTypes", []))
        if p.get("setBy") == "Rules":
            p["category"] = guess_category(p["title"], p["meta"] + " " + p["firstParagraph"])
        done += 1
        print(f"  {done}/{min(limit, len(todo))}  {p['company']}: {p['title'][:60]}", flush=True)
        if done % 10 == 0: save_store(pages)          # save progress as we go
    dups = dedupe(pages)
    if dups: print(f"Removed {dups} duplicate page(s) found through two sources.")
    save_store(pages)
    left = len([p for p in pages if not p.get("enriched") and not p.get("viaNews")])
    print(f"Opened {done} pages. Still to open: {left}.")


def step_status():
    pages = load_store()
    by = {}
    for p in pages: by.setdefault(p["company"], []).append(p)
    for co, ps in by.items():
        print(f"{co:<12} {len(ps):>4} pages · newest {max(p['published'] for p in ps)} · "
              f"not opened yet {sum(1 for p in ps if not p.get('enriched') and not p.get('viaNews'))} · "
              f"AI/manual categories {sum(1 for p in ps if p.get('setBy') in ('AI','Manual'))}")
    print(f"Total: {len(pages)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "feeds"
    if cmd == "feeds": step_feeds()
    elif cmd == "enrich":
        arg = sys.argv[2] if len(sys.argv) > 2 else "25"
        step_enrich(0 if arg == "all" else int(arg))
    elif cmd == "status": step_status()
    else: print(__doc__)
