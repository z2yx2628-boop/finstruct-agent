"""Deterministic clean-up for daily related-party transaction extractions."""
import re

from schemas.related_party import RelatedPartyDocument
from src.capacity_normalizer import INVESTMENT_UNIT_SCALE, collapse_cjk_spaces
from src.guarantee_normalizer import amount_supported

TOTAL_ROW = re.compile(r"^(?:合计|小计|总计|共计)")
NAME_FIELDS = ("listed_company", "counterparty")
AMOUNT_FIELDS = (
    ("estimated_amount", "estimated_unit"),
    ("prior_year_actual_amount", "prior_year_actual_unit"),
)


def amount_value(amount, unit) -> float | None:
    scale = INVESTMENT_UNIT_SCALE.get(unit or "")
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
        if TOTAL_ROW.match(compact(record["counterparty"])):
            changes.append({"record_index": index, "action": "drop_total_row"})
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
