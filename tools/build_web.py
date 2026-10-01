"""Build the static website (this is what GitHub Pages publishes).

    python tools/build_web.py [output_dir]

Writes into output_dir (default: dist/). It refuses to touch a folder that already exists,
so nothing is ever wiped: pass a new name, or remove the old folder yourself.
"""
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    if out.exists():
        sys.exit(f"{out} already exists; choose a new folder name.")
    out.mkdir(parents=True)
    for name in ("index.html", "style.css", "app.js", "worker.js", "web_api.py", "tidyweb_logo.png"):
        shutil.copy(SITE / name, out / name)
    (out / "fonts").mkdir()
    for font in ("dm-sans-latin-wght-normal.woff2", "dm-mono-latin-400-normal.woff2", "LICENSES.txt"):
        shutil.copy(SITE / "fonts" / font, out / "fonts" / font)
    (out / ".nojekyll").write_text("")
    with zipfile.ZipFile(out / "chaos.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((ROOT / "chaos").glob("*.py")):
            z.write(path, path.relative_to(ROOT).as_posix())
    print(f"Built {out} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) // 1024} KB)")


if __name__ == "__main__":
    main()
