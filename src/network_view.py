"""Risk-path network for the Streamlit graph page: compute key paths and draw them as Graphviz DOT."""
from __future__ import annotations

import csv
from pathlib import Path

from src.entity_resolver import ROOT, load_entities
from src.propagation import Graph, propagate, seeds_from, summarize
from src.validity import is_active

TIER_STYLE = {"weak": ("#fde2e2", "#c0392b"), "medium": ("#fff4d6", "#b9770e"),
              "strong": ("#e3f4e8", "#1e8449"), "unknown": ("#f0f0f0", "#7f8c8d")}
RULE_COLOR = {"R1": "#c0392b", "R2": "#2e86c1", "R3": "#7d3c98", "R4": "#7f8c8d"}
RULE_LABEL = {"R1": "担保", "R2": "供需", "R3": "同集团", "R4": "行业"}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def key_paths(chain: Path, snapshot: Path) -> tuple[list[dict], dict[str, dict], dict[str, str]]:
    as_of = snapshot.name
    fragility = {r["security_code"]: r for r in _read(snapshot / "fragility.csv")}
    equity = {r["security_code"]: float(r["equity"]) for r in _read(snapshot / "quarterly_metrics.csv") if r.get("equity")}
    rows, _ = load_entities()
    groups = {k: v["group_id"] for k, v in rows.items()}
    listed = {k for k, v in rows.items() if v.get("security_code")}
    names = {k: v["short_name"] for k, v in rows.items()}
    edges = [e for e in _read(chain / "edges.csv") if is_active(e, as_of)]
    graph = Graph(edges, fragility, equity, groups, listed)
    paths = []
    for node, shock, severity, reason in seeds_from(_read(chain / "signals.csv"), fragility, as_of, edges, equity):
        paths += propagate(graph, node, shock, severity, reason)
    ranked, _ = summarize(paths, listed)
    return ranked, fragility, names


def name_of(node: str, names: dict[str, str]) -> str:
    return names.get(node, node[2:] if node.startswith(("N_", "S_")) else node)


def to_dot(ranked: list[dict], fragility: dict[str, dict], names: dict[str, str], highlight: int | None = None) -> str:
    """One node per company (coloured by fragility tier), one edge per step (coloured by rule).
    Seeds get a thick border; the highlighted path is drawn bold and the rest faded."""
    nodes, edges = {}, {}
    for i, entry in enumerate(ranked):
        on = highlight is None or highlight == i
        nodes.setdefault(entry["seed"], {"seed": True, "on": False})["seed"] = True
        nodes[entry["seed"]]["on"] |= on
        for s in entry["steps"]:
            for n in (s.src, s.dst):
                nodes.setdefault(n, {"seed": False, "on": False})["on"] |= on
            key = (s.src, s.dst, s.rule)
            e = edges.setdefault(key, {"amount": s.amount_wan or 0, "on": False, "basis": s.basis})
            e["on"] |= on
    lines = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.7;',
             'node [shape=box, style="rounded,filled", fontname="Microsoft YaHei", fontsize=11];',
             'edge [fontname="Microsoft YaHei", fontsize=9];']
    for n, info in nodes.items():
        tier = fragility.get(n, {}).get("tier") or "unknown"
        fill, line = TIER_STYLE.get(tier, TIER_STYLE["unknown"])
        label = name_of(n, names) + ({"weak": "\\n弱", "medium": "\\n中", "strong": "\\n强"}.get(tier, ""))
        width = 3 if info["seed"] else 1.2
        faded = "" if info["on"] else ', fontcolor="#bbbbbb", color="#dddddd", fillcolor="#fafafa"'
        lines.append(f'"{n}" [label="{label}", fillcolor="{fill}", color="{line}", penwidth={width}{faded}];')
    for (src, dst, rule), e in edges.items():
        amount = f" {e['amount'] / 1e4:.1f}亿" if e["amount"] else ""
        style = "dashed" if e["basis"] == "industry_approx" else "solid"
        pen = 2.4 if e["on"] and highlight is not None else 1.4
        color = RULE_COLOR[rule] if e["on"] else "#dddddd"
        lines.append(f'"{src}" -> "{dst}" [label="{RULE_LABEL[rule]}{amount}", color="{color}", '
                     f'fontcolor="{color}", style={style}, penwidth={pen}];')
    lines.append("}")
    return "\n".join(lines)
