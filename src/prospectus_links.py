"""Named counterparties from bond prospectuses (债券募集说明书): top-5 suppliers, customers, receivables,
prepayments, payables and contract liabilities of steel groups. These are the few PUBLIC sources that name
non-related, cross-group trading partners with amounts. Display only; not added to the scored graph.

Data: data/reference/prospectus_links.csv, extracted by scripts/extract_prospectus_counterparties.py and
cleaned; verified = N until a person checks each row against the PDF page given. Point-in-time: a row is
used only after its balance date (the prospectuses were all published after these dates).
"""
from __future__ import annotations

import csv

from src.entity_resolver import ROOT, load_entities

LINKS = ROOT / "data" / "reference" / "prospectus_links.csv"
ROLE_LABEL = {"supplier": "前五大供应商（采购额）", "customer": "前五大客户（销售）", "receivable": "前五大应收账款（对方欠款）",
              "prepayment": "前五大预付款项（预付给对方）", "payable": "前五大应付账款（欠对方）",
              "contract_liability": "前五大合同负债（对方预付货款）"}
DIRECTION = {"supplier": "upstream", "payable": "upstream", "prepayment": "upstream",
             "customer": "downstream", "receivable": "downstream", "contract_liability": "downstream"}


def rows() -> list[dict]:
    if not LINKS.exists():
        return []
    with LINKS.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def issuers_for(code: str) -> set[str]:
    """The listed company itself and its group (a group prospectus covers all members)."""
    ents, _ = load_entities()
    group = ents.get(code, {}).get("group_id", "")
    return {code} | ({group} if group else set())


def for_company(code: str, as_of: str) -> list[dict]:
    ids = issuers_for(code)
    out = [r for r in rows() if r["issuer_id"] in ids and (r["period"] or "0000")[:7] <= as_of[:7]]
    return sorted(out, key=lambda r: (r["role"], r["period"]), reverse=False)


def cross_group(rows_: list[dict]) -> list[dict]:
    """Rows whose counterparty is stated as NOT a related party."""
    return [r for r in rows_ if r["related_party"] == "否"]
