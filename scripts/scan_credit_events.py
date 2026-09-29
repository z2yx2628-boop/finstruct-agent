"""Recognise credit events that have already happened from announcement titles (the 24 core mills, last 12 months).

Titles: the newest pages of each company's Sina announcement list (cached in data/live/announcement_titles/),
plus the titles already collected for the event study (data/event_study/titles/, read only).
Patterns: the pre-registered event-study patterns (scripts/collect_credit_events.py), so "事件" means the same
thing in the live warning and in the validation.

Rules for the live list:
  - a title already reviewed for the event study keeps that decision (status 人工核对); a new one is included
    with status 标题自动识别 (the page says so) until someone checks it
  - an event about a 参股 company is dropped; one about a subsidiary gets severity 中, the company itself 高
  - "可能被实施…风险警示" is a warning in advance (st_warning, 中)
  - the same kind of event of the same company within 90 days counts once (progress announcements)
  - an event stays in force for 12 months

    python scripts/scan_credit_events.py              # fetch the newest titles (network), then scan
    python scripts/scan_credit_events.py --offline    # scan the cached titles only
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.collect_credit_events import TITLE_FIELDS, classify, read, write  # noqa: E402
from scripts.fetch_financials import core_mills  # noqa: E402
from src.live_events import EVENT_CN, FIELDS, TABLE  # noqa: E402

CACHE = ROOT / "data" / "live" / "announcement_titles"
STUDY = ROOT / "data" / "event_study"
PAGES = 3                     # newest ~90 titles per company; the daily update runs far more often than that


def fetch_recent(code: str, name: str) -> list[dict]:
    from scripts.find_analysis_corpus import fetch_page, pdf_url
    rows = []
    for page in range(1, PAGES + 1):
        items = fetch_page(code, page)
        if not items:
            break
        rows += [{"security_code": code, "security_name": name, "notice_date": i["notice_date"][:10], "doc_id": i["doc_id"],
                  "title": i["title"], "source_url": pdf_url(code, i["notice_date"][:10], i["doc_id"])} for i in items]
        time.sleep(1)
    return rows


def main() -> None:
    offline = "--offline" in sys.argv
    today = date.today().isoformat()
    since = (date.today() - timedelta(days=400)).isoformat()
    reviewed = {(r["security_code"], r["notice_date"], r["title"]): r for r in read(STUDY / "events_reviewed.csv")}
    failures, found = [], []
    for m in core_mills():
        code, name = m["security_code"], m["security_name"]
        cache = CACHE / f"{code}.csv"
        titles = {r["doc_id"]: r for r in read(cache)}
        if not offline:
            try:
                for r in fetch_recent(code, name):
                    titles[r["doc_id"]] = r
                write(cache, TITLE_FIELDS, sorted(titles.values(), key=lambda r: r["notice_date"], reverse=True))
            except Exception as error:  # noqa: BLE001 - keep going with the cache
                failures.append(f"{code} {name}: {str(error)[:80]}")
        for r in read(STUDY / "titles" / f"{code}.csv"):
            titles.setdefault(r["doc_id"], r)
        for t in titles.values():
            if t["notice_date"] < since:
                continue
            kind = classify(t["title"])
            if not kind or "参股" in t["title"]:
                continue
            review = reviewed.get((code, t["notice_date"], t["title"]))
            if review and review["include"] == "N" and "可能被实施" not in t["title"]:
                continue
            if "可能被实施" in t["title"]:
                kind = "st_warning"
            severity = "medium" if kind == "st_warning" or "子公司" in t["title"] else "high"
            found.append({"security_code": code, "security_name": name, "date": t["notice_date"], "event_type": kind,
                          "event_label": EVENT_CN[kind], "severity": severity, "title": t["title"], "source_url": t["source_url"],
                          "status": "人工核对" if review else "标题自动识别",
                          "valid_to": (date.fromisoformat(t["notice_date"]) + timedelta(days=365)).isoformat()})
    found.sort(key=lambda r: (r["security_code"], r["event_type"], r["date"]))
    kept = []
    for r in found:                                   # progress announcements of the same event count once
        last = next((k for k in reversed(kept) if k["security_code"] == r["security_code"]
                     and k["event_type"] == r["event_type"]), None)
        if last and (date.fromisoformat(r["date"]) - date.fromisoformat(last["date"])).days <= 90:
            continue
        kept.append(r)
    kept.sort(key=lambda r: r["date"], reverse=True)
    write(TABLE, FIELDS, kept)
    live = [r for r in kept if r["valid_to"] >= today]
    print(f"{len(live)} credit events in force on {today} -> {TABLE.relative_to(ROOT)}")
    for r in live:
        print(f"  {r['date']} {r['security_name']} {r['event_label']}（{r['status']}）：{r['title']}")
    if failures:
        print("FAILED (cache used):", *failures, sep="\n  ")


if __name__ == "__main__":
    main()
