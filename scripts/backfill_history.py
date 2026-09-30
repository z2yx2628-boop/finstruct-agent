"""Select the 2019-01 .. 2025-04 announcements needed for the HISTORICAL graph (docs/history_graph_preregistration.md).

The event-study panel (7 evaluation dates, 2019-04-30 .. 2025-04-30) needs the related-party and guarantee relations that
were in force on each date. The live graph starts in 2024, so those years are rebuilt here from the announcement titles
already cached for the 24 core mills (data/event_study/titles/, 2019-01 onward).

Kept: titles the extraction system already handles (scripts/find_analysis_corpus.classify) for the chosen tasks,
published in the window, and not yet extracted by any frozen run (identified exactly: company, date, title).
Documents that were test or holdout documents and have no frozen output are listed and left out: they are never
re-extracted, so nothing here can touch an evaluation.

    python scripts/backfill_history.py                       # related-party + guarantee (default)
    python scripts/backfill_history.py --tasks related_party guarantee pledge capacity
Then (each step resumes where it stopped):
    python scripts/download_capacity_holdout.py --split hist
    python scripts/run_analysis_corpus.py --split hist
    python scripts/build_history_graph.py
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.find_analysis_corpus import classify, norm  # noqa: E402

TITLES = ROOT / "data" / "event_study" / "titles"
MANIFESTS = ROOT / "data" / "manifests"
SPLIT = "hist"
PATTERN = {"related_party": "related_estimate", "guarantee": "guarantee_live", "capacity": "capacity", "pledge": "pledge"}
ORDER = {"related_party": 0, "guarantee": 1, "pledge": 2, "capacity": 3}
EVALUATION = re.compile(r"test|blind|holdout|dev")
HOLDOUT_ID = re.compile(r"^(.*?_\d{3})_")


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def doc_key(row: dict) -> tuple[str, str, str] | None:
    code = (row.get("security_code") or "").zfill(6)
    title = row.get("announcement_title") or row.get("title") or ""
    day = row.get("announcement_date") or row.get("publish_date") or row.get("notice_date") or ""
    return (code, day, norm(title)) if code.strip("0") and title and day else None


def extracted_ids() -> set[str]:
    """holdout ids that have a frozen prediction in some outputs/*_freeze folder."""
    ids = set()
    for path in (ROOT / "outputs").glob("*_freeze/*/*.json"):
        m = HOLDOUT_ID.match(path.stem)
        if m:
            ids.add(m.group(1))
    return ids


def registry() -> tuple[set, set]:
    """(documents with a frozen extraction, evaluation documents without one) - both as exact keys."""
    done_ids = extracted_ids()
    done, evaluation = set(), set()
    for path in MANIFESTS.glob("*_selection.csv"):
        if path.name == f"{SPLIT}_selection.csv":
            continue
        for row in read(path):
            key = doc_key(row)
            if not key:
                continue
            if row.get("holdout_id") in done_ids:
                done.add(key)
            elif EVALUATION.search(path.name):
                evaluation.add(key)
    return done, evaluation - done


def candidates(start: str, end: str, tasks: list[str]) -> list[dict]:
    out = []
    for path in sorted(TITLES.glob("*.csv")):
        for row in read(path):
            if not start <= row["notice_date"] <= end:
                continue
            task = classify(row["title"])
            if task in tasks:
                out.append(dict(row, task=task))
    return out


def select(rows: list[dict], done: set, evaluation: set) -> tuple[list[dict], list[dict], int]:
    keep, skipped, already, seen = [], [], 0, set()
    for r in rows:
        key = doc_key(r)
        if key in seen:
            continue
        seen.add(key)
        if key in done:
            already += 1
        elif key in evaluation:
            skipped.append(r)
        else:
            keep.append(r)
    keep.sort(key=lambda r: (ORDER[r["task"]], r["notice_date"], r["security_code"]))
    return keep, skipped, already


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2025-04-30")
    ap.add_argument("--tasks", nargs="+", default=["related_party", "guarantee"], choices=list(PATTERN))
    args = ap.parse_args()
    done, evaluation = registry()
    keep, skipped, already = select(candidates(args.start, args.end, args.tasks), done, evaluation)
    path = MANIFESTS / f"{SPLIT}_selection.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["holdout_id", "security_code", "security_name", "announcement_date", "target_pattern",
                    "announcement_title", "source_url", "notes"])
        for i, r in enumerate(keep, 1):
            w.writerow([f"{SPLIT}_{i:03d}", r["security_code"], r["security_name"], r["notice_date"], PATTERN[r["task"]],
                        r["title"], r["source_url"], f"sina doc {r['doc_id']}; historical graph backfill"])
    by = {}
    for r in keep:
        by[(r["task"], r["notice_date"][:4])] = by.get((r["task"], r["notice_date"][:4]), 0) + 1
    print(f"{len(keep)} documents -> {path.relative_to(ROOT)}; {already} already extracted by a frozen run; "
          f"{len(skipped)} evaluation documents without a frozen output left out")
    for k in sorted(by):
        print(f"  {k[0]:13s} {k[1]}: {by[k]}")
    print(f"About {len(keep) * 80 / 3600:.1f} hours of extraction at ~80 s per document (the 2026-09-30 run).")


if __name__ == "__main__":
    main()
