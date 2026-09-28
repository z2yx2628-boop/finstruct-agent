"""集团财务公司资金归集通道 (group finance-company deposits) — display and scenario only, never scored.

Listed steel companies keep part of their cash at the group's finance company. If the group runs into
trouble, those deposits can be frozen (a contagion channel seen in several non-steel groups). Source:
each company's own 财务公司风险评估/持续评估报告 or related filings (A-grade disclosure), collected in
data/reference/finance_company_deposits.csv. Rows marked verified = N have not yet been checked against
the PDF by a person. Point-in-time: a row is used only on or after its publication date.
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.product_layer import ROOT

DEPOSITS = ROOT / "data" / "reference" / "finance_company_deposits.csv"
SOURCE_LABEL = {"risk_report": "风险评估报告", "parent_report": "母公司风险评估报告（同表列示）",
                "half_year_report": "半年度报告", "shareholder_pack": "股东会会议资料", "related_party_notice": "关联交易公告"}


def _rows() -> list[dict]:
    if not DEPOSITS.exists():
        return []
    with DEPOSITS.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(v: str | None) -> float | None:
    return float(v) if v not in (None, "") else None


def deposit(code: str, as_of: str) -> dict | None:
    """Latest disclosed deposit of the company at its group finance company, published on or before as_of."""
    rows = [r for r in _rows() if r["security_code"] == code and r["source_date"] <= as_of]
    if not rows:
        return None
    r = max(rows, key=lambda r: (r["source_date"], r["period"]))
    return {**r, "deposit_yi": _num(r["deposit_yi"]), "deposit_share": _num(r["deposit_share"]),
            "loan_yi": _num(r["loan_yi"]), "fc_capital_adequacy": _num(r["fc_capital_adequacy"]),
            "source_label": SOURCE_LABEL.get(r["source_type"], r["source_type"])}


def exposure(code: str, as_of: str, equity_yuan: float | None) -> dict | None:
    d = deposit(code, as_of)
    if not d:
        return None
    to_equity = d["deposit_yi"] * 1e8 / equity_yuan if equity_yuan and equity_yuan > 0 else None
    return {**d, "deposit_to_equity": round(to_equity, 4) if to_equity is not None else None}


def by_finance_company(as_of: str, fragility: dict[str, dict], equity: dict[str, float]) -> list[dict]:
    """Scenario '若该财务公司出现兑付问题': which listed companies' cash would be stuck, and how much it matters."""
    groups: dict[str, list[dict]] = {}
    for code in {r["security_code"] for r in _rows()}:
        e = exposure(code, as_of, equity.get(code))
        if e:
            f = fragility.get(code, {})
            groups.setdefault(e["finance_company"], []).append({**e, "tier": f.get("tier", ""), "name": e["security_name"]})
    out = []
    for fc, members in groups.items():
        out.append({"finance_company": fc, "members": sorted(members, key=lambda m: -(m["deposit_to_equity"] or 0)),
                    "total_yi": round(sum(m["deposit_yi"] for m in members), 2),
                    "max_to_equity": max((m["deposit_to_equity"] or 0) for m in members)})
    return sorted(out, key=lambda g: -g["total_yi"])
