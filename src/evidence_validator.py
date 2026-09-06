from decimal import Decimal
import re
from datetime import date
from typing import Any

from schemas.pledge import PledgeDocument


DOCUMENT_FIELDS = (
    "security_code",
    "security_name",
    "announcement_number",
    "company_name",
)

TEXT_FIELDS = (
    "shareholder_name",
    "pledgee",
    "pledge_purpose",
)

NUMBER_FIELDS = (
    "pledged_shares",
    "shareholder_holding_ratio",
    "total_share_capital_ratio",
)

DATE_FIELDS = (
    "pledge_start_date",
    "pledge_end_date",
)


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value))


def text_supported(value: Any, evidence: str) -> bool:
    return compact(value) in compact(evidence)


def number_supported(value: int | float, evidence: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(evidence))
    normalized = normalized.replace(",", "").replace("，", "")

    decimal_value = Decimal(str(value))
    number = format(decimal_value, "f")
    if "." in number:
        number = number.rstrip("0").rstrip(".")

    pattern = rf"(?<![\d.]){re.escape(number)}(?![\d.])"
    return re.search(pattern, normalized) is not None


def date_supported(value: str, evidence: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return text_supported(value, evidence)

    variants = (
        f"{parsed.year}-{parsed.month}-{parsed.day}",
        f"{parsed.year}/{parsed.month}/{parsed.day}",
        f"{parsed.year}年{parsed.month}月{parsed.day}日",
    )
    return any(text_supported(item, evidence) for item in variants)


def validate_evidence(
    document: PledgeDocument,
    pages: list[dict],
) -> dict:
    page_map = {item["page"]: item["text"] for item in pages}
    full_text = "\n".join(page_map.values())
    checks = []

    def add_check(
        name: str,
        passed: bool,
        value: Any,
        record_index: int | None = None,
    ) -> None:
        checks.append({
            "check": name,
            "record_index": record_index,
            "value": value,
            "passed": passed,
        })

    for field in DOCUMENT_FIELDS:
        value = getattr(document, field)
        if value is not None:
            add_check(field, text_supported(value, full_text), value)

    for index, record in enumerate(document.records):
        page_text = page_map.get(record.source_page)
        evidence = record.evidence_text or ""

        add_check(
            "evidence_on_source_page",
            bool(page_text) and text_supported(evidence, page_text),
            evidence,
            index,
        )

        if not page_text or not evidence:
            continue

        for field in TEXT_FIELDS:
            value = getattr(record, field)
            if value is not None:
                add_check(
                    field,
                    text_supported(value, evidence),
                    value,
                    index,
                )

        for field in NUMBER_FIELDS:
            value = getattr(record, field)
            if value is not None:
                add_check(
                    field,
                    number_supported(value, evidence),
                    value,
                    index,
                )

        for field in DATE_FIELDS:
            value = getattr(record, field)
            if value is not None:
                add_check(
                    field,
                    date_supported(value, evidence),
                    value,
                    index,
                )

        if record.pledged_shares_unit is not None:
            add_check(
                "pledged_shares_unit",
                text_supported(record.pledged_shares_unit, page_text),
                record.pledged_shares_unit,
                index,
            )

    issues = [item for item in checks if not item["passed"]]

    return {
        "passed": not issues,
        "checks_count": len(checks),
        "passed_checks": len(checks) - len(issues),
        "issues": issues,
    }
