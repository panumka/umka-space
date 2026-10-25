"""UmkA.space — точка входу (gunicorn app:app).

Код розкладено по модулях у umka/:
  promo.py        — відеозапрошення і банери на головній (тут правити промо)
  views.py        — маршрути сторінок і JSON
  notion_data.py  — релізи й пости з Notion
  youtube.py      — відео з PANAMABATTLE
  image_proxy.py  — /proxy_img
  config.py       — налаштування з .env
"""
import base64
import datetime as dt
import os
from datetime import timedelta

from flask import Flask
from flask import url_for as _flask_url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from umka import views
from umka.config import STATIC_MAX_AGE

app = Flask(__name__)
# Behind Railway/Cloudflare: trust X-Forwarded-Proto so external URLs are https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(seconds=STATIC_MAX_AGE)

# Optional: gzip/brotli compression if flask-compress is installed
try:
    from flask_compress import Compress  # type: ignore
    Compress(app)
except Exception:
    pass


# --- Auto cache-busting for static files (adds ?v=<mtime>) ---
@app.context_processor
def _override_url_for():
    def dated_url_for(endpoint, **values):
        if endpoint == "static":
            filename = values.get("filename")
            if filename:
                try:
                    values["v"] = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
                except Exception:
                    # якщо файл не знайдено — просто пропускаємо
                    pass
        return _flask_url_for(endpoint, **values)
    return dict(url_for=dated_url_for)


# Inject current year into all templates
@app.context_processor
def inject_now():
    return {"current_year": dt.datetime.now(dt.timezone.utc).year}


# Jinja filter: b64encode (URL-safe)
def _b64encode_filter(s):
    if not s:
        return ""
    b = s if isinstance(s, bytes) else str(s).encode("utf-8")
    return base64.urlsafe_b64encode(b).decode("utf-8")


app.jinja_env.filters["b64encode"] = _b64encode_filter


# Security headers for every response (relaxed CSP to avoid breaking current UI)
@app.after_request
def _set_default_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
    # Relaxed CSP that works with current inline styles/scripts and remote images
    csp = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' https:; "
        "frame-src https://www.youtube-nocookie.com https://www.youtube.com; "
        "frame-ancestors 'none'"
    )
    resp.headers.setdefault("Content-Security-Policy", csp)
    return resp


views.register(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)))
