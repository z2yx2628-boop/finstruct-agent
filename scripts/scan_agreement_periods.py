"""Find multi-year agreement periods stated in related-party announcements.

A related-party estimate is in force until the end of its estimate year (src/validity.py).
Framework agreements say more: Ma Steel's 2024-10-30 announcement signs agreements
"有效期自2025年1月1日起至2027年12月31日止，为期三年", so the relation with China Baowu holds
through 2027, not only 2025. This script reads the page text kept with each frozen extraction
and records the stated period. Rules only, no model call; every row keeps the page and sentence.

    python scripts/scan_agreement_periods.py          # every source of the live graph (as daily_update.py)
    -> data/manifests/agreement_periods.csv  (doc = frozen JSON path, valid_from, valid_to, page, evidence)

src/chain_inputs.py looks rows up by the frozen JSON path, so the period only extends edges built
from that exact file. The history graph (outputs/hist_freeze) is not scanned: the incremental test
in docs/history_graph_preregistration.md ran on the earlier rule and its inputs stay unchanged.

Accepted: an explicit "有效期/期限 自 YYYY年M月D日 起至 YYYY年M月D日" sentence, or a
"YYYY至YYYY年度" span next to 关联交易/协议; spans longer than three years are ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "manifests" / "agreement_periods.csv"
D = r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
EXPLICIT = re.compile(r"(?:有效期|期限)[^。；]{0,12}?自\s*" + D + r"[^。；]{0,12}?至\s*" + D)
SPAN = re.compile(r"(\d{4})\s*(?:年度?)?\s*(?:至|-|–|—|~)\s*(\d{4})\s*年度?[^。；]{0,12}(?:关联交易|协议)")


def pages_for(stem: str) -> list[dict]:
    runs = sorted((ROOT / "outputs" / stem).glob("*/pages.json"))
    return json.loads(runs[-1].read_text(encoding="utf-8")) if runs else []


def find_period(pages: list[dict]) -> tuple[str, str, int, str] | None:
    hits = []
    for p in pages:
        text = re.sub(r"\s+", " ", p.get("text") or "")
        for m in EXPLICIT.finditer(text):
            y1, m1, d1, y2, m2, d2 = map(int, m.groups())
            hits.append((date(y1, m1, d1), date(y2, m2, d2), p.get("page"), m.group(0)))
        for m in SPAN.finditer(text):
            y1, y2 = map(int, m.groups())
            if y2 > y1:
                hits.append((date(y1, 1, 1), date(y2, 12, 31), p.get("page"), m.group(0)))
    hits = [h for h in hits if 0 < (h[1] - h[0]).days <= 3 * 366 + 2]
    if not hits:
        return None
    start, end, page, text = max(hits, key=lambda h: (h[1], -len(h[3])))  # latest stated end
    return start.isoformat(), end.isoformat(), page, text.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="+", help="frozen extraction folders; default: the live graph's sources")
    args = ap.parse_args()
    if not args.src:
        args.src = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "outputs").glob("*_freeze"))
                    if p.name.startswith(("analysis", "live_", "manual"))]
    # page text lives in outputs/<doc>/<run>/pages.json, which is not in git; where it is missing
    # (e.g. on GitHub Actions) keep the row found earlier instead of dropping it
    kept = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as fh:
            kept = {r["doc"]: r for r in csv.DictReader(fh)}
    rows = []
    for src in args.src:
        for f in sorted((ROOT / src / "related_party").glob("*.json")):
            key = f.relative_to(ROOT).as_posix()
            pages = pages_for(f.stem)
            if not pages:
                if key in kept:
                    rows.append(kept[key])
                continue
            found = find_period(pages)
            if found:
                rows.append({"doc": f.relative_to(ROOT).as_posix(), "valid_from": found[0], "valid_to": found[1],
                             "page": found[2], "evidence": found[3]})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc", "valid_from", "valid_to", "page", "evidence"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} documents state an agreement period -> {OUT.relative_to(ROOT)}")
    for r in rows:
        print(f"  {Path(r['doc']).stem}: {r['valid_from']} ~ {r['valid_to']}  p{r['page']}  {r['evidence'][:50]}")


if __name__ == "__main__":
    main()
