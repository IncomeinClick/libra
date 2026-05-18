import json
import os
import glob
import httpx
import logging
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("libra")

# ── Config from .env ──
ENV = {}
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip()

app = FastAPI(title="Libra")

KDP_DIR = Path(ENV.get("KDP_DIR", "/root/kdp"))
USERNAME = ENV.get("USERNAME", "")
PASSWORD = ENV.get("PASSWORD", "")
TOKEN = ENV.get("SESSION_TOKEN", "")

TELEGRAM_BOT_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = ENV.get("TELEGRAM_CHAT_ID", "")


async def translate_th(text: str) -> str:
    """Translate text to Thai using Google Translate."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "auto", "tl": "th", "dt": "t", "q": text},
                timeout=5,
            )
            return resp.json()[0][0][0]
    except Exception:
        return ""


async def notify(message: str):
    """Send Telegram notification to Pond's personal chat."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Telegram notify failed: {e}")


def get_books():
    books = []
    for listing_file in sorted(KDP_DIR.glob("*/listing.json"), reverse=True):
        slug = listing_file.parent.name
        try:
            data = json.loads(listing_file.read_text())
            data["slug"] = slug
            # Find epub file
            epubs = list(listing_file.parent.glob("*.epub"))
            data["has_epub"] = len(epubs) > 0
            data["epub_name"] = epubs[0].name if epubs else None
            # Find paperback PDF
            pdfs = [p for p in listing_file.parent.glob("*paperback*.pdf")]
            data["has_pdf"] = len(pdfs) > 0
            data["pdf_name"] = pdfs[0].name if pdfs else None
            # Find cover
            cover = listing_file.parent / "cover.jpg"
            data["has_cover"] = cover.exists()
            books.append(data)
        except Exception:
            continue
    # Sort by created_at descending
    books.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return books


def check_auth(request: Request):
    token = request.cookies.get("libra_token")
    if token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    if body.get("username") == USERNAME and body.get("password") == PASSWORD:
        response = JSONResponse({"ok": True})
        response.set_cookie("libra_token", TOKEN, httponly=True, max_age=86400 * 30)
        return response
    raise HTTPException(status_code=401, detail="Wrong password")


@app.get("/api/books")
async def list_books(request: Request, status: str = None):
    check_auth(request)
    books = get_books()
    if status:
        books = [b for b in books if b.get("status") == status]
    return books


@app.get("/api/books/{slug}/epub")
async def download_epub(slug: str, request: Request):
    check_auth(request)
    book_dir = KDP_DIR / slug
    if not book_dir.exists():
        raise HTTPException(status_code=404)
    epubs = list(book_dir.glob("*.epub"))
    if not epubs:
        raise HTTPException(status_code=404, detail="No EPUB found")
    return FileResponse(epubs[0], filename=epubs[0].name, media_type="application/epub+zip")


@app.get("/api/books/{slug}/pdf")
async def download_pdf(slug: str, request: Request):
    check_auth(request)
    book_dir = KDP_DIR / slug
    if not book_dir.exists():
        raise HTTPException(status_code=404)
    pdfs = [p for p in book_dir.glob("*paperback*.pdf")]
    if not pdfs:
        raise HTTPException(status_code=404, detail="No PDF found")
    return FileResponse(pdfs[0], filename=pdfs[0].name, media_type="application/pdf")


@app.get("/api/books/{slug}/cover")
async def get_cover(slug: str, request: Request):
    check_auth(request)
    cover = KDP_DIR / slug / "cover.jpg"
    if not cover.exists():
        raise HTTPException(status_code=404)
    return FileResponse(cover, media_type="image/jpeg")


@app.post("/api/books/{slug}/generate-pdf")
async def generate_pdf(slug: str, request: Request):
    check_auth(request)
    book_dir = KDP_DIR / slug
    listing_file = book_dir / "listing.json"
    md_file = book_dir / "ebook.md"
    if not listing_file.exists():
        raise HTTPException(status_code=404, detail="Book not found")
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="No ebook.md found")

    data = json.loads(listing_file.read_text())
    title = data.get("title", slug)
    safe_name = title.replace(" ", "-").replace("/", "-").replace(":", "-")
    pdf_path = book_dir / f"{safe_name}-paperback.pdf"

    if pdf_path.exists():
        return {"ok": True, "message": "PDF already exists"}

    # Also create metadata.yaml if missing
    meta_file = book_dir / "metadata.yaml"
    if not meta_file.exists():
        lang = data.get("language", "pt-BR")
        lang_code = "pt-BR" if "Portuguese" in lang else "en" if "English" in lang else "id" if "Indonesian" in lang else lang[:5]
        meta_file.write_text(
            f'---\ntitle: "{title}"\n'
            f'subtitle: "{data.get("subtitle", "")}"\n'
            f'author: "IncomeinClick"\nlang: {lang_code}\ndate: "2026"\n---\n'
        )

    import subprocess
    # KDP paperback: 6x9 inch trim size, proper margins
    result = subprocess.run(
        ["pandoc", str(md_file), "-o", str(pdf_path),
         "--pdf-engine=xelatex",
         "--metadata-file", str(meta_file),
         "--toc", "--toc-depth=2",
         "-V", "geometry:paperwidth=6in,paperheight=9in,margin=0.75in,inner=0.875in",
         "-V", "fontsize=11pt",
         "-V", "mainfont=DejaVu Serif",
         "-V", "sansfont=DejaVu Sans",
         "-V", "monofont=DejaVu Sans Mono",
         "-V", "documentclass=book",
         "-V", "classoption=openany"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {result.stderr[:500]}")

    title_th = await translate_th(title)
    await notify(f"📄 <b>PDF Generated</b>\n{title}\n({title_th})")
    return {"ok": True, "message": "PDF generated", "filename": pdf_path.name}


@app.patch("/api/books/{slug}/status")
async def update_status(slug: str, request: Request):
    check_auth(request)
    listing_file = KDP_DIR / slug / "listing.json"
    if not listing_file.exists():
        raise HTTPException(status_code=404)
    data = json.loads(listing_file.read_text())
    body = await request.json()
    new_status = body.get("status", "uploaded")
    data["status"] = new_status
    if new_status == "uploaded":
        data["uploaded_at"] = datetime.now().strftime("%Y-%m-%d")
    elif new_status == "ready":
        data["uploaded_at"] = None
    listing_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    title = data.get("title", slug)
    title_th = await translate_th(title)
    if new_status == "uploaded":
        await notify(f"✅ <b>Uploaded to KDP</b>\n{title}\n({title_th})")
    else:
        await notify(f"↩️ <b>Moved back to Queue</b>\n{title}\n({title_th})")
    return {"ok": True, "status": new_status}


@app.post("/api/books")
async def create_book(request: Request):
    """Create a new book entry. Called by Tim/skills after generating an ebook."""
    check_auth(request)
    body = await request.json()
    slug = body.get("slug")
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    book_dir = KDP_DIR / slug
    listing_file = book_dir / "listing.json"
    if not listing_file.exists():
        raise HTTPException(status_code=404, detail=f"No listing.json found at {book_dir}")
    data = json.loads(listing_file.read_text())
    title = data.get("title", slug)
    subtitle = data.get("subtitle", "")
    lang = data.get("language", "")
    keywords_count = len(data.get("keywords", []))
    has_epub = any(book_dir.glob("*.epub"))
    has_cover = (book_dir / "cover.jpg").exists()
    title_th = await translate_th(title)
    parts = [f"📚 <b>New Book on Libra</b>"]
    parts.append(f"<b>{title}</b>")
    if title_th:
        parts.append(f"({title_th})")
    if subtitle:
        parts.append(f"<i>{subtitle}</i>")
    if lang:
        parts.append(f"Language: {lang}")
    parts.append(f"Keywords: {keywords_count}")
    parts.append(f"EPUB: {'✅' if has_epub else '❌'}  Cover: {'✅' if has_cover else '❌'}")
    parts.append(f"\nhttps://libra.incomeinclick.com")
    await notify("\n".join(parts))
    return {"ok": True, "slug": slug, "title": title}


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(html_path.read_text())
