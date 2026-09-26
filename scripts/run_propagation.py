"""Find risk propagation paths on a chain build, using a fragility snapshot.

    python scripts/run_propagation.py --chain data/chain/analysis_v1 --snapshot data/snapshots/2026-09-24
Writes <chain>/paths_<as_of>.json and paths_<as_of>.md (one line per path, with evidence).
"""
import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolver import load_entities  # noqa: E402
from src.propagation import Graph, propagate, seeds_from  # noqa: E402

LABEL = {"R1": "担保", "R2": "供需", "R3": "同集团", "R4": "行业(近似)"}
TIER = {"weak": "弱", "medium": "中", "strong": "强", "unknown": "未评分"}


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default="data/chain/analysis_v1")
    ap.add_argument("--snapshot", default=None, help="data/snapshots/<date>; default: latest")
    args = ap.parse_args()
    chain = ROOT / args.chain
    snaps = sorted(d for d in (ROOT / "data" / "snapshots").glob("*") if (d / "fragility.csv").exists())
    snap = ROOT / args.snapshot if args.snapshot else snaps[-1]
    as_of = snap.name
    fragility = {r["security_code"]: r for r in read(snap / "fragility.csv")}
    equity = {r["security_code"]: float(r["equity"]) for r in read(snap / "quarterly_metrics.csv") if r.get("equity")}
    rows, _ = load_entities()
    groups = {k: v["group_id"] for k, v in rows.items()}
    listed = {k for k, v in rows.items() if v.get("security_code")}
    graph = Graph(read(chain / "edges.csv"), fragility, equity, groups, listed)
    names = {k: v["short_name"] for k, v in rows.items()}

    paths = []
    for node, shock, severity, reason in seeds_from(read(chain / "signals.csv"), fragility, as_of):
        paths += propagate(graph, node, shock, severity, reason)
    paths.sort(key=lambda p: (-len(p.steps), p.seed))

    (chain / f"paths_{as_of}.json").write_text(
        json.dumps([asdict(p) for p in paths], ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# 风险传导路径（评估日 {as_of}，图 {args.chain}）", "",
             f"共 {len(paths)} 条路径。每一步：规则 · 对方承压等级 · 结论 · 证据。", ""]
    for i, p in enumerate(paths, 1):
        chain_txt = names.get(p.seed, p.seed)
        for s in p.steps:
            chain_txt += f" →[{LABEL[s.rule]}] {names.get(s.dst, s.dst)}({TIER.get(s.dst_tier, s.dst_tier)})"
        lines.append(f"## {i}. {chain_txt}")
        lines.append(f"- 起点：{p.seed_reason}")
        for s in p.steps:
            lines.append(f"- {LABEL[s.rule]} {names.get(s.src, s.src)} → {names.get(s.dst, s.dst)}：{s.decision}"
                         f"（冲击 {s.shock}/{s.severity}；{s.note}）依据[{s.basis}] {s.evidence}")
        lines.append("")
    (chain / f"paths_{as_of}.md").write_text("\n".join(lines), encoding="utf-8")
    by_rule = {}
    for p in paths:
        for s in p.steps:
            by_rule[s.rule] = by_rule.get(s.rule, 0) + 1
    print(f"{len(paths)} paths as of {as_of}; steps by rule {by_rule}")
    print(f"-> {(chain / f'paths_{as_of}.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
