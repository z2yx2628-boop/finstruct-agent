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
from src.entity_resolver import groups_as_of, load_entities  # noqa: E402
from src.propagation import Graph, propagate, seeds_from, summarize  # noqa: E402
from src.validity import is_active  # noqa: E402

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
    groups = groups_as_of(as_of)          # group membership on the evaluation date
    listed = {k for k, v in rows.items() if v.get("security_code")}
    # Point in time: an edge from an announcement published after the evaluation date does not exist yet.
    edges = [e for e in read(chain / "edges.csv") if is_active(e, as_of)]   # in force on the evaluation date
    graph = Graph(edges, fragility, equity, groups, listed)
    names = {k: v["short_name"] for k, v in rows.items()}

    paths = []
    for node, shock, severity, reason in seeds_from(read(chain / "signals.csv"), fragility, as_of, edges, equity):
        paths += propagate(graph, node, shock, severity, reason)
    paths.sort(key=lambda p: (-len(p.steps), p.seed))

    (chain / f"paths_{as_of}.json").write_text(
        json.dumps([asdict(p) for p in paths], ensure_ascii=False, indent=2), encoding="utf-8")
    ranked, reach = summarize(paths, listed)
    nm = lambda n: names.get(n, n[2:] if n.startswith("N_") else n)
    lines = [f"# 风险传导路径（评估日 {as_of}，图 {args.chain}）", "",
             f"原始分支 {len(paths)} 条；按“最后一个上市公司”截断、并把途经相同上市公司的路线合并后为 {len(ranked)} 条关键路径。",
             "得分 = 起点严重程度(高3/中2/低1) × (1 + log10(1 + 沿途金额亿元)) × 途经上市公司承压(弱1/中0.5/强0)。",
             "", "## 关键路径 Top 20", ""]
    for i, e in enumerate(ranked[:20], 1):
        chain_txt = nm(e["seed"]) + "".join(
            f" →[{LABEL[s.rule]}] {nm(s.dst)}({TIER.get(s.dst_tier, s.dst_tier)})" for s in e["steps"])
        lines.append(f"### {i}. {chain_txt}")
        alt = f"；另有 {e['alternatives']} 条经不同集团子公司的同类路线" if e.get("alternatives") else ""
        lines.append(f"- 得分 {e['score']}（沿途金额 {e['amount_yi']} 亿元，途经上市公司承压合计 {e['listed_reach']}{alt}）")
        lines.append(f"- 起点：{e['reason']}")
        for s in e["steps"]:
            amount = f"，金额 {s.amount_wan / 1e4:.2f} 亿元" if s.amount_wan else ""
            lines.append(f"- {LABEL[s.rule]}：{nm(s.src)} → {nm(s.dst)}，{s.decision}{amount}"
                         f"（{s.note or '冲击 ' + s.shock + '/' + s.severity}）依据[{s.basis}] {s.evidence}")
        if e["beyond"]:
            lines.append(f"- 其后还波及 {len(e['beyond'])} 家集团内非上市公司，合计约 "
                         f"{e['beyond_amount_wan'] / 1e4:.2f} 亿元（见 JSON）")
        lines.append("")
    lines += ["## 仅波及非上市关联方的起点", "", "| 起点 | 波及非上市关联方 | 首步金额合计（亿元） | 起因 |", "| --- | --- | --- | --- |"]
    for r in reach[:20]:
        lines.append(f"| {nm(r['seed'])} | {len(r['parties'])} 家 | {r['amount_wan'] / 1e4:.2f} | {r['reason'][:60]} |")
    (chain / f"paths_{as_of}.md").write_text("\n".join(lines), encoding="utf-8")
    summary = [{"rank": i, "score": e["score"], "seed": e["seed"], "reason": e["reason"],
                "path": " → ".join([nm(e["seed"])] + [nm(s.dst) for s in e["steps"]]),
                "rules": "+".join(s.rule for s in e["steps"]), "amount_yi": e["amount_yi"],
                "beyond_unlisted": len(e["beyond"]), "alternatives": e.get("alternatives", 0)} for i, e in enumerate(ranked, 1)]
    with (chain / f"key_paths_{as_of}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]) if summary else ["rank"], lineterminator="\n")
        w.writeheader()
        w.writerows(summary)
    by_rule = {}
    for p in paths:
        for s in p.steps:
            by_rule[s.rule] = by_rule.get(s.rule, 0) + 1
    print(f"{len(paths)} raw branches -> {len(ranked)} key paths as of {as_of}; steps by rule {by_rule}")
    print(f"-> {(chain / f'paths_{as_of}.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
