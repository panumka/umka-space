from flask import Flask, render_template, request, send_file, Response, jsonify
import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from notion_client import Client
import time

import io
from urllib.parse import unquote, unquote_plus, urlparse
import ipaddress
import socket
from PIL import Image
# Safety: guard against decompression-bomb attacks in Pillow
Image.MAX_IMAGE_PIXELS = int(os.environ.get("UMKA_MAX_IMAGE_PIXELS", "30000000"))  # default 30M px
import pillow_heif
import base64

# --- requests retrying session helpers ---
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _requests_session():
    retry = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    s = requests.Session()
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_REQ = _requests_session()

# Helper: fetch og:image from a webpage (for use as a thumbnail)
def get_og_image(url: str) -> str | None:
    """Fetch the Open Graph image (og:image) for a given webpage URL.
    Returns direct image URL or None if not found/failed.
    Uses the shared retrying session and a short timeout.
    """
    if not url:
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
        }
        r = _REQ.get(url, headers=headers, timeout=5)
        if r.status_code != 200 or not (r.text or "").strip():
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Prefer og:image, but also try twitter:image as fallback
        for prop, attr in (("og:image", "property"), ("twitter:image", "name")):
            tag = soup.find("meta", {attr: prop})
            if tag and tag.get("content"):
                return tag.get("content").strip()
    except Exception:
        pass
    return None

# --- Helper: favicon from URL using DuckDuckGo service ---
def _favicon_from_url(url: str) -> str | None:
    """
    Return a favicon URL for the given page URL using DuckDuckGo's favicon service.
    Works for most domains (spotify, music.apple.com, music.youtube.com, deezer.com, amazon, etc.).
    """
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        return f"https://icons.duckduckgo.com/ip3/{host}.ico"
    except Exception:
        return None


load_dotenv(override=True)
pillow_heif.register_heif_opener()




app = Flask(__name__)
# --- Auto cache-busting for static files (adds ?v=<mtime>) ---
from flask import url_for as _flask_url_for

@app.context_processor
def _override_url_for():
    def dated_url_for(endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename')
            if filename:
                try:
                    file_path = os.path.join(app.static_folder, filename)
                    values['v'] = int(os.stat(file_path).st_mtime)
                except Exception:
                    # якщо файл не знайдено — просто пропускаємо
                    pass
        return _flask_url_for(endpoint, **values)
    return dict(url_for=dated_url_for)
# Optional: gzip/brotli compression if flask-compress is installed
try:
    from flask_compress import Compress  # type: ignore
    Compress(app)
except Exception:
    pass

# Static files cache (can be overridden by env UMKA_STATIC_MAX_AGE)
try:
    from datetime import timedelta
    _static_max_age = int(os.environ.get("UMKA_STATIC_MAX_AGE", "604800"))  # 7 days
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(seconds=_static_max_age)
except Exception:
    pass

# Security headers for every response (relaxed CSP to avoid breaking current UI)
@app.after_request
def _set_default_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    # If app is served via HTTPS, uncomment the next line to enforce HSTS
    resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
    # Relaxed CSP that works with current inline styles/scripts and remote images
    csp = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none'"
    )
    resp.headers.setdefault("Content-Security-Policy", csp)
    return resp

# Inject current year into all templates
@app.context_processor
def inject_now():
    import datetime as _dt
    return {"current_year": _dt.datetime.utcnow().year}

# Register Jinja filter: b64encode (URL-safe)
def _b64encode_filter(s):
    if not s:
        return ""
    if isinstance(s, bytes):
        b = s
    else:
        b = str(s).encode("utf-8")
    return base64.urlsafe_b64encode(b).decode("utf-8")

app.jinja_env.filters["b64encode"] = _b64encode_filter

#
# Simple per-user (IP) cache for YouTube results
YT_CACHE = {}
YT_TTL_SEC = int(os.environ.get("UMKA_TTL_SEC", "1800"))  # default 30 minutes
YT_CACHE_MAX = int(os.environ.get("UMKA_YT_CACHE_MAX", "1000"))

def _prune_yt_cache():
    if not YT_CACHE:
        return
    now = time.time()
    expired = [k for k, v in YT_CACHE.items() if now - v.get("ts", 0) > YT_TTL_SEC]
    for k in expired:
        YT_CACHE.pop(k, None)
    if len(YT_CACHE) > YT_CACHE_MAX:
        items = sorted(YT_CACHE.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
        YT_CACHE.clear()
        for k, v in items[:YT_CACHE_MAX]:
            YT_CACHE[k] = v

# Very simple IP-based rate limit for /proxy_img
PROXY_LIMIT_COUNT = int(os.environ.get("UMKA_PROXY_LIMIT_COUNT", "60"))          # 60 hits
PROXY_LIMIT_WINDOW = int(os.environ.get("UMKA_PROXY_LIMIT_WINDOW_SEC", "300"))  # per 5 minutes
_PROXY_BUCKETS = {}  # ip -> {"ts": epoch, "count": n}
_PROXY_BUCKETS_MAX = int(os.environ.get("UMKA_PROXY_BUCKETS_MAX", "2000"))

def _prune_proxy_buckets():
    if not _PROXY_BUCKETS:
        return
    now = time.time()
    expired = [ip for ip, b in _PROXY_BUCKETS.items() if now - b.get("ts", 0) > PROXY_LIMIT_WINDOW]
    for ip in expired:
        _PROXY_BUCKETS.pop(ip, None)
    if len(_PROXY_BUCKETS) > _PROXY_BUCKETS_MAX:
        items = sorted(_PROXY_BUCKETS.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
        _PROXY_BUCKETS.clear()
        for ip, b in items[:_PROXY_BUCKETS_MAX]:
            _PROXY_BUCKETS[ip] = b

def _rate_limited(ip: str) -> bool:
    _prune_proxy_buckets()
    now = time.time()
    b = _PROXY_BUCKETS.get(ip)
    if not b or now - b["ts"] > PROXY_LIMIT_WINDOW:
        _PROXY_BUCKETS[ip] = {"ts": now, "count": 1}
        return False
    b["count"] += 1
    return b["count"] > PROXY_LIMIT_COUNT

# Notion credentials (optional)
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()
# Notion DB for releases/links to streaming platforms (optional)
NOTION_STREAMS_DATABASE_ID = os.environ.get("NOTION_STREAMS_DATABASE_ID", "").strip()
NOTION_TTL_SEC = int(os.environ.get("UMKA_NOTION_TTL_SEC", "600"))
_NOTION_CACHE = {}  # key -> {"ts": epoch, "data": payload}

def _get_cached_notion(key: str):
    if not _NOTION_CACHE:
        return None
    now = time.time()
    item = _NOTION_CACHE.get(key)
    if not item:
        return None
    if now - item.get("ts", 0) > NOTION_TTL_SEC:
        _NOTION_CACHE.pop(key, None)
        return None
    return item.get("data")

def _set_cached_notion(key: str, data):
    _NOTION_CACHE[key] = {"ts": time.time(), "data": data}

# --- helpers: terms + simple filter ---

def get_terms():
    raw = os.environ.get("UMKA_SEARCH_TERMS", "").strip()
    if raw:
        return [t.strip().lower() for t in raw.split(",") if t.strip()]
    # default terms (case-insensitive substring check)
    return ["umka", "umk", "нішеві", "fremd", "запоріжстайл"]


def fetch_panamabattle_videos(max_results=50):
    """Fetch videos from PANAMABATTLE channel using YouTube Data API v3.
    Filters *titles only* for any of the terms from get_terms() (case-insensitive).
    Returns a list of dicts: id, title, published_at (YYYY-MM-DD), url, thumb.
    Uses the uploads playlist to scan older videos beyond the first 150 search results.
    """
    API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
    channel_id = os.environ.get("PANAMABATTLE_CHANNEL_ID", "UC8zDVdKUnjs4E3FYGVIP0LQ").strip()

    # Fall back to empty if no prerequisites
    if not API_KEY or not channel_id:
        print("[YT API] missing API key or channel id")
        return []

    terms = [t.lower() for t in get_terms()]
    max_pages = int(os.environ.get("UMKA_YT_MAX_PAGES", "20"))
    max_scan = int(os.environ.get("UMKA_YT_MAX_SCAN", "1000"))

    # Resolve uploads playlist id (cheaper and more complete than search)
    uploads_id = None
    try:
        ch = _REQ.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"key": API_KEY, "part": "contentDetails", "id": channel_id},
            timeout=10,
        )
        if ch.status_code == 200:
            data = ch.json() or {}
            items = data.get("items") or []
            if items:
                uploads_id = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
    except Exception as e:
        print("[YT API] channels failed:", e)

    if not uploads_id:
        print("[YT API] missing uploads playlist id")
        return []

    base_url = "https://www.googleapis.com/youtube/v3/playlistItems"
    # We'll page through the uploads playlist (50 per page)
    page_token = None
    collected = {}
    fetched = 0
    pages_left = max_pages

    while pages_left > 0 and fetched < max_scan:  # hard ceiling guard
        params = {
            "key": API_KEY,
            "part": "snippet",
            "playlistId": uploads_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            r = _REQ.get(base_url, params=params, timeout=10)
            if r.status_code != 200:
                print("[YT API] status", r.status_code, "->", (r.text[:200] if r.text else ""))
                break
            data = r.json() or {}
        except Exception as e:
            print("[YT API] failed:", e)
            break

        for item in data.get("items", []):
            sn = item.get("snippet") or {}
            rid = sn.get("resourceId") or {}
            vid = rid.get("videoId") or ""
            title = sn.get("title") or ""
            title_l = title.lower()

            # Title-only term check (any term)
            if not any(t in title_l for t in terms):
                continue

            published_at = (sn.get("publishedAt") or "")[:10]
            if vid:
                collected[vid] = {
                    "id": vid,
                    "title": title,
                    "published_at": published_at,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                }

        fetched += len(data.get("items", []))
        page_token = data.get("nextPageToken")
        pages_left -= 1
        if not page_token:
            break

    items = list(collected.values())
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:max_results]

def fetch_notion_posts(limit: int = 20):
    """Return a list of posts from a Notion database (no 'Published' required).
    Expects (recommended) properties:
      - Name (title)
      - Date (date) — optional
      - Excerpt (rich_text) — optional
      - Text (rich_text) — optional (used as fallback excerpt)
      - Files & media (files) — optional (first file used as thumb)
    """
    if not (NOTION_API_KEY and NOTION_DATABASE_ID):
        return []

    cache_key = f"posts:{NOTION_DATABASE_ID}:{limit}"
    cached = _get_cached_notion(cache_key)
    if cached is not None:
        return cached

    try:
        notion = Client(auth=NOTION_API_KEY)
        # No server-side filter/sort: keep it robust if properties are missing
        resp = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            page_size=limit,
        )
    except Exception as e:
        print("[Notion] query failed:", e)
        return []

    posts = []
    for r in resp.get("results", []):
        props = r.get("properties", {})

        # Title
        title_parts = props.get("Name", {}).get("title", [])
        title = "".join(part.get("plain_text", "") for part in title_parts) or "Без назви"

        # Date (optional)
        date = (props.get("Date", {}).get("date") or {}).get("start")

        # Excerpt (optional) or fallback to Text
        excerpt_parts = props.get("Excerpt", {}).get("rich_text", [])
        excerpt = "".join(part.get("plain_text", "") for part in excerpt_parts) if excerpt_parts else ""
        if not excerpt:
            text_parts = props.get("Text", {}).get("rich_text", [])
            excerpt = "".join(part.get("plain_text", "") for part in text_parts)[:240] if text_parts else ""

        # Slug (optional)
        slug_parts = props.get("Slug", {}).get("rich_text", [])
        slug = "".join(part.get("plain_text", "") for part in slug_parts) if slug_parts else None

        # Thumb: prefer Files & media (files), fallback to page cover
        thumb = None
        files_prop = (
            props.get("Files & media")
            or props.get("Dateien und Medien")
            or props.get("Files")
            or {}
        )
        if files_prop.get("type") == "files":
            files_list = files_prop.get("files", [])
            if files_list:
                f = files_list[0]
                if f.get("type") == "external":
                    candidate = (f.get("external") or {}).get("url")
                elif f.get("type") == "file":
                    candidate = (f.get("file") or {}).get("url")
                else:
                    candidate = None
                # If candidate looks like a direct image, use it; otherwise try to extract og:image
                if candidate:
                    lower = candidate.lower()
                    if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic", ".heif")):
                        thumb = candidate
                    else:
                        og = get_og_image(candidate)
                        thumb = og or candidate
        if not thumb:
            cover_obj = r.get("cover")
            if cover_obj:
                if cover_obj.get("type") == "external":
                    thumb = (cover_obj.get("external") or {}).get("url")
                elif cover_obj.get("type") == "file":
                    thumb = (cover_obj.get("file") or {}).get("url")
        # If still no thumb, try to fetch og:image from a URL property (e.g., a YouTube link)
        if not thumb:
            url_prop = None
            # Tolerant variants for the property name
            for k in ("URL", "Url", "Link", "Посилання"):
                p = props.get(k)
                if isinstance(p, dict):
                    # Native URL type
                    url_prop = p.get("url") or url_prop
                    # Or rich_text fallback
                    if not url_prop:
                        rts = p.get("rich_text") or []
                        if rts:
                            url_prop = "".join(t.get("plain_text", "") for t in rts).strip() or None
                if url_prop:
                    break
            if url_prop:
                og = get_og_image(url_prop)
                if og:
                    thumb = og
        # External URL (optional) for rendering direct links in the blog list
        ext_url = None
        for k in ("URL", "Url", "Link", "Посилання"):
            p = props.get(k)
            if isinstance(p, dict):
                ext_url = p.get("url") or ext_url
                if not ext_url:
                    rts = p.get("rich_text") or []
                    if rts:
                        ext_url = "".join(t.get("plain_text", "") for t in rts).strip() or None
            if ext_url:
                break

        # Date display and sorting key
        date_iso = date
        date_display = date_iso

        # If no Date provided, fall back strictly to page creation time
        if not date_iso:
            date_iso = (r.get("created_time") or "").strip() or None
            if date_iso:
                date_display = date_iso[:10]

        posts.append({
            "id": r.get("id"),
            "title": title,
            "date": date_iso,
            "date_display": date_display,
            "slug": slug,
            "excerpt": excerpt,
            "url": r.get("url"),
            "thumb": thumb,
            "ext_url": ext_url,
        })

    # Local sort by date if present
    posts.sort(key=lambda x: x.get("date") or "", reverse=True)
    _set_cached_notion(cache_key, posts)
    return posts


# --- fetch_stream_releases: music releases with platform links from Notion ---
def fetch_stream_releases(limit: int = 24):
    """Return a list of music releases from a Notion database where each page
    can contain URLs for different platforms (Spotify, Apple Music, etc.).

    Expected properties (optional, read if present):
      - Name (title) — release title
      - Date (date) — release date (optional)
      - Cover (files) — preferred; falls back to page cover
      - Spotify (url)
      - Apple Music (url)
      - YouTube Music (url)
      - YouTube (url)
      - Deezer (url)
      - SoundCloud (url)
      - Bandcamp (url)
    """
    if not (NOTION_API_KEY and NOTION_STREAMS_DATABASE_ID):
        return []

    cache_key = f"streams:{NOTION_STREAMS_DATABASE_ID}:{limit}"
    cached = _get_cached_notion(cache_key)
    if cached is not None:
        return cached

    try:
        notion = Client(auth=NOTION_API_KEY)
        # Sort by Date desc if the property exists; if not, Notion will ignore it.
        resp = notion.databases.query(
            database_id=NOTION_STREAMS_DATABASE_ID,
            page_size=limit,
        )
    except Exception as e:
        print("[Notion] streams query failed:", e)
        return []

    def _prop_url(props, key):
        p = (props or {}).get(key) or {}
        # native URL property
        url = p.get("url") if isinstance(p, dict) else None
        if url:
            return url
        # fallback: text property named like the platform
        rts = (p.get("rich_text") or []) if isinstance(p, dict) else []
        if rts:
            return "".join(t.get("plain_text", "") for t in rts).strip() or None
        return None

    items = []
    for r in resp.get("results", []):
        props = r.get("properties", {})

        # Title (support both default "Name" and custom "Title")
        title_prop = props.get("Name") or props.get("Title") or {}
        title_parts = title_prop.get("title", []) if isinstance(title_prop, dict) else []
        title = "".join(part.get("plain_text", "") for part in title_parts) or "Без назви"

        # Date (optional)
        date = (props.get("Date", {}).get("date") or {}).get("start")

        # Cover: prefer Cover/Cover Art (files), fallback to page cover
        cover = None
        files_prop = (
            props.get("Cover")
            or props.get("Cover Art")
            or props.get("Files & media")
            or props.get("Files")
            or {}
        )
        if files_prop.get("type") == "files":
            flist = files_prop.get("files", [])
            if flist:
                f = flist[0]
                if f.get("type") == "external":
                    cover = (f.get("external") or {}).get("url")
                elif f.get("type") == "file":
                    cover = (f.get("file") or {}).get("url")
        if not cover:
            cover_obj = r.get("cover")
            if cover_obj:
                if cover_obj.get("type") == "external":
                    cover = (cover_obj.get("external") or {}).get("url")
                elif cover_obj.get("type") == "file":
                    cover = (cover_obj.get("file") or {}).get("url")

        # Collect platform links (read if present, skip empties)
        platforms_spec = [
            ("spotify",      "Spotify"),
            ("apple",        "Apple Music"),
            ("youtubemusic", "YouTube Music"),
            ("deezer",       "Deezer"),
            ("amazon",       "Amazon Music"),
            ("itunes",       "iTunes"),
            ("bandcamp",     "bandcamp"),
            ("soundcloud",   "SoundCloud"),
            ("youtube",      "YouTube"),
        ]
        links = []
        # Case-insensitive match for platform keys/labels in property names
        for key, label in platforms_spec:
            match_key = next((k for k in props.keys() if k.lower() == key.lower() or k.lower() == label.lower()), None)
            if match_key:
                url = _prop_url(props, match_key)
                if url:
                    links.append({"key": key, "label": label, "url": url, "icon": _favicon_from_url(url)})

        items.append({
            "id": r.get("id"),
            "title": title,
            "date": date,
            "cover": cover,
            "links": links,
        })

    # Notion manual (drag&drop) order: last row = newest → show first
    items = list(reversed(items))
    _set_cached_notion(cache_key, items)
    return items

# --- Notion helpers: rich text & blocks -> HTML for modal rendering ---
def _rt_to_html(rts: list) -> str:
    parts = []
    for rt in rts or []:
        t = (rt.get("plain_text") or "")
        href = (rt.get("href") or "")
        if href:
            parts.append(f'<a href="{href}" target="_blank" rel="noopener">{t}</a>')
        else:
            parts.append(t)
    return "".join(parts)

def _image_block_to_html(block: dict) -> str:
    try:
        img = block.get("image") or {}
        t = img.get("type")
        if t == "external":
            url = (img.get("external") or {}).get("url")
        else:
            url = (img.get("file") or {}).get("url")
        cap = _rt_to_html((img.get("caption") or []))
        if url:
            b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
            src = f"/proxy_img?b={b64}"
            figcap = f"<figcaption>{cap}</figcaption>" if cap else ""
            return f"<figure><img src=\"{src}\" alt=\"{cap}\" loading=\"lazy\" decoding=\"async\"/>{figcap}</figure>"
    except Exception:
        pass
    return ""

def _blocks_to_html(blocks: list) -> str:
    html = []
    for b in blocks or []:
        t = b.get("type")
        data = b.get(t) or {}
        if t in ("heading_1", "heading_2", "heading_3"):
            tag = {"heading_1": "h1", "heading_2": "h2", "heading_3": "h3"}[t]
            html.append(f"<{tag}>" + _rt_to_html(data.get("rich_text") or []) + f"</{tag}>")
        elif t == "paragraph":
            txt = _rt_to_html(data.get("rich_text") or [])
            if txt.strip():
                html.append(f"<p>{txt}</p>")
        elif t == "bulleted_list_item":
            html.append("<ul><li>" + _rt_to_html(data.get("rich_text") or []) + "</li></ul>")
        elif t == "numbered_list_item":
            html.append("<ol><li>" + _rt_to_html(data.get("rich_text") or []) + "</li></ol>")
        elif t == "quote":
            html.append("<blockquote>" + _rt_to_html(data.get("rich_text") or []) + "</blockquote>")
        elif t == "to_do":
            checked = "checked" if data.get("checked") else ""
            html.append(f"<label class=\"todo\"><input type=\"checkbox\" disabled {checked}/> " + _rt_to_html(data.get("rich_text") or []) + "</label>")
        elif t == "divider":
            html.append("<hr/>")
        elif t == "image":
            html.append(_image_block_to_html(b))
        # unsupported types are skipped silently
    return "\n".join(html)

@app.route('/post_json/<page_id>')
def post_json(page_id: str):
    """Return full post content (rendered HTML) as JSON for modal view."""
    if not NOTION_API_KEY:
        return jsonify(ok=False, error="Missing NOTION_API_KEY"), 400
    try:
        notion = Client(auth=NOTION_API_KEY)

        # 1) Page meta (title/date)
        page = notion.pages.retrieve(page_id=page_id)
        props = page.get("properties", {})
        title_parts = (props.get("Name", {}) or {}).get("title", [])
        title = _rt_to_html(title_parts) or "Без назви"
        date = ((props.get("Date", {}) or {}).get("date") or {}).get("start")

        # Extract external URL (URL/Url/Link/Посилання)
        ext_url = None
        for k in ("URL", "Url", "Link", "Посилання"):
            p = props.get(k)
            if isinstance(p, dict):
                ext_url = p.get("url") or ext_url
                if not ext_url:
                    rts = p.get("rich_text") or []
                    if rts:
                        ext_url = "".join(t.get("plain_text", "") for t in rts).strip() or None
            if ext_url:
                break

        # 2) Blocks (paginate, up to a few pages)
        blocks = []
        cursor = None
        for _ in range(10):  # hard limit to avoid endless loops
            resp = notion.blocks.children.list(block_id=page_id, start_cursor=cursor)
            blocks.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        html = _blocks_to_html(blocks)
        # Fallback: якщо блоки нічого не дали, підтягуємо текст із властивостей
        if not (html or "").strip():
            text_rt = (props.get("Text") or {}).get("rich_text") or []
            excerpt_rt = (props.get("Excerpt") or {}).get("rich_text") or []
            body_inline = _rt_to_html(text_rt) or _rt_to_html(excerpt_rt)
            if body_inline:
                html = f"<p>{body_inline}</p>"
        # Prepend cover image if present (page cover or first file in Files & media)
        cover_url = None
        # Prefer page cover
        cover_obj = page.get("cover") or {}
        if cover_obj:
            if cover_obj.get("type") == "external":
                cover_url = (cover_obj.get("external") or {}).get("url")
            elif cover_obj.get("type") == "file":
                cover_url = (cover_obj.get("file") or {}).get("url")
        # Fallback to first file in Files & media / Dateien und Medien / Files property
        if not cover_url:
            props_files = (
                props.get("Files & media")
                or props.get("Dateien und Medien")
                or props.get("Files")
                or {}
            )
            if props_files.get("type") == "files":
                flist = props_files.get("files", [])
                if flist:
                    f0 = flist[0]
                    if f0.get("type") == "external":
                        cover_url = (f0.get("external") or {}).get("url")
                    elif f0.get("type") == "file":
                        cover_url = (f0.get("file") or {}).get("url")

        if isinstance(cover_url, str) and cover_url.strip():
            b64 = base64.urlsafe_b64encode(cover_url.encode("utf-8")).decode("utf-8").rstrip("=")
            cover_html = (
                f'<figure class="cover"><img src="/proxy_img?b={b64}" alt="{title}" '
                f'loading="lazy" decoding="async"/></figure>'
            )
            html = cover_html + (html or "")

        # If there is an external URL, render a link block near the top
        if ext_url:
            link_html = f'<p class="ext-link"><a href="{ext_url}" target="_blank" rel="noopener">🔗 Відкрити посилання</a></p>'
            html = (html or "")
            # Place the link just after cover (if present) or at the top otherwise
            if 'cover' in locals() or cover_url:
                html = link_html + html
            else:
                html = link_html + html

        return jsonify(ok=True, title=title, date=date, html=html, ext_url=ext_url)

    except Exception as e:
        app.logger.error("[post_json] failed: %r", e)
        return jsonify(ok=False, error=str(e)), 502

# --- Release page -> modal HTML (cover left + links right) -------------------
@app.route('/release_json/<page_id>')
def release_json(page_id: str):
    """Return a compact HTML snippet for a music release page in Notion.

    The HTML is a two-column layout:
      - left: cover image (fixed width ~320px, responsive)
      - right: title and a vertical list of platform buttons.

    It reads the same properties as fetch_stream_releases()
    (Spotify, Apple Music, YouTube Music, YouTube, Deezer, SoundCloud, Bandcamp).
    """
    if not NOTION_API_KEY:
        return jsonify(ok=False, error="Missing NOTION_API_KEY"), 400

    try:
        notion = Client(auth=NOTION_API_KEY)

        # Fetch page meta
        page = notion.pages.retrieve(page_id=page_id)
        props = page.get("properties", {})

        # Title (support Name/Title)
        title_prop = props.get("Name") or props.get("Title") or {}
        title_parts = title_prop.get("title", []) if isinstance(title_prop, dict) else []
        title = "".join(part.get("plain_text", "") for part in title_parts) or "Без назви"

        # Cover: prefer Cover / Cover Art / Files & media, else page cover
        cover_url = None
        files_prop = (
            props.get("Cover")
            or props.get("Cover Art")
            or props.get("Files & media")
            or props.get("Dateien und Medien")
            or props.get("Files")
            or {}
        )
        if isinstance(files_prop, dict) and files_prop.get("type") == "files":
            flist = files_prop.get("files", [])
            if flist:
                f = flist[0]
                if f.get("type") == "external":
                    cover_url = (f.get("external") or {}).get("url")
                elif f.get("type") == "file":
                    cover_url = (f.get("file") or {}).get("url")
        if not cover_url:
            cover_obj = page.get("cover") or {}
            if cover_obj.get("type") == "external":
                cover_url = (cover_obj.get("external") or {}).get("url")
            elif cover_obj.get("type") == "file":
                cover_url = (cover_obj.get("file") or {}).get("url")

        # Platforms (same tolerant variants as in fetch_stream_releases)
        def _prop_url(pdict, key):
            p = (pdict or {}).get(key) or {}
            if isinstance(p, dict):
                url = p.get("url")
                if url:
                    return url
                rts = p.get("rich_text") or []
                if rts:
                    return "".join(t.get("plain_text", "") for t in rts).strip() or None
            return None

        platforms_spec = [
            ("spotify",      "Spotify"),
            ("apple",        "Apple Music"),
            ("youtubemusic", "YouTube Music"),
            ("deezer",       "Deezer"),
            ("amazon",       "Amazon Music"),
            ("itunes",       "iTunes"),
            ("bandcamp",     "bandcamp"),
            ("soundcloud",   "SoundCloud"),
            ("youtube",      "YouTube"),
        ]
        links = []
        for key, label in platforms_spec:
            match_key = next((k for k in props.keys() if k.lower() == key.lower() or k.lower() == label.lower()), None)
            if match_key:
                url = _prop_url(props, match_key)
                if url:
                    links.append({"key": key, "label": label, "url": url, "icon": _favicon_from_url(url)})

        # Build HTML (cover left + links right)
        cover_html = ""
        if isinstance(cover_url, str) and cover_url.strip():
            b64 = base64.urlsafe_b64encode(cover_url.encode("utf-8")).decode("utf-8").rstrip("=")
            cover_html = (
                f'<div class="rm-cover">'
                f'  <img src="/proxy_img?b={b64}" alt="{title}" loading="lazy" decoding="async"/>'
                f'</div>'
            )

        links_html = []
        for l in links:
            esc_label = l["label"]
            esc_url = l["url"]
            links_html.append(
                f'<a class="btn btn-sm link-btn platform-{l["key"]}" href="{esc_url}" target="_blank" rel="noopener">{esc_label}</a>'
            )
        if not links_html:
            links_html.append('<div class="muted">Посилання відсутні.</div>')

        share_btn = (
            '<button type="button" class="rm-share" data-share aria-label="Поділитися">'
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M12 3l4 4m-4-4l-4 4m4-4v11" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M5 10v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-9" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
            '<span class="rm-share-label" aria-live="polite">Скопійовано</span>'
            '</button>'
        )

        html = (
            '<div class="release-modal">'
            '  <div class="rm-grid">'
            f'    {cover_html}'
            '    <div class="rm-links-list">'
            f'      {"".join(links_html)}'
            '    </div>'
            f'    <div class="rm-title-under">{title}</div>'
            f'    {share_btn}'
            '  </div>'
            '</div>'
        )
        return jsonify(ok=True, title=title, html=html, links=links)

    except Exception as e:
        app.logger.error("[release_json] failed: %r", e)
        return jsonify(ok=False, error=str(e)), 502

def _client_cache_key():
    # best-effort client id (supports proxies)
    ip = (request.headers.get('X-Forwarded-For') or request.remote_addr or '0.0.0.0').split(',')[0].strip()
    terms_key = ",".join(get_terms())
    return f"{ip}|{terms_key}"

# 🏠 Головна сторінка — UmkA на музичних майданчиках
@app.route('/')
def index():
    need_streams_keys = not (NOTION_API_KEY and NOTION_STREAMS_DATABASE_ID)
    releases = fetch_stream_releases() if not need_streams_keys else []
    return render_template(
        'index.html',
        title='UmkA тут',
        releases=releases,
        need_streams_keys=need_streams_keys,
    )

# 🎤 Вкладка — UmkA на PANAMABATTLE
@app.route('/panamabattle')
def panamabattle():
    # Per-user cache (30 min default) — bypass with ?refresh=1
    use_refresh = request.args.get('refresh') == '1'
    key = _client_cache_key()
    now = time.time()
    _prune_yt_cache()

    videos = None
    if not use_refresh:
        cached = YT_CACHE.get(key)
        if cached and (now - cached['ts'] < YT_TTL_SEC):
            videos = cached['data']

    if videos is None:
        videos = fetch_panamabattle_videos()
        YT_CACHE[key] = {'ts': now, 'data': videos}

    return render_template(
        'panamabattle.html',
        title='UmkA — на PANAMABATTLE',
        videos=videos,
        need_api_key=False,
    )

@app.route('/proxy_img')
def proxy_img():
    """Проксі для зображень із Notion: конвертує HEIC/HEIF або application/octet-stream у JPEG.
    Робить додаткові захисні перевірки:
      - перевіряє Content-Length і блокує великі файли
      - стрімить завантаження та відсікає якщо перевищено ліміт (без алокації всієї пам'яті)
      - перевіряє Content-Type (припускає image/* або octet-stream)
      - захищає від DecompressionBombError при відкритті через Pillow
    Параметри конфігурації через оточення:
      - UMKA_PROXY_MAX_BYTES (int) — макс байт для завантаження (за замовчуванням 5_000_000)
      - UMKA_MAX_IMAGE_PIXELS    (int) — max pixels для Pillow (додано вище)
    """
    # Config
    MAX_BYTES = int(os.environ.get("UMKA_PROXY_MAX_BYTES", "5000000"))  # default 5 MB

    # 1) Читаємо URL
    raw_b = request.args.get('b')
    if raw_b:
        try:
            pad = (-len(raw_b)) % 4
            raw_b_padded = raw_b + ("=" * pad)
            url = base64.urlsafe_b64decode(raw_b_padded.encode('utf-8')).decode('utf-8').strip()
        except Exception:
            return Response('bad base64', status=400)
    else:
        url = request.args.get('u', '').strip()
        url = unquote_plus(unquote(url))

    if not url:
        app.logger.warning('[proxy_img] missing url param')
        return Response('missing url', status=400)
    # Minimal SSRF guard: block private/loopback/link-local IPs
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return Response('bad url scheme', status=400)
        host = parsed.hostname
        if not host:
            return Response('bad url host', status=400)
        try:
            ip = ipaddress.ip_address(host)
            ips = [ip]
        except ValueError:
            infos = socket.getaddrinfo(host, None)
            ips = []
            for info in infos:
                try:
                    ips.append(ipaddress.ip_address(info[4][0]))
                except ValueError:
                    continue
        for ip in ips:
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
                app.logger.warning('[proxy_img] blocked private ip: %s', ip)
                return Response('blocked host', status=403)
    except Exception:
        return Response('bad url', status=400)

    # Simple rate-limit per client IP
    client_ip = (request.headers.get('X-Forwarded-For') or request.remote_addr or '0.0.0.0').split(',')[0].strip()
    if _rate_limited(client_ip):
        app.logger.warning("[proxy_img] rate-limited ip=%s", client_ip)
        return Response("rate limited", status=429)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
            'Accept': '*/*',
        }
        # Stream the response and impose size checks
        r = requests.get(url, timeout=(5, 15), headers=headers, allow_redirects=True, stream=True)
        app.logger.info('[proxy_img] upstream %s -> %s', url.split('?')[0], r.status_code)

        if r.status_code != 200:
            blank = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
            return Response(blank, headers={'Content-Type': 'image/gif'})

        content_type = (r.headers.get('Content-Type') or '').lower()
        # If upstream provides Content-Length, reject too-large files early
        try:
            cl = int(r.headers.get('Content-Length')) if r.headers.get('Content-Length') else None
        except Exception:
            cl = None
        if cl and cl > MAX_BYTES:
            app.logger.warning('[proxy_img] upstream content-length too large: %s', cl)
            return Response('too large', status=413)

        # Acceptable types: image/* or application/octet-stream (we'll try to convert)
        allowed_ct = ("image/", "application/octet-stream")
        if content_type and not (content_type.startswith(allowed_ct[0]) or content_type.startswith(allowed_ct[1])):
            app.logger.warning('[proxy_img] unacceptable content-type: %s', content_type)
            return Response('unsupported media type', status=415)

        # Stream and accumulate up to MAX_BYTES
        raw_chunks = io.BytesIO()
        total = 0
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                total += len(chunk)
                if total > MAX_BYTES:
                    app.logger.warning('[proxy_img] download exceeded max bytes (%s)', total)
                    return Response('too large', status=413)
                raw_chunks.write(chunk)
        raw = raw_chunks.getvalue()

        # Helper: convert any bytes to JPEG and send as response with bomb protection
        def _as_jpeg(img_bytes: bytes) -> Response:
            try:
                im = Image.open(io.BytesIO(img_bytes))
                # convert and send
                out = io.BytesIO()
                im.convert('RGB').save(out, format='JPEG', quality=88)
                out.seek(0)
                resp = send_file(out, mimetype='image/jpeg')
                resp.headers['Cache-Control'] = 'public, max-age=86400'
                return resp
            except Exception as e:
                # If Pillow raises DecompressionBombError or other parsing errors, log and fallback
                app.logger.warning('[proxy_img] _as_jpeg failed: %r', e)
                blank = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
                return Response(blank, headers={'Content-Type': 'image/gif'})

        # HEIC/HEIF -> JPEG check based on content-type or extension
        if ('heic' in content_type) or ('heif' in content_type) or url.lower().endswith(('.heic', '.heif')):
            return _as_jpeg(raw)

        # If it's image/* return raw bytes with same Content-Type
        if content_type.startswith('image/') and raw:
            resp = Response(raw, headers={
                'Content-Type': content_type,
                'Cache-Control': 'public, max-age=86400',
            })
            return resp

        # Otherwise try to open and convert
        try:
            if raw:
                return _as_jpeg(raw)
        except Exception as e:
            app.logger.warning('[proxy_img] fallback-to-jpeg failed: %r', e)

        blank = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
        return Response(blank, headers={'Content-Type': 'image/gif'})

    except Exception as e:
        app.logger.error('[proxy_img] exception: %r', e)
        blank = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
        return Response(blank, headers={'Content-Type': 'image/gif'})

# 🧠 Вкладка — UmkA каже (блог / нотатки)
@app.route('/blog')
def blog():
    need_notion_keys = not (NOTION_API_KEY and NOTION_DATABASE_ID)
    posts = fetch_notion_posts() if not need_notion_keys else []
    return render_template('blog.html', title='UmkA каже', posts=posts, need_notion_keys=need_notion_keys)


# --- healthcheck, robots.txt, security.txt endpoints ---
@app.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200

@app.route("/robots.txt")
def robots_txt():
    body = "User-agent: *\nAllow: /\n"
    return Response(body, mimetype="text/plain")

@app.route("/.well-known/security.txt")
def security_txt():
    contact = os.environ.get("UMKA_SECURITY_CONTACT", "mailto:admin@umka.space")
    body = (
        f"Contact: {contact}\n"
        "Preferred-Languages: uk, en\n"
        "Policy: https://umka.space/\n"
    )
    return Response(body, mimetype="text/plain")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
