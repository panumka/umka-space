"""YouTube: відео UmkA з каналу PANAMABATTLE і розбір посилань на відео."""
import os
import time
from urllib.parse import parse_qs, urlparse

from .config import YT_CACHE_MAX, YT_TTL_SEC
from .net import REQ

YT_CACHE = {}  # client key -> {"ts": epoch, "data": videos}


def get_terms():
    raw = os.environ.get("UMKA_SEARCH_TERMS", "").strip()
    if raw:
        return [t.strip().lower() for t in raw.split(",") if t.strip()]
    # default terms (case-insensitive substring check)
    return ["umka", "umk", "нішеві", "fremd", "запоріжстайл"]


def prune_cache():
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


def fetch_panamabattle_videos(max_results=50):
    """Fetch videos from PANAMABATTLE channel using YouTube Data API v3.
    Filters *titles only* for any of the terms from get_terms() (case-insensitive).
    Returns a list of dicts: id, title, published_at (YYYY-MM-DD), url, thumb.
    Uses the uploads playlist to scan older videos beyond the first 150 search results.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    channel_id = os.environ.get("PANAMABATTLE_CHANNEL_ID", "UC8zDVdKUnjs4E3FYGVIP0LQ").strip()

    # Fall back to empty if no prerequisites
    if not api_key or not channel_id:
        print("[YT API] missing API key or channel id")
        return []

    terms = [t.lower() for t in get_terms()]
    max_pages = int(os.environ.get("UMKA_YT_MAX_PAGES", "20"))
    max_scan = int(os.environ.get("UMKA_YT_MAX_SCAN", "1000"))

    # Resolve uploads playlist id (cheaper and more complete than search)
    uploads_id = None
    try:
        ch = REQ.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"key": api_key, "part": "contentDetails", "id": channel_id},
            timeout=10,
        )
        if ch.status_code == 200:
            items = (ch.json() or {}).get("items") or []
            if items:
                uploads_id = (((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
    except Exception as e:
        print("[YT API] channels failed:", e)

    if not uploads_id:
        print("[YT API] missing uploads playlist id")
        return []

    # Page through the uploads playlist (50 per page)
    page_token = None
    collected = {}
    fetched = 0
    pages_left = max_pages

    while pages_left > 0 and fetched < max_scan:  # hard ceiling guard
        params = {
            "key": api_key,
            "part": "snippet",
            "playlistId": uploads_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            r = REQ.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params, timeout=10)
            if r.status_code != 200:
                print("[YT API] status", r.status_code, "->", (r.text[:200] if r.text else ""))
                break
            data = r.json() or {}
        except Exception as e:
            print("[YT API] failed:", e)
            break

        for item in data.get("items", []):
            sn = item.get("snippet") or {}
            vid = (sn.get("resourceId") or {}).get("videoId") or ""
            title = sn.get("title") or ""

            # Title-only term check (any term)
            if not any(t in title.lower() for t in terms):
                continue

            if vid:
                collected[vid] = {
                    "id": vid,
                    "title": title,
                    "published_at": (sn.get("publishedAt") or "")[:10],
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


def youtube_id(url: str) -> str | None:
    """Extract an 11-char YouTube video id from common URL forms."""
    if not url:
        return None
    try:
        p = urlparse(url.strip())
    except Exception:
        return None
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = p.path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        parts = [s for s in p.path.split("/") if s]
        if parts and parts[0] in ("shorts", "embed", "live") and len(parts) > 1:
            vid = parts[1]
        else:
            vid = (parse_qs(p.query).get("v") or [None])[0]
    if vid and len(vid) == 11 and all(c.isalnum() or c in "-_" for c in vid):
        return vid
    return None
