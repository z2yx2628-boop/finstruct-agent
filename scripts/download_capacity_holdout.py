"""Download the selected capacity holdout PDFs and write a source manifest.

Reads  data/manifests/capacity_holdout_selection.csv
Writes data/raw/capacity_holdout/<holdout_id>_<code>_<pattern>.pdf
       data/manifests/capacity_holdout_sources.csv

Only file-level facts are recorded (SHA-256, pages, text length, whether text
is extractable). Announcement content is not summarized, so this step cannot
leak Gold information into the extractor.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\download_capacity_holdout.py
"""
import csv
import datetime
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

import pymupdf as fitz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SELECTION = PROJECT_ROOT / "data" / "manifests" / "capacity_holdout_selection.csv"
MANIFEST = PROJECT_ROOT / "data" / "manifests" / "capacity_holdout_sources.csv"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "capacity_holdout"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "http://www.cninfo.com.cn/",
}


def download(url: str, attempts: int = 5) -> bytes:
    """Fetch a PDF, retrying with backoff and alternating http/https.

    CNINFO often resets or stalls connections after several quick requests,
    so each failure waits longer before the next attempt.
    """
    candidates = [url, url.replace("https://", "http://", 1)]
    last_error: Exception | None = None
    for attempt in range(attempts):
        target = candidates[attempt % len(candidates)]
        try:
            request = urllib.request.Request(target, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if not data.startswith(b"%PDF"):
                raise ValueError("response is not a PDF")
            return data
        except Exception as error:
            last_error = error
            wait = 5 * (attempt + 1)
            print(f"  retry {attempt + 1}/{attempts} in {wait}s: {error}")
            time.sleep(wait)
    raise RuntimeError(f"download failed after {attempts} attempts: {last_error}")


def inspect_pdf(path: Path) -> dict:
    with fitz.open(path) as document:
        texts = [page.get_text() for page in document]
    char_counts = [len(text.strip()) for text in texts]
    return {
        "page_count": len(texts),
        "text_char_count": sum(char_counts),
        "empty_pages": sum(1 for count in char_counts if count < 20),
        "is_text_pdf": all(count >= 20 for count in char_counts),
    }


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with SELECTION.open(encoding="utf-8-sig") as handle:
        selection = list(csv.DictReader(handle))

    rows, hashes, failures = [], {}, 0
    today = datetime.date.today().isoformat()
    for item in selection:
        file_name = (
            f"{item['holdout_id']}_{item['security_code']}_"
            f"{item['target_pattern']}.pdf"
        )
        path = RAW_DIR / file_name
        try:
            if not path.exists():
                print(f"[get  ] {file_name}")
                data = download(item["source_url"])
                path.write_bytes(data)
                time.sleep(3)
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            info = inspect_pdf(path)
        except Exception as error:
            failures += 1
            print(f"[fail] {file_name}: {error}")
            continue

        duplicate = hashes.get(sha256)
        hashes[sha256] = file_name
        status = "ok" if info["is_text_pdf"] and not duplicate else "check"
        print(
            f"[{status:5}] {file_name}: {info['page_count']} pages, "
            f"{info['text_char_count']} chars"
            + (f", {info['empty_pages']} empty pages" if info["empty_pages"] else "")
            + (f", DUPLICATE of {duplicate}" if duplicate else "")
        )
        rows.append({
            "split": "capacity_holdout",
            "file_name": file_name,
            "security_code": item["security_code"],
            "security_name": item["security_name"],
            "announcement_date": item["announcement_date"],
            "target_pattern": item["target_pattern"],
            "announcement_title": item["announcement_title"],
            "source_url": item["source_url"],
            "download_date": today,
            "sha256": sha256,
            **info,
        })

    with MANIFEST.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)}/{len(selection)} documents recorded in {MANIFEST}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
