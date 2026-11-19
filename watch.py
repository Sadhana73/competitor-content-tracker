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
def same_page(u):
    """hubspot.com, www.hubspot.com and https://www.hubspot.com/ are the same page."""
    p = urllib.parse.urlparse(u if "://" in u else "https://" + u)
    return p.netloc.lower().removeprefix("www.") + (p.path.rstrip("/") or "/") + (("?" + p.query) if p.query else "")

def load_list():
    w = json.load(open(LIST, encoding="utf-8")) if os.path.exists(LIST) else {"pages": []}
    seen, keep = set(), []
    for x in w["pages"]:                      # drop duplicates such as hubspot.com vs www.hubspot.com (keep the first)
        k = same_page(x["url"])
        if k not in seen: seen.add(k); keep.append(x)
    w["pages"] = keep
    return w

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
    if any(same_page(x["url"]) == same_page(url) for x in w["pages"]): return url, False
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    w["pages"].append({"url": url, "name": name.strip() or host + (urllib.parse.urlparse(url).path if urllib.parse.urlparse(url).path != "/" else " home page"),
                       "added": collect.today_ist()})
    save_list(w); return url, True

def remove_page(url):
    w = load_list(); before = len(w["pages"])
    w["pages"] = [x for x in w["pages"] if x["url"] != url]
    save_list(w); return len(w["pages"]) < before


# ---------------------------------------------------------------- reading a page
from html.parser import HTMLParser

CTA_VERBS = re.compile(r"\b(get|start|try|book|request|schedule|sign ?up|join|download|contact|talk|buy|subscribe|register|demo|free|trial|see pricing|watch)\b", re.I)

def _tidy(t):
    t = re.sub(r"\s+", " ", html.unescape(t or "")).strip()
    m = re.fullmatch(r"(.+?)(?: \1)+", t)           # "Email Tracking Email Tracking" -> "Email Tracking"
    return (m.group(1) if m else t)[:90]

class _Page(HTMLParser):
    """Reads a page the way a browser would: headings, links, buttons, and which part (menu/footer) they are in."""
    SKIP = {"script", "style", "noscript", "svg", "template"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.skip = [], 0
        self.title = ""; self.meta = {}; self.jsonld_types = set(); self.ai_links = []
        self.h1, self.h2, self.menu, self.footer, self.buttons, self.links = [], [], [], [], [], []
        self.words = 0; self._cap = None; self._in_ld = False
    def _zone(self):
        tags = [t for t, _ in self.stack]
        if "footer" in tags: return "footer"
        if "nav" in tags or "header" in tags: return "menu"
        return "body"
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("meta",):
            k = (a.get("name") or a.get("property") or "").lower()
            if k: self.meta[k] = a.get("content") or ""
            return
        if tag == "link":
            h = a.get("href") or ""
            if re.search(r"llms?(-full)?\.txt", h, re.I): self.ai_links.append(f"<link> {h}")
            return
        if tag in ("br", "img", "input", "hr", "source", "wbr"):
            if tag == "img" and self._cap is not None: self._cap["text"] += " " + (a.get("alt") or "")
            return
        if tag == "script" and "ld+json" in (a.get("type") or ""): self._in_ld = True
        if tag in self.SKIP: self.skip += 1
        self.stack.append((tag, a))
        if tag in ("title", "h1", "h2", "a", "button") and self._cap is None:
            self._cap = {"tag": tag, "text": "", "href": a.get("href") or "", "label": a.get("aria-label") or a.get("title") or "", "zone": self._zone()}
    def handle_endtag(self, tag):
        if self._cap is not None and self._cap["tag"] == tag:
            c, self._cap = self._cap, None
            t = _tidy(c["text"]) or _tidy(c["label"])
            if t:
                if tag == "title": self.title = t
                elif tag == "h1": self.h1.append(t)
                elif tag == "h2": self.h2.append(t)
                else:
                    if tag == "a":
                        self.links.append((t, c["href"]))
                        if c["zone"] == "menu": self.menu.append(t)
                        elif c["zone"] == "footer": self.footer.append(t)
                    self.buttons.append(t)
                    if AI_HINTS.search(t + " " + c["href"]): self.ai_links.append(f"{t} ({c['href']})")
        if tag == "script": self._in_ld = False
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if tag in self.SKIP: self.skip = max(0, self.skip - 1)
                del self.stack[i:]; break
    def handle_data(self, d):
        if self._in_ld: self.jsonld_types.update(re.findall(r'"@type"\s*:\s*"([^"]+)"', d)); return
        if self.skip: return
        if self._cap is not None: self._cap["text"] += d
        if self.stack and self.stack[-1][0] != "title": self.words += len(d.split())

def _uniq(xs, n):
    seen, out = set(), []
    for x in xs:
        k = x.lower()
        if k not in seen: seen.add(k); out.append(x)
        if len(out) >= n: break
    return out

def extract(doc, cfg):
    """Pull out the parts of a page worth comparing."""
    p = _Page()
    try: p.feed(doc); p.close()
    except Exception: pass
    words = {w for c in cfg.get("ctaTypes", []) for w in c["words"]}
    ctas = [t for t in p.buttons if (any(w in t.lower() for w in words) or CTA_VERBS.search(t)) and len(t.split()) <= 8]
    return {
        "title": p.title[:200],
        "description": (p.meta.get("description") or p.meta.get("og:description") or "")[:300],
        "h1": _uniq(p.h1, 5), "h2": _uniq(p.h2, 15),
        "menu": _uniq(p.menu, 40), "footer": _uniq(p.footer, 80),
        "buttons": _uniq(ctas, 25), "ai": _uniq(p.ai_links, 15),
        "schema": sorted(p.jsonld_types)[:20], "words": p.words,
    }


# ---------------------------------------------------------------- screenshots (on GitHub; skipped if the browser isn't installed)
SHOTS = os.path.join(HERE, "data", "watch-shots")

def screenshot(url, out):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 900}, user_agent=collect.UA)
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            for label in ("Decline All", "Reject All", "Accept All", "Accept all", "Accept", "I agree", "Got it"):   # close cookie banners
                try:
                    btn = pg.get_by_role("button", name=label, exact=True)
                    if btn.count(): btn.first.click(timeout=1500); pg.wait_for_timeout(800); break
                except Exception: pass
            os.makedirs(os.path.dirname(out), exist_ok=True)
            pg.screenshot(path=out, type="jpeg", quality=65, full_page=False)
            b.close()
        return True
    except Exception as e:
        print(f"    screenshot skipped ({type(e).__name__})", flush=True); return False


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
    w = load_list(); save_list(w)              # saves the list with any duplicates removed
    pages = w["pages"]
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
        key = _key(w["url"])
        shot_now = f"{key}-now.jpg" if screenshot(w["url"], os.path.join(SHOTS, f"{key}-now.jpg")) else None
        s["live"] = [x for x in s["live"] if x["date"] != today] + [{"date": today, "fields": fields, "shot": shot_now}]
        s["live"] = s["live"][-30:]
        for k, days in WAYBACK_AGES.items():
            old = s["wayback"].get(k)
            if old and old.get("checked") == today and old.get("version") == 2: continue   # at most once a day
            d, got = wayback_copy(w["url"], days)
            if not d:                                   # the Wayback Machine is often slow: wait and try once more
                time.sleep(8); d, got = wayback_copy(w["url"], days)
            if d:
                ts = d.replace("-", "")
                view = f"https://web.archive.org/web/{ts}/{w['url']}"
                shot = f"{key}-{k}.jpg" if screenshot(f"https://web.archive.org/web/{ts}if_/{w['url']}", os.path.join(SHOTS, f"{key}-{k}.jpg")) else None
                s["wayback"][k] = {"date": d, "checked": today, "fields": extract(got, cfg), "view": view, "shot": shot, "version": 2}
            elif old and old.get("fields"):            # keep the last good copy rather than losing it
                old["lastTry"] = {"date": today, "note": got}
            else: s["wayback"][k] = {"date": None, "checked": today, "note": got, "version": 2}
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
                    "wayback": s.get("wayback", {}), "lastError": s.get("lastError"), "key": _key(w["url"])})
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
