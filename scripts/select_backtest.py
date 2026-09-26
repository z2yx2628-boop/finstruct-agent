"""Select a backtest's input announcements: everything public BEFORE the event date.

    python scripts/select_backtest.py antai --codes 600408 --before 2025-02-06
Writes data/manifests/backtest_<name>_selection.csv for
    python scripts/download_capacity_holdout.py --split backtest_<name>
Titles only. Documents also used in development are kept (the backtest tests propagation,
not extraction accuracy) and marked in `notes`; final-test documents are never selected.
"""
import argparse
import csv
import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["holdout_id", "security_code", "security_name", "announcement_date", "target_pattern",
          "announcement_title", "source_url", "notes"]
PATTERN = {"related_party": "related_estimate", "guarantee": "guarantee_backtest", "capacity": "capacity",
           "pledge": "pledge"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--codes", nargs="+", required=True)
    ap.add_argument("--before", required=True, help="event date; only earlier announcements are used")
    ap.add_argument("--exclude", default="", help="regex on titles that are not events (rules, margin collateral)")
    args = ap.parse_args()
    rows, seen = [], set()
    for path in sorted(glob.glob(str(ROOT / "data" / "manifests" / "analysis_corpus_candidates*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                key = (r["security_code"], r["doc_id"])
                if r["security_code"] in args.codes and r["notice_date"] < args.before and key not in seen:
                    if "final_test" in r["used_in"] or (args.exclude and re.search(args.exclude, r["title"])):
                        continue
                    seen.add(key)
                    rows.append(r)
    rows.sort(key=lambda r: (r["security_code"], r["notice_date"]))
    out = ROOT / "data" / "manifests" / f"backtest_{args.name}_selection.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            note = f"sina doc {r['doc_id']}; event {args.before}"
            if r["used_in"]:
                note += f"; also used in {r['used_in']} (development)"
            w.writerow({"holdout_id": f"backtest_{args.name}_{i:03d}", "security_code": r["security_code"],
                        "security_name": r["security_name"], "announcement_date": r["notice_date"],
                        "target_pattern": PATTERN[r["task"]], "announcement_title": r["title"],
                        "source_url": r["source_url"], "notes": note})
    print(f"{len(rows)} documents before {args.before} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
