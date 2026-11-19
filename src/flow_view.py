"""风险传导 page, redrawn as three columns: who passes risk TO a company (left), the company or shock
(centre), and who it passes risk ON to (right), ordered from the strongest link down.

Nothing here changes how paths are found or scored (src/propagation.py, src/scenario.py): these functions
only regroup the existing paths by their far end, merge the middle hops into one "channel" label, rank
them, and draw them. One channel at a time: credit (scored) or supply (scenario).

Strength (0–1) is a display order, not a forecast:
  credit : path score / the largest score shown (the score is the scored ranking itself)
  supply : evidence weight (A 1.0, B 0.7, C 0.4) x size (disclosed amount, else revenue share, else 0.3)
"""
from __future__ import annotations

import math
from collections import deque

from src.network_view import TIER_LABEL, name_of, path_grade

GRADE_W = {"A": 1.0, "B": 0.7, "C": 0.4}
CREDIT_RULE = {"R1": "担保", "R2": "关联交易", "R3": "同集团", "R4": "行业"}
TOP = 8


def level(strength: float) -> str:
    return "高" if strength >= 0.5 else "中" if strength >= 0.3 else "低"


def supply_strength(grade: str, amount_wan: float | None = None, share: float | None = None) -> float:
    if amount_wan:
        size = min(1.0, 0.35 + math.log10(1 + amount_wan / 1e4) / 3)     # 1 亿 ≈ .45, 10 亿 ≈ .70, 100 亿 = 1
    elif share:
        size = min(1.0, 0.25 + share)
    else:
        size = 0.3
    return round(GRADE_W.get(grade, 0.4) * size, 3)


def _worst(grades) -> str:
    gs = [g for g in grades if g in GRADE_W]
    return max(gs) if gs else "C"                                       # "A" < "B" < "C": the weakest link decides


# ---------------------------------------------------------------- credit channel (scored key paths)
def credit_flows(entries: list[dict], names: dict[str, str], fragility: dict[str, dict], focus: str | None) -> dict:
    """-> {"left": [...], "right": [...]}. focus=None: every path goes right of its seed (shock mode)."""
    left, right = {}, {}
    for e in entries:
        nodes = [e["seed"]] + [s.dst for s in e["steps"]]
        rules = "+".join(dict.fromkeys(CREDIT_RULE.get(s.rule, s.rule) for s in e["steps"]))
        grade = path_grade(e)
        base = {"score": e["score"], "grade": grade, "amount_yi": e.get("amount_yi", 0.0), "rules": rules,
                "evidence": e["steps"][0].evidence}
        if focus is None or e["seed"] == focus:
            via = nodes[1:-1]
            far, side = nodes[-1], right
        elif focus in nodes[1:]:
            k = nodes.index(focus)
            if k < len(nodes) - 1:                      # passes through: what comes after it goes right
                far, via, side = nodes[-1], nodes[k + 1:-1], right
                _add(right, far, dict(base, via=via), names, fragility)
            far, via, side = nodes[0], nodes[1:k], left
        else:
            continue
        _add(side, far, dict(base, via=via), names, fragility)
    top = max([r["score"] for r in (*left.values(), *right.values())] or [1]) or 1
    out = {}
    for side, rows in (("left", left), ("right", right)):
        items = []
        for r in rows.values():
            channel = r["rules"] + ("：经 " + "、".join(name_of(v, names) for v in r["via"]) if r["via"] else "")
            absorbed = r["score"] <= 0
            items.append({"node": r["node"], "name": r["name"], "tier": r["tier"],
                          "channel": channel + ("（风险可能被缓释）" if absorbed else ""),
                          "grade": r["grade"], "strength": 0.05 if absorbed else round(max(0.08, r["score"] / top), 3),
                          "score": r["score"], "absorbed": absorbed,
                          "size": f"{r['amount_yi']:.1f} 亿" if r["amount_yi"] else "—", "evidence": r["evidence"], "kind": "credit"})
        out[side] = sorted(items, key=lambda x: (x["absorbed"], -x["strength"]))
    return out


def _add(side: dict, far: str, row: dict, names, fragility) -> None:
    old = side.get(far)
    if old is None or row["score"] > old["score"]:
        side[far] = dict(row, node=far, name=name_of(far, names), tier=fragility.get(far, {}).get("tier", ""))


# ---------------------------------------------------------------- supply channel (scenario graph)
def supply_flows(supply: dict | None, start: str, upstream: list[dict] | None = None) -> dict:
    """Each company reachable from `start` once, with the hops in between merged into one channel label.
    `upstream`: disclosed suppliers of `start` (chain edges), drawn on the left."""
    out = {"left": [], "right": []}
    if supply:
        nodes = {n["node"]: n for n in supply["nodes"]}
        by_src: dict[str, list[dict]] = {}
        for e in supply["edges"]:
            by_src.setdefault(e["src"], []).append(e)
        parent: dict[str, dict] = {start: None}
        queue = deque([start])
        while queue:                                    # shortest route from the start to every node
            cur = queue.popleft()
            for e in by_src.get(cur, []):
                if e["dst"] not in parent:
                    parent[e["dst"]] = e
                    queue.append(e["dst"])
        for nid, edge in parent.items():
            n = nodes.get(nid)
            if edge is None or not n or n["kind"] != "企业" or nid == start:
                continue
            hops, cur = [], edge
            while cur is not None:
                hops.append(cur)
                cur = parent.get(cur["src"])
            hops.reverse()
            middle = [nodes[h["dst"]]["name"] for h in hops[:-1] if h["dst"] in nodes]   # products, sectors, mills in between
            grade = _worst(h["grade"] for h in hops)
            last = hops[-1]
            effect = last["effect"].split("（")[0]
            channel = " → ".join(middle) + (f" · {effect}" if effect else "") if middle else effect
            out["right"].append({"node": nid, "name": n["name"], "tier": n.get("tier", ""), "channel": channel,
                                 "grade": grade, "strength": supply_strength(grade, last.get("amount_wan"), last.get("share")),
                                 "size": (f"{last['amount_wan'] / 1e4:.1f} 亿" if last.get("amount_wan")
                                          else f"占收入 {last['share']:.0%}" if last.get("share") else "—"),
                                 "effect": last["effect"], "evidence": last["evidence"], "kind": "supply",
                                 "amount_wan": last.get("amount_wan") or 0, "share": last.get("share") or 0})
        out["right"].sort(key=lambda x: (-x["strength"], -x["amount_wan"], -x["share"], x["name"]))
    for u in upstream or []:
        out["left"].append(dict(u, strength=supply_strength("A", u.get("amount_wan")), kind="supply"))
    out["left"].sort(key=lambda x: -x["strength"])
    return out


def disclosed_suppliers(chain_edges: list[dict], code: str, names: dict[str, str], fragility: dict[str, dict],
                        top: int = 12) -> list[dict]:
    """Companies with a disclosed sale to `code` (A-grade): they lose a customer if `code` stops."""
    best: dict[str, dict] = {}
    for t in chain_edges:
        if t.get("edge_type") != "supply" or t.get("basis") != "disclosed" or t.get("dst_id") != code or t.get("src_id") == code:
            continue
        amt = float(t.get("amount_wan") or 0)
        src = t["src_id"]
        if src not in best or amt > best[src]["amount_wan"]:
            best[src] = {"node": src, "name": name_of(src, names) if src in names else (t.get("src_name") or src),
                         "tier": fragility.get(src, {}).get("tier", ""), "channel": "披露向其供货", "grade": "A",
                         "amount_wan": amt, "size": f"{amt / 1e4:.1f} 亿" if amt else "—",
                         "evidence": f"{t.get('source_doc', '')} 第{t.get('source_page', '')}页：{(t.get('evidence_text') or '')[:80]}"}
    return sorted(best.values(), key=lambda r: -r["amount_wan"])[:top]


# ---------------------------------------------------------------- one sentence
def conclusion(name: str, credit: dict, supply: dict, shock: bool = False) -> tuple[str, str]:
    """-> (level, text) for ui.verdict."""
    subject = name if shock else f"{name}出现风险"
    cr = [r for r in credit["right"] if not r.get("absorbed")]
    ab = [r for r in credit["right"] if r.get("absorbed")]
    if cr:
        top = "、".join(f"{r['name']}（{TIER_LABEL.get(r['tier'], '未评分')}）" for r in cr[:3])
        credit_text = f"**信用上**有 {len(cr)} 家企业在计分路径上，最可能被拖累的是 {top}"
        if all(r["channel"].startswith("同集团") and r["size"] == "—" for r in cr):
            credit_text += "（仅凭同集团关系，没有披露金额）"
    else:
        credit_text = "**信用上**没有计分路径"
    if ab:
        names_ = "、".join(r["name"] for r in ab[:4]) + ("等" if len(ab) > 4 else "")
        credit_text += f"；风险还会传到{names_} {len(ab)} 家，但它们承压为强，风险可能被缓释，不计分"
    sr = supply["right"]
    if sr:
        top = "、".join(r["name"] for r in sr[:3])
        supply_text = f"**供需上**波及 {len(sr)} 家企业（情景，不计分），证据与暴露最强的是 {top}"
    else:
        supply_text = "**供需上**没有找到受影响的企业"
    left = [r for r in credit["left"] if not r.get("absorbed")]
    if left:
        supply_text += f"；另有 {len(left)} 家企业的风险可能传到它"
    return ("error" if cr else "info"), f"{subject}：{credit_text}；{supply_text}。"


# ---------------------------------------------------------------- the picture
CREDIT_COLORS = ("#e9d8fd", "#7b2cbf")
SUPPLY_COLORS = ("#d6e6f5", "#1c5d99")


def flow_chart(center: str, center_tier: str, left: list[dict], right: list[dict], channel: str,
               top: int = TOP, width: int = 1000) -> dict:
    """Vega-Lite spec: left column -> centre -> right column, strongest at the top, line width = strength."""
    left, right = left[:top], right[:top]
    rows = max(len(left), len(right), 1)
    lo, hi = CREDIT_COLORS if channel == "credit" else SUPPLY_COLORS
    nodes, edges = [], []

    def ys(n):
        return [(n - 1) / 2 - i for i in range(n)]

    for side, items, x in (("left", left, 0.0), ("right", right, 2.0)):
        for r, y in zip(items, ys(len(items))):
            tier = TIER_LABEL.get(r.get("tier") or "unknown", "未评分")
            nodes.append({"x": x, "y": y, "name": r["name"], "label": f"{r['name']}（{tier}）", "sub": r["channel"][:26], "tier": tier,
                          "strength": 0 if r.get("absorbed") else r["strength"],
                          "level": "缓释" if r.get("absorbed") else level(r["strength"]), "side": side,
                          "grade": r["grade"], "size": r.get("size", "—"), "channel_full": r["channel"]})
            x1, y1, x2, y2 = (x, y, 1.0, 0.0) if side == "left" else (1.0, 0.0, x, y)
            edges.append({"x": x1, "y": y1, "x2": x2, "y2": y2, "w": 1.2 + 7 * r["strength"],
                          "dash": "推断" if (r["grade"] == "C" or r.get("absorbed")) else "披露", "name": r["name"],
                          "channel_full": r["channel"], "grade": r["grade"], "size": r.get("size", "—"),
                          "level": "缓释" if r.get("absorbed") else level(r["strength"]),
                          "ink": "#B8C2CC" if r.get("absorbed") else hi})
    nodes.append({"x": 1.0, "y": 0.0, "name": center, "sub": "", "tier": TIER_LABEL.get(center_tier or "unknown", ""),
                  "strength": 1.0, "level": "", "side": "center", "grade": "", "size": "", "channel_full": ""})
    xs = {"field": "x", "type": "quantitative", "axis": None, "scale": {"domain": [-0.75, 2.85]}}
    yd = {"field": "y", "type": "quantitative", "axis": None, "scale": {"domain": [-(rows / 2) - 0.2, rows / 2 + 0.2]}}
    tip_e = [{"field": "name", "title": "企业"}, {"field": "channel_full", "title": "通道"},
             {"field": "grade", "title": "证据等级"}, {"field": "size", "title": "金额/占比"}, {"field": "level", "title": "影响强度"}]
    return {
        "width": width, "height": max(240, 58 * rows),
        "config": {"view": {"stroke": None}, "font": "Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"},
        "layer": [
            {"data": {"values": edges}, "mark": {"type": "rule", "opacity": 0.75, "strokeCap": "round"},
             "encoding": {"x": xs, "y": yd, "x2": {"field": "x2"}, "y2": {"field": "y2"},
                          "strokeWidth": {"field": "w", "type": "quantitative", "scale": None},
                          "strokeDash": {"field": "dash", "type": "nominal",
                                         "scale": {"domain": ["披露", "推断"], "range": [[1, 0], [5, 4]]}, "legend": None},
                          "color": {"field": "ink", "type": "nominal", "scale": None}, "tooltip": tip_e}},
            {"data": {"values": [n for n in nodes if n["side"] != "center"]},
             "mark": {"type": "circle", "size": 260, "stroke": "white", "strokeWidth": 1.5, "opacity": 1},
             "encoding": {"x": xs, "y": yd,
                          "color": {"field": "strength", "type": "quantitative", "legend": None,
                                    "scale": {"domain": [0, 1], "range": [lo, hi]}},
                          "tooltip": tip_e}},
            {"data": {"values": [n for n in nodes if n["side"] == "center"]},
             "mark": {"type": "circle", "size": 900, "color": "#1D2433"},
             "encoding": {"x": xs, "y": yd, "tooltip": [{"field": "name", "title": "起点"}, {"field": "tier", "title": "承压"}]}},
            {"data": {"values": [n for n in nodes if n["side"] == "center"]},
             "mark": {"type": "text", "dy": 30, "fontSize": 14, "fontWeight": 700, "color": "#1D2433"},
             "encoding": {"x": xs, "y": yd, "text": {"field": "name"}}},
            *[{"data": {"values": [n for n in nodes if n["side"] == side]},
               "mark": {"type": "text", "align": align, "dx": dx, "dy": -6, "fontSize": 13, "fontWeight": 600, "color": "#1D2433"},
               "encoding": {"x": xs, "y": yd, "text": {"field": "label"}}}
              for side, align, dx in (("left", "right", -14), ("right", "left", 14))],
            *[{"data": {"values": [n for n in nodes if n["side"] == side]},
               "mark": {"type": "text", "align": align, "dx": dx, "dy": 10, "fontSize": 11, "color": "#667085"},
               "encoding": {"x": xs, "y": yd, "text": {"field": "sub"}}}
              for side, align, dx in (("left", "right", -14), ("right", "left", 14))],
        ],
    }


def table_rows(items: list[dict]) -> list[dict]:
    return [{"排序": i + 1, "企业": r["name"], "自身承压": TIER_LABEL.get(r.get("tier") or "unknown", "未评分"),
             "通道": r["channel"], "证据": r["grade"], "金额/占比": r.get("size", "—"),
             "影响强度": r["strength"], "计分": "否（缓释）" if r.get("absorbed") else "是" if r.get("kind") == "credit" else "情景",
             "依据": (r.get("evidence") or "")[:120]} for i, r in enumerate(items)]


# ---------------------------------------------------------------- the full graph, for checking
KIND_SHAPE = {"冲击": "triangle-down", "产品": "square", "行业": "diamond", "企业": "circle"}
TIER_FILL = {"weak": "#E8A3A6", "medium": "#F2C894", "strong": "#9FD3B5"}
GRADE_LINE = {"A": "#1C5D99", "B": "#6C8EAD", "C": "#B8C2CC", "—": "#475467"}


def layered_chart(result: dict, width: int = 1100) -> dict:
    """Every node and relation of a scenario, in columns by distance from the shock. Rows inside a column are
    ordered by the average row of their parents (fewer crossings); no text on the lines (hover for it)."""
    nodes = {n["node"]: n for n in result["nodes"]}
    depth = {"SHOCK": 0}
    changed = True
    while changed:
        changed = False
        for e in result["edges"]:
            if e["src"] in depth and depth.get(e["dst"], 99) > depth[e["src"]] + 1:
                depth[e["dst"]] = depth[e["src"]] + 1
                changed = True
    for n in nodes:
        depth.setdefault(n, 0)
    cols: dict[int, list[str]] = {}
    for n in nodes:
        cols.setdefault(depth[n], []).append(n)
    parents: dict[str, list[str]] = {}
    for e in result["edges"]:
        parents.setdefault(e["dst"], []).append(e["src"])
    row: dict[str, float] = {}
    for d in sorted(cols):
        col = cols[d]
        def key(n):
            ps = [row[p] for p in parents.get(n, []) if p in row]
            return (sum(ps) / len(ps) if ps else 0.0, nodes[n]["name"])
        col.sort(key=key)
        for i, n in enumerate(col):
            row[n] = float(i)
    tallest = max(len(c) for c in cols.values())
    y = {n: -(row[n] - (len(cols[depth[n]]) - 1) / 2) for n in nodes}
    pts = [{"x": float(depth[n]), "y": y[n], "name": nodes[n]["name"], "kind": nodes[n]["kind"],
            "shape": KIND_SHAPE.get(nodes[n]["kind"], "circle"),
            "fill": "#1D2433" if n == "SHOCK" else TIER_FILL.get(nodes[n].get("tier"), "#D0D5DD") if nodes[n]["kind"] == "企业"
            else "#98A2B3",
            "tier": TIER_LABEL.get(nodes[n].get("tier") or "unknown", "未评分") if nodes[n]["kind"] == "企业" else nodes[n]["kind"]}
           for n in nodes]
    lines = [{"x": float(depth[e["src"]]), "y": y[e["src"]], "x2": float(depth[e["dst"]]), "y2": y[e["dst"]],
              "src": nodes[e["src"]]["name"], "dst": nodes[e["dst"]]["name"], "effect": e["effect"], "grade": e["grade"],
              "color": GRADE_LINE.get(e["grade"], "#98A2B3"), "dash": "推断" if e["grade"] == "C" else "披露",
              "evidence": (e.get("evidence") or "")[:100]}
             for e in result["edges"] if e["src"] in nodes and e["dst"] in nodes]
    heads = []
    for d, col in cols.items():
        kinds = dict.fromkeys({"冲击": "冲击", "产品": "产品", "行业": "下游行业", "企业": "企业"}.get(nodes[n]["kind"], nodes[n]["kind"])
                                for n in col)
        heads.append({"x": float(d), "label": " / ".join(kinds)})
    top = tallest / 2 + 0.6
    xs = {"field": "x", "type": "quantitative", "axis": None, "scale": {"domain": [-0.3, max(cols) + 0.9]}}
    ys = {"field": "y", "type": "quantitative", "axis": None, "scale": {"domain": [-tallest / 2 - 0.3, top + 0.3]}}
    return {
        "width": width, "height": max(260, 30 * tallest + 60),
        "config": {"view": {"stroke": None}, "font": "Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"},
        "layer": [
            {"data": {"values": lines}, "mark": {"type": "rule", "opacity": 0.55, "strokeWidth": 1.4},
             "encoding": {"x": xs, "y": ys, "x2": {"field": "x2"}, "y2": {"field": "y2"},
                          "color": {"field": "color", "type": "nominal", "scale": None},
                          "strokeDash": {"field": "dash", "type": "nominal", "legend": None,
                                         "scale": {"domain": ["披露", "推断"], "range": [[1, 0], [4, 3]]}},
                          "tooltip": [{"field": "src", "title": "从"}, {"field": "dst", "title": "到"},
                                      {"field": "effect", "title": "影响"}, {"field": "grade", "title": "证据等级"},
                                      {"field": "evidence", "title": "依据"}]}},
            {"data": {"values": pts}, "mark": {"type": "point", "filled": True, "size": 150, "opacity": 1,
                                               "stroke": "white", "strokeWidth": 1},
             "encoding": {"x": xs, "y": ys, "shape": {"field": "shape", "type": "nominal", "scale": None},
                          "color": {"field": "fill", "type": "nominal", "scale": None},
                          "tooltip": [{"field": "name", "title": "名称"}, {"field": "tier", "title": "类型/承压"}]}},
            {"data": {"values": pts}, "mark": {"type": "text", "align": "left", "dx": 9, "fontSize": 11, "color": "#344054"},
             "encoding": {"x": xs, "y": ys, "text": {"field": "name"}}},
            {"data": {"values": [dict(h, y=top) for h in heads]},
             "mark": {"type": "text", "fontSize": 12, "fontWeight": 600, "color": "#667085", "align": "left", "dx": -6},
             "encoding": {"x": xs, "y": ys, "text": {"field": "label"}}},
        ],
    }
