#!/usr/bin/env python3
"""Builds "Competitor Content Tracker.html" (one file, opens in Chrome) from
index.html + config.js + data/pages.json."""
import os, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
cfg = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
store = os.path.join(HERE, "data", "pages.json")
pages = json.load(open(store, encoding="utf-8")) if os.path.exists(store) else []
import sys; sys.path.insert(0, HERE); import watch
data = "window.TRACKER_DATA = " + json.dumps({"isSample": False,
        "asOf": datetime.datetime.now(IST).date().isoformat(), "pages": pages, "watch": watch.for_dashboard()}, ensure_ascii=False) + ";"
data = data.replace("</", "<\\/")
src = src.replace('<script src="config.js"></script>', "<script>\n" + cfg + "\n</script>")
src = src.replace('<script src="data.js"></script>', "<script>\n" + data + "\n</script>")
out = os.path.join(HERE, "Competitor Content Tracker.html")
open(out, "w", encoding="utf-8").write(src)
print(f"Dashboard updated: {out} ({len(pages)} pages)")
