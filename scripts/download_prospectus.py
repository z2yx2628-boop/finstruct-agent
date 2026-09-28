"""Download the bond prospectuses listed in data/manifests/prospectus_download_list.csv into data/raw/prospectus/.
Run on your own computer (these mirrors are reachable there; sse.com.cn is not):
    python scripts/download_prospectus.py
Already-downloaded files are skipped; failures are listed at the end so they can be saved by hand from a browser.
"""
import csv
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "prospectus"
OUT.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

failed = []
with (ROOT / "data" / "manifests" / "prospectus_download_list.csv").open(encoding="utf-8") as f:
    for row in csv.DictReader(f):
        target = OUT / row["save_as"]
        if target.exists() and target.stat().st_size > 10_000:
            print("skip", target.name)
            continue
        try:
            r = requests.get(row["url"], headers=HEADERS, timeout=60, allow_redirects=True)
            ok = r.status_code == 200 and r.content[:4] == b"%PDF"
            if ok:
                target.write_bytes(r.content)
                print(f"ok   {target.name}  {len(r.content) / 1e6:.1f} MB  {row['issuer']}")
            else:
                failed.append((row, f"HTTP {r.status_code}, not a PDF" if r.status_code == 200 else f"HTTP {r.status_code}"))
        except Exception as e:  # noqa: BLE001
            failed.append((row, f"{type(e).__name__}: {str(e)[:80]}"))
print(f"\n{len(failed)} failed:")
for row, why in failed:
    print(f"  {row['issuer']} {row['save_as']}: {why}\n    {row['url']}")
