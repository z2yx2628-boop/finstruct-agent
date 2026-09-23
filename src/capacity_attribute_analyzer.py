import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


NARRATIVE_FIELDS = {
    "timeline_text",
    "technology_description",
    "project_purpose",
}

CATEGORICAL_FIELDS = {
    "event_type",
    "project_status",
    "action",
    "metric_type",
    "source_page",
}


def classify_mismatch(item: dict[str, Any]) -> str:
    expected = item.get("expected")
    actual = item.get("actual")
    field = item["field"]
    if expected is None and actual is not None:
        return "overfill"
    if expected is not None and actual is None:
        return "missing_value"
    if item.get("canonical_matched"):
        return "safe_formatting_difference"
    if field in NARRATIVE_FIELDS:
        return "narrative_wording_or_coverage"
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return "numeric_mismatch"
    if field in CATEGORICAL_FIELDS or field.endswith("_date"):
        return "categorical_or_date_mismatch"
    return "factual_text_mismatch"


def analyze_report(report: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for document_name, document in report.get("documents", {}).items():
        for mismatch in document.get("field_mismatches", []):
            row = {
                "document": document_name,
                **mismatch,
                "category": classify_mismatch(mismatch),
            }
            rows.append(row)

    by_category = Counter(row["category"] for row in rows)
    by_record_type = Counter(row["record_type"] for row in rows)
    by_field = Counter(
        f"{row['record_type']}.{row['field']}" for row in rows
    )
    return {
        "mismatch_count": len(rows),
        "by_category": dict(by_category.most_common()),
        "by_record_type": dict(by_record_type.most_common()),
        "by_field": dict(by_field.most_common()),
        "items": rows,
        "interpretation": {
            "strict_score_preserved": True,
            "safe_formatting_difference": (
                "Only Unicode/whitespace and explicit unit aliases are "
                "treated as formatting differences."
            ),
            "narrative_wording_or_coverage": (
                "Reported separately; it is not converted into a strict "
                "match without semantic review."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    analysis = analyze_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Mismatches analyzed: {analysis['mismatch_count']}")
    for name, count in analysis["by_category"].items():
        print(f"{name}: {count}")
    print(f"Analysis saved to: {args.output}")


if __name__ == "__main__":
    main()
