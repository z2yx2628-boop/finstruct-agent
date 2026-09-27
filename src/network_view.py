"""Risk-path network for the Streamlit graph page: compute key paths and draw them as Graphviz DOT."""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from src.entity_resolver import ROOT, groups_as_of, load_entities
from src.propagation import SEVERITY_WEIGHT, TIER_WEIGHT, Graph, propagate, seeds_from, summarize
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
    groups = groups_as_of(as_of)          # same point-in-time group membership as run_propagation.py
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


# ---------------------------------------------------------------- interactive page helpers
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强", "unknown": "未评分"}
SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}
DECISION_LABEL = {"continue": "继续传导", "weakened": "继续传导（减弱）", "absorbed": "被吸收，停止",
                  "immaterial": "金额不重大，停止", "end": "已减弱至最低，停止"}


GRADE_LABEL = {"A": "A 披露确认", "B": "B 部分确认", "C": "C 行业推断"}
GRADE_HELP = {"A": "公告或年报写明双方（和金额），或股权关系已核对来源",
              "B": "产品暴露或集团归属：有依据但未写明具体交易对手，或集团归属未逐一核对",
              "C": "按行业分类推断的潜在关系，只作情景提示，不是实际交易，不计入路径得分"}


def evidence_grade(step) -> str:
    """A = disclosed by an announcement (or a verified shareholding), B = partly confirmed,
    C = industry-level inference. Stated on every edge so a C-grade link is never read as a real trade."""
    if step.rule == "R4" or step.basis == "industry_approx":
        return "C"
    if step.rule == "R3":
        rows, _ = load_entities()
        verified = any(rows.get(n, {}).get("group_verified") == "Y" for n in (step.src, step.dst))
        return "A" if verified else "B"
    if step.basis == "product_exposure":
        return "B"
    return "A" if step.basis == "disclosed" else "B"


def path_grade(entry: dict) -> str:
    return max(evidence_grade(s) for s in entry["steps"])        # the weakest link decides ("A" < "B" < "C")


def route(entry: dict, names: dict[str, str]) -> str:
    return " → ".join([name_of(entry["seed"], names)] + [name_of(s.dst, names) for s in entry["steps"]])


def is_low_information(entry: dict) -> bool:
    """Only same-group steps and no amount anywhere: a membership fact, not a disclosed exposure."""
    return all(s.rule == "R3" for s in entry["steps"]) and not any(s.amount_wan for s in entry["steps"])


def filter_paths(ranked: list[dict], rules: set[str] | None = None, min_amount_yi: float = 0.0,
                 company: str | None = None, hide_low_information: bool = False,
                 show_scenarios: bool = True) -> list[tuple[int, dict]]:
    """Display filter only: returns (original rank index, entry); the ranking itself is never changed."""
    out = []
    for i, e in enumerate(ranked):
        if not show_scenarios and e.get("scenario"):
            continue
        if rules is not None and not {s.rule for s in e["steps"]} & rules:
            continue
        if e.get("amount_yi", 0) < min_amount_yi:
            continue
        if company and company != e["seed"] and all(company not in (s.src, s.dst) for s in e["steps"]):
            continue
        if hide_low_information and is_low_information(e):
            continue
        out.append((i, e))
    return out


def path_rows(items: list[tuple[int, dict]], names: dict[str, str]) -> list[dict]:
    rows = []
    for i, e in items:
        last = e["steps"][-1]
        rows.append({"排名": i + 1, "传导路径": route(e, names),
                     "规则": "+".join(RULE_LABEL[s.rule] for s in e["steps"]),
                     "金额(亿元)": e.get("amount_yi", 0.0),
                     "终点": name_of(last.dst, names), "终点承压": TIER_LABEL.get(last.dst_tier, last.dst_tier),
                     "证据等级": path_grade(e) + ("（情景）" if e.get("scenario") else ""),
                     "得分": e["score"]})
    return rows


def score_parts(entry: dict) -> dict:
    """The three factors of the score, as printed on the page (see propagation.summarize)."""
    import math
    severity = entry["steps"][0].severity
    amount = entry.get("amount_yi", 0.0)
    return {"severity": severity, "severity_weight": SEVERITY_WEIGHT[severity],
            "amount_yi": amount, "amount_factor": round(1 + math.log10(1 + amount), 2),
            "reach": entry.get("listed_reach", 0.0),
            "reached": [(s.dst, s.dst_tier, TIER_WEIGHT.get(s.dst_tier, 0.0)) for s in entry["steps"]
                        if s.dst_tier in TIER_WEIGHT]}


def stop_reason(entry: dict, names: dict[str, str]) -> str:
    last = entry["steps"][-1]
    if last.decision in ("absorbed", "immaterial", "end"):
        return f"止于{name_of(last.dst, names)}：{DECISION_LABEL[last.decision]}"
    if entry.get("beyond"):
        return (f"最后一家上市公司为{name_of(last.dst, names)}；其后还波及 {len(entry['beyond'])} 家集团内非上市公司"
                f"（约 {entry.get('beyond_amount_wan', 0) / 1e4:.2f} 亿元）")
    return f"止于{name_of(last.dst, names)}：没有更多满足条件的关系（或已达最多 3 步）"


EVIDENCE_REF = re.compile(r"(?P<path>\S*?(?P<stem>[A-Za-z0-9_]+)(?:/prediction)?\.json)(?:\s*第\s*(?P<page>\d+)\s*页)?[：:]?\s*(?P<quote>.*)",
                          re.S)


def evidence_ref(evidence: str) -> dict:
    """'outputs/x_freeze/task/<stem>.json 第4页：quote' -> {stem, page, quote}; other evidence -> {quote}."""
    m = EVIDENCE_REF.match((evidence or "").strip())
    if not m:
        return {"stem": None, "page": None, "quote": (evidence or "").strip()}
    return {"stem": m.group("stem"), "page": int(m.group("page")) if m.group("page") else None,
            "quote": m.group("quote").strip()}


@lru_cache(maxsize=1)
def _raw_index() -> dict[str, str]:
    out = {}
    for p in (ROOT / "data" / "raw").glob("*/*"):
        if p.suffix.lower() in (".pdf", ".html", ".htm", ".docx", ".doc", ".xls", ".xlsx"):
            out.setdefault(p.stem, str(p))
    return out


def source_file(stem: str | None) -> Path | None:
    path = _raw_index().get(stem or "")
    return Path(path) if path else None


def edge_windows(chain: Path) -> dict[tuple[str, str, str], dict]:
    """(src_id, dst_id, document stem) -> announcement date and validity window of that edge."""
    out = {}
    for e in _read(chain / "edges.csv"):
        stem = Path(e.get("source_doc", "")).stem
        out.setdefault((e["src_id"], e["dst_id"], stem), {"announcement_date": e.get("announcement_date", ""),
                                                          "valid_from": e.get("valid_from", ""),
                                                          "valid_to": e.get("valid_to", "")})
    return out


def page_png(pdf: Path, page: int, zoom: float = 1.6) -> bytes | None:
    """One PDF page as PNG, for showing the evidence page next to the quote."""
    try:
        import fitz
        with fitz.open(pdf) as doc:
            if not 1 <= page <= doc.page_count:
                return None
            return doc[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    except Exception:
        return None


def focus_entries(ranked: list[dict], index: int) -> list[dict]:
    """The chosen path plus every other ranked path that shares a company with it (its one-step neighbourhood)."""
    chosen = ranked[index]
    nodes = {chosen["seed"]} | {s.dst for s in chosen["steps"]}
    others = [e for j, e in enumerate(ranked) if j != index
              and ({e["seed"]} | {s.src for s in e["steps"]} | {s.dst for s in e["steps"]}) & nodes]
    return [chosen] + others[:8]


# ---------------------------------------------------------------- clickable overview graph (Altair, no extra dependency)
RULE_ORDER = ["R1", "R2", "R3", "R4"]
TIER_ORDER = ["weak", "medium", "strong", "unknown"]


def overview_layout(items: list[tuple[int, dict]], fragility: dict[str, dict], names: dict[str, str],
                    chosen: int | None = None) -> tuple[list[dict], list[dict]]:
    """Nodes and edges of the displayed paths, laid out in layers (seed = column 0, k-th step = column k).

    Deterministic (same input, same picture): columns are ordered by the mean height of each node's
    predecessors, so edges cross as little as a single sweep allows. `chosen` is the original rank index
    of the highlighted path; its nodes and edges are flagged `on`."""
    import math
    depth, tier, seeds, through, best = {}, {}, set(), {}, {}
    edges: dict[tuple[str, str, str], dict] = {}
    for i, e in items:
        chain = [e["seed"]] + [s.dst for s in e["steps"]]
        seeds.add(e["seed"])
        tier.setdefault(e["seed"], fragility.get(e["seed"], {}).get("tier") or "unknown")
        for k, n in enumerate(chain):
            depth[n] = min(depth.get(n, k), k)
            through.setdefault(n, set()).add(i)
            best[n] = max(best.get(n, 0.0), e["score"])
        for s in e["steps"]:
            tier[s.dst] = s.dst_tier or tier.get(s.dst, "unknown")
            key = (s.src, s.dst, s.rule)
            info = edges.setdefault(key, {"amount_wan": 0.0, "paths": [], "grade": evidence_grade(s)})
            info["amount_wan"] = max(info["amount_wan"], s.amount_wan or 0.0)
            info["paths"].append(i)
    # longest-path layering on the displayed subgraph, cycles broken by DFS back edges, so almost every
    # edge points one column to the right (min-depth layering put many edges inside a column)
    succ: dict[str, list[str]] = {}
    for (a, b, _) in edges:
        if b not in succ.setdefault(a, []):
            succ[a].append(b)
    state, back = {}, set()

    def visit(n: str) -> None:
        state[n] = 1
        for m in succ.get(n, []):
            if state.get(m) == 1:
                back.add((n, m))
            elif m not in state:
                visit(m)
        state[n] = 2
    for n in sorted(depth, key=lambda n: (depth[n], -best[n], name_of(n, names))):
        if n not in state:
            visit(n)
    preds: dict[str, list[str]] = {}
    for a, outs in succ.items():
        for b in outs:
            if (a, b) not in back and a != b:
                preds.setdefault(b, []).append(a)
    layer: dict[str, int] = {}

    def lay(n: str, seen: frozenset = frozenset()) -> int:
        if n not in layer:
            ps = [p for p in preds.get(n, []) if p not in seen]
            layer[n] = 0 if not ps else 1 + max(lay(p, seen | {n}) for p in ps)
        return layer[n]
    for n in depth:
        lay(n)
    depth = layer
    columns: dict[int, list[str]] = {}
    for n, d in depth.items():
        columns.setdefault(d, []).append(n)
    y: dict[str, float] = {}

    def place(order: dict[int, list[str]]) -> None:
        for d, nodes in order.items():
            for j, n in enumerate(nodes):
                y[n] = (len(nodes) - 1) / 2 - j          # compact, centred columns
    for d in sorted(columns):
        columns[d].sort(key=lambda n: (-best[n], name_of(n, names)))
    place(columns)
    for sweep in range(2):                                   # barycentre sweeps: left-to-right, then right-to-left
        for d in (sorted(columns) if sweep == 0 else sorted(columns, reverse=True)):
            def bary(n: str) -> float:
                ys = [y[a] for (a, b, _) in edges if b == n and a != n] if sweep == 0 else \
                     [y[b] for (a, b, _) in edges if a == n and b != n]
                return sum(ys) / len(ys) if ys else y[n]
            columns[d].sort(key=lambda n: (-bary(n), name_of(n, names)))
            place({d: columns[d]})
    chosen_nodes, chosen_edges = set(), set()
    for i, e in items:
        if i == chosen:
            chosen_nodes = {e["seed"]} | {s.dst for s in e["steps"]}
            chosen_edges = {(s.src, s.dst, s.rule) for s in e["steps"]}
    node_rows = [{"node": n, "name": name_of(n, names), "x": float(depth[n]), "y": y[n],
                  "tier": tier.get(n, "unknown"), "tier_label": TIER_LABEL.get(tier.get(n, "unknown"), "未评分"),
                  "seed": n in seeds, "paths": len(through[n]), "best": best[n],
                  "on": chosen is None or n in chosen_nodes} for n in depth]
    edge_rows = []
    for (a, b, rule), info in edges.items():
        x1, y1, x2, y2 = float(depth[a]), y[a], float(depth[b]), y[b]
        if (b, a, rule) in edges or (b, a) in {(p, q) for (p, q, _) in edges}:      # two-way: offset sideways
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            off = 0.12 if a < b else -0.12
            x1, x2 = x1 - dy / length * off, x2 - dy / length * off
            y1, y2 = y1 + dx / length * off, y2 + dx / length * off
        amount = info["amount_wan"] / 1e4
        edge_rows.append({"edge": f"{a}|{b}|{rule}", "src": name_of(a, names), "dst": name_of(b, names),
                          "rule": RULE_LABEL[rule], "rule_code": rule, "grade": GRADE_LABEL[info["grade"]], "x": x1, "y": y1, "x2": x2, "y2": y2,
                          "mx": x1 + (x2 - x1) * 0.62, "my": y1 + (y2 - y1) * 0.62,
                          "amount_yi": round(amount, 2),
                          # only disclosed amounts are labelled; same-group links carry no amount and would only add clutter
                          "label": f"{RULE_LABEL[rule]} {amount:.1f}亿" if amount else "",
                          "span": abs(depth[b] - depth[a]),
                          "width": 1.2 if rule == "R3" else 1.4 + min(math.log10(1 + amount), 2.5) * 1.6,
                          "paths": len(info["paths"]),
                          "first_path": min(info["paths"]), "on": chosen is None or (a, b, rule) in chosen_edges})
    return node_rows, edge_rows


SCENARIO_RULE_SCALE = (["冲击", "产品暴露（B）", "披露采购/销售（A）", "行业用钢（C）", "下游企业"],
                       ["#222222", "#2e86c1", "#c0392b", "#7f8c8d", "#8e44ad"])


def overview_chart(node_rows: list[dict], edge_rows: list[dict], width: int = 900, height: int = 440,
                   rule_scale: tuple[list[str], list[str]] | None = None) -> dict:
    """Plain Vega-Lite spec (no Altair API, rendered by st.vega_lite_chart): edges, arrowheads, clickable edge
    labels, clickable company nodes, names. Selections are top-level params `company` (node click) and
    `link` (edge-label click), bound to their layers by name, which is the form Streamlit reads."""
    import math
    xs = [n["x"] for n in node_rows] + [e["x"] for e in edge_rows] + [e["x2"] for e in edge_rows]
    ys = [n["y"] for n in node_rows] + [e["y"] for e in edge_rows] + [e["y2"] for e in edge_rows]
    xdom, ydom = [min(xs) - 0.45, max(xs) + 0.45], [min(ys) - 0.7, max(ys) + 0.7]
    sx, sy = width / (xdom[1] - xdom[0]), height / (ydom[1] - ydom[0])
    edges = [dict(e, angle=round((90 - math.degrees(math.atan2((e["y2"] - e["y"]) * sy, (e["x2"] - e["x"]) * sx))) % 360, 1))
             for e in edge_rows]
    q = lambda field, domain: {"field": field, "type": "quantitative", "scale": {"domain": domain}, "axis": None}
    domain, colors = rule_scale or ([RULE_LABEL[r] for r in RULE_ORDER], [RULE_COLOR[r] for r in RULE_ORDER])
    rule_color = {"field": "rule", "type": "nominal", "legend": None, "scale": {"domain": domain, "range": colors}}
    node_rows = [dict(n, kind=n.get("kind", "企业")) for n in node_rows]
    fade = {"condition": {"test": "datum.on", "value": 0.95}, "value": 0.15}
    # edges: faded when not on the chosen path; links that skip a column are drawn lighter so they do not
    # read as passing through the companies they cross
    edge_fade = {"condition": [{"test": "!datum.on", "value": 0.12}, {"test": "datum.span > 1", "value": 0.4}], "value": 0.9}
    tip_edge = [{"field": "src", "title": "从"}, {"field": "dst", "title": "到"}, {"field": "rule", "title": "规则"},
                {"field": "grade", "title": "证据等级"},
                {"field": "amount_yi", "type": "quantitative", "title": "金额(亿元)", "format": ".2f"},
                {"field": "paths", "type": "quantitative", "title": "经过的路径数"}]
    tip_node = [{"field": "name", "title": "企业"}, {"field": "tier_label", "title": "承压"},
                {"field": "paths", "type": "quantitative", "title": "经过的路径数"},
                {"field": "best", "type": "quantitative", "title": "最高路径得分", "format": ".2f"}]
    at_mid = {"x": q("mx", xdom), "y": q("my", ydom)}
    at_node = {"x": q("x", xdom), "y": q("y", ydom)}
    layers = [
        {"name": "edges", "data": {"values": edges}, "mark": {"type": "rule"},
         "encoding": {**at_node, "x2": {"field": "x2"}, "y2": {"field": "y2"},
                      "color": dict(rule_color, legend={"title": "传导规则", "orient": "bottom"}),
                      "strokeWidth": {"field": "width", "type": "quantitative", "scale": None, "legend": None},
                      "strokeDash": {"condition": {"test": "datum.rule_code == 'R4' || datum.rule_code == 'R3'", "value": [5, 4]},
                                     "value": [1, 0]},
                      "opacity": edge_fade, "tooltip": tip_edge}},
        {"name": "heads", "data": {"values": edges}, "mark": {"type": "point", "shape": "triangle-up", "filled": True, "size": 110},
         "encoding": {**at_mid, "angle": {"field": "angle", "type": "quantitative", "scale": None},
                      "color": rule_color, "opacity": edge_fade, "tooltip": tip_edge}},
        {"name": "edge_labels", "data": {"values": edges},
         "mark": {"type": "text", "dy": -11, "fontSize": 12, "fontWeight": "bold", "cursor": "pointer"},
         "encoding": {**at_mid, "text": {"field": "label"}, "color": rule_color, "opacity": edge_fade, "tooltip": tip_edge}},
        {"name": "rings", "data": {"values": [n for n in node_rows if n["seed"]]},
         "mark": {"type": "point", "shape": "circle", "filled": False, "stroke": "#222222", "strokeWidth": 2.5, "size": 2000},
         "encoding": {**at_node, "opacity": fade}},
        {"name": "nodes", "data": {"values": node_rows},
         "mark": {"type": "point", "filled": True, "stroke": "white", "strokeWidth": 1.5, "cursor": "pointer"},
         "encoding": {**at_node, "size": {"field": "paths", "type": "quantitative", "scale": {"range": [420, 1500]}, "legend": None},
                      "shape": {"field": "kind", "type": "nominal",
                                "scale": {"domain": ["企业", "产品", "行业", "冲击"], "range": ["circle", "square", "diamond", "triangle-down"]},
                                "legend": None if len({n["kind"] for n in node_rows}) == 1 else {"title": "节点", "orient": "bottom"}},
                      "color": {"field": "tier_label", "type": "nominal",
                                "scale": {"domain": [TIER_LABEL[t] for t in TIER_ORDER] + ["产品", "行业", "冲击"],
                                          "range": [TIER_STYLE[t][1] for t in TIER_ORDER] + ["#2e86c1", "#95a5a6", "#222222"]},
                                "legend": {"title": "承压等级（点企业筛选）", "orient": "bottom"}},
                      "opacity": fade, "tooltip": tip_node}},
        {"name": "names", "data": {"values": node_rows}, "mark": {"type": "text", "dy": 28, "fontSize": 13, "fontWeight": "bold"},
         "encoding": {**at_node, "text": {"field": "name"}, "opacity": fade, "tooltip": tip_node}},
    ]
    return {"$schema": "https://vega.github.io/schema/vega-lite/v6.json", "width": width, "height": height,
            "params": [{"name": "company", "select": {"type": "point", "fields": ["node"], "on": "click", "clear": "dblclick"},
                        "views": ["nodes"]},
                       {"name": "link", "select": {"type": "point", "fields": ["edge"], "on": "click", "clear": "dblclick"},
                        "views": ["edge_labels"]}],
            "layer": layers,
            "resolve": {"scale": {"color": "independent", "size": "independent", "shape": "independent"},
                        "legend": {"color": "independent", "shape": "independent"}},
            "config": {"view": {"stroke": None}, "font": "Microsoft YaHei, PingFang SC, sans-serif"}}
