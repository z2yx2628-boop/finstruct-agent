from collections import Counter
from typing import Any

from schemas.capacity import CapacityDocument
from src.evidence_validator import (
    date_supported,
    number_supported,
    text_supported,
)


EVENT_ORDER = (
    "capacity_construction",
    "capacity_replacement",
    "technical_upgrade",
    "commissioning",
    "delay",
    "suspension",
    "termination",
)

DOCUMENT_TEXT_FIELDS = (
    "security_code",
    "security_name",
    "company_name",
    "announcement_number",
)


def capacity_unit_supported(value: str, evidence: str) -> bool:
    if text_supported(value, evidence):
        return True
    if value.endswith("/年"):
        base_unit = value.removesuffix("/年")
        return (
            text_supported(base_unit, evidence)
            and text_supported("年产", evidence)
        )
    return False


def validate_capacity_evidence(
    document: CapacityDocument,
    pages: list[dict],
) -> dict:
    page_map = {item["page"]: item["text"] for item in pages}
    full_text = "\n".join(page_map.values())
    checks: list[dict[str, Any]] = []

    def add_check(
        check: str,
        passed: bool,
        value: Any,
        event_index: int | None = None,
        field: str | None = None,
        record_type: str | None = None,
        record_index: int | None = None,
    ) -> None:
        checks.append({
            "check": check,
            "event_index": event_index,
            "record_type": record_type,
            "record_index": record_index,
            "field": field,
            "value": value,
            "passed": passed,
        })

    def check_evidence(
        item: Any,
        event_index: int,
        record_type: str,
        record_index: int | None = None,
    ) -> str:
        page_text = page_map.get(item.source_page, "")
        evidence = item.evidence_text
        add_check(
            "evidence_on_source_page",
            bool(page_text) and text_supported(evidence, page_text),
            evidence,
            event_index,
            "evidence_text",
            record_type,
            record_index,
        )
        return evidence

    for field in DOCUMENT_TEXT_FIELDS:
        value = getattr(document, field)
        if value is not None:
            add_check(
                "document_field_support",
                text_supported(value, full_text),
                value,
                field=field,
            )

    if document.announcement_date is not None:
        add_check(
            "document_field_support",
            date_supported(document.announcement_date, full_text),
            document.announcement_date,
            field="announcement_date",
        )

    for event_index, event in enumerate(document.events):
        check_evidence(event, event_index, "event")

        if event.project_name is not None:
            add_check(
                "project_name_support",
                text_supported(event.project_name, full_text),
                event.project_name,
                event_index,
                "project_name",
                "event",
            )

        if event.investment_amount is not None:
            add_check(
                "investment_support",
                number_supported(event.investment_amount, full_text),
                event.investment_amount,
                event_index,
                "investment_amount",
                "event",
            )
            add_check(
                "investment_support",
                text_supported(event.investment_unit, full_text),
                event.investment_unit,
                event_index,
                "investment_unit",
                "event",
            )

        for record_index, change in enumerate(event.capacity_changes):
            evidence = check_evidence(
                change,
                event_index,
                "capacity_change",
                record_index,
            )
            add_check(
                "capacity_support",
                number_supported(change.capacity, evidence),
                change.capacity,
                event_index,
                "capacity",
                "capacity_change",
                record_index,
            )
            add_check(
                "capacity_support",
                capacity_unit_supported(change.capacity_unit, evidence),
                change.capacity_unit,
                event_index,
                "capacity_unit",
                "capacity_change",
                record_index,
            )

        for record_index, metric in enumerate(
            event.environmental_metrics
        ):
            evidence = check_evidence(
                metric,
                event_index,
                "environmental_metric",
                record_index,
            )
            add_check(
                "environmental_metric_support",
                number_supported(metric.value, evidence),
                metric.value,
                event_index,
                "value",
                "environmental_metric",
                record_index,
            )
            add_check(
                "environmental_metric_support",
                text_supported(metric.unit, evidence),
                metric.unit,
                event_index,
                "unit",
                "environmental_metric",
                record_index,
            )

    issues = [item for item in checks if not item["passed"]]
    event_counts = Counter(event.event_type for event in document.events)
    extracted_event_types = [
        item for item in EVENT_ORDER if event_counts.get(item, 0)
    ]

    return {
        "passed": not issues,
        "checks_count": len(checks),
        "passed_checks": len(checks) - len(issues),
        "expected_event_types": [],
        "extracted_event_types": extracted_event_types,
        "missing_event_types": [],
        "event_counts": {
            item: event_counts.get(item, 0) for item in EVENT_ORDER
        },
        "issues": issues,
    }
