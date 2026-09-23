from collections import Counter
from datetime import date
from decimal import Decimal
import re
from typing import Any

from schemas.pledge import PledgeDocument


EVENT_ORDER = ("pledge", "release", "extension")

DOCUMENT_FIELDS = (
    "security_code",
    "security_name",
    "announcement_number",
    "company_name",
)

TEXT_FIELDS = (
    "shareholder_name",
    "pledgee",
    "purpose",
    "pledge_end_condition",
)

NUMBER_FIELDS = (
    "shares",
    "shareholder_holding_ratio",
    "total_share_capital_ratio",
)

DATE_FIELDS = (
    "pledge_start_date",
    "pledge_end_date",
    "release_date",
    "original_end_date",
    "extended_end_date",
)

BOOLEAN_FIELDS = (
    "is_restricted_share",
    "is_supplementary_pledge",
)

COMMON_REQUIRED_FIELDS = (
    "shareholder_name",
    "shares",
    "shares_unit",
    "shareholder_holding_ratio",
    "total_share_capital_ratio",
    "source_page",
    "evidence_text",
    "confidence",
)

EVENT_REQUIRED_FIELDS = {
    "pledge": (
        "pledge_start_date",
        "pledgee",
        "purpose",
    ),
    "release": (
        "release_date",
        "pledgee",
    ),
    "extension": (
        "pledge_start_date",
        "original_end_date",
        "extended_end_date",
        "pledgee",
        "purpose",
    ),
}

EVENT_SECTION_PHRASES = {
    "pledge": (
        "本次股份质押基本情况",
        "本次质押基本情况",
    ),
    "release": (
        "本次股份解除质押基本情况",
        "本次解除质押基本情况",
        "本次股份解质押基本情况",
        "本次解质押基本情况",
    ),
    "extension": (
        "质押展期",
        "质押延期",
        "延期购回",
    ),
}


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value))


def is_present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def text_supported(value: Any, evidence: str) -> bool:
    return compact(value) in compact(evidence)


def number_supported(value: int | float, evidence: str) -> bool:
    normalized = str(evidence).replace("，", ",")
    normalized = re.sub(r",\s+(?=\d)", ",", normalized)
    normalized = re.sub(r"(?<=\d)\s+(?=\d{1,2},)", "", normalized)
    normalized = normalized.replace(",", "")

    expected = Decimal(str(value))
    candidates = re.findall(
        r"(?<![\d.])[+-]?\d+(?:\.\d+)?(?![\d.])",
        normalized,
    )
    return any(Decimal(candidate) == expected for candidate in candidates)


def date_supported(value: str, evidence: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return text_supported(value, evidence)

    variants = (
        parsed.isoformat(),
        f"{parsed.year}-{parsed.month}-{parsed.day}",
        f"{parsed.year}/{parsed.month}/{parsed.day}",
        f"{parsed.year}年{parsed.month}月{parsed.day}日",
    )
    return any(text_supported(item, evidence) for item in variants)


def boolean_supported(value: bool, evidence: str) -> bool:
    return text_supported("是" if value else "否", evidence)


def detect_expected_event_types(pages: list[dict]) -> set[str]:
    full_text = compact("\n".join(item["text"] for item in pages))
    return {
        event_type
        for event_type, phrases in EVENT_SECTION_PHRASES.items()
        if any(compact(phrase) in full_text for phrase in phrases)
    }


def validate_evidence(
    document: PledgeDocument,
    pages: list[dict],
) -> dict:
    page_map = {item["page"]: item["text"] for item in pages}
    full_text = "\n".join(page_map.values())
    checks = []

    def add_check(
        check: str,
        passed: bool,
        value: Any,
        event_index: int | None = None,
        event_type: str | None = None,
        field: str | None = None,
    ) -> None:
        checks.append({
            "check": check,
            "event_index": event_index,
            "event_type": event_type,
            "field": field,
            "value": value,
            "passed": passed,
        })

    for field in DOCUMENT_FIELDS:
        value = getattr(document, field)
        add_check(
            "document_field",
            is_present(value) and text_supported(value, full_text),
            value,
            field=field,
        )

    expected_event_types = detect_expected_event_types(pages)
    extracted_event_types = {event.event_type for event in document.events}

    for event_type in expected_event_types:
        add_check(
            "event_type_coverage",
            event_type in extracted_event_types,
            event_type,
            event_type=event_type,
        )

    for index, event in enumerate(document.events):
        required_fields = (
            *COMMON_REQUIRED_FIELDS,
            *EVENT_REQUIRED_FIELDS[event.event_type],
        )
        for field in required_fields:
            value = getattr(event, field)
            if not is_present(value):
                add_check(
                    "required_field",
                    False,
                    value,
                    index,
                    event.event_type,
                    field,
                )

        if event.event_type == "pledge" and not (
            is_present(event.pledge_end_date)
            or is_present(event.pledge_end_condition)
        ):
            add_check(
                "required_field",
                False,
                None,
                index,
                event.event_type,
                "pledge_end_date_or_condition",
            )

        page_text = page_map.get(event.source_page)
        evidence = event.evidence_text or ""
        add_check(
            "evidence_on_source_page",
            bool(page_text) and text_supported(evidence, page_text),
            evidence,
            index,
            event.event_type,
            "evidence_text",
        )

        if not page_text or not evidence:
            continue

        for field in TEXT_FIELDS:
            value = getattr(event, field)
            if is_present(value):
                add_check(
                    "evidence_support",
                    text_supported(value, evidence),
                    value,
                    index,
                    event.event_type,
                    field,
                )

        for field in NUMBER_FIELDS:
            value = getattr(event, field)
            if value is not None:
                add_check(
                    "evidence_support",
                    number_supported(value, evidence),
                    value,
                    index,
                    event.event_type,
                    field,
                )

        for field in DATE_FIELDS:
            value = getattr(event, field)
            if value is not None:
                add_check(
                    "evidence_support",
                    date_supported(value, evidence),
                    value,
                    index,
                    event.event_type,
                    field,
                )

        for field in BOOLEAN_FIELDS:
            value = getattr(event, field)
            if value is not None:
                add_check(
                    "evidence_support",
                    boolean_supported(value, evidence),
                    value,
                    index,
                    event.event_type,
                    field,
                )

        add_check(
            "evidence_support",
            text_supported(event.shares_unit, page_text),
            event.shares_unit,
            index,
            event.event_type,
            "shares_unit",
        )

    issues = [item for item in checks if not item["passed"]]
    event_counts = Counter(event.event_type for event in document.events)

    return {
        "passed": not issues,
        "checks_count": len(checks),
        "passed_checks": len(checks) - len(issues),
        "expected_event_types": [
            item for item in EVENT_ORDER if item in expected_event_types
        ],
        "extracted_event_types": [
            item for item in EVENT_ORDER if item in extracted_event_types
        ],
        "missing_event_types": [
            item
            for item in EVENT_ORDER
            if item in expected_event_types and item not in extracted_event_types
        ],
        "event_counts": {
            item: event_counts.get(item, 0) for item in EVENT_ORDER
        },
        "issues": issues,
    }
