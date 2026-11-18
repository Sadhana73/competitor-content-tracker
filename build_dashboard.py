#!/usr/bin/env python3
"""Builds "Competitor Content Tracker.html" (one file, opens in Chrome) from
index.html + config.js + data/pages.json."""
import os, sys, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
cfg = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
store = os.path.join(HERE, "data", "pages.json")
pages = json.load(open(store, encoding="utf-8")) if os.path.exists(store) else []
import sys; sys.path.insert(0, HERE); import watch
SITE = "--site" in sys.argv
if SITE:   # public site: only pages that count, without long text
    pages = [{k: v for k, v in p.items() if k not in ("firstParagraph", "fetchError")} | {"meta": (p.get("meta") or "")[:160]}
             for p in pages if not p.get("exclude") and not p.get("needsDate")]
last = open(os.path.join(HERE, "data", "last-update.txt")).read().strip() if os.path.exists(os.path.join(HERE, "data", "last-update.txt")) else None
data = "window.TRACKER_DATA = " + json.dumps({"isSample": False, "hosted": SITE, "lastUpdate": last,
        "asOf": datetime.datetime.now(IST).date().isoformat(), "pages": pages, "watch": watch.for_dashboard()}, ensure_ascii=False) + ";"
data = data.replace("</", "<\\/")
src = src.replace('<script src="config.js"></script>', "<script>\n" + cfg + "\n</script>")
src = src.replace('<script src="data.js"></script>', "<script>\n" + data + "\n</script>")
out = os.path.join(HERE, "site", "index.html") if SITE else os.path.join(HERE, "Competitor Content Tracker.html")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write(src)
print(f"Dashboard updated: {out} ({len(pages)} pages)")
