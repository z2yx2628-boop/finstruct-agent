"""Overseas / EU revenue share from annual-report regional disclosures.

Direction 2 external variable: each steel mill's exposure to overseas and EU
markets. Values are typed in by hand from the "营业收入按地区分类" table of the
annual report; this module only validates rows and derives the shares, so the
numbers stay traceable to a page.
"""
from __future__ import annotations

import csv
from pathlib import Path

FIELDS = [
    "security_code", "security_name", "fiscal_year", "currency", "unit",
    "total_revenue", "domestic_revenue", "overseas_revenue", "overseas_share",
    "eu_revenue", "eu_share", "eu_disclosure", "region_labels",
    "export_volume", "export_volume_unit", "source_report", "source_page",
    "source_url", "filled_by", "verified", "notes",
]
EU_DISCLOSURE = {"", "explicit_eu", "europe_region", "not_disclosed"}
UNITS = {"", "元", "千元", "万元", "百万元", "亿元"}


def _number(value: str) -> float | None:
    value = (value or "").replace(",", "").replace("，", "").strip()
    return float(value) if value else None


def validate_row(row: dict) -> list[str]:
    problems = []
    total = _number(row.get("total_revenue", ""))
    domestic = _number(row.get("domestic_revenue", ""))
    overseas = _number(row.get("overseas_revenue", ""))
    eu = _number(row.get("eu_revenue", ""))
    filled = any(v is not None for v in (total, domestic, overseas, eu))
    if row.get("unit", "") not in UNITS:
        problems.append(f"unknown unit {row.get('unit')!r}")
    if row.get("eu_disclosure", "") not in EU_DISCLOSURE:
        problems.append(f"unknown eu_disclosure {row.get('eu_disclosure')!r}")
    if not filled:
        return problems
    if not row.get("unit"):
        problems.append("amounts filled but unit empty")
    if not row.get("source_report") or not row.get("source_page"):
        problems.append("amounts filled but source_report/source_page empty")
    if total is not None and overseas is not None and overseas > total * 1.001:
        problems.append("overseas_revenue exceeds total_revenue")
    if total is not None and domestic is not None and overseas is not None:
        if abs(domestic + overseas - total) > max(total * 0.02, 1e-6):
            problems.append("domestic + overseas differs from total by >2% (check 分部抵销)")
    if eu is not None and overseas is not None and eu > overseas * 1.001:
        problems.append("eu_revenue exceeds overseas_revenue")
    if eu is not None and row.get("eu_disclosure") not in {"explicit_eu", "europe_region"}:
        problems.append("eu_revenue filled but eu_disclosure not explicit_eu/europe_region")
    return problems


def derive_shares(row: dict) -> dict:
    out = dict(row)
    total = _number(row.get("total_revenue", ""))
    domestic = _number(row.get("domestic_revenue", ""))
    overseas = _number(row.get("overseas_revenue", ""))
    eu = _number(row.get("eu_revenue", ""))
    if overseas is None and total is not None and domestic is not None:
        overseas = total - domestic
        out["overseas_revenue"] = f"{overseas:.2f}"
        out["notes"] = (row.get("notes", "") + " overseas=total-domestic").strip()
    # Denominator: domestic+overseas when both known (regional table basis),
    # otherwise total revenue.
    base = domestic + overseas if domestic is not None and overseas is not None else total
    if base:
        if overseas is not None:
            out["overseas_share"] = f"{overseas / base:.4f}"
        if eu is not None:
            out["eu_share"] = f"{eu / base:.4f}"
    return out


def process(path: Path, write: bool = False) -> dict[int, list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    problems = {i + 2: p for i, r in enumerate(rows) if (p := validate_row(r))}
    if write and not problems:
        rows = [derive_shares(r) for r in rows]
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    return problems
