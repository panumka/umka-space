"""Налаштування з оточення (.env у корені проєкту)."""
import os

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)

# Notion credentials (optional)
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()
# Notion DB for releases/links to streaming platforms (optional)
NOTION_STREAMS_DATABASE_ID = os.environ.get("NOTION_STREAMS_DATABASE_ID", "").strip()
NOTION_TTL_SEC = int(os.environ.get("UMKA_NOTION_TTL_SEC", "600"))
PAGE_TTL_SEC = int(os.environ.get("UMKA_PAGE_TTL_SEC", "45"))

# Simple per-user (IP) cache for YouTube results
YT_TTL_SEC = int(os.environ.get("UMKA_TTL_SEC", "1800"))  # default 30 minutes
YT_CACHE_MAX = int(os.environ.get("UMKA_YT_CACHE_MAX", "1000"))

# /proxy_img rate-limit (images can burst-load; keep defaults generous)
PROXY_LIMIT_COUNT = int(os.environ.get("UMKA_PROXY_LIMIT_COUNT", "300"))          # 300 hits
PROXY_LIMIT_WINDOW = int(os.environ.get("UMKA_PROXY_LIMIT_WINDOW_SEC", "300"))  # per 5 minutes
PROXY_BUCKETS_MAX = int(os.environ.get("UMKA_PROXY_BUCKETS_MAX", "2000"))
PROXY_MAX_BYTES = int(os.environ.get("UMKA_PROXY_MAX_BYTES", "5000000"))  # default 5 MB
# Safety: guard against decompression-bomb attacks in Pillow
MAX_IMAGE_PIXELS = int(os.environ.get("UMKA_MAX_IMAGE_PIXELS", "30000000"))  # default 30M px

STATIC_MAX_AGE = int(os.environ.get("UMKA_STATIC_MAX_AGE", "604800"))  # 7 days

# --- simple visit counter (cookie-based, persisted to a local file) ---
COUNTER_FILE = os.path.join(ROOT_DIR, ".counter.json")
COUNTER_COOKIE = "umka_counter"


def has_streams_keys() -> bool:
    return bool(NOTION_API_KEY and NOTION_STREAMS_DATABASE_ID)


def has_blog_keys() -> bool:
    return bool(NOTION_API_KEY and NOTION_DATABASE_ID)
