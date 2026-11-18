#!/bin/bash
# Double-click this file to update the Competitor Content Tracker.
# It reads every company's feed, opens the new pages, checks watched pages, and rebuilds the dashboard.
cd "$(dirname "$0")" || exit 1
echo ""
echo "=== Competitor Content Tracker: updating ==="
echo ""
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed on this Mac. Ask Claude for help."; read -n 1 -s -r -p "Press any key to close."; exit 1
fi
echo "Step 1 of 4: reading the feeds…"
python3 collect.py feeds || { echo "Something went wrong reading the feeds."; read -n 1 -s -r -p "Press any key to close."; exit 1; }
echo ""
echo "Step 2 of 4: opening the new pages (this can take a few minutes)…"
python3 collect.py enrich all
echo ""
echo "Step 3 of 4: checking watched pages…"
python3 watch.py
echo ""
echo "Step 4 of 4: building the dashboard…"
python3 build_dashboard.py
date "+%Y-%m-%d %H:%M" > data/last-update.txt
open "Competitor Content Tracker.html"
echo ""
echo "Done. The dashboard has opened in your browser. You can close this window."
