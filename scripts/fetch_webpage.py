"""Save a web page and its provenance for extraction.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\fetch_webpage.py URL [--name NAME] [--dir data\\raw\\web]

Writes NAME.html (the raw page, unmodified) and NAME.meta.json
(url, fetch time, SHA-256), so every extracted fact can be traced to the
exact page version that was read.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


def fetch(url: str, directory: Path, name: str | None = None) -> Path:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        final_url = response.geturl()
    if not name:
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", url.split("//", 1)[-1])[:80].strip("_")
    directory.mkdir(parents=True, exist_ok=True)
    html_path = directory / f"{name}.html"
    html_path.write_bytes(raw)
    meta = {
        "url": url,
        "final_url": final_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    html_path.with_name(f"{name}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return html_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--name")
    parser.add_argument("--dir", type=Path, default=PROJECT_ROOT / "data" / "raw" / "web")
    args = parser.parse_args()
    path = fetch(args.url, args.dir, args.name)
    print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
