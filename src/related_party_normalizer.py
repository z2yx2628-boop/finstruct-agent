"""Deterministic clean-up for daily related-party transaction extractions."""
import re

from schemas.related_party import RelatedPartyDocument
from src.capacity_normalizer import collapse_cjk_spaces
from src.guarantee_normalizer import amount_supported as _amount_supported
from src.guarantee_normalizer import compact_keep_number_breaks
from src.capacity_normalizer import number_positions

TOTAL_ROW = re.compile(r"^(?:合计|小计|总计|共计|关联采购合计|关联销售合计|日常关联交易总)")
UNIT_SCALE = {"元": 1, "千元": 1e3, "万元": 1e4, "百万元": 1e6, "亿元": 1e8,
              "美元": 1, "万美元": 1e4, "百万美元": 1e6, "亿美元": 1e8}
NAME_FIELDS = ("listed_company", "counterparty")
AMOUNT_FIELDS = (
    ("estimated_amount", "estimated_unit"),
    ("prior_year_actual_amount", "prior_year_actual_unit"),
)


# Deposit/loan/discount arrangements with a group finance company are a
# separate table (out of scope, prompt rule 6a), not daily trading rows.
FINANCE_COMPANY = re.compile(r"财务(?:有限责任|股份有限)?公司")
UNIT_DECLARATION = re.compile(r"单位[:：](千元|百万元|万元|亿元|元)|[（(](千元|百万元|万元|亿元|元)[）)]")


def amount_supported(amount: float, unit: str, text: str, evidence: str | None = None):
    """Like the guarantee check, plus long tables: a number is in `unit` when
    the nearest unit declaration before it ("单位：万元") names that unit and
    no sentence end (。) lies between them, however many rows apart."""
    found = _amount_supported(amount, unit, text, evidence)
    if found is not None:
        return found
    compact_text = compact_keep_number_breaks(text)
    for position in number_positions(amount, compact_text):
        declarations = list(UNIT_DECLARATION.finditer(compact_text, 0, position))
        if not declarations:
            continue
        last = declarations[-1]
        if (last.group(1) or last.group(2)) == unit and "。" not in compact_text[last.end():position]:
            return amount, unit
    return None


def amount_value(amount, unit) -> float | None:
    scale = UNIT_SCALE.get(unit or "")
    return None if amount is None or scale is None else amount * scale


def compact(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def subtotal_indexes(records: list[dict]) -> set[int]:
    """A record whose estimate equals the sum of >= 2 other rows of the same
    category is a category subtotal, not a separate related party."""
    drop = set()
    for index, record in enumerate(records):
        total = amount_value(record["estimated_amount"], record["estimated_unit"])
        if not total:
            continue
        rows = [
            amount_value(other["estimated_amount"], other["estimated_unit"])
            for other_index, other in enumerate(records)
            if other_index != index
            and other["transaction_category"] == record["transaction_category"]
            and compact(other["counterparty"]) != compact(record["counterparty"])
        ]
        rows = [value for value in rows if value]
        if len(rows) >= 2 and abs(sum(rows) - total) <= total * 0.001:
            drop.add(index)
    return drop


def normalize_related_party_fields(
    document: RelatedPartyDocument,
    pages: list[dict],
) -> tuple[RelatedPartyDocument, list[dict]]:
    data = document.model_dump()
    full_text = "\n".join(page["text"] for page in pages)
    changes: list[dict] = []

    for field in ("announcement_number", "company_name", "security_name"):
        value = data.get(field)
        collapsed = collapse_cjk_spaces(value)
        if value is not None and collapsed != value:
            data[field] = collapsed
            changes.append({"action": "collapse_cjk_spaces", "field": field, "original": value})

    amount, unit = data["total_estimated_amount"], data["total_estimated_unit"]
    if amount and unit and amount_supported(amount, unit, full_text) is None:
        changes.append({"action": "clear_unsupported_total", "original": {"amount": amount, "unit": unit}})
        data["total_estimated_amount"] = data["total_estimated_unit"] = None

    records = data["transactions"]
    for index, record in enumerate(records):
        for field in NAME_FIELDS:
            if record[field] is None:
                continue
            collapsed = collapse_cjk_spaces(record[field])
            if collapsed != record[field]:
                changes.append({"record_index": index, "action": "collapse_cjk_spaces",
                                "field": field, "original": record[field]})
                record[field] = collapsed
        for amount_field, unit_field in AMOUNT_FIELDS:
            amount, unit = record[amount_field], record[unit_field]
            if amount is None:
                continue
            supported = amount_supported(amount, unit, full_text, record["evidence_text"]) if unit else None
            if supported is None:
                changes.append({"record_index": index, "action": "clear_unsupported_amount",
                                "field": amount_field, "original": {amount_field: amount, unit_field: unit}})
                record[amount_field] = record[unit_field] = None
            elif supported != (amount, unit):
                record[amount_field], record[unit_field] = supported
                changes.append({"record_index": index, "action": "restore_source_unit",
                                "field": amount_field, "original": {amount_field: amount, unit_field: unit}})
        if record["estimated_amount"] is None and record["prior_year_actual_amount"] is None:
            record["currency"] = None

    subtotals = subtotal_indexes(records)
    kept, seen = [], set()
    for index, record in enumerate(records):
        if TOTAL_ROW.match(compact(record["counterparty"])) or TOTAL_ROW.match(compact(record["category_text"])):
            changes.append({"record_index": index, "action": "drop_total_row"})
            continue
        if record["transaction_category"] == "financial_services" and FINANCE_COMPANY.search(record["counterparty"] or ""):
            changes.append({"record_index": index, "action": "drop_finance_company_service"})
            continue
        if index in subtotals:
            changes.append({"record_index": index, "action": "drop_category_subtotal"})
            continue
        key = (
            record["transaction_category"],
            compact(record["counterparty"]),
            amount_value(record["estimated_amount"], record["estimated_unit"]),
            compact(record["goods_or_services"]),
        )
        if key in seen:
            changes.append({"record_index": index, "action": "remove_duplicate_record"})
            continue
        seen.add(key)
        kept.append(record)
    data["transactions"] = kept
    return RelatedPartyDocument.model_validate(data), changes
