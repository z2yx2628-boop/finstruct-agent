"""Annual financial-risk indicators for direction 2 (can the mill absorb a shock?).

Input: Eastmoney statement rows (one dict per report, raw column names, amounts in yuan).
Output: one row per mill x fiscal year with the indicators below plus the raw inputs
they were computed from, so every number can be checked against the annual report.

Only annual reports (REPORT_DATE = YYYY-12-31) are used. `notice_date` is the
publication date of that annual report: a backtest may only use a row after that
date (no look-ahead).
"""
from __future__ import annotations

from typing import Iterable

YI = 1e8  # amounts reported in 亿元

# raw inputs kept in the output for audit, statement -> columns
INPUTS = {
    "balance": ["TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_CURRENT_ASSETS", "TOTAL_CURRENT_LIAB",
                "INVENTORY", "MONETARYFUNDS", "SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "SHORT_BOND_PAYABLE",
                "LONG_LOAN", "BOND_PAYABLE", "CIP", "TOTAL_PARENT_EQUITY"],
    "income": ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "OPERATE_COST", "NETPROFIT", "PARENT_NETPROFIT",
               "DEDUCT_PARENT_NETPROFIT", "TOTAL_PROFIT", "FE_INTEREST_EXPENSE"],
    "cashflow": ["NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET"],
}

INDICATORS = [
    "debt_ratio", "current_ratio", "quick_ratio", "cash_to_short_debt", "interest_bearing_debt_yi",
    "short_term_debt_yi", "ocf_yi", "ocf_to_current_liab", "capex_yi", "fcf_yi", "gross_margin",
    "net_margin", "roe", "roa", "deduct_netprofit_yi", "interest_coverage", "cip_to_assets",
    "revenue_yoy", "loss_flag", "negative_equity",
]


def num(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "nan", "None", "NaN", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def total(*values: float | None) -> float | None:
    """Sum treating a missing line item as 0, but None if every item is missing."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def yi(value: float | None) -> float | None:
    return None if value is None else value / YI


def positive(value: float | None) -> float | None:
    """ROE on negative equity is meaningless (loss / negative equity looks like a gain)."""
    return value if value is not None and value > 0 else None


def average(current: float | None, prior: float | None) -> float | None:
    if current is None:
        return None
    return current if prior is None else (current + prior) / 2


def annual_rows(rows: Iterable[dict]) -> dict[int, dict]:
    """Fiscal year -> annual report row; the first row per date wins (Eastmoney lists latest version)."""
    out: dict[int, dict] = {}
    for row in rows:
        date = str(row.get("REPORT_DATE", ""))[:10]
        if date.endswith("-12-31"):
            out.setdefault(int(date[:4]), row)
    return out


def indicators_for_year(year: int, balance: dict[int, dict], income: dict[int, dict],
                        cashflow: dict[int, dict]) -> dict | None:
    b, i, c = balance.get(year), income.get(year), cashflow.get(year)
    if b is None or i is None:
        return None
    c = c or {}
    pb, pi = balance.get(year - 1, {}), income.get(year - 1, {})
    g = {k: num(b.get(k)) for k in INPUTS["balance"]}
    g.update({k: num(i.get(k)) for k in INPUTS["income"]})
    g.update({k: num(c.get(k)) for k in INPUTS["cashflow"]})

    short_debt = total(g["SHORT_LOAN"], g["NONCURRENT_LIAB_1YEAR"], g["SHORT_BOND_PAYABLE"])
    debt = total(short_debt, g["LONG_LOAN"], g["BOND_PAYABLE"])
    ocf, capex = g["NETCASH_OPERATE"], g["CONSTRUCT_LONG_ASSET"]
    interest = g["FE_INTEREST_EXPENSE"]
    prior_revenue = num(pi.get("TOTAL_OPERATE_INCOME"))
    gross = None
    if g["OPERATE_INCOME"] is not None and g["OPERATE_COST"] is not None:
        gross = ratio(g["OPERATE_INCOME"] - g["OPERATE_COST"], g["OPERATE_INCOME"])
    inventory = g["INVENTORY"] or 0.0

    result = {
        "fiscal_year": year,
        "notice_date": str(b.get("NOTICE_DATE", ""))[:10],
        "debt_ratio": ratio(g["TOTAL_LIABILITIES"], g["TOTAL_ASSETS"]),
        "current_ratio": ratio(g["TOTAL_CURRENT_ASSETS"], g["TOTAL_CURRENT_LIAB"]),
        "quick_ratio": ratio(None if g["TOTAL_CURRENT_ASSETS"] is None else g["TOTAL_CURRENT_ASSETS"] - inventory,
                             g["TOTAL_CURRENT_LIAB"]),
        "cash_to_short_debt": ratio(g["MONETARYFUNDS"], short_debt),
        "interest_bearing_debt_yi": yi(debt),
        "short_term_debt_yi": yi(short_debt),
        "ocf_yi": yi(ocf),
        "ocf_to_current_liab": ratio(ocf, g["TOTAL_CURRENT_LIAB"]),
        "capex_yi": yi(capex),
        "fcf_yi": yi(None if ocf is None or capex is None else ocf - capex),
        "gross_margin": gross,
        "net_margin": ratio(g["PARENT_NETPROFIT"], g["TOTAL_OPERATE_INCOME"]),
        "roe": ratio(g["PARENT_NETPROFIT"], positive(average(g["TOTAL_PARENT_EQUITY"], num(pb.get("TOTAL_PARENT_EQUITY"))))),
        "negative_equity": None if g["TOTAL_PARENT_EQUITY"] is None else int(g["TOTAL_PARENT_EQUITY"] < 0),
        "roa": ratio(g["NETPROFIT"], average(g["TOTAL_ASSETS"], num(pb.get("TOTAL_ASSETS")))),
        "deduct_netprofit_yi": yi(g["DEDUCT_PARENT_NETPROFIT"]),
        "interest_coverage": (ratio(g["TOTAL_PROFIT"] + interest, interest)
                              if g["TOTAL_PROFIT"] is not None and interest else None),
        "cip_to_assets": ratio(g["CIP"], g["TOTAL_ASSETS"]),
        "revenue_yoy": (ratio(g["TOTAL_OPERATE_INCOME"] - prior_revenue, prior_revenue)
                        if g["TOTAL_OPERATE_INCOME"] is not None and prior_revenue else None),
        "loss_flag": None if g["PARENT_NETPROFIT"] is None else int(g["PARENT_NETPROFIT"] < 0),
    }
    result.update({f"raw_{k}": v for k, v in g.items()})
    return result


def build(balance_rows, income_rows, cashflow_rows, years: Iterable[int]) -> list[dict]:
    b, i, c = annual_rows(balance_rows), annual_rows(income_rows), annual_rows(cashflow_rows)
    out = []
    for year in years:
        row = indicators_for_year(year, b, i, c)
        if row is not None:
            out.append(row)
    return out
