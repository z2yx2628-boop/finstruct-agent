"""One-click analysis: a new announcement in, a risk alert card out (directions 1 -> 2 -> 3).

    analyze(path)                       # task detected from the text, evaluated as of today
    analyze(path, task="guarantee", as_of="2025-01-31", chain="data/chain/backtest_antai")

Steps: parse + extract with the frozen system (1) -> turn the result into signals and edges
-> add them to the existing chain -> look up fragility tiers from the latest snapshot on or
before `as_of` (2) -> propagate from THIS document's signals only (3) -> alert card.
Everything the card says carries its evidence (document, page, sentence).
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from src.chain_inputs import as_row, edges_from, signals_from
from src.entity_resolver import ROOT, load_entities
from src.propagation import Graph, SUBSIDIARY, opaque_guarantee_seeds, propagate, summarize

TASK_KEYWORDS = [  # checked on the first pages; first match wins
    ("related_party", re.compile(r"日常关[联连]交易|日常经营相关的关[联连]交易|持续关[联连]交易")),
    ("guarantee", re.compile(r"担保")),
    ("pledge", re.compile(r"质押")),
    ("capacity", re.compile(r"停产|检修|产能|投产|技术改造|技改|建设项目|高炉|转炉|电炉|项目")),
]
SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "info": 0}
RULE_LABEL = {"R1": "担保", "R2": "供需", "R3": "同集团", "R4": "行业(近似)"}
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强", "unknown": "未评分"}
SIGNAL_LABEL = {"credit_exposure": "担保敞口", "credit_event": "担保违约/代偿", "supply_disruption": "供应中断",
                "capacity_reduction": "产能减少", "capacity_increase": "产能增加", "project_delay": "项目延期/终止",
                "share_pledge": "股权质押"}


def flat(text: str | None, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def detect_task(text: str) -> str:
    head = text[:3000]
    for task, pattern in TASK_KEYWORDS:
        if pattern.search(head):
            return task
    return "capacity"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def snapshot_for(as_of: str) -> Path | None:
    snaps = sorted(d for d in (ROOT / "data" / "snapshots").glob("*") if (d / "fragility.csv").exists() and d.name <= as_of)
    return snaps[-1] if snaps else None


def build_card(doc: dict, source: str, as_of: str, chain: Path) -> dict:
    """Directions 2 and 3 for an already-extracted document (no model call; testable)."""
    new_edges = [as_row(e) for e in edges_from(doc, source)[0]]
    new_signals = [as_row(s) for s in signals_from(doc, source)]
    snap = snapshot_for(as_of)
    fragility = {r["security_code"]: r for r in _read(snap / "fragility.csv")} if snap else {}
    equity = {r["security_code"]: float(r["equity"]) for r in _read(snap / "quarterly_metrics.csv") if r.get("equity")} if snap else {}
    base = [e for e in _read(chain / "edges.csv") if (e.get("announcement_date") or "") <= as_of]
    rows, _ = load_entities()
    groups = {k: v["group_id"] for k, v in rows.items()}
    listed = {k for k, v in rows.items() if v.get("security_code")}
    names = {k: v["short_name"] for k, v in rows.items()}
    graph = Graph(base + new_edges, fragility, equity, groups, listed)

    seeds = {}
    for s in new_signals:
        shock = "supply" if s["signal_type"] in ("supply_disruption", "capacity_reduction") else \
                "credit" if s["signal_type"] in ("credit_event", "credit_exposure", "share_pledge") else None
        if shock and s["severity"] in ("medium", "high"):
            key = (s["entity_id"], shock)
            if key not in seeds or SEVERITY_ORDER[s["severity"]] > SEVERITY_ORDER[seeds[key][2]]:
                seeds[key] = (s["entity_id"], shock, s["severity"], f"{s['signal_type']}：{s['detail']}")
    seeds.update(opaque_guarantee_seeds(new_edges, fragility, equity, as_of))
    paths = []
    for node, shock, severity, reason in seeds.values():
        paths += propagate(graph, node, shock, severity, reason)
    ranked, reach = summarize(paths, listed)

    issuer = doc.get("security_code") or ""
    issuer_row = fragility.get(issuer, {})
    nm = lambda n: names.get(n, n[2:] if n.startswith("N_") else n)
    involved = sorted({e["src_id"] for e in new_edges} | {e["dst_id"] for e in new_edges} | {s["entity_id"] for s in new_signals})
    happened = {}
    for s in new_signals:
        key = (s["entity_id"], s["signal_type"], s["detail"])
        h = happened.setdefault(key, {"type": SIGNAL_LABEL.get(s["signal_type"], s["signal_type"]),
                                      "severity": s["severity"], "entity": nm(s["entity_id"]), "detail": s["detail"],
                                      "rule": s["severity_rule"], "rows": 0, "magnitude": 0.0,
                                      "evidence": f"第{s['source_page']}页：{flat(s['evidence_text'])}"})
        h["rows"] += 1
        h["magnitude"] += float(s["magnitude"]) if s.get("magnitude") not in ("", None) else 0.0
    relations = {}
    for e in new_edges:
        key = (e["src_id"], e["dst_id"], e["edge_type"])
        r = relations.setdefault(key, {"type": e["edge_type"], "from": nm(e["src_id"]), "to": nm(e["dst_id"]),
                                       "amount_yi": 0.0, "rows": 0, "relationship": e["relationship"],
                                       "evidence": f"第{e['source_page']}页：{flat(e['evidence_text'])}"})
        r["rows"] += 1
        r["amount_yi"] += float(e["amount_wan"]) / 1e4 if e["amount_wan"] not in ("", None) else 0.0
    return {
        "as_of": as_of, "source": source, "snapshot": snap.name if snap else None,
        "company": doc.get("company_name") or doc.get("security_name") or issuer,
        "announcement_date": doc.get("announcement_date"),
        "what_happened": list(happened.values()),
        "relations": [dict(r, amount_yi=round(r["amount_yi"], 2)) for r in relations.values()],
        "can_they_absorb": [{"entity": nm(c), "tier": fragility[c].get("tier_label") or fragility[c].get("tier"),
                             "score": fragility[c].get("total_score"), "reasons": fragility[c].get("reasons")}
                            for c in involved if c in fragility] or
                           ([{"entity": nm(issuer), "tier": issuer_row.get("tier_label"), "score": issuer_row.get("total_score"),
                              "reasons": issuer_row.get("reasons")}] if issuer_row else []),
        "who_is_next": [{"rank": i, "score": e["score"],
                         "path": nm(e["seed"]) + "".join(f" →[{RULE_LABEL[s.rule]}] {nm(s.dst)}({TIER_LABEL.get(s.dst_tier, s.dst_tier)})"
                                                         for s in e["steps"]),
                         "steps": [dict(asdict(s), src_name=nm(s.src), dst_name=nm(s.dst), rule_label=RULE_LABEL[s.rule],
                                        tier_label=TIER_LABEL.get(s.dst_tier, s.dst_tier), evidence=flat(s.evidence, 200))
                                   for s in e["steps"]],
                         "alternatives": e.get("alternatives", 0),
                         "alternative_routes": sorted({"+".join(RULE_LABEL[r] for r in route.split("+"))
                                                       for route in e.get("alternative_routes", [])}),
                         "reason": e["reason"]} for i, e in enumerate(ranked[:10], 1)],
        "unlisted_reach": [{"from": nm(r["seed"]), "parties": len(r["parties"]),
                            "amount_yi": round(r["amount_wan"] / 1e4, 2)} for r in reach[:5]],
        "counts": {"signals": len(new_signals), "edges": len(new_edges), "paths": len(paths)},
    }


def card_markdown(card: dict) -> str:
    lines = [f"# 风险预警 · {card['company']} · 评估日 {card['as_of']}",
             f"来源：{card['source']}（公告日 {card['announcement_date']}；承压快照 {card['snapshot']}）", ""]
    lines.append("## ① 发生了什么")
    if not card["what_happened"]:
        lines.append("- 未识别出风险信号。")
    for w in card["what_happened"]:
        rows = f"（{w['rows']}行）" if w["rows"] > 1 else ""
        lines.append(f"- [{w['severity']}] {w['entity']} · {w['type']}：{w['detail']}{rows}。判定规则：{w['rule']}。"
                     f"依据 {w['evidence']}")
    for r in card["relations"][:10]:
        amount = f"，合计 {r['amount_yi']} 亿元" if r["amount_yi"] else ""
        rows = f"（{r['rows']}行）" if r["rows"] > 1 else ""
        lines.append(f"- 关系：{r['from']} →[{r['type']}] {r['to']}{amount}{rows}，关系 {r['relationship']}。依据 {r['evidence']}")
    lines += ["", "## ② 扛不扛得住"]
    for c in card["can_they_absorb"] or [{"entity": card["company"], "tier": "未评分", "score": "", "reasons": ""}]:
        lines.append(f"- {c['entity']}：{c['tier']}（{c['score']}分）{c['reasons'] or ''}")
    lines += ["", "## ③ 会传给谁"]
    if not card["who_is_next"]:
        lines.append("- 未发现需要关注的传导路径（风险被强企业吸收、金额不重大，或本公告只含低严重度信号）。")
    for p in card["who_is_next"]:
        alt = f"（另有 {p['alternatives']} 条同类路线，经由：{'、'.join(p['alternative_routes'])}）" if p["alternatives"] else ""
        lines.append(f"- {p['rank']}. {p['path']} · 得分 {p['score']}{alt}")
        lines.append(f"    - 起点：{p['reason']}")
        for s in p["steps"]:
            lines.append(f"    - {s['rule_label']}：{s['src_name']} → {s['dst_name']}（{s['tier_label']}），{s['decision']} · 依据 {s['evidence']}")
    return "\n".join(lines)


def analyze(path: str | Path, task: str | None = None, as_of: str | None = None,
            chain: str | Path = "data/chain/analysis_v1") -> dict:
    from src.document_parser import parse_document
    from src.pipeline import run_pipeline

    path = Path(path)
    as_of = as_of or date.today().isoformat()
    if task is None:
        parsed = parse_document(path)
        task = detect_task("\n".join(p.text for p in parsed.pages[:2]))
    result = run_pipeline(path, task=task)
    doc = json.loads(Path(result["prediction_path"]).read_text(encoding="utf-8"))
    card = build_card(doc, str(Path(result["prediction_path"]).relative_to(ROOT)), as_of, ROOT / chain)
    card.update({"task": task, "extraction_status": result["status"]})
    out = Path(result["run_directory"])
    (out / "alert_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "alert_card.md").write_text(card_markdown(card), encoding="utf-8")
    card["card_path"] = str(out / "alert_card.md")
    return card
