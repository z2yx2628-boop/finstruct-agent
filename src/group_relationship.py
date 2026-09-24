"""Deterministic relationship for group-level rows of a related-party table.

"八钢公司及子公司" in 八一钢铁's table is its controlling shareholder (plus subsidiaries);
"八钢公司之子公司" are sister companies; "宝武集团之联营企业" are other related parties.
When a counterparty resolves (src/entity_resolver.py) to the issuer itself or to a company
on the issuer's parent chain, the name's scope decides the relationship; otherwise the
model's answer is kept.
"""
from __future__ import annotations

from src.entity_resolver import load_entities, resolve

BY_SCOPE_FOR_PARENT = {
    "self": "parent_or_controlling_shareholder",
    "self_and_subsidiaries": "parent_or_controlling_shareholder",
    "subsidiaries": "sister_company",
    "associates": "other_related_party",
}


def ancestors(entity_id: str) -> list[str]:
    rows, _ = load_entities()
    chain, current = [], rows.get(entity_id, {}).get("parent_id")
    while current and current in rows and current not in chain:
        chain.append(current)
        current = rows[current].get("parent_id")
    return chain


def group_relationship(counterparty: str | None, issuer_code: str | None) -> str | None:
    """Relationship implied by the entity table, or None when the table does not decide it."""
    rows, _ = load_entities()
    if not counterparty or issuer_code not in rows:
        return None
    res = resolve(counterparty, issuer_code)
    if res.entity_id is None:
        return None
    if res.entity_id == issuer_code:
        return "associate_or_joint_venture" if res.scope == "associates" else None
    if res.entity_id in ancestors(issuer_code):
        return BY_SCOPE_FOR_PARENT.get(res.scope)
    return None
