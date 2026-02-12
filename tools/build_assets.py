#!/usr/bin/env python3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
ESBUILD = ROOT / "node_modules" / ".bin" / "esbuild"

def _minify_lines(text: str) -> str:
    # Conservative "minify": trim whitespace and drop empty lines.
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln.strip() != ""]).strip() + "\n"

def _minify_with_esbuild() -> bool:
    if not ESBUILD.exists():
        return False
    css_cmd = [str(ESBUILD), str(STATIC / "style.css"), "--minify", f"--outfile={STATIC / 'app.min.css'}"]
    js_cmd = [str(ESBUILD), str(STATIC / "script.js"), "--minify", f"--outfile={STATIC / 'app.min.js'}"]
    try:
        subprocess.run(css_cmd, check=True, cwd=str(ROOT), capture_output=True, text=True)
        subprocess.run(js_cmd, check=True, cwd=str(ROOT), capture_output=True, text=True)
        return True
    except Exception:
        return False

def main() -> None:
    if _minify_with_esbuild():
        return
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    js = (STATIC / "script.js").read_text(encoding="utf-8")
    (STATIC / "app.min.css").write_text(_minify_lines(css), encoding="utf-8")
    (STATIC / "app.min.js").write_text(_minify_lines(js), encoding="utf-8")

if __name__ == "__main__":
    main()
