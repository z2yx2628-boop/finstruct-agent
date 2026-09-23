"""Accuracy evaluation for guarantee extraction against Gold JSON files.

Events are matched within the same event_type, preferring the same
guaranteed party (whitespace-insensitive). Attribute scoring is strict, with
a separate canonical score that ignores whitespace and full/half-width
differences in names.
"""
import argparse
import json
from pathlib import Path
import re

from schemas.guarantee import GuaranteeDocument
from src.capacity_accuracy_evaluator import (
    attribute_metrics,
    comparison_rows,
    detection_metrics,
    ratio,
    values_match,
)

DOCUMENT_FIELDS = (
    "security_code", "security_name", "company_name",
    "announcement_number", "announcement_date",
    "total_guarantee_balance", "total_guarantee_unit",
    "total_guarantee_net_asset_ratio",
    "external_guarantee_balance", "external_guarantee_unit",
    "overdue_guarantee_amount", "overdue_guarantee_unit",
)
EVENT_FIELDS = (
    "guarantor", "guaranteed_party", "relationship", "is_related_transaction",
    "guarantee_amount", "guarantee_unit", "guarantee_currency",
    "guarantee_type", "creditor", "start_date", "end_date",
    "has_counter_guarantee", "guaranteed_party_debt_ratio", "source_page",
)
NARRATIVE_FIELDS = ("period_text", "guaranteed_debt_purpose")
NAME_FIELDS = {"guarantor", "guaranteed_party", "creditor", "company_name"}


def canon(value):
    if isinstance(value, str):
        import unicodedata
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))
    return value


def pair_events(gold: list, predicted: list):
    pairs, missing, remaining = [], [], list(predicted)
    for gold_event in gold:
        candidates = [e for e in remaining if e.event_type == gold_event.event_type]
        if not candidates:
            missing.append(gold_event)
            continue

        def score(event):
            value = sum(values_match(getattr(gold_event, f), getattr(event, f)) for f in EVENT_FIELDS)
            if canon(gold_event.guaranteed_party) == canon(event.guaranteed_party):
                value += len(EVENT_FIELDS) + 1
            return value

        best = max(candidates, key=score)
        remaining.remove(best)
        pairs.append((gold_event, best))
    return pairs, missing, remaining


AMOUNT_PAIRS = {
    "guarantee_amount": "guarantee_unit",
    "total_guarantee_balance": "total_guarantee_unit",
    "external_guarantee_balance": "external_guarantee_unit",
    "overdue_guarantee_amount": "overdue_guarantee_unit",
}
UNIT_SCALE = {"元": 1, "万元": 1e4, "亿元": 1e8, "美元": 1, "万美元": 1e4, "亿美元": 1e8}


def amount_value(amount, unit):
    if amount is None or unit not in UNIT_SCALE:
        return None
    return round(amount * UNIT_SCALE[unit], 2), "USD" if unit.endswith("美元") else "CNY"


def mark_equal_amounts(rows: list[dict], pairs: list[tuple]) -> list[dict]:
    """Canonical scoring: 1.5亿元 and 15,000万元 are the same amount."""
    for row in rows:
        field = row["field"]
        amount_field = next((a for a, u in AMOUNT_PAIRS.items() if field in (a, u)), None)
        if amount_field is None or row["canonical_matched"]:
            continue
        gold, predicted = pairs[row["record_index"]]
        unit_field = AMOUNT_PAIRS[amount_field]
        expected = amount_value(getattr(gold, amount_field), getattr(gold, unit_field))
        actual = amount_value(getattr(predicted, amount_field), getattr(predicted, unit_field))
        if expected is not None and expected == actual:
            row["canonical_matched"] = True
    return rows


def add_canonical(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["canonical_matched"] = row["matched"] or (
            row["field"] in NAME_FIELDS and canon(row["expected"]) == canon(row["actual"])
        )
    return rows


def evaluate_document(gold: GuaranteeDocument, prediction: GuaranteeDocument) -> dict:
    document_rows = mark_equal_amounts(
        add_canonical(comparison_rows([(gold, prediction)], DOCUMENT_FIELDS, "document")),
        [(gold, prediction)],
    )
    pairs, missing, unexpected = pair_events(gold.events, prediction.events)
    event_rows = mark_equal_amounts(add_canonical(comparison_rows(pairs, EVENT_FIELDS, "event")), pairs)
    narrative_rows = comparison_rows(pairs, NARRATIVE_FIELDS, "event")
    factual = document_rows + event_rows
    return {
        "passed": not missing and not unexpected and all(r["matched"] for r in factual),
        "event_metrics": detection_metrics(pairs, missing, unexpected),
        "document_field_metrics": attribute_metrics(document_rows),
        "event_attribute_metrics": attribute_metrics(event_rows),
        "factual_attribute_metrics": attribute_metrics(factual),
        "canonical_attribute_metrics": attribute_metrics(factual, "canonical_matched"),
        "narrative_attribute_metrics": attribute_metrics(narrative_rows),
        "field_mismatches": [
            {k: row[k] for k in ("record_type", "record_index", "field", "expected", "actual")}
            for row in factual + narrative_rows if not row["matched"]
        ],
        "missing_events": [e.model_dump(include={"event_type", "guarantor", "guaranteed_party"}) for e in missing],
        "unexpected_events": [e.model_dump(include={"event_type", "guarantor", "guaranteed_party"}) for e in unexpected],
    }


def sum_detection(reports: list[dict]) -> dict:
    tp = sum(r["event_metrics"]["true_positives"] for r in reports)
    fp = sum(r["event_metrics"]["false_positives"] for r in reports)
    fn = sum(r["event_metrics"]["false_negatives"] for r in reports)
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": precision, "recall": recall,
        "f1": 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall),
    }


def sum_attributes(reports: list[dict], name: str) -> dict:
    keys = ("matched", "total", "present_matched", "present_total", "overfilled")
    total = {key: sum(r[name][key] for r in reports) for key in keys}
    total["accuracy"] = ratio(total["matched"], total["total"])
    total["present_accuracy"] = ratio(total["present_matched"], total["present_total"])
    return total


def evaluate_directories(gold_dir: Path, prediction_dir: Path) -> dict:
    documents, missing_predictions = {}, []
    for gold_path in sorted(Path(gold_dir).glob("*.json")):
        prediction_path = Path(prediction_dir) / gold_path.name
        if not prediction_path.exists():
            missing_predictions.append(gold_path.name)
            continue
        gold = GuaranteeDocument.model_validate_json(gold_path.read_text(encoding="utf-8"))
        prediction = GuaranteeDocument.model_validate_json(prediction_path.read_text(encoding="utf-8"))
        documents[gold_path.stem] = evaluate_document(gold, prediction)
    reports = list(documents.values())
    return {
        "passed": not missing_predictions and all(r["passed"] for r in reports),
        "corpus": {"evaluated_documents": len(reports), "missing_predictions": missing_predictions},
        "event_metrics": sum_detection(reports),
        **{
            name: sum_attributes(reports, name)
            for name in (
                "document_field_metrics", "event_attribute_metrics",
                "factual_attribute_metrics", "canonical_attribute_metrics",
                "narrative_attribute_metrics",
            )
        },
        "documents": documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gold_dir", type=Path)
    parser.add_argument("prediction_dir", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_directories(args.gold_dir, args.prediction_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    e = report["event_metrics"]
    print(f"Documents evaluated: {report['corpus']['evaluated_documents']}")
    print(f"Event TP/FP/FN: {e['true_positives']}/{e['false_positives']}/{e['false_negatives']}  "
          f"P/R/F1: {e['precision']:.2%}/{e['recall']:.2%}/{e['f1']:.2%}")
    for name, label in (
        ("document_field_metrics", "Document fields"),
        ("event_attribute_metrics", "Event attributes"),
        ("factual_attribute_metrics", "Factual attributes"),
        ("canonical_attribute_metrics", "Factual (canonical names, equal amounts)"),
        ("narrative_attribute_metrics", "Narrative fields (strict)"),
    ):
        m = report[name]
        print(f"{label}: {m['matched']}/{m['total']} ({m['accuracy']:.2%}); overfilled={m['overfilled']}")
    print(f"Report saved to: {args.report}")


if __name__ == "__main__":
    main()
