"""Download the annual reports of the 24 core mills (FY2022-2025) for the top-5 customer / supplier tables.

Titles come from the Sina announcement lists already cached by scripts/collect_credit_events.py
(data/event_study/titles/<code>.csv); a company without a cache is fetched first.
Writes data/raw/annual_reports/<code>_<fy>.pdf (skips files already there) and
data/manifests/annual_report_sources.csv.

    python scripts/download_annual_reports.py            # all 24 mills, FY2022-2025
    python scripts/download_annual_reports.py 000761     # only these
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import core_mills  # noqa: E402

TITLES = ROOT / "data" / "event_study" / "titles"
RAW = ROOT / "data" / "raw" / "annual_reports"
MANIFEST = ROOT / "data" / "manifests" / "annual_report_sources.csv"
YEARS = range(2022, 2026)
TITLE = re.compile(r"^(20\d\d)年(?:年度|度)报告(?:全文)?\s*(?:[（(]修订版?[）)])?$")
FIELDS = ["security_code", "security_name", "fy", "notice_date", "title", "source_url", "file", "sha256", "status"]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pick(titles: list[dict]) -> dict[str, dict]:
    """fy -> the annual report (the latest one, so a revised version replaces the original)."""
    out: dict[str, dict] = {}
    for t in titles:
        m = TITLE.match(t["title"].strip())
        if m and int(m.group(1)) in YEARS:
            fy = m.group(1)
            if fy not in out or t["notice_date"] > out[fy]["notice_date"]:
                out[fy] = t
    return out


def main() -> None:
    from scripts.download_capacity_holdout import download   # retries, checks the bytes are a PDF
    codes = {a for a in sys.argv[1:] if a.isdigit()}
    mills = [m for m in core_mills() if not codes or m["security_code"] in codes]
    done = {(r["security_code"], r["fy"]): r for r in read(MANIFEST)}
    RAW.mkdir(parents=True, exist_ok=True)
    failures = []
    for m in mills:
        code, name = m["security_code"], m["security_name"]
        cache = TITLES / f"{code}.csv"
        if not cache.exists():
            from scripts.collect_credit_events import TITLE_FIELDS, fetch_titles, write
            write(cache, TITLE_FIELDS, fetch_titles(code, name))
        chosen = pick(read(cache))
        for fy in (str(y) for y in YEARS):
            t = chosen.get(fy)
            if not t:
                failures.append(f"{code} {name} FY{fy}: no annual-report title in the list")
                continue
            path = RAW / f"{code}_{fy}.pdf"
            row = {"security_code": code, "security_name": name, "fy": fy, "notice_date": t["notice_date"], "title": t["title"],
                   "source_url": t["source_url"], "file": path.relative_to(ROOT).as_posix()}
            if not path.exists():
                try:
                    path.write_bytes(download(t["source_url"]))
                    time.sleep(3)
                except Exception as error:  # noqa: BLE001 - keep going, report at the end
                    failures.append(f"{code} {name} FY{fy}: {str(error)[:90]}")
                    done[(code, fy)] = dict(row, sha256="", status="failed")
                    continue
            done[(code, fy)] = dict(row, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), status="ok")
            print(f"[{code} {name}] FY{fy} ok ({path.stat().st_size / 1e6:.1f} MB)")
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(done.values(), key=lambda r: (r["security_code"], r["fy"])))
    ok = sum(1 for r in done.values() if r["status"] == "ok")
    print(f"\n{ok} annual reports ready -> {RAW.relative_to(ROOT)}; manifest {MANIFEST.relative_to(ROOT)}")
    if failures:
        print("FAILED / MISSING:", *failures, sep="\n  ")


if __name__ == "__main__":
    main()
