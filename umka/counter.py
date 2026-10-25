"""Простий лічильник унікальних відвідувачів (кука + файл .counter.json)."""
import json
import os

from .config import COUNTER_FILE


def read_total() -> int:
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                return int(data.get("unique_total", 0))
    except Exception:
        pass
    return 0


def write_total(total: int) -> None:
    try:
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump({"unique_total": int(total)}, f)
    except Exception:
        pass
