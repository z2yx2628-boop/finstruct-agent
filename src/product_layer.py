"""Product layer: company -> product (what it sells, from its own disclosure) -> downstream sector.

Steel companies rarely name customers or suppliers, so up/downstream links go through products:
the revenue share of each product in a company's own business composition (主营构成) is a B-grade
exposure (disclosed by the company, but no counterparty); product -> sector links are industry
knowledge (C-grade, scenario only). See data/reference/products.csv and product_sector_links.csv.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
NOT_PRODUCT = re.compile(r"其他|补充|合计|租赁|劳务|服务|贸易|物流|利息|内部抵消|抵销|分部间")


@lru_cache(maxsize=1)
def products() -> list[dict]:
    with (REF / "products.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["pattern"] = re.compile(r["keywords"])
    return rows            # file order = match priority (special steel before flat, pipe before flat, …)


def classify(item: str) -> str | None:
    """'中宽热带' -> P_FLAT, '棒材' -> P_LONG, '不锈钢冷轧板' -> P_SPECIAL, '提供劳务' -> None."""
    name = (item or "").strip()
    if not name or NOT_PRODUCT.search(name):
        return None
    for p in products():
        if p["pattern"].search(name):
            return p["product_id"]
    return None


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def exposures_by_period(rows: list[dict]) -> list[dict]:
    """Every annual period with a usable breakdown (for point-in-time use: an annual report is public
    after 30 April of the next year)."""
    out = []
    for period in sorted({r["报告日期"][:10] for r in rows if r["报告日期"][5:10] == "12-31"}):
        e = exposure_from_composition([r for r in rows if r["报告日期"][:10] == period])
        if e:
            e["available_by"] = f"{int(period[:4]) + 1}-04-30"
            out.append(e)
    return out


def exposure_from_composition(rows: list[dict]) -> dict | None:
    """Pick the latest annual report whose product breakdown names at least one known product
    (falling back to the industry breakdown), and return revenue shares per product.

    rows: 东方财富 主营构成 rows (报告日期, 分类类型, 主营构成, 主营收入, 收入比例, 毛利率)."""
    periods = sorted({r["报告日期"][:10] for r in rows if r["报告日期"][5:10] == "12-31"}, reverse=True)
    for period in periods:
        for kind in ("按产品分类", "按行业分类"):
            items = [r for r in rows if r["报告日期"][:10] == period and r["分类类型"] == kind]
            shares: dict[str, dict] = {}
            for r in items:
                pid = classify(r["主营构成"])
                share = _num(r["收入比例"])
                if pid is None or share is None or share <= 0:
                    continue
                s = shares.setdefault(pid, {"share": 0.0, "items": [], "margin_revenue": 0.0, "profit": 0.0})
                s["share"] += share
                s["items"].append(r["主营构成"].strip())
                revenue, margin = _num(r["主营收入"]), _num(r["毛利率"])
                if revenue and margin is not None:
                    s["margin_revenue"] += revenue
                    s["profit"] += revenue * margin
            if shares:
                return {"period": period, "basis": kind, "unmapped_share": round(max(0.0, 1 - sum(s["share"] for s in shares.values())), 4),
                        "products": {pid: {"share": round(s["share"], 4), "items": s["items"],
                                           "gross_margin": round(s["profit"] / s["margin_revenue"], 4) if s["margin_revenue"] else None}
                                     for pid, s in shares.items()}}
    return None


SPECIFIC_STEEL = {"P_FLAT", "P_LONG", "P_SPECIAL", "P_PIPE"}


@lru_cache(maxsize=1)
def exposure_table() -> list[dict]:
    path = ROOT / "data" / "external" / "exposure" / "product_exposure.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def exposure_as_of(code: str, as_of: str, lookback_years: int = 3) -> dict | None:
    """Point-in-time exposure: the latest annual breakdown public on `as_of`. When that year only says
    "钢材" (no split by product), the product split is taken from the most recent earlier year that has
    one (at most `lookback_years` back) and flagged, because product mix changes slowly."""
    rows = [r for r in exposure_table() if r["security_code"] == code]
    if rows and rows[0]["tier"] == "end_user":
        return {"period": "", "split_from": "", "products": {r["product_id"]: {"share": None, "grade": r["grade"]} for r in rows},
                "source": rows[0]["source"]}
    periods = sorted({r["period"] for r in rows if r["available_by"] <= as_of}, reverse=True)
    if not periods:
        return None
    latest = periods[0]

    def split(period: str) -> dict:
        return {r["product_id"]: {"share": float(r["revenue_share"]), "items": r["items"], "grade": r["grade"]}
                for r in rows if r["period"] == period}
    products_now = split(latest)
    specific = {k: v for k, v in products_now.items() if k in SPECIFIC_STEEL}
    split_from = latest
    if not specific:
        for p in periods[1:]:
            if int(latest[:4]) - int(p[:4]) > lookback_years:
                break
            earlier = {k: v for k, v in split(p).items() if k in SPECIFIC_STEEL}
            if earlier:
                split_from = p
                total = sum(v["share"] for v in earlier.values())
                steel_now = sum(v["share"] for k, v in products_now.items() if k in ("P_STEEL",))
                # scale the earlier product mix to this year's steel revenue share
                products_now = {k: v for k, v in products_now.items() if k != "P_STEEL"}
                for k, v in earlier.items():
                    products_now[k] = dict(v, share=round(steel_now * v["share"] / total, 4) if total else v["share"])
                break
    return {"period": latest, "split_from": split_from, "products": products_now}
