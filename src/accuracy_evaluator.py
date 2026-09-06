import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any

from schemas.pledge import PledgeDocument, PledgeEvent


DOCUMENT_FIELDS = (
    "security_code",
    "security_name",
    "announcement_number",
    "company_name",
)

EVENT_IDENTITY_FIELDS = (
    "event_type",
    "shareholder_name",
    "shares",
    "shares_unit",
    "source_page",
)

EVENT_ATTRIBUTE_FIELDS = (
    "shareholder_holding_ratio",
    "total_share_capital_ratio",
    "is_restricted_share",
    "is_supplementary_pledge",
    "pledge_start_date",
    "pledge_end_date",
    "pledge_end_condition",
    "release_date",
    "original_end_date",
    "extended_end_date",
    "pledgee",
    "purpose",
)


def values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9)
    return expected == actual


def event_identity(event: PledgeEvent) -> tuple:
    return tuple(getattr(event, field) for field in EVENT_IDENTITY_FIELDS)


def identity_dict(identity: tuple) -> dict:
    return dict(zip(EVENT_IDENTITY_FIELDS, identity))


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def f1_score(precision: float, recall: float) -> float:
    return (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def pair_matching_events(
    gold_events: list[PledgeEvent],
    predicted_events: list[PledgeEvent],
) -> tuple[list[tuple[PledgeEvent, PledgeEvent]], list[tuple], list[tuple]]:
    gold_buckets = defaultdict(list)
    prediction_buckets = defaultdict(list)

    for event in gold_events:
        gold_buckets[event_identity(event)].append(event)
    for event in predicted_events:
        prediction_buckets[event_identity(event)].append(event)

    pairs = []
    missing = []
    unexpected = []

    for identity in sorted(set(gold_buckets) | set(prediction_buckets)):
        gold_bucket = list(gold_buckets[identity])
        prediction_bucket = list(prediction_buckets[identity])

        while gold_bucket and prediction_bucket:
            gold_event = gold_bucket.pop(0)
            best_index = max(
                range(len(prediction_bucket)),
                key=lambda index: sum(
                    values_match(
                        getattr(gold_event, field),
                        getattr(prediction_bucket[index], field),
                    )
                    for field in EVENT_ATTRIBUTE_FIELDS
                ),
            )
            pairs.append((gold_event, prediction_bucket.pop(best_index)))

        missing.extend([identity] * len(gold_bucket))
        unexpected.extend([identity] * len(prediction_bucket))

    return pairs, missing, unexpected


def evaluate_document(
    gold: PledgeDocument,
    prediction: PledgeDocument,
) -> dict:
    document_comparisons = []
    for field in DOCUMENT_FIELDS:
        expected = getattr(gold, field)
        actual = getattr(prediction, field)
        document_comparisons.append({
            "field": field,
            "expected": expected,
            "actual": actual,
            "matched": values_match(expected, actual),
        })

    pairs, missing, unexpected = pair_matching_events(
        gold.events,
        prediction.events,
    )
    attribute_comparisons = []
    for event_index, (gold_event, predicted_event) in enumerate(pairs):
        for field in EVENT_ATTRIBUTE_FIELDS:
            expected = getattr(gold_event, field)
            actual = getattr(predicted_event, field)
            attribute_comparisons.append({
                "event_index": event_index,
                "event_identity": identity_dict(event_identity(gold_event)),
                "field": field,
                "expected": expected,
                "actual": actual,
                "matched": values_match(expected, actual),
            })

    true_positives = len(pairs)
    false_negatives = len(missing)
    false_positives = len(unexpected)
    event_precision = ratio(
        true_positives,
        true_positives + false_positives,
    )
    event_recall = ratio(
        true_positives,
        true_positives + false_negatives,
    )

    document_matched = sum(item["matched"] for item in document_comparisons)
    attribute_matched = sum(item["matched"] for item in attribute_comparisons)
    present_attribute_comparisons = [
        item for item in attribute_comparisons if item["expected"] is not None
    ]
    present_attribute_matched = sum(
        item["matched"] for item in present_attribute_comparisons
    )

    return {
        "passed": (
            false_negatives == 0
            and false_positives == 0
            and document_matched == len(document_comparisons)
            and attribute_matched == len(attribute_comparisons)
        ),
        "event_metrics": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": event_precision,
            "recall": event_recall,
            "f1": f1_score(event_precision, event_recall),
        },
        "document_field_metrics": {
            "matched": document_matched,
            "total": len(document_comparisons),
            "accuracy": ratio(document_matched, len(document_comparisons)),
        },
        "event_attribute_metrics": {
            "matched": attribute_matched,
            "total": len(attribute_comparisons),
            "accuracy": ratio(attribute_matched, len(attribute_comparisons)),
            "present_matched": present_attribute_matched,
            "present_total": len(present_attribute_comparisons),
            "present_accuracy": ratio(
                present_attribute_matched,
                len(present_attribute_comparisons),
            ),
        },
        "missing_events": [identity_dict(item) for item in missing],
        "unexpected_events": [identity_dict(item) for item in unexpected],
        "field_mismatches": [
            item
            for item in (*document_comparisons, *attribute_comparisons)
            if not item["matched"]
        ],
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

        gold = PledgeDocument.model_validate_json(
            gold_path.read_text(encoding="utf-8")
        )
        prediction = PledgeDocument.model_validate_json(
            prediction_path.read_text(encoding="utf-8")
        )
        document_reports[gold_path.stem] = evaluate_document(gold, prediction)

    reports = list(document_reports.values())
    event_tp = sum(item["event_metrics"]["true_positives"] for item in reports)
    event_fp = sum(item["event_metrics"]["false_positives"] for item in reports)
    event_fn = sum(item["event_metrics"]["false_negatives"] for item in reports)
    event_precision = ratio(event_tp, event_tp + event_fp)
    event_recall = ratio(event_tp, event_tp + event_fn)

    document_matched = sum(
        item["document_field_metrics"]["matched"] for item in reports
    )
    document_total = sum(
        item["document_field_metrics"]["total"] for item in reports
    )
    attribute_matched = sum(
        item["event_attribute_metrics"]["matched"] for item in reports
    )
    attribute_total = sum(
        item["event_attribute_metrics"]["total"] for item in reports
    )
    present_matched = sum(
        item["event_attribute_metrics"]["present_matched"] for item in reports
    )
    present_total = sum(
        item["event_attribute_metrics"]["present_total"] for item in reports
    )

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
        "event_metrics": {
            "true_positives": event_tp,
            "false_positives": event_fp,
            "false_negatives": event_fn,
            "precision": event_precision,
            "recall": event_recall,
            "f1": f1_score(event_precision, event_recall),
        },
        "document_field_metrics": {
            "matched": document_matched,
            "total": document_total,
            "accuracy": ratio(document_matched, document_total),
        },
        "event_attribute_metrics": {
            "matched": attribute_matched,
            "total": attribute_total,
            "accuracy": ratio(attribute_matched, attribute_total),
            "present_matched": present_matched,
            "present_total": present_total,
            "present_accuracy": ratio(present_matched, present_total),
        },
        "documents": document_reports,
    }


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

    metrics = report["event_metrics"]
    attributes = report["event_attribute_metrics"]
    print(
        "Event precision/recall/F1: "
        f"{metrics['precision']:.2%}/"
        f"{metrics['recall']:.2%}/"
        f"{metrics['f1']:.2%}"
    )
    print(f"Present attribute accuracy: {attributes['present_accuracy']:.2%}")
    print(f"Report saved to: {args.report}")


if __name__ == "__main__":
    main()
