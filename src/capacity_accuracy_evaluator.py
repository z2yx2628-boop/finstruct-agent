import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
from typing import Any
import unicodedata

from schemas.capacity import CapacityDocument


DOCUMENT_FIELDS = (
    "security_code",
    "security_name",
    "company_name",
    "announcement_number",
    "announcement_date",
)

EVENT_IDENTITY_FIELDS = ("event_type",)
EVENT_ATTRIBUTE_FIELDS = (
    "project_name",
    "project_entity",
    "project_location",
    "project_status",
    "investment_amount",
    "investment_unit",
    "investment_currency",
    "funding_source",
    "planned_start_date",
    "planned_completion_date",
    "commissioning_date",
    "delay_until_date",
    "timeline_text",
    "technology_description",
    "project_purpose",
    "source_page",
)

NARRATIVE_EVENT_FIELDS = (
    "timeline_text",
    "technology_description",
    "project_purpose",
)

FACTUAL_EVENT_FIELDS = tuple(
    field for field in EVENT_ATTRIBUTE_FIELDS
    if field not in NARRATIVE_EVENT_FIELDS
)

CAPACITY_IDENTITY_FIELDS = ("action",)
CAPACITY_ATTRIBUTE_FIELDS = (
    "facility_type",
    "product_name",
    "capacity",
    "capacity_unit",
    "source_page",
)

ENVIRONMENT_IDENTITY_FIELDS = ("metric_type",)
ENVIRONMENT_ATTRIBUTE_FIELDS = (
    "metric_name",
    "value",
    "unit",
    "period",
    "source_page",
)


def values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9)
    return expected == actual


def canonical_text(value: str, field: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("m³", "m3")
    value = re.sub(r"\s+", "", value)
    if field == "capacity_unit":
        value = value.replace("吨/座", "t/座")
    return value


def canonical_values_match(field: str, expected: Any, actual: Any) -> bool:
    if values_match(expected, actual):
        return True
    if not isinstance(expected, str) or not isinstance(actual, str):
        return False
    if field not in {"project_name", "capacity_unit"}:
        return False
    return canonical_text(expected, field) == canonical_text(actual, field)


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def f1_score(precision: float, recall: float) -> float:
    if not precision + recall:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def identity(record: Any, fields: tuple[str, ...]) -> tuple:
    return tuple(getattr(record, field) for field in fields)


def pairing_score(gold_record: Any, predicted_record: Any, fields: tuple[str, ...]) -> int:
    """Score a candidate pair; project names dominate and ignore whitespace.

    Pairing only decides which records are compared. Attribute scoring still
    uses the strict and canonical rules, so this cannot inflate accuracy.
    """
    score = sum(
        values_match(
            getattr(gold_record, field),
            getattr(predicted_record, field),
        )
        for field in fields
    )
    gold_name = getattr(gold_record, "project_name", None)
    predicted_name = getattr(predicted_record, "project_name", None)
    if (
        isinstance(gold_name, str)
        and isinstance(predicted_name, str)
        and re.sub(r"\s+", "", gold_name) == re.sub(r"\s+", "", predicted_name)
    ):
        score += len(fields) + 1
    return score


def pair_records(
    gold_records: list,
    predicted_records: list,
    identity_fields: tuple[str, ...],
    attribute_fields: tuple[str, ...],
) -> tuple[list[tuple], list, list]:
    gold_buckets = defaultdict(list)
    prediction_buckets = defaultdict(list)
    for record in gold_records:
        gold_buckets[identity(record, identity_fields)].append(record)
    for record in predicted_records:
        prediction_buckets[identity(record, identity_fields)].append(record)

    pairs = []
    missing = []
    unexpected = []
    for key in sorted(set(gold_buckets) | set(prediction_buckets)):
        gold_bucket = list(gold_buckets[key])
        prediction_bucket = list(prediction_buckets[key])
        while gold_bucket and prediction_bucket:
            gold_record = gold_bucket.pop(0)
            best_index = max(
                range(len(prediction_bucket)),
                key=lambda index: pairing_score(
                    gold_record,
                    prediction_bucket[index],
                    attribute_fields,
                ),
            )
            pairs.append((gold_record, prediction_bucket.pop(best_index)))
        missing.extend(gold_bucket)
        unexpected.extend(prediction_bucket)
    return pairs, missing, unexpected


def comparison_rows(
    pairs: list[tuple],
    fields: tuple[str, ...],
    record_type: str,
) -> list[dict]:
    rows = []
    for record_index, (gold_record, predicted_record) in enumerate(pairs):
        for field in fields:
            expected = getattr(gold_record, field)
            actual = getattr(predicted_record, field)
            rows.append({
                "record_type": record_type,
                "record_index": record_index,
                "field": field,
                "expected": expected,
                "actual": actual,
                "matched": values_match(expected, actual),
                "canonical_matched": canonical_values_match(
                    field,
                    expected,
                    actual,
                ),
            })
    return rows


def detection_metrics(pairs: list, missing: list, unexpected: list) -> dict:
    true_positives = len(pairs)
    false_negatives = len(missing)
    false_positives = len(unexpected)
    precision = ratio(true_positives, true_positives + false_positives)
    recall = ratio(true_positives, true_positives + false_negatives)
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
    }


def attribute_metrics(
    rows: list[dict],
    match_key: str = "matched",
) -> dict:
    matched = sum(item[match_key] for item in rows)
    present = [item for item in rows if item["expected"] is not None]
    present_matched = sum(item[match_key] for item in present)
    overfilled = [
        item
        for item in rows
        if item["expected"] is None and item["actual"] is not None
    ]
    return {
        "matched": matched,
        "total": len(rows),
        "accuracy": ratio(matched, len(rows)),
        "present_matched": present_matched,
        "present_total": len(present),
        "present_accuracy": ratio(present_matched, len(present)),
        "overfilled": len(overfilled),
    }


def evaluate_document(
    gold: CapacityDocument,
    prediction: CapacityDocument,
) -> dict:
    document_rows = comparison_rows(
        [(gold, prediction)],
        DOCUMENT_FIELDS,
        "document",
    )
    event_pairs, missing_events, unexpected_events = pair_records(
        gold.events,
        prediction.events,
        EVENT_IDENTITY_FIELDS,
        EVENT_ATTRIBUTE_FIELDS,
    )
    event_rows = comparison_rows(
        event_pairs,
        EVENT_ATTRIBUTE_FIELDS,
        "event",
    )
    factual_event_rows = [
        row for row in event_rows
        if row["field"] in FACTUAL_EVENT_FIELDS
    ]
    narrative_rows = [
        row for row in event_rows
        if row["field"] in NARRATIVE_EVENT_FIELDS
    ]

    capacity_pairs = []
    missing_capacity = []
    unexpected_capacity = []
    environment_pairs = []
    missing_environment = []
    unexpected_environment = []

    for gold_event, predicted_event in event_pairs:
        pairs, missing, unexpected = pair_records(
            gold_event.capacity_changes,
            predicted_event.capacity_changes,
            CAPACITY_IDENTITY_FIELDS,
            CAPACITY_ATTRIBUTE_FIELDS,
        )
        capacity_pairs.extend(pairs)
        missing_capacity.extend(missing)
        unexpected_capacity.extend(unexpected)

        pairs, missing, unexpected = pair_records(
            gold_event.environmental_metrics,
            predicted_event.environmental_metrics,
            ENVIRONMENT_IDENTITY_FIELDS,
            ENVIRONMENT_ATTRIBUTE_FIELDS,
        )
        environment_pairs.extend(pairs)
        missing_environment.extend(missing)
        unexpected_environment.extend(unexpected)

    for event in missing_events:
        missing_capacity.extend(event.capacity_changes)
        missing_environment.extend(event.environmental_metrics)
    for event in unexpected_events:
        unexpected_capacity.extend(event.capacity_changes)
        unexpected_environment.extend(event.environmental_metrics)

    capacity_rows = comparison_rows(
        capacity_pairs,
        CAPACITY_ATTRIBUTE_FIELDS,
        "capacity_change",
    )
    environment_rows = comparison_rows(
        environment_pairs,
        ENVIRONMENT_ATTRIBUTE_FIELDS,
        "environmental_metric",
    )
    all_rows = document_rows + event_rows + capacity_rows + environment_rows
    factual_rows = (
        document_rows
        + factual_event_rows
        + capacity_rows
        + environment_rows
    )
    all_missing = missing_events + missing_capacity + missing_environment
    all_unexpected = (
        unexpected_events + unexpected_capacity + unexpected_environment
    )

    return {
        "passed": (
            not all_missing
            and not all_unexpected
            and all(item["matched"] for item in all_rows)
        ),
        "event_metrics": detection_metrics(
            event_pairs,
            missing_events,
            unexpected_events,
        ),
        "capacity_record_metrics": detection_metrics(
            capacity_pairs,
            missing_capacity,
            unexpected_capacity,
        ),
        "environment_record_metrics": detection_metrics(
            environment_pairs,
            missing_environment,
            unexpected_environment,
        ),
        "document_field_metrics": attribute_metrics(document_rows),
        "event_attribute_metrics": attribute_metrics(event_rows),
        "capacity_attribute_metrics": attribute_metrics(capacity_rows),
        "environment_attribute_metrics": attribute_metrics(environment_rows),
        "factual_attribute_metrics": attribute_metrics(factual_rows),
        "narrative_attribute_metrics": attribute_metrics(narrative_rows),
        "canonical_attribute_metrics": attribute_metrics(
            all_rows,
            match_key="canonical_matched",
        ),
        "field_mismatches": [
            item for item in all_rows if not item["matched"]
        ],
        "missing_counts": {
            "events": len(missing_events),
            "capacity_records": len(missing_capacity),
            "environment_records": len(missing_environment),
        },
        "unexpected_counts": {
            "events": len(unexpected_events),
            "capacity_records": len(unexpected_capacity),
            "environment_records": len(unexpected_environment),
        },
    }


def sum_metric(reports: list[dict], name: str) -> dict:
    true_positives = sum(item[name]["true_positives"] for item in reports)
    false_positives = sum(item[name]["false_positives"] for item in reports)
    false_negatives = sum(item[name]["false_negatives"] for item in reports)
    precision = ratio(true_positives, true_positives + false_positives)
    recall = ratio(true_positives, true_positives + false_negatives)
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
    }


def sum_attributes(reports: list[dict], name: str) -> dict:
    matched = sum(item[name]["matched"] for item in reports)
    total = sum(item[name]["total"] for item in reports)
    present_matched = sum(item[name]["present_matched"] for item in reports)
    present_total = sum(item[name]["present_total"] for item in reports)
    overfilled = sum(item[name]["overfilled"] for item in reports)
    return {
        "matched": matched,
        "total": total,
        "accuracy": ratio(matched, total),
        "present_matched": present_matched,
        "present_total": present_total,
        "present_accuracy": ratio(present_matched, present_total),
        "overfilled": overfilled,
    }


def evaluate_directories(gold_dir: Path, prediction_dir: Path) -> dict:
    gold_paths = sorted(gold_dir.glob("*.json"))
    prediction_paths = {
        path.name: path for path in prediction_dir.glob("*.json")
    }
    document_reports = {}
    missing_predictions = []

    for gold_path in gold_paths:
        prediction_path = prediction_paths.pop(gold_path.name, None)
        if prediction_path is None:
            missing_predictions.append(gold_path.name)
            continue
        gold = CapacityDocument.model_validate_json(
            gold_path.read_text(encoding="utf-8")
        )
        prediction = CapacityDocument.model_validate_json(
            prediction_path.read_text(encoding="utf-8")
        )
        document_reports[gold_path.stem] = evaluate_document(gold, prediction)

    reports = list(document_reports.values())
    return {
        "passed": (
            bool(gold_paths)
            and not missing_predictions
            and not prediction_paths
            and all(item["passed"] for item in reports)
        ),
        "corpus": {
            "gold_documents": len(gold_paths),
            "evaluated_documents": len(reports),
            "missing_predictions": missing_predictions,
            "unexpected_predictions": sorted(prediction_paths),
        },
        "event_metrics": sum_metric(reports, "event_metrics"),
        "capacity_record_metrics": sum_metric(
            reports,
            "capacity_record_metrics",
        ),
        "environment_record_metrics": sum_metric(
            reports,
            "environment_record_metrics",
        ),
        "document_field_metrics": sum_attributes(
            reports,
            "document_field_metrics",
        ),
        "event_attribute_metrics": sum_attributes(
            reports,
            "event_attribute_metrics",
        ),
        "capacity_attribute_metrics": sum_attributes(
            reports,
            "capacity_attribute_metrics",
        ),
        "environment_attribute_metrics": sum_attributes(
            reports,
            "environment_attribute_metrics",
        ),
        "factual_attribute_metrics": sum_attributes(
            reports,
            "factual_attribute_metrics",
        ),
        "narrative_attribute_metrics": sum_attributes(
            reports,
            "narrative_attribute_metrics",
        ),
        "canonical_attribute_metrics": sum_attributes(
            reports,
            "canonical_attribute_metrics",
        ),
        "documents": document_reports,
    }


def print_detection(label: str, metrics: dict) -> None:
    print(
        f"{label} precision/recall/F1: "
        f"{metrics['precision']:.2%}/"
        f"{metrics['recall']:.2%}/"
        f"{metrics['f1']:.2%}"
    )


def print_attributes(label: str, metrics: dict) -> None:
    print(
        f"{label} accuracy: {metrics['matched']}/{metrics['total']} "
        f"({metrics['accuracy']:.2%}); overfilled={metrics['overfilled']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gold_dir", type=Path)
    parser.add_argument("prediction_dir", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = evaluate_directories(args.gold_dir, args.prediction_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    corpus = report["corpus"]
    print(f"Strict pass: {report['passed']}")
    print(
        "Documents evaluated: "
        f"{corpus['evaluated_documents']}/{corpus['gold_documents']}"
    )
    print_detection("Event", report["event_metrics"])
    print_detection("Capacity record", report["capacity_record_metrics"])
    print_detection(
        "Environmental record",
        report["environment_record_metrics"],
    )
    print_attributes("Document fields", report["document_field_metrics"])
    print_attributes("Event attributes", report["event_attribute_metrics"])
    print_attributes(
        "Capacity attributes",
        report["capacity_attribute_metrics"],
    )
    print_attributes(
        "Environmental attributes",
        report["environment_attribute_metrics"],
    )
    print_attributes(
        "Factual attributes",
        report["factual_attribute_metrics"],
    )
    print_attributes(
        "Narrative fields (strict)",
        report["narrative_attribute_metrics"],
    )
    print_attributes(
        "All attributes (safe canonical formatting)",
        report["canonical_attribute_metrics"],
    )
    print(f"Report saved to: {args.report}")


if __name__ == "__main__":
    main()
