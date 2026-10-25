"""Промо на головній: відеозапрошення і банери. Правиш тут — і перезапускаєш сайт.

Поле "until" (РРРР-ММ-ДД) — останній день показу за київським часом.
Після нього блок зникає сам, нічого видаляти не треба.
"""
import datetime as dt
import os

from .youtube import youtube_id

try:
    from zoneinfo import ZoneInfo
    _KYIV = ZoneInfo("Europe/Kyiv")
except Exception:  # no tz database on the host
    _KYIV = dt.timezone(dt.timedelta(hours=2))

# 🎬 Відеозапрошення над банерами. url — будь-яке посилання YouTube
# (watch?v=..., youtu.be/..., shorts/...). Порожній url — блок не показується.
INVITE_VIDEO = {
    "url": os.environ.get("UMKA_INVITE_VIDEO_URL", "https://www.youtube.com/shorts/GdUN1YacYcI"),
    "title": "",
    "text": "50 000 грн призовий",
    # Рядок під відео, тим самим стилем, що text (регістр як написано)
    "tagline": "",
    # Кнопка під відео (порожній cta_url — без кнопки); \n — новий рядок
    "cta_text": "ВЗЯТИ УЧАСТЬ У\nPANAMABATTLE V",
    "cta_url": "https://www.panamabattle.com/season-new",
    # Перший раунд PANAMABATTLE — до 21.11; показуємо ще 22.11, потім ховаємо
    "until": "2026-11-22",
}

# 📣 Банери під відеозапрошенням (показуються стопкою, у цьому порядку).
# Поля: title — жирний текст, text — опис, url — куди веде,
# image — (необов'язково) шлях у static/ або https-посилання на картинку-банер,
# image_mobile — (необов'язково) окрема картинка для екранів до 640px,
# until — (необов'язково) останній день показу.
BANNERS = [
    # Розкоментуй, коли файли будуть у static/banners/
    # {
    #     "title": "PANAMABATTLE",
    #     "text": "Сезон V · реп-батл онлайн — взяти участь",
    #     "url": "https://www.panamabattle.com/season-new",
    #     "image": "banners/panamabattle-970x250.png",
    #     "image_mobile": "banners/panamabattle-468x60.png",
    #     "until": "2026-11-22",
    # },
    {
        "title": "Чарт українського репу",
        "text": "",
        "url": "https://music.youtube.com/playlist?list=PLqfj-GxxzQq_6jSrlCicVPoDt9uhqtajH&si=fOWdP01o6w-M2xGm",
    },
]


def _today() -> dt.date:
    return dt.datetime.now(_KYIV).date()


def is_active(item: dict, today: dt.date | None = None) -> bool:
    until = (item.get("until") or "").strip()
    if not until:
        return True
    try:
        last_day = dt.date.fromisoformat(until)
    except ValueError:
        return True  # typo in the date should not hide the block silently
    return (today or _today()) <= last_day


def active_banners(today: dt.date | None = None) -> list:
    return [b for b in BANNERS if is_active(b, today)]


def invite_video(today: dt.date | None = None) -> dict | None:
    if not is_active(INVITE_VIDEO, today):
        return None
    url = INVITE_VIDEO.get("url", "")
    vid = youtube_id(url)
    if not vid:
        return None
    return {
        "id": vid,
        "title": INVITE_VIDEO.get("title") or "",
        "text": INVITE_VIDEO.get("text") or "",
        "tagline": INVITE_VIDEO.get("tagline") or "",
        "vertical": "/shorts/" in url,
        "cta_text": INVITE_VIDEO.get("cta_text") or "",
        "cta_url": INVITE_VIDEO.get("cta_url") or "",
    }
