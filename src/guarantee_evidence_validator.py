"""Deterministic evidence checks for guarantee extractions."""
from collections import Counter
import re

from schemas.guarantee import GuaranteeDocument
from src.evidence_validator import compact, date_supported, text_supported
from src.guarantee_normalizer import amount_supported

EVENT_ORDER = (
    "guarantee_provided",
    "guarantee_limit",
    "guarantee_released",
    "guarantee_overdue",
)
SECTION_PHRASES = {
    "guarantee_limit": ("担保额度", "额度预计"),
    "guarantee_released": ("解除担保", "担保解除", "提前终止"),
    "guarantee_overdue": ("逾期担保金额为", "代偿", "承担担保责任"),
}


def detect_expected_event_types(full_text: str) -> set[str]:
    text = compact(full_text)
    expected = set()
    for event_type, phrases in SECTION_PHRASES.items():
        if any(phrase in text for phrase in phrases):
            expected.add(event_type)
    # "无逾期担保" and "逾期担保金额为0" are not overdue events.
    if re.search(r"(?:无|不存在|没有)逾期|逾期担保(?:金额)?(?:为|累计)?0", text):
        expected.discard("guarantee_overdue")
    return expected


def validate_guarantee_evidence(
    document: GuaranteeDocument,
    pages: list[dict],
) -> dict:
    page_map = {page["page"]: page["text"] for page in pages}
    full_text = "\n".join(page["text"] for page in pages)
    issues: list[dict] = []
    checks = 0

    def check(ok: bool, value, field: str, event_index: int | None = None, reason: str = ""):
        nonlocal checks
        checks += 1
        if not ok:
            issues.append({
                "event_index": event_index,
                "field": field,
                "value": value,
                "reason": reason or "not found in source text",
            })

    for field in ("security_code", "security_name", "company_name", "announcement_number"):
        value = getattr(document, field)
        if value:
            check(text_supported(value, full_text), value, field)
    if document.announcement_date:
        check(date_supported(document.announcement_date, full_text),
              document.announcement_date, "announcement_date")

    for index, event in enumerate(document.events):
        page_text = page_map.get(event.source_page, "")
        check(text_supported(event.evidence_text, page_text), event.evidence_text[:60],
              "evidence_text", index, "evidence not found on source_page")
        for field in ("guarantor", "guaranteed_party", "creditor"):
            value = getattr(event, field)
            if value:
                check(text_supported(value, full_text), value, field, index)
        if event.guarantee_amount is not None:
            check(amount_supported(event.guarantee_amount, event.guarantee_unit, full_text, event.evidence_text) is not None,
                  event.guarantee_amount, "guarantee_amount", index)
        for field in ("start_date", "end_date"):
            value = getattr(event, field)
            if value:
                check(date_supported(value, full_text), value, field, index)
        if event.event_type != "guarantee_limit" and event.guaranteed_party is None:
            check(False, None, "guaranteed_party", index, "guaranteed party missing")

    counts = Counter(event.event_type for event in document.events)
    extracted = [item for item in EVENT_ORDER if counts.get(item)]
    expected = sorted(detect_expected_event_types(full_text), key=EVENT_ORDER.index)
    missing = [item for item in expected if not counts.get(item)]
    for item in missing:
        check(False, item, "event_type", None, "section wording suggests this event type")

    return {
        "passed": not issues,
        "checks_count": checks,
        "passed_checks": checks - len(issues),
        "issues": issues,
        "expected_event_types": expected,
        "extracted_event_types": extracted,
        "missing_event_types": missing,
        "event_counts": {item: counts.get(item, 0) for item in EVENT_ORDER},
    }
