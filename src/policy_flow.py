"""Policy shocks and futures context for the 风险传导 page.

Policy shocks hit each mill directly (no product hops), so they are drawn as one hop from the policy to the mills,
ranked by the same stress index as the 市场冲击 page; scenario only, never scored. Futures add context: where the
industry-wide board margin stands when a price shock happens, and which mills disclose hedging.
"""
from __future__ import annotations

import re

from src.futures import hedge_label, hedging, margin_snapshot
from src.policy_shock import CBAM_FACTOR, carbon, export_change

POLICY_KINDS = {"policy_carbon": "政策：欧盟碳关税（CBAM）", "policy_export": "政策：出口退税下调或加征关税"}
CARBON_DEFAULT = {"year": list(CBAM_FACTOR)[1], "eu_price": 600.0, "domestic_price": 60.0, "domestic_gap": 0.03}
EXPORT_DEFAULT = 0.05
POLICY_NOTE = {
    "policy_carbon": (f"默认假设：{CARBON_DEFAULT['year']} 年 CBAM 系数 {CBAM_FACTOR[CARBON_DEFAULT['year']]:.1%}、欧盟碳价 600 元/吨 CO₂、"
                      "国内碳价 60 元/吨、国内配额缺口 3%；可在「市场冲击 → 政策」调整。"),
    "policy_export": f"默认假设：出口退税下调或新增关税 = 出口收入的 {EXPORT_DEFAULT:.0%}；可在「市场冲击 → 政策」调整。",
}


def _grade(source: str) -> str:
    m = re.search(r"（([ABC])）\s*$", source or "")
    return m.group(1) if m else "B"


def policy_rows(kind: str, fragility: dict[str, dict], as_of: str) -> list[dict]:
    if kind == "policy_carbon":
        d = CARBON_DEFAULT
        return carbon(fragility, as_of, d["eu_price"], d["year"], d["domestic_price"], d["domestic_gap"])
    return export_change(fragility, as_of, EXPORT_DEFAULT)


def _share(x: float) -> str:
    return "<1%" if x < 0.005 else f"{x:.0%}"


def policy_flows(kind: str, rows: list[dict]) -> dict:
    """flow_view-shaped items: the policy on the left of nothing, the mills on the right, strongest first."""
    valid = [r for r in rows if r.get("index")]
    top = max((r["index"] for r in valid), default=0) or 1
    right = []
    for r in valid:
        share = r.get("overseas_share")
        if kind == "policy_carbon":
            channel = (f"境外收入 {_share(share)} · CBAM {r['cbam_per_ton']:.0f} 元/吨出口" if share else "国内碳成本") \
                      + f" · {r['route']}{'' if r['route_verified'] else '（默认）'}"
        else:
            channel = f"境外收入 {_share(share)} · 出口收入受损" if share else "出口收入受损"
        right.append({"node": r["code"], "name": r["name"], "tier": r.get("tier", ""), "channel": channel,
                      "grade": _grade(r.get("overseas_source", "")), "strength": round(max(0.12, r["index"] / top), 3),
                      "size": f"境外收入 {_share(share)}" if share else "—", "effect": f"压力指数 {r['index']:.2f}",
                      "evidence": f"{r.get('overseas_source') or '工艺路线与碳价假设'}；压力指数 {r['index']:.2f}（只用于排序）",
                      "kind": "supply", "amount_wan": 0, "share": share or 0, "index": r["index"]})
    return {"left": [], "right": right}


def bridge_candidates(flows: dict) -> list[str]:
    """Policy-hit mills that may carry the shock on into the credit channel: weak or medium, with a disclosed share."""
    return [r["node"] for r in flows["right"] if r["tier"] in ("weak", "medium") and r["share"] > 0]


# ---------------------------------------------------------------- futures context
MARGIN_FOR = {"P_IRON_ORE": ("rebar", "hrc"), "P_COKE": ("rebar", "hrc", "coke"), "P_COKING_COAL": ("coke",),
              "P_LONG": ("rebar",), "P_FLAT": ("hrc",)}


def margin_context(product_id: str | None, as_of: str) -> list[str]:
    """One line per relevant board margin: level, 20-day change and percentile over the last three years."""
    out = []
    for kind in MARGIN_FOR.get(product_id or "", ("rebar", "hrc")):
        m = margin_snapshot(kind, as_of)
        if not m:
            continue
        pct = m["pct_3y"]
        tone = "，处于近三年低位" if pct is not None and pct <= 0.2 else "，处于近三年高位" if pct is not None and pct >= 0.8 else ""
        out.append(f"{m['label']} {m['value']:,.0f} 元/吨（{m['date']}，近 20 日 {m['change']:+,.0f}；近三年 {pct:.0%} 分位{tone}）")
    return out


def mark_hedging(items: list[dict], as_of: str) -> int:
    """Append the disclosed hedging status to listed companies in a price-shock flow; returns how many hedge."""
    n = 0
    for r in items:
        if not re.fullmatch(r"\d{6}", str(r.get("node", ""))):
            continue
        label = hedge_label(hedging(r["node"], as_of))
        if label not in ("缓存中未见", "仅有管理制度"):
            r["channel"] += f" · 已披露套保（{label}）"
            r["hedged"] = True
            n += 1
    return n
