"""Quarterly indicators from the Sina financial abstract (one request per company, all periods).

The abstract has no publication date, so each period is treated as public only from its
statutory deadline (Q1 04-30, H1 08-31, Q3 10-31, annual 04-30 of the next year). All
companies therefore share the same latest period on any date, which keeps peer ranking
like-for-like and never uses information before it had to be published.
"""
from __future__ import annotations

from datetime import date

from src.financial_indicators import num

# (abstract indicator name, our field, scale)
FIELDS = [
    ("资产负债率", "debt_ratio", 0.01), ("流动比率", "current_ratio", 1), ("速动比率", "quick_ratio", 1),
    ("现金比率", "cash_ratio", 1), ("毛利率", "gross_margin", 0.01), ("销售净利率", "net_margin", 0.01),
    ("净资产收益率(ROE)", "roe", 0.01), ("经营性现金净流量/营业总收入", "ocf_to_revenue", 1),
    ("营业总收入增长率", "revenue_growth", 0.01), ("归母净利润", "parent_netprofit", 1),
    ("扣非净利润", "deduct_netprofit", 1), ("股东权益合计(净资产)", "equity", 1),
    ("经营现金流量净额", "ocf", 1), ("营业总收入", "revenue", 1),
]
DEADLINE = {"0331": "04-30", "0630": "08-31", "0930": "10-31"}


def available_by(period: str) -> str:
    """'20250630' -> '2025-08-31'; annual '20251231' -> '2026-04-30'."""
    year, md = period[:4], period[4:]
    if md == "1231":
        return f"{int(year) + 1}-04-30"
    return f"{year}-{DEADLINE[md]}"


def parse_abstract(rows: list[list[str]]) -> dict[str, dict]:
    """Rows of the abstract CSV (header: 选项, 指标, YYYYMMDD...) -> period -> metrics."""
    header, body = rows[0], rows[1:]
    periods = [p for p in header[2:] if len(p) == 8 and p.isdigit() and p[4:] in ("0331", "0630", "0930", "1231")]
    first = {}
    for row in body:
        name = row[1]
        if name not in first:
            first[name] = dict(zip(header[2:], row[2:]))
    out = {}
    for period in periods:
        metrics = {"period": period, "available_by": available_by(period)}
        for source, field, scale in FIELDS:
            value = num(first.get(source, {}).get(period))
            metrics[field] = None if value is None else value * scale
        equity = metrics["equity"]
        metrics["negative_equity"] = None if equity is None else int(equity < 0)
        out[period] = metrics
    return out


def latest_public_period(as_of: str) -> str:
    """Latest period whose statutory deadline is on or before `as_of` (YYYY-MM-DD)."""
    y = int(as_of[:4])
    candidates = []
    for year in (y - 1, y):
        for md in ("0331", "0630", "0930", "1231"):
            p = f"{year}{md}"
            if available_by(p) <= as_of:
                candidates.append(p)
    return max(candidates)


def today() -> str:
    return date.today().isoformat()
