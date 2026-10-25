"""/proxy_img: проксі для зображень із Notion з захистом від SSRF, бомб і флуду."""
import base64
import io
import ipaddress
import socket
import time
from urllib.parse import unquote, unquote_plus, urlparse

import pillow_heif
from flask import Response, current_app, request, send_file
from PIL import Image, ImageOps

from .config import (
    MAX_IMAGE_PIXELS,
    PROXY_BUCKETS_MAX,
    PROXY_LIMIT_COUNT,
    PROXY_LIMIT_WINDOW,
    PROXY_MAX_BYTES,
)
from .net import BROWSER_UA, REQ

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
pillow_heif.register_heif_opener()

# 1×1 transparent GIF returned whenever we can't (or won't) serve the image
_BLANK_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
_CACHE_HEADER = "public, max-age=604800"

_PROXY_BUCKETS = {}  # ip -> {"ts": epoch, "count": n}


def _blank() -> Response:
    return Response(_BLANK_GIF, headers={"Content-Type": "image/gif"})


def client_ip() -> str:
    # best-effort client id (supports proxies)
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "0.0.0.0").split(",")[0].strip()


def _prune_buckets():
    if not _PROXY_BUCKETS:
        return
    now = time.time()
    expired = [ip for ip, b in _PROXY_BUCKETS.items() if now - b.get("ts", 0) > PROXY_LIMIT_WINDOW]
    for ip in expired:
        _PROXY_BUCKETS.pop(ip, None)
    if len(_PROXY_BUCKETS) > PROXY_BUCKETS_MAX:
        items = sorted(_PROXY_BUCKETS.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
        _PROXY_BUCKETS.clear()
        for ip, b in items[:PROXY_BUCKETS_MAX]:
            _PROXY_BUCKETS[ip] = b


def _rate_limited(ip: str) -> bool:
    _prune_buckets()
    now = time.time()
    b = _PROXY_BUCKETS.get(ip)
    if not b or now - b["ts"] > PROXY_LIMIT_WINDOW:
        _PROXY_BUCKETS[ip] = {"ts": now, "count": 1}
        return False
    b["count"] += 1
    return b["count"] > PROXY_LIMIT_COUNT


def _is_public_url(url: str) -> bool:
    """Minimal SSRF guard: only http(s) hosts that don't resolve to private/loopback/link-local IPs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        try:
            ips = [ipaddress.ip_address(host)]
        except ValueError:
            ips = []
            for info in socket.getaddrinfo(host, None):
                try:
                    ips.append(ipaddress.ip_address(info[4][0]))
                except ValueError:
                    continue
        for ip in ips:
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
                current_app.logger.warning("[proxy_img] blocked private ip: %s", ip)
                return False
        return True
    except Exception:
        return False


def _as_int(val: str | None, default: int, lo: int, hi: int) -> int:
    try:
        n = int(val) if val is not None else default
    except Exception:
        n = default
    return max(lo, min(hi, n))


def _encode_transformed(img_bytes: bytes, target_w: int, quality: int, fmt: str) -> Response | None:
    """Optional resize / re-encode for list views (?w=, ?q=, ?fmt=)."""
    if target_w <= 0 and not fmt:
        return None
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im = ImageOps.exif_transpose(im)
        if target_w > 0 and im.width > target_w:
            ratio = target_w / float(im.width)
            target_h = max(1, int(im.height * ratio))
            im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)

        out = io.BytesIO()
        out_fmt = "WEBP" if fmt == "webp" else "JPEG"
        save_kwargs = {"quality": quality, "optimize": True}
        if out_fmt == "WEBP":
            save_kwargs["method"] = 6
        else:
            if im.mode in ("RGBA", "LA", "P"):
                if im.mode == "P":
                    im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (0, 0, 0))
                alpha = im.split()[-1] if im.mode in ("RGBA", "LA") else None
                bg.paste(im, mask=alpha)
                im = bg
            else:
                im = im.convert("RGB")
        im.save(out, format=out_fmt, **save_kwargs)
        out.seek(0)
        resp = send_file(out, mimetype="image/webp" if out_fmt == "WEBP" else "image/jpeg")
        resp.headers["Cache-Control"] = _CACHE_HEADER
        return resp
    except Exception as e:
        current_app.logger.warning("[proxy_img] transform failed: %r", e)
        return None


def _as_jpeg(img_bytes: bytes) -> Response:
    """Convert any bytes to JPEG (Pillow bomb protection applies)."""
    try:
        im = Image.open(io.BytesIO(img_bytes))
        out = io.BytesIO()
        im.convert("RGB").save(out, format="JPEG", quality=88)
        out.seek(0)
        resp = send_file(out, mimetype="image/jpeg")
        resp.headers["Cache-Control"] = _CACHE_HEADER
        return resp
    except Exception as e:
        current_app.logger.warning("[proxy_img] _as_jpeg failed: %r", e)
        return _blank()


def proxy_img():
    """Проксі для зображень із Notion: конвертує HEIC/HEIF або application/octet-stream у JPEG.
    Робить додаткові захисні перевірки:
      - перевіряє Content-Length і блокує великі файли
      - стрімить завантаження та відсікає якщо перевищено ліміт (без алокації всієї пам'яті)
      - перевіряє Content-Type (припускає image/* або octet-stream)
      - захищає від DecompressionBombError при відкритті через Pillow
    Параметри конфігурації через оточення:
      - UMKA_PROXY_MAX_BYTES (int) — макс байт для завантаження (за замовчуванням 5_000_000)
      - UMKA_MAX_IMAGE_PIXELS    (int) — max pixels для Pillow
    """
    log = current_app.logger
    target_w = _as_int(request.args.get("w"), 0, 0, 2048)
    quality = _as_int(request.args.get("q"), 82, 40, 95)
    fmt = (request.args.get("fmt") or "").strip().lower()
    if fmt not in ("", "jpeg", "jpg", "webp"):
        fmt = ""

    # 1) Читаємо URL
    raw_b = request.args.get("b")
    if raw_b:
        try:
            pad = (-len(raw_b)) % 4
            url = base64.urlsafe_b64decode((raw_b + "=" * pad).encode("utf-8")).decode("utf-8").strip()
        except Exception:
            return Response("bad base64", status=400)
    else:
        url = unquote_plus(unquote(request.args.get("u", "").strip()))

    if not url:
        log.warning("[proxy_img] missing url param")
        return _blank()
    if not _is_public_url(url):
        return _blank()

    # Simple rate-limit per client IP
    ip = client_ip()
    if _rate_limited(ip):
        log.warning("[proxy_img] rate-limited ip=%s", ip)
        return _blank()

    try:
        # Stream the response and impose size checks
        r = REQ.get(url, timeout=(5, 15), headers={"User-Agent": BROWSER_UA, "Accept": "*/*"},
                    allow_redirects=True, stream=True)
        log.info("[proxy_img] upstream %s -> %s", url.split("?")[0], r.status_code)
        if r.status_code != 200:
            return _blank()

        content_type = (r.headers.get("Content-Type") or "").lower()
        # If upstream provides Content-Length, reject too-large files early
        try:
            cl = int(r.headers.get("Content-Length")) if r.headers.get("Content-Length") else None
        except Exception:
            cl = None
        if cl and cl > PROXY_MAX_BYTES:
            log.warning("[proxy_img] upstream content-length too large: %s", cl)
            return Response("too large", status=413)

        # Acceptable types: image/* or application/octet-stream (we'll try to convert)
        if content_type and not content_type.startswith(("image/", "application/octet-stream")):
            log.warning("[proxy_img] unacceptable content-type: %s", content_type)
            return Response("unsupported media type", status=415)

        # Stream and accumulate up to PROXY_MAX_BYTES
        buf = io.BytesIO()
        total = 0
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                total += len(chunk)
                if total > PROXY_MAX_BYTES:
                    log.warning("[proxy_img] download exceeded max bytes (%s)", total)
                    return Response("too large", status=413)
                buf.write(chunk)
        raw = buf.getvalue()

        transformed = _encode_transformed(raw, target_w, quality, fmt)
        if transformed is not None:
            return transformed

        # HEIC/HEIF -> JPEG check based on content-type or extension
        if ("heic" in content_type) or ("heif" in content_type) or url.lower().endswith((".heic", ".heif")):
            return _as_jpeg(raw)

        # If it's image/* return raw bytes with same Content-Type
        if content_type.startswith("image/") and raw:
            return Response(raw, headers={"Content-Type": content_type, "Cache-Control": _CACHE_HEADER})

        # Otherwise try to open and convert
        if raw:
            return _as_jpeg(raw)
        return _blank()

    except Exception as e:
        log.error("[proxy_img] exception: %r", e)
        return _blank()
