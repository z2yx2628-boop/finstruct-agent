"""Historical graph: every frozen extraction -> data/chain/hist, then the risk paths on each event-study date.

Edges and signals keep their validity windows, so the graph "as of 2021-04-30" contains only what had been announced by
then and was still in force (src/validity.is_active). Fragility on each date is the frozen event-study snapshot
(data/event_study/snapshots/<date>), never recomputed. Title-recognised live credit events are NOT added (they belong to
the live chain only).

    python scripts/build_history_graph.py
Writes data/chain/hist/{edges,signals}.csv, key_paths_<date>.csv, paths_<date>.{json,md} and coverage.csv.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validity import is_active  # noqa: E402

CHAIN = "data/chain/hist"
DATES = [f"{y}-04-30" for y in range(2019, 2026)]
PREFIXES = ("analysis", "backtest_", "live_", "manual", "hist")
RELATION = {"guarantee", "supply", "service", "lease", "finance"}


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def core_codes() -> list[str]:
    from scripts.fetch_financials import core_mills
    return [m["security_code"] for m in core_mills()]


def coverage(edges: list[dict], codes: list[str], as_of: str) -> dict:
    """How much of the panel the graph can see on as_of: mills that are an endpoint of an active disclosed relation."""
    active = [e for e in edges if is_active(e, as_of) and e["edge_type"] in RELATION]
    touched = {c for e in active for c in (e["src_id"], e["dst_id"], e.get("issuer_id", "")) if c in codes}
    by_type = {}
    for e in active:
        by_type[e["edge_type"]] = by_type.get(e["edge_type"], 0) + 1
    return {"as_of": as_of, "active_relations": len(active), "mills_covered": len(touched), "mills": len(codes),
            "share": round(len(touched) / len(codes), 3), **{f"n_{k}": by_type.get(k, 0) for k in sorted(RELATION)}}


def main() -> None:
    sources = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "outputs").glob("*_freeze"))
               if p.name.startswith(PREFIXES)]
    print("sources:", ", ".join(sources))
    subprocess.run([sys.executable, "scripts/build_chain_inputs.py", "--src", *sources, "--out", CHAIN], cwd=ROOT, check=True)
    edges, codes, rows = read(ROOT / CHAIN / "edges.csv"), core_codes(), []
    for day in DATES:
        snap = f"data/event_study/snapshots/{day}"
        subprocess.run([sys.executable, "scripts/run_propagation.py", "--chain", CHAIN, "--snapshot", snap], cwd=ROOT, check=True)
        rows.append(coverage(edges, codes, day))
    with (ROOT / CHAIN / "coverage.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['as_of']}: {r['active_relations']} active relations; {r['mills_covered']}/{r['mills']} mills covered")


if __name__ == "__main__":
    main()
