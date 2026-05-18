#!/usr/bin/env python3
"""Scan for new books created today and send Telegram notification."""

import json
import urllib.request
from pathlib import Path
from datetime import datetime

def _load_env() -> dict:
    env: dict[str, str] = {}
    p = Path(__file__).parent / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_ENV = _load_env()

KDP_DIR = Path(_ENV.get("KDP_DIR", "/root/kdp"))
TELEGRAM_BOT_TOKEN = _ENV.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _ENV.get("TELEGRAM_CHAT_ID", "")
today = datetime.now().strftime("%Y-%m-%d")


def translate_th(text):
    try:
        import urllib.parse
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
            {"client": "gtx", "sl": "auto", "tl": "th", "dt": "t", "q": text}
        )
        resp = urllib.request.urlopen(url, timeout=5)
        return json.loads(resp.read())[0][0][0]
    except Exception:
        return ""


def send_telegram(message):
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


new_books = []
for listing_file in KDP_DIR.glob("*/listing.json"):
    try:
        d = json.loads(listing_file.read_text())
        if d.get("created_at", "")[:10] == today and d.get("status") == "ready":
            d["_dir"] = listing_file.parent
            new_books.append(d)
    except Exception:
        continue

for book in new_books:
    title = book.get("title", "")
    subtitle = book.get("subtitle", "")
    lang = book.get("language", "")
    kw_count = len(book.get("keywords", []))
    book_dir = book["_dir"]
    has_epub = any(book_dir.glob("*.epub"))
    has_cover = (book_dir / "cover.jpg").exists()

    title_th = translate_th(title)

    parts = ["📚 <b>New Book on Libra</b>"]
    parts.append(f"<b>{title}</b>")
    if title_th:
        parts.append(f"({title_th})")
    if subtitle:
        parts.append(f"<i>{subtitle}</i>")
    if lang:
        parts.append(f"Language: {lang}")
    parts.append(f"Keywords: {kw_count}")
    parts.append(f"EPUB: {'✅' if has_epub else '❌'}  Cover: {'✅' if has_cover else '❌'}")
    parts.append(f"\nhttps://libra.incomeinclick.com")

    send_telegram("\n".join(parts))
    print(f"Notified: {title}")

if not new_books:
    print("No new books created today.")
