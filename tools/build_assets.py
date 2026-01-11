#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

def _minify_lines(text: str) -> str:
    # Conservative "minify": trim whitespace and drop empty lines.
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln.strip() != ""]).strip() + "\n"

def main() -> None:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    js = (STATIC / "script.js").read_text(encoding="utf-8")
    (STATIC / "app.min.css").write_text(_minify_lines(css), encoding="utf-8")
    (STATIC / "app.min.js").write_text(_minify_lines(js), encoding="utf-8")

if __name__ == "__main__":
    main()
