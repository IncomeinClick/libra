#!/usr/bin/env python3
"""Delete uploaded ebook folders older than 7 days."""

import json
from pathlib import Path
from datetime import datetime, timedelta
import shutil

KDP_DIR = Path("/root/kdp")
KEEP_DAYS = 7

now = datetime.now()
deleted = []

for listing_file in KDP_DIR.glob("*/listing.json"):
    try:
        data = json.loads(listing_file.read_text())
        if data.get("status") != "uploaded":
            continue
        uploaded_at = data.get("uploaded_at")
        if not uploaded_at:
            continue
        uploaded_date = datetime.strptime(uploaded_at, "%Y-%m-%d")
        if now - uploaded_date > timedelta(days=KEEP_DAYS):
            slug = listing_file.parent.name
            shutil.rmtree(listing_file.parent)
            deleted.append(slug)
    except Exception as e:
        print(f"Error processing {listing_file}: {e}")

if deleted:
    print(f"Deleted {len(deleted)} old ebook(s): {', '.join(deleted)}")
else:
    print("Nothing to clean up")
