"""风险传导总图: ONE graph, TWO channels.

  集团信用通道 (scored)   : disclosed guarantees, related-party trades, group links (R1/R2/R3) — the key paths
  供需情景通道 (scenario) : product exposure, disclosed/named purchases and sales, industry inference (S0–S6)

They share nodes (the same companies, the same fragility tiers) and are drawn in one picture, but the
colours, the evidence grade and the scoring stay separate: only the credit channel feeds the ranking.
A shock in the supply channel continues into the credit channel only through the gated bridge
(A/B exposure + disclosed share + weak/medium tier; guarantees and related-party trades only).
"""
from __future__ import annotations

import math

from src.network_view import evidence_grade, name_of
from src.scenario import RULES as SUPPLY_RULES
from src.scenario import TIER_LABEL

CREDIT = {"R1": "担保（信用·计分）", "R2": "关联交易（信用·计分）", "R3": "同集团（信用·计分）"}
SUPPLY = {code: f"{label}·情景" for code, label in SUPPLY_RULES.items()}
SCALE = ([*CREDIT.values(), *SUPPLY.values()],
         ["#c0392b", "#e67e22", "#922b21",                                  # credit: reds
          "#222222", "#2e86c1", "#1f618d", "#7f8c8d", "#5b2c6f", "#16a085", "#2874a6"])   # supply: blues/greys
DASHED = {"R3", "S3"}                     # membership-only / industry-inferred links are drawn dashed


def credit_edges(entries: list[dict], names: dict[str, str], fragility: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    nodes, edges = {}, []
    for e in entries:
        for s in e["steps"]:
            for n in (s.src, s.dst):
                nodes.setdefault(n, {"node": n, "name": name_of(n, names), "kind": "企业",
                                     "tier": fragility.get(n, {}).get("tier", "")})
            if not any(x["src"] == s.src and x["dst"] == s.dst and x["rule"] == s.rule for x in edges):
                edges.append({"src": s.src, "dst": s.dst, "rule": s.rule, "channel": "credit", "grade": evidence_grade(s),
                              "effect": f"{CREDIT[s.rule].split('（')[0]}{f' {s.amount_wan / 1e4:.1f}亿' if s.amount_wan else ''}",
                              "evidence": s.evidence, "amount_wan": s.amount_wan, "share": None})
    return list(nodes.values()), edges


def merge(supply: dict | None, credit_nodes: list[dict], credit: list[dict]) -> dict:
    nodes = {n["node"]: dict(n) for n in (supply or {}).get("nodes", [])}
    for n in credit_nodes:
        nodes.setdefault(n["node"], n)
    edges = [dict(e, channel="supply") for e in (supply or {}).get("edges", [])] + credit
    return {"nodes": list(nodes.values()), "edges": edges}


def layout(graph: dict) -> tuple[list[dict], list[dict]]:
    """Columns by shortest distance from the roots (nodes nobody points to, or the shock); fits overview_chart."""
    from collections import deque
    ids = [n["node"] for n in graph["nodes"]]
    incoming = {e["dst"] for e in graph["edges"]}
    roots = ["SHOCK"] if "SHOCK" in ids else [i for i in ids if i not in incoming] or ids[:1]
    depth = {r: 0 for r in roots}
    queue = deque(roots)
    while queue:
        cur = queue.popleft()
        for e in graph["edges"]:
            if e["src"] == cur and e["dst"] not in depth:
                depth[e["dst"]] = depth[cur] + 1
                queue.append(e["dst"])
    for i in ids:
        depth.setdefault(i, 0)
    kinds = {n["node"]: n for n in graph["nodes"]}
    columns: dict[int, list[str]] = {}
    for i in ids:
        columns.setdefault(depth[i], []).append(i)
    y = {}
    for d, col in columns.items():
        col.sort(key=lambda i: (kinds[i]["kind"], kinds[i]["name"]))
        for j, i in enumerate(col):
            y[i] = (len(col) - 1) / 2 - j
    nodes = [{"node": n["node"], "name": n["name"], "kind": n["kind"], "x": float(depth[n["node"]]), "y": y[n["node"]],
              "tier": n.get("tier") or "unknown",
              "tier_label": TIER_LABEL.get(n.get("tier", ""), "未评分" if n["kind"] == "企业" else n["kind"]),
              "seed": n["node"] == "SHOCK", "paths": 1, "best": 0.0, "on": True} for n in graph["nodes"]]
    edges = []
    for e in graph["edges"]:
        x1, y1, x2, y2 = float(depth[e["src"]]), y[e["src"]], float(depth[e["dst"]]), y[e["dst"]]
        amount = (e.get("amount_wan") or 0) / 1e4
        label = (CREDIT if e["channel"] == "credit" else SUPPLY)[e["rule"]]
        edges.append({"edge": f"{e['src']}|{e['dst']}|{e['rule']}", "src": kinds[e["src"]]["name"], "dst": kinds[e["dst"]]["name"],
                      "rule": label, "rule_code": "R3" if e["rule"] in DASHED else e["rule"], "grade": e["grade"],
                      "x": x1, "y": y1, "x2": x2, "y2": y2, "mx": x1 + (x2 - x1) * 0.62, "my": y1 + (y2 - y1) * 0.62,
                      "amount_yi": round(amount, 2), "label": e["effect"].split("（")[0][:10], "span": abs(x2 - x1),
                      "width": 1.4 + (min(math.log10(1 + amount), 2.5) * 1.6 if amount else (e.get("share") or 0) * 3),
                      "paths": 1, "first_path": 0, "on": True})
    return nodes, edges
