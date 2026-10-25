"""Маршрути сайту. Імена ендпоінтів (index, blog, ...) використовуються в url_for у шаблонах."""
import datetime as dt
import os
import time
from xml.sax.saxutils import escape as xml_escape

from flask import Response, current_app, jsonify, render_template, request, send_file, url_for

from . import cache, counter, notion_data, promo, youtube
from .config import COUNTER_COOKIE, NOTION_API_KEY, has_blog_keys, has_streams_keys
from .image_proxy import client_ip, proxy_img
from .net import b64url


def _public_base_url() -> str:
    env_base = os.environ.get("UMKA_SITE_URL", "").strip()
    if env_base.startswith(("http://", "https://")):
        return env_base.rstrip("/")
    return request.url_root.rstrip("/")


def _render_home(cache_key: str, **extra) -> Response:
    """Головна (і сторінка релізу, яка відкриває його модалку поверх головної)."""
    cached_html = cache.get_page_html(cache_key)
    if cached_html:
        return Response(cached_html, mimetype="text/html")

    need_streams_keys = not has_streams_keys()
    html = render_template(
        "index.html",
        title="UmkA.space",
        active="home",
        releases=notion_data.fetch_stream_releases() if not need_streams_keys else [],
        need_streams_keys=need_streams_keys,
        banners=promo.active_banners(),
        invite_video=promo.invite_video(),
        **extra,
    )
    cache.set_page_html(cache_key, html)
    return Response(html, mimetype="text/html")


# 🏠 Головна сторінка — UmkA на музичних майданчиках
def index():
    return _render_home(f"index:{request.host}", description="тут живе Пан UmkA")


# Shareable release URL with OG meta
def release_page(page_id: str):
    og = {
        "title": "UmkA",
        "image": url_for("static", filename="UmkA.png", _external=True),
        "url": request.url,
    }
    cache_key = f"release:{request.host}:{page_id}"
    if NOTION_API_KEY and cache.get_page_html(cache_key) is None:
        try:
            page = notion_data.client().pages.retrieve(page_id=page_id)
            props = page.get("properties", {})
            title = notion_data.release_title(page)
            og["title"] = og["title"] if title == "Без назви" else title
            cover_url = notion_data.extract_release_cover(props, page)
            if cover_url:
                og["image"] = url_for("proxy_img", b=b64url(cover_url), _external=True)
        except Exception as e:
            current_app.logger.warning("[release_page] og meta failed: %r", e)
    return _render_home(
        cache_key,
        description="Слухайте реліз UmkA на улюбленому музичному майданчику.",
        release_id=page_id,
        og=og,
    )


def release_json(page_id: str):
    """Compact HTML snippet for a release modal (cover left + links right)."""
    if not NOTION_API_KEY:
        return jsonify(ok=False, error="Missing NOTION_API_KEY"), 400
    try:
        return jsonify(notion_data.release_modal(page_id))
    except Exception as e:
        current_app.logger.error("[release_json] failed: %r", e)
        return jsonify(ok=False, error=str(e)), 502


def post_json(page_id: str):
    """Return full post content (rendered HTML) as JSON for modal view."""
    if not NOTION_API_KEY:
        return jsonify(ok=False, error="Missing NOTION_API_KEY"), 400
    try:
        return jsonify(notion_data.post_detail(page_id))
    except Exception as e:
        current_app.logger.error("[post_json] failed: %r", e)
        return jsonify(ok=False, error=str(e)), 502


# 🎤 Вкладка — UmkA на PANAMABATTLE
def panamabattle():
    # Per-user cache (30 min default) — bypass with ?refresh=1
    use_refresh = request.args.get("refresh") == "1"
    key = f"{client_ip()}|{','.join(youtube.get_terms())}"
    now = time.time()
    youtube.prune_cache()

    videos = None
    if not use_refresh:
        cached = youtube.YT_CACHE.get(key)
        if cached and (now - cached["ts"] < youtube.YT_TTL_SEC):
            videos = cached["data"]

    if videos is None:
        videos = youtube.fetch_panamabattle_videos()
        youtube.YT_CACHE[key] = {"ts": now, "data": videos}

    return render_template(
        "panamabattle.html",
        title="UmkA — на PANAMABATTLE",
        description="Виступи UmkA на PANAMABATTLE: добірка відео та посилань на YouTube.",
        active="panamabattle",
        videos=videos,
        need_api_key=False,
    )


# 🧠 Вкладка — UmkA каже (блог / нотатки)
def blog():
    need_notion_keys = not has_blog_keys()
    refresh = request.args.get("refresh") == "1"
    posts = notion_data.fetch_notion_posts(refresh=refresh) if not need_notion_keys else []
    return render_template(
        "blog.html",
        title="UmkA каже",
        description="Блог UmkA: новини, думки, посилання та матеріали з Notion.",
        active="blog",
        posts=posts,
        need_notion_keys=need_notion_keys,
    )


# --- healthcheck, counter, robots.txt, sitemap, security.txt ---

def healthz():
    return jsonify(status="ok"), 200


def counter_json():
    total = counter.read_total()
    has_cookie = bool(request.cookies.get(COUNTER_COOKIE))
    if not has_cookie:
        total += 1
        counter.write_total(total)
    resp = jsonify(unique_total=total)
    if not has_cookie:
        resp.set_cookie(COUNTER_COOKIE, "1", max_age=60 * 60 * 24 * 365 * 2, samesite="Lax")
    return resp


def robots_txt():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /healthz\n"
        "Disallow: /counter.json\n"
        "Disallow: /proxy_img\n"
        "Disallow: /post_json/\n"
        "Disallow: /release_json/\n"
        f"Sitemap: {_public_base_url()}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


def sitemap_xml():
    now_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    urls = [
        {"loc": url_for("index", _external=True), "lastmod": now_date, "changefreq": "daily", "priority": "1.0"},
        {"loc": url_for("blog", _external=True), "lastmod": now_date, "changefreq": "daily", "priority": "0.8"},
        {"loc": url_for("panamabattle", _external=True), "lastmod": now_date, "changefreq": "daily", "priority": "0.8"},
    ]

    if has_streams_keys():
        for item in notion_data.fetch_stream_releases(limit=200):
            page_id = (item or {}).get("id")
            if not page_id:
                continue
            urls.append({
                "loc": url_for("release_page", page_id=page_id, _external=True),
                "lastmod": (item.get("date") or now_date)[:10],
                "changefreq": "weekly",
                "priority": "0.7",
            })

    items_xml = [
        "  <url>\n"
        f"    <loc>{xml_escape(u['loc'])}</loc>\n"
        f"    <lastmod>{xml_escape(u['lastmod'])}</lastmod>\n"
        f"    <changefreq>{u['changefreq']}</changefreq>\n"
        f"    <priority>{u['priority']}</priority>\n"
        "  </url>"
        for u in urls
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(items_xml)
        + "\n</urlset>\n"
    )
    return Response(xml, mimetype="application/xml")


def security_txt():
    contact = os.environ.get("UMKA_SECURITY_CONTACT", "mailto:admin@umka.space")
    body = (
        f"Contact: {contact}\n"
        "Preferred-Languages: uk, en\n"
        "Policy: https://umka.space/\n"
    )
    return Response(body, mimetype="text/plain")


def google_ads_verification():
    return send_file(os.path.join(current_app.root_path, "googlead3267ff1c364dba.html"), mimetype="text/html")


_ROUTES = [
    ("/", index),
    ("/release/<page_id>", release_page),
    ("/release_json/<page_id>", release_json),
    ("/post_json/<page_id>", post_json),
    ("/panamabattle", panamabattle),
    ("/blog", blog),
    ("/proxy_img", proxy_img),
    ("/healthz", healthz),
    ("/counter.json", counter_json),
    ("/robots.txt", robots_txt),
    ("/sitemap.xml", sitemap_xml),
    ("/.well-known/security.txt", security_txt),
    ("/googlead3267ff1c364dba.html", google_ads_verification),
]


def register(app):
    for rule, view in _ROUTES:
        app.add_url_rule(rule, view_func=view)
