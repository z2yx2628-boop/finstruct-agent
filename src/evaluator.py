import json
import math
from pathlib import Path
from typing import Any

from schemas.pledge import PledgeDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = PROJECT_ROOT / "data" / "gold" / "sample_pledge_gold.json"
PREDICTION_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_prediction.json"
REPORT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_evaluation.json"

DOCUMENT_FIELDS = (
    "security_code",
    "security_name",
    "announcement_number",
    "company_name",
)

RECORD_FIELDS = (
    "shareholder_name",
    "pledged_shares",
    "pledged_shares_unit",
    "pledge_start_date",
    "pledge_end_date",
    "pledgee",
    "shareholder_holding_ratio",
    "total_share_capital_ratio",
    "pledge_purpose",
    "source_page",
)


def values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9)
    return expected == actual


def main() -> None:
    gold = PledgeDocument.model_validate_json(
        GOLD_PATH.read_text(encoding="utf-8")
    )
    prediction = PledgeDocument.model_validate_json(
        PREDICTION_PATH.read_text(encoding="utf-8")
    )

    comparisons = []

    for field in DOCUMENT_FIELDS:
        expected = getattr(gold, field)
        actual = getattr(prediction, field)
        comparisons.append({
            "field": field,
            "expected": expected,
            "actual": actual,
            "matched": values_match(expected, actual),
        })

    for index, (gold_record, predicted_record) in enumerate(
        zip(gold.records, prediction.records)
    ):
        for field in RECORD_FIELDS:
            expected = getattr(gold_record, field)
            actual = getattr(predicted_record, field)
            comparisons.append({
                "field": f"records[{index}].{field}",
                "expected": expected,
                "actual": actual,
                "matched": values_match(expected, actual),
            })

    matched = sum(item["matched"] for item in comparisons)
    total = len(comparisons)
    record_count_match = len(gold.records) == len(prediction.records)

    report = {
        "passed": matched == total and record_count_match,
        "matched_fields": matched,
        "total_fields": total,
        "field_accuracy": matched / total if total else 0,
        "expected_record_count": len(gold.records),
        "predicted_record_count": len(prediction.records),
        "record_count_match": record_count_match,
        "mismatches": [
            item for item in comparisons if not item["matched"]
        ],
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Passed: {report['passed']}")
    print(f"Field accuracy: {matched}/{total} ({report['field_accuracy']:.2%})")
    print(f"Record count match: {record_count_match}")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()