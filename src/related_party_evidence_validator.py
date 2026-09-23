"""Deterministic evidence checks for related-party transaction extractions."""
from schemas.related_party import RelatedPartyDocument
from src.evidence_validator import compact, date_supported, text_supported
from src.related_party_normalizer import amount_supported

ESTIMATE_PHRASES = ("日常关联交易", "预计金额", "预计发生")


def validate_related_party_evidence(document: RelatedPartyDocument, pages: list[dict]) -> dict:
    page_map = {page["page"]: page["text"] for page in pages}
    full_text = "\n".join(page["text"] for page in pages)
    issues: list[dict] = []
    checks = 0

    def check(ok: bool, value, field: str, index: int | None = None, reason: str = ""):
        nonlocal checks
        checks += 1
        if not ok:
            issues.append({"record_index": index, "field": field, "value": value,
                           "reason": reason or "not found in source text"})

    for field in ("security_code", "security_name", "company_name", "announcement_number"):
        value = getattr(document, field)
        if value:
            check(text_supported(value, full_text), value, field)
    if document.announcement_date:
        check(date_supported(document.announcement_date, full_text), document.announcement_date, "announcement_date")

    for index, record in enumerate(document.transactions):
        check(text_supported(record.evidence_text, page_map.get(record.source_page, "")),
              record.evidence_text[:60], "evidence_text", index, "evidence not found on source_page")
        if record.counterparty:
            check(text_supported(record.counterparty, full_text), record.counterparty, "counterparty", index)
        for amount_field, unit_field in (("estimated_amount", "estimated_unit"),
                                         ("prior_year_actual_amount", "prior_year_actual_unit")):
            amount = getattr(record, amount_field)
            if amount is not None:
                check(amount_supported(amount, getattr(record, unit_field), full_text, record.evidence_text) is not None,
                      amount, amount_field, index)
        if record.estimated_amount is None:
            check(False, None, "estimated_amount", index, "estimate missing")

    text = compact(full_text)
    if not document.transactions and all(phrase in text for phrase in ESTIMATE_PHRASES[:2]):
        check(False, None, "transactions", None, "announcement has an estimate table but no records")

    return {
        "passed": not issues,
        "checks_count": checks,
        "passed_checks": checks - len(issues),
        "issues": issues,
        "record_count": len(document.transactions),
    }
