#!/usr/bin/env python3
"""
Competitor Content Tracker — local app
--------------------------------------
Serves the dashboard at http://127.0.0.1:8765 (only this Mac can open it) and
adds an "Update now" button that collects new pages and shows progress on the page.
Started by double-clicking "Competitor Tracker" in this folder.
"""
import os, sys, io, json, time, threading, datetime, contextlib, importlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import collect, watch

PORT = 8765
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
LAST = os.path.join(HERE, "data", "last-update.txt")
STATE = {"running": False, "step": "", "log": [], "started": None, "finished": None, "error": None}
LOCK = threading.Lock()
LAST_SEEN = [time.time()]


class LogWriter(io.TextIOBase):
    """Sends everything the collector prints to the page's progress box."""
    def write(self, s):
        for line in s.splitlines():
            if line.strip():
                with LOCK:
                    STATE["log"].append(line.rstrip())
                    STATE["log"] = STATE["log"][-400:]
        return len(s)


def run_update():
    w = LogWriter()
    try:
        importlib.reload(collect); importlib.reload(watch)   # always use the newest program, even if it changed while the app was open
        with contextlib.redirect_stdout(w):
            STATE["step"] = "Step 1 of 3: reading the feeds"
            print("Reading every company's feeds…")
            collect.step_feeds()
            STATE["step"] = "Step 2 of 3: opening the new pages"
            print("Opening new pages to read dates, descriptions and calls to action…")
            collect.step_enrich(0)
            STATE["step"] = "Step 3 of 3: checking watched pages"
            watch.check_all()
        os.makedirs(os.path.dirname(LAST), exist_ok=True)
        open(LAST, "w").write(datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M"))
        STATE["step"] = "Done"
    except Exception as e:
        STATE["error"] = f"{type(e).__name__}: {e}"
        STATE["step"] = "Stopped with a problem"
    finally:
        STATE["running"] = False
        STATE["finished"] = time.time()


def run_watch_only():
    w = LogWriter()
    try:
        importlib.reload(collect); importlib.reload(watch)
        with contextlib.redirect_stdout(w):
            STATE["step"] = "Checking watched pages"
            watch.check_all()
        STATE["step"] = "Done"
    except Exception as e:
        STATE["error"] = f"{type(e).__name__}: {e}"; STATE["step"] = "Stopped with a problem"
    finally:
        STATE["running"] = False; STATE["finished"] = time.time()


def dashboard_html():
    """Same page the builder makes, assembled fresh on every visit."""
    src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    cfg = open(os.path.join(HERE, "config.js"), encoding="utf-8").read()
    store = os.path.join(HERE, "data", "pages.json")
    pages = json.load(open(store, encoding="utf-8")) if os.path.exists(store) else []
    importlib.reload(watch)
    data = "window.TRACKER_DATA = " + json.dumps({"isSample": False, "live": True,
            "asOf": datetime.datetime.now(IST).date().isoformat(), "pages": pages, "watch": watch.for_dashboard()}, ensure_ascii=False) + ";"
    src = src.replace('<script src="config.js"></script>', "<script>\n" + cfg + "\n</script>")
    src = src.replace('<script src="data.js"></script>', "<script>\n" + data.replace("</", "<\\/") + "\n</script>")
    return src


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def status(self):
        last = open(LAST).read().strip() if os.path.exists(LAST) else None
        with LOCK:
            return {"running": STATE["running"], "step": STATE["step"], "log": STATE["log"][-60:],
                    "error": STATE["error"], "lastUpdate": last}

    def do_GET(self):
        LAST_SEEN[0] = time.time()
        if self.path in ("/", "/index.html") or self.path.startswith("/#"):
            self.send(200, dashboard_html(), "text/html")
        elif self.path == "/api/status":
            self.send(200, json.dumps(self.status()))
        else:
            self.send(404, "{}")

    def do_POST(self):
        LAST_SEEN[0] = time.time()
        # only accept clicks from the dashboard itself
        origin = self.headers.get("Origin", "")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self.send(403, json.dumps({"error": "not allowed"}))
        if self.path == "/api/watch":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if body.get("action") == "remove":
                    return self.send(200, json.dumps({"ok": watch.remove_page(body.get("url", ""))}))
                url, added = watch.add_page(body.get("url", ""), body.get("name", ""))
                return self.send(200, json.dumps({"ok": True, "url": url, "added": added}))
            except Exception as e:
                return self.send(400, json.dumps({"ok": False, "error": str(e)}))
        if self.path not in ("/api/update", "/api/watch/check"):
            return self.send(404, "{}")
        with LOCK:
            if STATE["running"]:
                return self.send(200, json.dumps({"started": False, "reason": "already running"}))
            STATE.update(running=True, step="Starting…", log=[], started=time.time(), finished=None, error=None)
        threading.Thread(target=run_watch_only if self.path == "/api/watch/check" else run_update, daemon=True).start()
        self.send(200, json.dumps({"started": True}))


def idle_watch():
    """Close the helper after 3 hours with the dashboard unused (and nothing running)."""
    while True:
        time.sleep(300)
        if not STATE["running"] and time.time() - LAST_SEEN[0] > 3 * 3600:
            os._exit(0)


if __name__ == "__main__":
    threading.Thread(target=idle_watch, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Competitor Content Tracker running at http://127.0.0.1:{PORT}")
    srv.serve_forever()
