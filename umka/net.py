"""Спільна HTTP-сесія з повторами та дрібні хелпери для зовнішніх сторінок."""
import base64
import re
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


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


REQ = _requests_session()


def b64url(s: str) -> str:
    """URL-safe base64 без padding — формат параметра ?b= для /proxy_img."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8").rstrip("=")


def proxy_img_src(url: str) -> str:
    return f"/proxy_img?b={b64url(url)}"


# Helper: fetch og:image from a webpage (for use as a thumbnail)
def get_og_image(url: str) -> str | None:
    """Fetch the Open Graph image (og:image) for a given webpage URL.
    Returns direct image URL or None if not found/failed.
    Uses the shared retrying session and a short timeout.
    """
    if not url:
        return None
    try:
        r = REQ.get(url, headers={"User-Agent": BROWSER_UA}, timeout=5)
        if r.status_code != 200 or not (r.text or "").strip():
            return None
        html = r.text or ""
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            # Prefer og:image, but also try twitter:image as fallback
            for prop, attr in (("og:image", "property"), ("twitter:image", "name")):
                tag = soup.find("meta", {attr: prop})
                if tag and tag.get("content"):
                    return tag.get("content").strip()
        else:
            patterns = [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
            ]
            for p in patterns:
                m = re.search(p, html, flags=re.IGNORECASE)
                if m and m.group(1):
                    return m.group(1).strip()
    except Exception:
        pass
    return None


def favicon_from_url(url: str) -> str | None:
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
