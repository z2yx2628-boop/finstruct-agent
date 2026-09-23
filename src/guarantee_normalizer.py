"""Deterministic clean-up for guarantee extractions."""
import re

from schemas.guarantee import GuaranteeDocument
from src.capacity_normalizer import (
    collapse_cjk_spaces,
    exact_date_supported,
    investment_unit_forms,
    number_positions,
)

FINANCIAL_INSTITUTION = re.compile(
    r"银行|信用社|信托|金融租赁|融资租赁|证券|保险|资产管理|财务有限公司|农商行|农信"
)
NAME_FIELDS = ("guarantor", "guaranteed_party", "creditor")


def amount_supported(
    amount: float,
    unit: str,
    text: str,
    evidence: str | None = None,
) -> tuple[float, str] | None:
    """The amount must appear in the text with its unit (or an equal 万/亿 form).

    The event's own evidence is searched first, so an equal amount elsewhere
    in the announcement (another row of a table) cannot decide the unit.
    """
    if evidence:
        found = _amount_in(amount, unit, evidence)
        if found is not None:
            return found
    return _amount_in(amount, unit, text)


def _amount_in(amount: float, unit: str, text: str) -> tuple[float, str] | None:
    compact_text = re.sub(r"\s+", "", text)
    for form_amount, form_unit in investment_unit_forms(amount, unit):
        for position in number_positions(form_amount, compact_text):
            number = re.match(r"[\d,.]+", compact_text[position:]).group(0)
            after = compact_text[position + len(number): position + len(number) + len(form_unit) + 3]
            if form_unit in after:
                return form_amount, form_unit
            segment_start = max(compact_text.rfind(m, 0, position) for m in ("。", "；", "\n"))
            header = compact_text[max(0, segment_start, position - 400):position]
            if f"单位：{form_unit}" in header or f"（{form_unit}）" in header:
                return form_amount, form_unit
    return None


def event_key(event: dict) -> tuple:
    return (
        event["event_type"],
        re.sub(r"\s+", "", event["guarantor"] or ""),
        re.sub(r"\s+", "", event["guaranteed_party"] or ""),
        event["guarantee_amount"],
        event["guarantee_unit"],
    )


def normalize_guarantee_fields(
    document: GuaranteeDocument,
    pages: list[dict],
) -> tuple[GuaranteeDocument, list[dict]]:
    data = document.model_dump()
    full_text = "\n".join(page["text"] for page in pages)
    changes: list[dict] = []

    for field in ("announcement_number", "company_name", "security_name"):
        value = data.get(field)
        collapsed = collapse_cjk_spaces(value)
        if value is not None and collapsed != value:
            data[field] = collapsed
            changes.append({"action": "collapse_cjk_spaces", "field": field, "original": value})

    for amount_field, unit_field in (
        ("total_guarantee_balance", "total_guarantee_unit"),
        ("external_guarantee_balance", "external_guarantee_unit"),
        ("overdue_guarantee_amount", "overdue_guarantee_unit"),
    ):
        amount, unit = data[amount_field], data[unit_field]
        if amount and unit and amount_supported(amount, unit, full_text) is None:
            changes.append({
                "action": "clear_unsupported_document_amount",
                "field": amount_field,
                "original": {amount_field: amount, unit_field: unit},
            })
            data[amount_field] = None
            data[unit_field] = None

    kept_events = []
    seen = set()
    for index, event in enumerate(data["events"]):
        for field in NAME_FIELDS:
            value = event[field]
            collapsed = collapse_cjk_spaces(value)
            if value is not None and collapsed != value:
                event[field] = collapsed
                changes.append({
                    "event_index": index, "action": "collapse_cjk_spaces",
                    "field": field, "original": value,
                })

        party = event["guaranteed_party"]
        if (
            party
            and FINANCIAL_INSTITUTION.search(party)
            and not event["creditor"]
            and event["relationship"] is None
        ):
            event["creditor"] = party
            event["guaranteed_party"] = None
            changes.append({
                "event_index": index,
                "action": "move_financial_institution_to_creditor",
                "original": party,
            })

        amount, unit = event["guarantee_amount"], event["guarantee_unit"]
        if amount is not None:
            supported = amount_supported(amount, unit, full_text, event["evidence_text"])
            if supported is None:
                changes.append({
                    "event_index": index, "action": "clear_unsupported_guarantee_amount",
                    "original": {"guarantee_amount": amount, "guarantee_unit": unit},
                })
                event["guarantee_amount"] = None
                event["guarantee_unit"] = None
                event["guarantee_currency"] = None
            elif supported != (amount, unit):
                event["guarantee_amount"], event["guarantee_unit"] = supported
                changes.append({
                    "event_index": index, "action": "restore_source_guarantee_unit",
                    "original": {"guarantee_amount": amount, "guarantee_unit": unit},
                })

        for field in ("start_date", "end_date"):
            value = event[field]
            if value is not None and not exact_date_supported(value, full_text):
                event[field] = None
                changes.append({
                    "event_index": index, "action": "clear_unsupported_exact_date",
                    "field": field, "original": value,
                })

        key = event_key(event)
        if key in seen:
            changes.append({"event_index": index, "action": "remove_duplicate_event"})
            continue
        seen.add(key)
        kept_events.append(event)

    data["events"] = kept_events
    return GuaranteeDocument.model_validate(data), changes
