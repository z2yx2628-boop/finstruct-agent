"""Named trading relations with amount (亿元), share and persistence, point-in-time.

Data: data/reference/supply_relations.csv (scripts/build_supply_relations.py). A row is used only from its
`available_from` date (announcement date / balance date / annual-report deadline), and the persistence
(years seen, consecutive years) is recomputed from the rows available on the assessment date, so a backtest
never counts a year that had not been disclosed yet.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache

from src.entity_resolver import ROOT, load_entities

TABLE = ROOT / "data" / "reference" / "supply_relations.csv"
SIDE = {"upstream": "上游：供应商", "downstream": "下游：客户"}


@lru_cache(maxsize=1)
def _rows() -> tuple[dict, ...]:
    if not TABLE.exists():
        return ()
    with TABLE.open(encoding="utf-8-sig", newline="") as f:
        return tuple(csv.DictReader(f))


def issuers_for(code: str) -> set[str]:
    ents, _ = load_entities()
    group = ents.get(code, {}).get("group_id", "")
    return {code} | ({group} if group else set())


def available(code: str, as_of: str, include_group: bool = True) -> list[dict]:
    ids = issuers_for(code) if include_group else {code}
    return [r for r in _rows() if r["company_id"] in ids and r.get("available_from", "") <= as_of]


def _norm(name: str) -> str:
    n = re.sub(r"\s+", "", name or "").replace("(", "（").replace(")", "）")
    return re.sub(r"(股份)?有限(责任)?公司$", "", n)


def summary(code: str, as_of: str, include_group: bool = True) -> list[dict]:
    """One line per (issuer, direction, counterparty): the latest year with an amount, its total over all
    categories, the share of that total, and how many years the relation has appeared (as of `as_of`)."""
    rows = available(code, as_of, include_group)
    by_key: dict[tuple, list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["company_id"], r["direction"], r["counterparty_key"]), []).append(r)
    out = []
    for (company, direction, key), rs in by_key.items():
        # a year counts only when the relation happened (next year's cap is a plan; an anonymous "客户一" cannot be
        # followed from one annual report to the next)
        years = sorted({int(r["year"]) for r in rs if r["year"] and r["amount_type"] != "预计额度（上限）"
                        and r.get("counterparty_named", "Y") != "N"})
        last, run = (years[-1], 1) if years else (None, 0)
        while last is not None and last - run in years:
            run += 1
        # the most informative figure: actual amounts before caps and balances, latest year first
        rank = {"上年实际发生": 3, "采购额": 3, "销售额": 3, "期末余额": 2, "销量": 2, "预计额度（上限）": 1}
        best_year = max(years) if years else None
        pick = max(rs, key=lambda r: (rank.get(r["amount_type"], 0), r["year"]))
        same = [r for r in rs if r["year"] == pick["year"] and r["amount_type"] == pick["amount_type"]]
        amount = sum(float(r["amount_wan"]) for r in same if r["amount_wan"]) or None
        shares = [float(r["share"]) for r in same if r["share"]]
        share = sum(shares) if shares and len(shares) == len(same) else (max(shares) if shares else None)
        out.append({"company_id": company, "company_name": pick["company_name"], "direction": direction,
                    "counterparty": max((r["counterparty"] for r in rs), key=len), "related_party": pick["related_party"],
                    "relation": pick["relation"], "year": pick["year"], "amount_type": pick["amount_type"],
                    "amount_yi": amount / 1e4 if amount else None,
                    "quantity": f"{pick['quantity']} {pick['quantity_unit']}" if pick.get("quantity") else "",
                    "share": share, "share_basis": pick["share_basis"], "share_method": pick["share_method"],
                    "years_seen": len(years), "run_years": run, "first_year": years[0] if years else None,
                    "last_year": best_year, "source_type": pick["source_type"], "source": pick["source"],
                    "n_items": len(same)})
    return sorted(out, key=lambda r: (r["direction"], -(r["share"] or 0), -(r["amount_yi"] or 0)))


def lookup(company: str, counterparty: str, direction: str, as_of: str) -> dict | None:
    """The summary line for one counterparty of `company` (matched on the normalised name), or None."""
    target = _norm(counterparty)
    for r in summary(company, as_of, include_group=False):
        if r["direction"] == direction and (target in _norm(r["counterparty"]) or _norm(r["counterparty"]) in target):
            return r
    return None


def describe(r: dict | None) -> str:
    """'占营业成本 4.5%，连续 3 年' for effect labels; empty when nothing is known."""
    if not r:
        return ""
    parts = []
    if r["share"] is not None:
        basis = re.sub(r"（.*?）", "", r["share_basis"] or "占比").replace(f"{r['year']}年", "")
        parts.append(f"{basis} {r['share']:.1%}")
    if r["years_seen"] > 1:
        parts.append(f"连续 {r['run_years']} 年" if r["run_years"] == r["years_seen"] else f"{r['years_seen']} 年出现")
    return "，".join(parts)


CONC = ROOT / "data" / "reference" / "annual_concentration.csv"


@lru_cache(maxsize=1)
def _conc() -> tuple[dict, ...]:
    if not CONC.exists():
        return ()
    with CONC.open(encoding="utf-8-sig", newline="") as f:
        return tuple(csv.DictReader(f))


def concentration(code: str, as_of: str) -> list[dict]:
    """Top-5 customer / supplier concentration by year from the annual reports published by `as_of`
    (an annual report counts from its statutory deadline, 30 April of the next year, when no date is known)."""
    from src.quarterly import available_by
    out = []
    for r in _conc():
        if r["company_id"] != code or r.get("check") == "section_not_found":
            continue
        if available_by(f"{r['fy']}1231") > as_of:
            continue
        f = lambda k: float(r[k]) if r.get(k) not in (None, "") else None  # noqa: E731
        out.append({"fy": r["fy"], "side": r["side"], "top5_share": f("top5_share"), "top5_yi": (f("top5_wan") or 0) / 1e4 or None,
                    "related_share": f("related_share"), "largest_share": f("largest_share"),
                    "total_yi": (f("total_wan") or 0) / 1e4 or None, "rows_named": int(r.get("rows_named") or 0),
                    "page": r["page"], "check": r["check"], "source": r["source"]})
    return sorted(out, key=lambda r: (r["side"], r["fy"]))
