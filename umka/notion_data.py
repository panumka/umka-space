"""Дані з Notion: релізи (майданчики), пости блогу, рендер блоків у HTML."""
import os

from notion_client import Client

from . import cache
from .config import NOTION_API_KEY, NOTION_DATABASE_ID, NOTION_STREAMS_DATABASE_ID
from .net import favicon_from_url, get_og_image, proxy_img_src

# Порядок кнопок майданчиків у модалці релізу: (key, label у Notion)
PLATFORMS = [
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

# Tolerant variants for the external-link property name
_LINK_PROPS = ("URL", "Url", "Link", "Посилання")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic", ".heif")


def client() -> Client:
    return Client(auth=NOTION_API_KEY)


# --- property helpers ---------------------------------------------------------

def _plain(rts: list) -> str:
    return "".join(t.get("plain_text", "") for t in rts or [])


def _title(props: dict, keys=("Name", "Title")) -> str:
    for k in keys:
        p = props.get(k)
        if p:
            return _plain(p.get("title", []) if isinstance(p, dict) else []) or "Без назви"
    return "Без назви"


def _date(props: dict) -> str | None:
    return ((props.get("Date", {}) or {}).get("date") or {}).get("start")


def _file_url(f: dict) -> str | None:
    """URL з файлу Notion або з обкладинки сторінки (external / file)."""
    if f.get("type") == "external":
        return (f.get("external") or {}).get("url")
    if f.get("type") == "file":
        return (f.get("file") or {}).get("url")
    return None


def _first_file_url(prop) -> str | None:
    if isinstance(prop, dict) and prop.get("type") == "files":
        flist = prop.get("files", [])
        if flist:
            return _file_url(flist[0])
    return None


def _page_cover(page: dict) -> str | None:
    return _file_url(page.get("cover") or {})


def _prop_url(props: dict, key: str) -> str | None:
    p = (props or {}).get(key) or {}
    if isinstance(p, dict):
        # native URL property
        url = p.get("url")
        if url:
            return url
        # fallback: text property named like the platform
        rts = p.get("rich_text") or []
        if rts:
            return _plain(rts).strip() or None
    return None


def _ext_url(props: dict) -> str | None:
    for k in _LINK_PROPS:
        url = _prop_url(props, k)
        if url:
            return url
    return None


def _platform_links(props: dict) -> list:
    links = []
    # Case-insensitive match for platform keys/labels in property names
    for key, label in PLATFORMS:
        match_key = next((k for k in props.keys() if k.lower() == key.lower() or k.lower() == label.lower()), None)
        if match_key:
            url = _prop_url(props, match_key)
            if url:
                links.append({"key": key, "label": label, "url": url, "icon": favicon_from_url(url)})
    return links


def extract_release_cover(props: dict, page: dict) -> str | None:
    """Cover: prefer Cover / Cover Art / Files & media, else page cover."""
    files_prop = (
        props.get("Cover")
        or props.get("Cover Art")
        or props.get("Files & media")
        or props.get("Dateien und Medien")
        or props.get("Files")
        or {}
    )
    return _first_file_url(files_prop) or _page_cover(page)


def release_title(page: dict) -> str:
    return _title(page.get("properties", {}))


# --- releases -----------------------------------------------------------------

def fetch_stream_releases(limit: int = 24):
    """Return a list of music releases from a Notion database where each page
    can contain URLs for different platforms (Spotify, Apple Music, etc.).

    Expected properties (optional, read if present):
      - Name (title) — release title
      - Date (date) — release date (optional)
      - Cover (files) — preferred; falls back to page cover
      - Spotify / Apple Music / YouTube Music / YouTube / Deezer / SoundCloud / Bandcamp (url)
    """
    if not (NOTION_API_KEY and NOTION_STREAMS_DATABASE_ID):
        return []

    cache_key = f"streams:{NOTION_STREAMS_DATABASE_ID}:{limit}"
    cached = cache.get_notion(cache_key)
    if cached is not None:
        return cached

    try:
        resp = client().databases.query(
            database_id=NOTION_STREAMS_DATABASE_ID,
            page_size=limit,
        )
    except Exception as e:
        print("[Notion] streams query failed:", e)
        return []

    items = []
    for r in resp.get("results", []):
        props = r.get("properties", {})
        date = _date(props)
        items.append({
            "id": r.get("id"),
            "title": _title(props),
            "date": date,
            "cover": extract_release_cover(props, r),
            "links": _platform_links(props),
            "_sort": date or r.get("created_time") or "",
        })

    # Newest first: by Date if set, otherwise by when the Notion row was created
    items.sort(key=lambda it: it.pop("_sort"), reverse=True)
    cache.set_notion(cache_key, items)
    return items


_SHARE_BTN = (
    '<button type="button" class="rm-share" data-share aria-label="Поділитися">'
    '<svg viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M12 3l4 4m-4-4l-4 4m4-4v11" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M5 10v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-9" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
    '<span class="rm-share-label" aria-live="polite">Скопійовано</span>'
    '</button>'
)


def release_modal(page_id: str) -> dict:
    """Compact HTML snippet for a music release page: cover + platform buttons.
    Raises on Notion errors; result is cached."""
    cache_key = f"release_json:{page_id}"
    cached = cache.get_notion(cache_key)
    if cached is not None:
        return cached

    page = client().pages.retrieve(page_id=page_id)
    props = page.get("properties", {})
    title = _title(props)
    cover_url = extract_release_cover(props, page)
    links = _platform_links(props)

    cover_html = ""
    if isinstance(cover_url, str) and cover_url.strip():
        cover_html = (
            f'<div class="rm-cover">'
            f'  <img src="{proxy_img_src(cover_url)}" alt="{title}" loading="lazy" decoding="async"/>'
            f'</div>'
        )

    links_html = [
        f'<a class="btn btn-sm link-btn platform-{l["key"]}" href="{l["url"]}" target="_blank" rel="noopener">{l["label"]}</a>'
        for l in links
    ]
    if not links_html:
        links_html.append('<div class="muted">Посилання відсутні.</div>')

    html = (
        '<div class="release-modal">'
        '  <div class="rm-grid">'
        f'    {cover_html}'
        '    <div class="rm-links-list">'
        f'      {"".join(links_html)}'
        '    </div>'
        f'    <div class="rm-title-under">{title}</div>'
        f'    {_SHARE_BTN}'
        '  </div>'
        '</div>'
    )
    payload = {"ok": True, "title": title, "html": html, "links": links}
    cache.set_notion(cache_key, payload)
    return payload


# --- blog ---------------------------------------------------------------------

def _post_thumb(props: dict, page: dict) -> str | None:
    # Thumb: prefer Files & media (files), fallback to page cover
    thumb = None
    candidate = _first_file_url(
        props.get("Files & media")
        or props.get("Dateien und Medien")
        or props.get("Files")
        or {}
    )
    # If candidate looks like a direct image, use it; otherwise try to extract og:image
    if candidate:
        if candidate.lower().endswith(_IMAGE_EXTS):
            thumb = candidate
        else:
            thumb = get_og_image(candidate) or candidate
    if not thumb:
        thumb = _page_cover(page)
    # If still no thumb, try to fetch og:image from a URL property (e.g., a YouTube link)
    if not thumb:
        url_prop = _ext_url(props)
        if url_prop:
            thumb = get_og_image(url_prop)
    return thumb


def fetch_notion_posts(limit: int | None = None, refresh: bool = False):
    """Return a list of posts from a Notion database (no 'Published' required).
    Expects (recommended) properties:
      - Name (title)
      - Date (date) — optional
      - Excerpt (rich_text) — optional
      - Text (rich_text) — optional (used as fallback excerpt)
      - Files & media (files) — optional (first file used as thumb)
    """
    fetch_all = False
    if limit is None:
        try:
            limit = int(os.environ.get("UMKA_BLOG_LIMIT", "50"))
        except Exception:
            limit = 50

    # If limit <= 0, fetch all pages (paginated). Keep a hard safety cap.
    if int(limit) <= 0:
        fetch_all = True
        # Notion API max page_size is 100
        page_size = 100
        try:
            max_scan = int(os.environ.get("UMKA_BLOG_MAX_SCAN", "500"))
        except Exception:
            max_scan = 500
        max_scan = max(1, int(max_scan))
    else:
        page_size = max(1, min(int(limit), 100))
        max_scan = page_size
    if not (NOTION_API_KEY and NOTION_DATABASE_ID):
        return []

    cache_key = f"posts:{NOTION_DATABASE_ID}:{'all' if fetch_all else page_size}"
    if not refresh:
        cached = cache.get_notion(cache_key)
        if cached is not None:
            return cached

    try:
        notion = client()
        # No server-side filter: keep it robust if properties are missing
        results = []
        cursor = None
        while True:
            resp = notion.databases.query(
                database_id=NOTION_DATABASE_ID,
                page_size=page_size,
                start_cursor=cursor,
                sorts=[{"timestamp": "created_time", "direction": "descending"}],
            )
            results.extend(resp.get("results", []) or [])

            # Stop conditions
            if not fetch_all:
                break
            if len(results) >= max_scan:
                results = results[:max_scan]
                break
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print("[Notion] query failed:", e)
        return []

    posts = []
    for r in results:
        props = r.get("properties", {})

        # Excerpt (optional) or fallback to Text
        excerpt = _plain(props.get("Excerpt", {}).get("rich_text", []))
        if not excerpt:
            excerpt = _plain(props.get("Text", {}).get("rich_text", []))[:240]

        slug_parts = props.get("Slug", {}).get("rich_text", [])

        # If no Date provided, fall back strictly to page creation time
        date_iso = _date(props)
        date_display = date_iso
        if not date_iso:
            date_iso = (r.get("created_time") or "").strip() or None
            if date_iso:
                date_display = date_iso[:10]

        posts.append({
            "id": r.get("id"),
            "title": _title(props, keys=("Name",)),
            "date": date_iso,
            "date_display": date_display,
            "slug": _plain(slug_parts) if slug_parts else None,
            "excerpt": excerpt,
            "url": r.get("url"),
            "thumb": _post_thumb(props, r),
            "ext_url": _ext_url(props),
        })

    posts.sort(key=lambda x: x.get("date") or "", reverse=True)
    cache.set_notion(cache_key, posts)
    return posts


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
        url = (img.get("external") or {}).get("url") if img.get("type") == "external" else (img.get("file") or {}).get("url")
        cap = _rt_to_html((img.get("caption") or []))
        if url:
            figcap = f"<figcaption>{cap}</figcaption>" if cap else ""
            return f"<figure><img src=\"{proxy_img_src(url)}\" alt=\"{cap}\" loading=\"lazy\" decoding=\"async\"/>{figcap}</figure>"
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


def post_detail(page_id: str) -> dict:
    """Full post content (rendered HTML) for the blog modal. Raises on Notion errors."""
    notion = client()

    # 1) Page meta (title/date)
    page = notion.pages.retrieve(page_id=page_id)
    props = page.get("properties", {})
    title = _rt_to_html((props.get("Name", {}) or {}).get("title", [])) or "Без назви"
    date = _date(props)
    ext_url = _ext_url(props)

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
        body_inline = _rt_to_html((props.get("Text") or {}).get("rich_text") or []) \
            or _rt_to_html((props.get("Excerpt") or {}).get("rich_text") or [])
        if body_inline:
            html = f"<p>{body_inline}</p>"

    # Prepend cover image: page cover, else first file in Files & media / Dateien und Medien / Files
    cover_url = _page_cover(page) or _first_file_url(
        props.get("Files & media")
        or props.get("Dateien und Medien")
        or props.get("Files")
        or {}
    )
    if isinstance(cover_url, str) and cover_url.strip():
        cover_html = (
            f'<figure class="cover"><img src="{proxy_img_src(cover_url)}" alt="{title}" '
            f'loading="lazy" decoding="async"/></figure>'
        )
        html = cover_html + (html or "")

    # If there is an external URL, render a link block at the top
    if ext_url:
        link_html = f'<p class="ext-link"><a href="{ext_url}" target="_blank" rel="noopener">🔗 Відкрити посилання</a></p>'
        html = link_html + (html or "")

    return {"ok": True, "title": title, "date": date, "html": html, "ext_url": ext_url}
