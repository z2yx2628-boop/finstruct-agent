"""How many company names in the guarantee / related-party Gold resolve to a node?

    python scripts/entity_coverage.py            # summary + unresolved names
Writes data/reference/entity_coverage.csv (one row per distinct name) for review.
"""
import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolver import resolve  # noqa: E402

FIELDS = ("counterparty", "guarantor", "guaranteed_party")
OUT = ROOT / "data" / "reference" / "entity_coverage.csv"


def names_in(doc):
    for key in ("transactions", "events"):
        for rec in doc.get(key) or []:
            for field in FIELDS:
                if rec.get(field):
                    yield field, rec[field], rec.get("relationship")


def main() -> None:
    _, index = __import__("src.entity_resolver", fromlist=["load_entities"]).load_entities()
    by_full = {k: v[0] for k, v in index.items()}
    seen = {}
    for path in sorted(glob.glob(str(ROOT / "data" / "gold" / "*" / "*.json"))):
        split = Path(path).parent.name
        if not split.startswith(("related", "guarantee")):
            continue
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        issuer = by_full.get(doc.get("company_name") or "")
        for field, name, relationship in names_in(doc):
            r = resolve(name, issuer_id=issuer, relationship=relationship)
            seen.setdefault((field, name), (split, r))
    counts = Counter(r.matched_by for _, r in seen.values())
    total = len(seen)
    print(f"{total} distinct (field, name) pairs")
    for how in ("exact", "alias", "self_reference", "group_token", "relationship", "unresolved"):
        print(f"  {how:15s} {counts.get(how, 0):4d}  {counts.get(how, 0) / total:6.1%}")
    node = sum(1 for _, r in seen.values() if r.entity_id)
    group = sum(1 for _, r in seen.values() if r.group_id)
    print(f"entity resolved {node / total:.1%}; group known {group / total:.1%}")
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["split", "field", "raw_name", "base_name", "scope", "entity_id", "group_id", "matched_by", "note"])
        for (field, name), (split, r) in sorted(seen.items(), key=lambda x: (x[1][1].matched_by, x[0])):
            w.writerow([split, field, name, r.base_name, r.scope, r.entity_id or "", r.group_id or "", r.matched_by, r.note])
    print("unresolved:", "、".join(sorted({r.base_name for _, r in seen.values() if r.matched_by == "unresolved"})))


if __name__ == "__main__":
    main()
