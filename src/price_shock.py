"""Price-shock scenario hints: when a chain product's price moves sharply, list the companies most
exposed to it (their own disclosed product mix) that are also fragile.

This is a SCENARIO HINT, not a validated prediction: two pre-registered tests of the product layer
(docs/product_exposure_validation.md, docs/product_price_validation.md) found the expected direction
in share prices but no statistically significant effect. Every output says so.
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.product_layer import ROOT, exposure_as_of, exposure_table, products

PRICES = ROOT / "data" / "external" / "prices"
WINDOW, THRESHOLD = 20, 0.10          # 20 trading days, |return| >= 10% (a scenario trigger, not calibrated)
TIER_WEIGHT = {"weak": 1.0, "medium": 0.5, "strong": 0.2, "": 0.5}
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强", "": "未评分"}
CAVEAT = "情景提示：依据企业自己披露的产品构成（B 级）；产品暴露经两次预先登记的检验，方向一致但不显著，不作为预测。"


def stress_index(price_change: float, exposure_share: float | None, tier: str) -> float | None:
    """Dimensionless scenario index, not an earnings or loss forecast.

    |price move| x disclosed product exposure x fragility multiplier x 100.
    Missing exposure stays missing instead of being replaced with an assumption.
    """
    if exposure_share is None or exposure_share <= 0:
        return None
    return round(abs(price_change) * exposure_share * TIER_WEIGHT.get(tier, 0.5) * 100, 2)


def scenario_stress(companies: list[dict], price_change: float) -> list[dict]:
    rows = []
    for company in companies:
        share = company.get("share") or None
        index = stress_index(price_change, share, company.get("tier", ""))
        rows.append({**company, "price_change": price_change, "buffer_factor": TIER_WEIGHT.get(company.get("tier", ""), 0.5),
                     "stress_index": index, "quantifiable": index is not None})
    return sorted(rows, key=lambda r: (r["stress_index"] is None, -(r["stress_index"] or 0), r["name"]))


def price_moves(as_of: str) -> list[dict]:
    out = []
    for p in products():
        path = PRICES / f"{p['price_symbol']}.csv" if p["price_symbol"] else None
        if not path or not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["date"][:10] <= as_of and r.get("close")]
        if len(rows) <= WINDOW:
            continue
        last, base = float(rows[-1]["close"]), float(rows[-1 - WINDOW]["close"])
        out.append({"product_id": p["product_id"], "product": p["name"], "symbol": p["price_symbol"], "layer": p["layer"],
                    "date": rows[-1]["date"][:10], "close": last, "ret": last / base - 1,
                    "shock": abs(last / base - 1) >= THRESHOLD})
    return out


def exposed(product_id: str, as_of: str, fragility: dict[str, dict], top: int = 6) -> list[dict]:
    """Sellers of the product (revenue share >= 10%), ranked by share x fragility. For upstream inputs
    (ore, coke, coal) every steel mill is also a buyer; buyers are not ranked here because mills do not
    disclose purchase shares."""
    rows = []
    for code in sorted({r["security_code"] for r in exposure_table() if r["tier"] != "end_user"}):
        e = exposure_as_of(code, as_of)
        share = ((e or {}).get("products", {}).get(product_id) or {}).get("share")
        if not share or share < 0.10:
            continue
        f = fragility.get(code, {})
        tier = f.get("tier", "")
        rows.append({"code": code, "name": f.get("security_name") or next(
            r["security_name"] for r in exposure_table() if r["security_code"] == code),
            "share": share, "tier": tier, "tier_label": TIER_LABEL.get(tier, "未评分"),
            "score": share * TIER_WEIGHT.get(tier, 0.5), "period": e["period"], "split_from": e["split_from"]})
    return sorted(rows, key=lambda r: -r["score"])[:top]


def report_section(as_of: str, fragility: dict[str, dict]) -> list[str]:
    moves = price_moves(as_of)
    if not moves:
        return ["## 产品价格冲击（情景提示）", "", "- 没有可用的产品价格数据。"]
    lines = ["## 产品价格冲击（情景提示）", "", f"> {CAVEAT}", "",
             f"近 {WINDOW} 个交易日涨跌幅（|涨跌| ≥ {THRESHOLD:.0%} 视为冲击）：" + "；".join(
                 f"{m['product']} {m['ret']:+.1%}（{m['date']}）" for m in moves), ""]
    shocks = [m for m in moves if m["shock"]]
    if not shocks:
        lines.append("- 今日无产品价格冲击。")
    for m in shocks:
        direction = "上涨" if m["ret"] > 0 else "下跌"
        who = exposed(m["product_id"], as_of, fragility)
        effect = ("对钢厂是成本上升、对生产该原料的企业是收入上升" if m["layer"] == "upstream" and m["ret"] > 0 else
                  "对钢厂是成本下降、对生产该原料的企业是收入下降" if m["layer"] == "upstream" else
                  "对以该产品为主的钢厂是收入" + ("上升" if m["ret"] > 0 else "下降"))
        lines.append(f"- **{m['product']}{direction} {abs(m['ret']):.1%}**（{effect}）。收入中该产品占比高的企业（按 占比 × 承压 排序，承压越弱越靠前）：")
        for r in who:
            split = "" if r["split_from"] == r["period"] else f"，细分取自 {r['split_from'][:4]}"
            lines.append(f"  - {r['name']}：{m['product']}占收入 {r['share']:.0%}（{r['period'][:4]} 年报{split}），承压{r['tier_label']}")
        if not who:
            lines.append("  - 无收入占比 ≥10% 的企业。")
    return lines
