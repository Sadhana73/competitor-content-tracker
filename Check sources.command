#!/bin/bash
# Double-click to test which feed and sitemap links work for each company.
cd "$(dirname "$0")" || exit 1
echo "Checking feed and sitemap links (about 1–2 minutes)…"
python3 find_sources.py
