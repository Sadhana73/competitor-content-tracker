#!/usr/bin/env python3
"""Tests possible feed and sitemap links for each company and saves what works
to data/source-check.txt (Claude reads it to fix config.js)."""
import re, os, time
from collect import fetch, parse_feed

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = {
    "Pipedrive": {
        "feeds": ["https://www.pipedrive.com/en/blog/rss", "https://www.pipedrive.com/en/blog/rss.xml",
                  "https://www.pipedrive.com/en/blog/feed.xml", "https://www.pipedrive.com/blog/feed",
                  "https://news.google.com/rss/search?q=site:pipedrive.com/en/blog&hl=en-US&gl=US&ceid=US:en"],
        "sites": ["https://www.pipedrive.com"]},
    "Brevo": {
        "feeds": ["https://www.brevo.com/blog/rss/", "https://www.brevo.com/blog/feed.xml",
                  "https://www.brevo.com/feed/", "https://www.brevo.com/blog/rss.xml",
                  "https://news.google.com/rss/search?q=site:brevo.com/blog&hl=en-US&gl=US&ceid=US:en"],
        "sites": ["https://www.brevo.com"]},
    "monday.com": {
        "feeds": ["https://monday.com/blog/feed", "https://monday.com/blog/rss", "https://monday.com/blog/rss.xml",
                  "https://monday.com/blog/en/feed/",
                  "https://news.google.com/rss/search?q=site:monday.com/blog&hl=en-US&gl=US&ceid=US:en"],
        "sites": ["https://monday.com"]},
    "Zoho CRM": {
        "feeds": ["https://www.zoho.com/blog/crm/feed", "https://www.zoho.com/crm/feed"],
        "sites": ["https://www.zoho.com"],
        "sitemaps": ["https://www.zoho.com/crm/sitemap.xml", "https://www.zoho.com/sitemap.xml"]},
    "Salesforce": {"feeds": [], "sites": ["https://www.salesforce.com"]},
    "HubSpot": {"feeds": [], "sites": ["https://blog.hubspot.com", "https://www.hubspot.com"]},
}

out = []
def log(s=""):
    print(s, flush=True); out.append(s)

for co, c in CANDIDATES.items():
    log(f"===== {co} =====")
    for u in c.get("feeds", []):
        xml, info = fetch(u)
        n = len(parse_feed(xml)) if xml else 0
        log(f"FEED {'OK ' if n else 'no '} {n:>3} items  {u}" + ("" if xml else f"  ({info[:60]})"))
        time.sleep(0.3)
    maps = list(c.get("sitemaps", []))
    for site in c.get("sites", []):
        txt, info = fetch(site + "/robots.txt")
        found = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt or "")
        log(f"ROBOTS {site}: {len(found)} sitemap(s)" + ("" if txt else f" ({info[:60]})"))
        maps += found
    seen = set()
    for m in maps[:12]:
        if m in seen: continue
        seen.add(m)
        xml, info = fetch(m)
        if not xml:
            log(f"SITEMAP no   {m} ({info[:60]})"); continue
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", xml)
        kind = "index" if "<sitemapindex" in xml else "urls"
        log(f"SITEMAP OK   {kind:<5} {len(locs):>5} entries  {m}")
        sample = [l for l in locs if re.search(r"blog|crm|resources|articles|sitemap", l)][:25] or locs[:15]
        for l in sample: log(f"      {l}")
        time.sleep(0.3)
    log()

os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
open(os.path.join(HERE, "data", "source-check.txt"), "w").write("\n".join(out))
print("\nSaved to data/source-check.txt. You can close this window and tell Claude 'checked'.")
