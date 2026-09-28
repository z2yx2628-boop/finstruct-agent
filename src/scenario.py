"""Up/downstream scenario paths through the product layer (NOT part of the formal risk ranking).

    shock (price up/down of a product, a mill outage, a sector demand drop)
      -> companies exposed to that product (their own revenue mix, B; disclosed purchases, A)
      -> their fragility (direction 2)
      -> the steel products they sell (B) -> downstream sectors (C) -> end users (B if their annual
         report names steel as a main raw material, else C)

Two pre-registered tests found the product layer's expected direction but no significant effect
(docs/product_exposure_validation.md, docs/product_price_validation.md), so every result here is a
scenario: it says who is exposed and how fragile they are, not who will be hurt.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from src.entity_resolver import load_entities
from src.product_layer import REF, ROOT, exposure_as_of, exposure_table, products

KINDS = {"price_up": "价格上涨", "price_down": "价格下跌", "outage": "企业停产", "demand_down": "下游需求下降"}
TIER_WEIGHT = {"weak": 1.0, "medium": 0.5, "strong": 0.2}
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强"}
RULES = {"S0": "冲击", "S1": "产品暴露（B）", "S2": "披露采购/销售（A）", "S3": "行业用钢（C）",
         "S4": "下游企业", "S5": "企业级采购/应用（B）"}
CAVEAT = ("情景路径：说明谁暴露在这个冲击上、承压如何，不预测谁会受损；不计入正式风险得分。"
          "产品暴露经两次预先登记的检验，方向一致但不显著。")
MIN_SHARE = 0.10


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def product_map() -> dict[str, dict]:
    return {p["product_id"]: p for p in products()}


def sector_links() -> list[dict]:
    return _read(REF / "product_sector_links.csv")


def end_users() -> list[dict]:
    return _read(REF / "downstream_users.csv")


def verified_product_links(as_of: str, product_id: str | None = None) -> list[dict]:
    """Point-in-time company/product links confirmed by a named company's own disclosure.

    These B-grade links prove procurement exposure or product application, not an undisclosed
    transaction amount, supplier share, or causal loss. The CSV preserves that boundary per row.
    """
    rows = _read(REF / "verified_product_links.csv")
    return [r for r in rows if (not product_id or r["product_id"] == product_id)
            and r["valid_from"] <= as_of and (not r["valid_to"] or as_of <= r["valid_to"])]


def core_mills() -> list[str]:
    return [r["security_code"] for r in _read(ROOT / "data" / "manifests" / "steel_universe.csv") if r["tier"] == "core"]


def company_name(code: str) -> str:
    rows, _ = load_entities()
    if code in rows:
        return rows[code]["short_name"]
    hit = next((r["security_name"] for r in exposure_table() if r["security_code"] == code), None)
    return hit or (code[2:] if code.startswith("N_") else code)


class Builder:
    def __init__(self, fragility: dict[str, dict]):
        self.fragility = fragility
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

    def tier(self, code: str) -> str:
        return self.fragility.get(code, {}).get("tier", "")

    def node(self, node_id: str, name: str, kind: str, tier: str = "") -> str:
        self.nodes.setdefault(node_id, {"node": node_id, "name": name, "kind": kind, "tier": tier})
        return node_id

    def company(self, code: str) -> str:
        return self.node(code, company_name(code), "企业", self.tier(code))

    def product(self, pid: str) -> str:
        return self.node(pid, product_map()[pid]["name"], "产品")

    def sector(self, sid: str, name: str) -> str:
        return self.node(sid, name, "行业")

    def edge(self, src: str, dst: str, rule: str, grade: str, effect: str, evidence: str,
             share: float | None = None, amount_wan: float | None = None) -> None:
        if not any(e["src"] == src and e["dst"] == dst for e in self.edges):
            self.edges.append({"src": src, "dst": dst, "rule": rule, "grade": grade, "effect": effect,
                               "evidence": evidence, "share": share, "amount_wan": amount_wan})

    def impact(self, code: str, share: float) -> float:
        return share * TIER_WEIGHT.get(self.tier(code), 0.5)


def sellers(pid: str, as_of: str, exclude: set[str] = frozenset()) -> list[tuple[str, float, dict]]:
    """Companies whose own revenue is >= 10% this product. For steel products only producers (mills and
    upstream companies that also roll steel, e.g. 安泰 型钢) count: downstream processors buy steel."""
    steel = product_map()[pid]["layer"] == "steel"
    tiers = {"core", "upstream"} if steel else {"core", "upstream", "downstream"}
    out = []
    for code in sorted({r["security_code"] for r in exposure_table() if r["tier"] in tiers} - set(exclude)):
        e = exposure_as_of(code, as_of) or {}
        v = e.get("products", {}).get(pid)
        if v and v.get("share") and v["share"] >= MIN_SHARE:
            out.append((code, v["share"], e))
    return out


def _b_evidence(e: dict, pid: str) -> str:
    v = e["products"][pid]
    split = "" if e["split_from"] == e["period"] else f"，品种比例取自 {e['split_from'][:4]} 年报"
    return f"公司定期报告 {e['period'][:4]} 年分产品收入（东方财富主营构成）：{v.get('items', '')} 占 {v['share']:.0%}{split}"


def _verified_evidence(link: dict) -> str:
    page = f" 第{link['source_page']}页" if link["source_page"] else ""
    return (f"{link['source_title']}{page}：{link['evidence_text']} "
            f"边界：{link['scope_note']} 来源：{link['source_url']}")


def _verified_input_buyers(b: Builder, pid: str, sign: str, as_of: str) -> list[str]:
    """B-grade input exposure disclosed by the mill itself or its parent."""
    buyers = []
    for link in verified_product_links(as_of, pid):
        if link["relation"] != "input_exposure" or link["src_id"] != pid:
            continue
        code = link["dst_id"]
        b.edge(pid, b.company(code), "S5", "B", f"采购成本{sign}（披露原料采购暴露）", _verified_evidence(link))
        buyers.append(code)
    return buyers


def _verified_downstream(b: Builder, pid: str, sign: str, as_of: str, sellers_only: set[str] | None = None) -> None:
    """Add named producer -> end-user application links without inventing a sales amount."""
    for link in verified_product_links(as_of, pid):
        if link["relation"] != "product_application" or (sellers_only is not None and link["src_id"] not in sellers_only):
            continue
        src, dst = link["src_id"], link["dst_id"]
        exposure = exposure_as_of(src, as_of) or {}
        product = exposure.get("products", {}).get(pid)
        if product and product.get("share"):
            b.edge(pid, b.company(src), "S1", "B", f"收入暴露（占 {product['share']:.0%}）",
                   _b_evidence(exposure, pid), product["share"])
        else:
            b.company(src)
        b.edge(src, b.company(dst), "S5", "B", f"若价格传导：采购成本{sign}（披露产品应用）",
               _verified_evidence(link))


def disclosed_trades(pid: str, chain_edges: list[dict], buyer_side: bool = True) -> list[dict]:
    """A-grade: disclosed related-party trade rows whose goods name the product."""
    pattern = product_map()[pid]["keywords"]
    return [e for e in chain_edges if e.get("edge_type") == "supply" and e.get("basis") == "disclosed"
            and re.search(pattern, e.get("category_text") or "")]


def _downstream(b: Builder, pid: str, sign: str, as_of: str, user_effect: str) -> None:
    for link in (l for l in sector_links() if l["product_id"] == pid):
        s = b.sector(link["sector_id"], link["sector"])
        b.edge(pid, s, "S3", "C", f"{link['sector']}用钢{user_effect}", link["basis"])
        for u in (u for u in end_users() if u["sector_id"] == link["sector_id"]):
            c = b.company(u["security_code"])
            # point in time: an annual report counts only after it was due (30 April of the next year)
            year = re.search(r"(20\d\d)年年度报告", u["evidence_source"] or "")
            public = bool(u["steel_input_evidence"]) and (not year or f"{int(year.group(1)) + 1}-04-30" <= as_of)
            grade = "B" if public else "C"
            ev = (f"{u['evidence_source']}：{u['steel_input_evidence']}" if public else
                  f"该证据来自评估日之后才公布的年报（{u['evidence_source'][:10]}），评估日按行业推断" if u["steel_input_evidence"]
                  else "年报未点名钢材为原材料，按所属行业推断")
            b.edge(s, c, "S4", grade, f"用钢{user_effect}", ev)


def build(kind: str, as_of: str, fragility: dict[str, dict], chain_edges: list[dict] | None = None,
          product_id: str | None = None, company: str | None = None, sector_id: str | None = None,
          top: int = 6) -> dict:
    chain_edges = chain_edges or []
    b = Builder(fragility)
    up = kind in ("price_up",)
    arrow = "↑" if up else "↓"
    title = ""
    if kind in ("price_up", "price_down"):
        p = product_map()[product_id]
        shock = b.node("SHOCK", f"{p['name']}{KINDS[kind]}", "冲击")
        b.product(product_id)
        b.edge(shock, product_id, "S0", "—", KINDS[kind], "情景设定（可由价格数据触发）")
        title = f"{p['name']}{KINDS[kind]}"
        if p["layer"] == "upstream":
            for code, share, e in sorted(sellers(product_id, as_of), key=lambda x: -b.impact(x[0], x[1]))[:top]:
                b.edge(product_id, b.company(code), "S1", "B", f"收入{arrow}（占 {share:.0%}）", _b_evidence(e, product_id), share)
            buyers = {}
            for t in disclosed_trades(product_id, chain_edges):
                if t["dst_id"] in core_mills():
                    buyers.setdefault(t["dst_id"], t)
            for code, t in list(buyers.items())[:top]:
                b.edge(product_id, b.company(code), "S2", "A", f"采购成本{arrow}（披露采购 {float(t['amount_wan'] or 0) / 1e4:.1f} 亿元）",
                       f"{Path(t['source_doc']).stem} 第{t['source_page']}页：{(t['evidence_text'] or '')[:80]}",
                       amount_wan=float(t["amount_wan"] or 0))
            verified_buyers = _verified_input_buyers(b, product_id, arrow, as_of)
            # every blast-furnace mill buys this input, but mills do not disclose purchase shares: C-grade,
            # shown for the most fragile mills only
            fragile = sorted((c for c in core_mills() if c not in buyers and c not in verified_buyers),
                             key=lambda c: -TIER_WEIGHT.get(b.tier(c), 0.5))[:3]
            for code in fragile:
                b.edge(product_id, b.company(code), "S3", "C", f"采购成本{arrow}（采购比例未披露）",
                       f"长流程钢厂以{p['name']}为主要原料（行业常识，未披露采购比例）")
            # cost pass-through: the fragile buyers' main steel products and who uses them
            pass_through = list(dict.fromkeys(list(buyers)[:2] + verified_buyers + fragile[:2]))
            for code in pass_through:
                e = exposure_as_of(code, as_of) or {}
                main = sorted(((k, v) for k, v in e.get("products", {}).items() if k in ("P_FLAT", "P_LONG", "P_SPECIAL", "P_PIPE")
                               and (v.get("share") or 0) >= 0.2), key=lambda kv: -kv[1]["share"])[:1]
                for pid, v in main:
                    b.edge(code, b.product(pid), "S1", "B", f"若成本转嫁：{product_map()[pid]['name']}价格{arrow}", _b_evidence(e, pid), v["share"])
                    _downstream(b, pid, arrow, as_of, f"成本{arrow}")
                    _verified_downstream(b, pid, arrow, as_of, {code})
        else:
            for code, share, e in sorted(sellers(product_id, as_of), key=lambda x: -b.impact(x[0], x[1]))[:top]:
                b.edge(product_id, b.company(code), "S1", "B", f"收入{arrow}（占 {share:.0%}）", _b_evidence(e, product_id), share)
            _downstream(b, product_id, arrow, as_of, f"成本{arrow}")
            _verified_downstream(b, product_id, arrow, as_of)
    elif kind == "outage":
        shock = b.node("SHOCK", f"{company_name(company)}停产", "冲击")
        b.edge(shock, b.company(company), "S0", "—", "产量↓、收入↓", "情景设定（可由方向一的检修/停产事件触发）")
        title = f"{company_name(company)}停产"
        e = exposure_as_of(company, as_of) or {}
        for pid, v in sorted(e.get("products", {}).items(), key=lambda kv: -(kv[1].get("share") or 0)):
            if pid in ("P_FLAT", "P_LONG", "P_SPECIAL", "P_PIPE") and (v.get("share") or 0) >= MIN_SHARE:
                b.edge(company, b.product(pid), "S1", "B", f"{product_map()[pid]['name']}供给↓（占其收入 {v['share']:.0%}）", _b_evidence(e, pid), v["share"])
                _downstream(b, pid, "↓", as_of, "供给↓")
                _verified_downstream(b, pid, "↓", as_of, {company})
        sales = sorted((t for t in chain_edges if t.get("edge_type") == "supply" and t.get("basis") == "disclosed"
                        and t.get("src_id") == company), key=lambda t: -float(t.get("amount_wan") or 0))[:top]
        for t in sales:
            b.edge(company, b.company(t["dst_id"]), "S2", "A", f"供货中断（披露销售 {float(t['amount_wan'] or 0) / 1e4:.1f} 亿元）",
                   f"{Path(t['source_doc']).stem} 第{t['source_page']}页：{(t['evidence_text'] or '')[:80]}",
                   amount_wan=float(t["amount_wan"] or 0))
    elif kind == "demand_down":
        link0 = next(l for l in sector_links() if l["sector_id"] == sector_id)
        shock = b.node("SHOCK", f"{link0['sector']}需求下降", "冲击")
        s = b.sector(sector_id, link0["sector"])
        b.edge(shock, s, "S0", "—", "需求↓", "情景设定")
        title = f"{link0['sector']}需求下降"
        for link in (l for l in sector_links() if l["sector_id"] == sector_id):
            pid = b.product(link["product_id"])
            b.edge(s, pid, "S3", "C", f"{product_map()[pid]['name']}需求↓", link["basis"])
            for code, share, e in sorted(sellers(link["product_id"], as_of), key=lambda x: -b.impact(x[0], x[1]))[:top]:
                b.edge(pid, b.company(code), "S1", "B", f"收入↓（占 {share:.0%}）", _b_evidence(e, link["product_id"]), share)
    else:
        raise ValueError(kind)
    ranked = sorted(({"code": n["node"], "name": n["name"], "tier": n["tier"],
                      "effect": "；".join(e["effect"] for e in b.edges if e["dst"] == n["node"]),
                      "grade": min((e["grade"] for e in b.edges if e["dst"] == n["node"]), default="—"),
                      "share": max((e["share"] or 0 for e in b.edges if e["dst"] == n["node"]), default=0)}
                     for n in b.nodes.values() if n["kind"] == "企业"),
                    key=lambda r: (-TIER_WEIGHT.get(r["tier"], 0.5) * max(r["share"], 0.3), r["name"]))
    return {"title": title, "kind": kind, "as_of": as_of, "nodes": list(b.nodes.values()), "edges": b.edges,
            "companies": ranked, "caveat": CAVEAT}


def layout(result: dict) -> tuple[list[dict], list[dict]]:
    """Columns by distance from the shock; rows centred per column. Output fits network_view.overview_chart."""
    import math
    depth = {"SHOCK": 0}
    changed = True
    while changed:
        changed = False
        for e in result["edges"]:
            if e["src"] in depth and depth.get(e["dst"], 99) > depth[e["src"]] + 1:
                depth[e["dst"]] = depth[e["src"]] + 1
                changed = True
    columns: dict[int, list[str]] = {}
    kinds = {n["node"]: n for n in result["nodes"]}
    for n in result["nodes"]:
        columns.setdefault(depth.get(n["node"], 0), []).append(n["node"])
    y = {}
    for d, ids in columns.items():
        ids.sort(key=lambda i: (kinds[i]["kind"], kinds[i]["name"]))
        for j, i in enumerate(ids):
            y[i] = (len(ids) - 1) / 2 - j
    nodes = [{"node": n["node"], "name": n["name"], "kind": n["kind"], "x": float(depth.get(n["node"], 0)), "y": y[n["node"]],
              "tier": n["tier"] or "unknown", "tier_label": TIER_LABEL.get(n["tier"], "未评分" if n["kind"] == "企业" else n["kind"]),
              "seed": n["node"] == "SHOCK", "paths": 1, "best": 0.0, "on": True} for n in result["nodes"]]
    edges = []
    for e in result["edges"]:
        x1, y1, x2, y2 = float(depth.get(e["src"], 0)), y[e["src"]], float(depth.get(e["dst"], 0)), y[e["dst"]]
        amount = (e["amount_wan"] or 0) / 1e4
        edges.append({"edge": f"{e['src']}|{e['dst']}|{e['rule']}", "src": kinds[e["src"]]["name"], "dst": kinds[e["dst"]]["name"],
                      "rule": RULES[e["rule"]], "rule_code": e["rule"], "grade": e["grade"], "x": x1, "y": y1, "x2": x2, "y2": y2,
                      "mx": x1 + (x2 - x1) * 0.62, "my": y1 + (y2 - y1) * 0.62, "amount_yi": round(amount, 2),
                      "label": e["effect"].split("（")[0][:10], "span": abs(x2 - x1),
                      "width": 1.4 + (min(math.log10(1 + amount), 2.5) * 1.6 if amount else (e["share"] or 0) * 3),
                      "paths": 1, "first_path": 0, "on": True})
    return nodes, edges
