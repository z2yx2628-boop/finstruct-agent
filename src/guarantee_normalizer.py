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
# Numbered closing section "六、累计对外担保数量及逾期担保的数量": background only.
CUMULATIVE_HEADING = re.compile(r"[一二三四五六七八九十]+、(?:公司)?累计对外担保")
PROGRESS_TITLE = re.compile(r"担保(?:事项)?的?进展")
QUOTA_TITLE = re.compile(r"调剂|额度预计|预计.{0,6}额度")


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


def compact_keep_number_breaks(text: str) -> str:
    """Remove whitespace, but keep one space between two digits.

    Table cells such as "3,600.00" followed by the next row number "2" would
    otherwise merge into "3,600.002" and hide the amount.
    """
    def replace(match: re.Match) -> str:
        before = text[match.start() - 1] if match.start() > 0 else ""
        after = text[match.end()] if match.end() < len(text) else ""
        return " " if before.isdigit() and after.isdigit() else ""

    return re.sub(r"\s+", replace, text)


def _amount_in(amount: float, unit: str, text: str) -> tuple[float, str] | None:
    compact_text = compact_keep_number_breaks(text)
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


def cumulative_section_start(pages: list[dict]) -> tuple[int, int] | None:
    """(page, offset in whitespace-free page text) of the cumulative section."""
    for page in pages:
        match = CUMULATIVE_HEADING.search(re.sub(r"\s+", "", page["text"]))
        if match:
            return page["page"], match.start()
    return None


def in_cumulative_section(evidence: str, source_page: int, pages: list[dict]) -> bool:
    start = cumulative_section_start(pages)
    if start is None:
        return False
    page_no, offset = start
    if source_page > page_no:
        return True
    if source_page < page_no:
        return False
    page_text = next((re.sub(r"\s+", "", p["text"]) for p in pages if p["page"] == page_no), "")
    position = page_text.find(re.sub(r"\s+", "", evidence or ""))
    return position >= offset


def is_progress_announcement(pages: list[dict]) -> bool:
    head = re.sub(r"\s+", "", pages[0]["text"])[:300] if pages else ""
    title = re.search(r"关于.{0,60}?公告", head)
    title_text = title.group(0) if title else ""
    return bool(PROGRESS_TITLE.search(title_text)) and not QUOTA_TITLE.search(title_text)


def debt_ratio_supported(value: float, text: str) -> bool:
    compact_text = compact_keep_number_breaks(text)
    for position in number_positions(value, compact_text):
        number = re.match(r"[\d,.]+", compact_text[position:]).group(0)
        if compact_text[position + len(number): position + len(number) + 1] in ("%", "％"):
            return True
    return False


def event_key(event: dict) -> tuple:
    return (
        event["event_type"],
        re.sub(r"\s+", "", event["guarantor"] or ""),
        re.sub(r"\s+", "", event["guaranteed_party"] or ""),
        event["guarantee_amount"],
        event["guarantee_unit"],
        # Same party and amount with different creditors are separate
        # guarantees (one table row per bank), not duplicates.
        re.sub(r"\s+", "", event["creditor"] or ""),
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
    progress = is_progress_announcement(pages)
    for index, event in enumerate(data["events"]):
        if in_cumulative_section(event["evidence_text"], event["source_page"], pages):
            changes.append({"event_index": index, "action": "drop_cumulative_section_event",
                            "event_type": event["event_type"]})
            continue
        if progress and event["event_type"] == "guarantee_limit":
            changes.append({"event_index": index, "action": "drop_prior_limit_in_progress_announcement"})
            continue
        ratio = event["guaranteed_party_debt_ratio"]
        if ratio is not None and not debt_ratio_supported(ratio, full_text):
            event["guaranteed_party_debt_ratio"] = None
            changes.append({"event_index": index, "action": "clear_unsupported_debt_ratio",
                            "original": ratio})
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
