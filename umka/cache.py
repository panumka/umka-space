"""In-memory кеші: відповіді Notion і готовий HTML сторінок."""
import time

from .config import NOTION_TTL_SEC, PAGE_TTL_SEC

_NOTION_CACHE = {}  # key -> {"ts": epoch, "data": payload}
_PAGE_CACHE = {}  # key -> {"ts": epoch, "html": str}


def get_notion(key: str):
    item = _NOTION_CACHE.get(key)
    if not item:
        return None
    if time.time() - item.get("ts", 0) > NOTION_TTL_SEC:
        _NOTION_CACHE.pop(key, None)
        return None
    return item.get("data")


def set_notion(key: str, data):
    _NOTION_CACHE[key] = {"ts": time.time(), "data": data}


def get_page_html(key: str) -> str | None:
    item = _PAGE_CACHE.get(key)
    if not item:
        return None
    if time.time() - item.get("ts", 0) > PAGE_TTL_SEC:
        _PAGE_CACHE.pop(key, None)
        return None
    return item.get("html")


def set_page_html(key: str, html: str) -> None:
    if not html:
        return
    _PAGE_CACHE[key] = {"ts": time.time(), "html": html}
