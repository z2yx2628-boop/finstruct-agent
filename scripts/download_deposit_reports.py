"""Download the newest finance-company risk report (财务公司风险评估报告) for every company in
data/reference/finance_company_deposits.csv whose recorded source is older than a report already listed in the
cached announcement titles. The PDFs go to data/raw/finance_deposits/<code>_<date>_<doc_id>.pdf; the deposit and
loan figures are then read from them and written to the CSV by hand (verified = N until checked against the PDF).

    python scripts/download_deposit_reports.py            # needs internet
"""
import csv
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.related_view import newer_report  # noqa: E402

CSV = ROOT / "data" / "reference" / "finance_company_deposits.csv"
OUT = ROOT / "data" / "raw" / "finance_deposits"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    with CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    latest = {}
    for r in rows:
        if r["source_date"] > latest.get(r["security_code"], ("", None))[0]:
            latest[r["security_code"]] = (r["source_date"], r["security_name"])
    for code, (seen, name) in sorted(latest.items()):
        hit = newer_report(code, seen, today)
        if not hit or not hit["url"]:
            print(f"{code} {name}: up to date ({seen})")
            continue
        target = OUT / f"{code}_{hit['date']}_{hit['doc_id']}.pdf"
        if target.exists():
            print(f"{code} {name}: already downloaded {target.name}")
            continue
        try:
            resp = requests.get(hit["url"], headers=HEADERS, timeout=60)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            target.write_bytes(resp.content)
            print(f"{code} {name}: {hit['date']}《{hit['title']}》 -> {target.name}")
        except Exception as error:                     # one failure does not stop the rest
            print(f"{code} {name}: FAILED {hit['url']} ({error})")
        time.sleep(1)


if __name__ == "__main__":
    main()
