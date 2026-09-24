"""Build edges.csv and signals.csv (direction 3 inputs) from direction-1 JSON documents.

    python scripts/build_chain_inputs.py                                  # Gold data, demo only
    python scripts/build_chain_inputs.py --src outputs/<run>/predictions --out data/chain/<run>

The Gold build is for developing direction 3; the analysis itself must use outputs of the
frozen extraction system.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.chain_inputs import EDGE_FIELDS, SIGNAL_FIELDS, as_row, doc_key, doc_kind, edges_from, signals_from  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/gold")
    ap.add_argument("--out", default="data/chain/gold_demo")
    args = ap.parse_args()
    src, out = ROOT / args.src, ROOT / args.out
    edges, signals, kinds, skipped, seen, dup = [], [], Counter(), 0, set(), 0
    for path in sorted(src.rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(doc, dict) or "security_code" not in doc:
            continue
        if doc_key(doc) in seen:
            dup += 1
            continue
        seen.add(doc_key(doc))
        kinds[doc_kind(doc)] += 1
        rel = path.relative_to(ROOT).as_posix()
        e, s = edges_from(doc, rel)
        edges += e
        skipped += s
        signals += signals_from(doc, rel)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (("edges.csv", edges, EDGE_FIELDS), ("signals.csv", signals, SIGNAL_FIELDS)):
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(as_row(r) for r in rows)
    print("documents:", dict(kinds), f"(duplicates across splits skipped: {dup})")
    print(f"edges: {len(edges)} ({dict(Counter(e.edge_type for e in edges))}); "
          f"same-group {sum(e.same_group for e in edges)}; skipped (party not named) {skipped}")
    nodes = {e.src_id for e in edges} | {e.dst_id for e in edges}
    print(f"nodes: {len(nodes)} ({sum(1 for n in nodes if n.startswith('N_'))} without a table entry)")
    print(f"signals: {len(signals)} {dict(Counter(s.signal_type for s in signals))}")
    print(f"         severity {dict(Counter(s.severity for s in signals))}")
    print(f"written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
