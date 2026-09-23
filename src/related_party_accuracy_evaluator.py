"""Accuracy evaluation for related-party transaction extraction against Gold.

Records are matched within the same transaction_category, preferring the
same counterparty (whitespace/width-insensitive). Strict scoring plus a
canonical score that ignores name spacing/width and accepts equal amounts in
different units (e.g. 1.5亿元 vs 15,000万元).
"""
import argparse
import json
from pathlib import Path

from schemas.related_party import RelatedPartyDocument
from src.capacity_accuracy_evaluator import (
    attribute_metrics,
    comparison_rows,
    detection_metrics,
    ratio,
    values_match,
)
from src.guarantee_accuracy_evaluator import canon
from src.related_party_normalizer import UNIT_SCALE

DOCUMENT_FIELDS = (
    "security_code", "security_name", "company_name", "announcement_number",
    "announcement_date", "estimate_year", "total_estimated_amount",
    "total_estimated_unit", "requires_shareholder_approval",
)
RECORD_FIELDS = (
    "listed_company", "counterparty", "relationship", "transaction_category",
    "estimated_amount", "estimated_unit", "prior_year_actual_amount",
    "prior_year_actual_unit", "currency", "source_page",
)
NARRATIVE_FIELDS = ("category_text", "goods_or_services")
NAME_FIELDS = {"listed_company", "counterparty", "company_name"}
AMOUNT_PAIRS = {
    "estimated_amount": "estimated_unit",
    "prior_year_actual_amount": "prior_year_actual_unit",
    "total_estimated_amount": "total_estimated_unit",
}


def pair_records(gold: list, predicted: list):
    pairs, missing, remaining = [], [], list(predicted)
    for gold_record in gold:
        candidates = [r for r in remaining if r.transaction_category == gold_record.transaction_category]
        if not candidates:
            missing.append(gold_record)
            continue

        def score(record):
            value = sum(values_match(getattr(gold_record, f), getattr(record, f)) for f in RECORD_FIELDS)
            if canon(gold_record.counterparty) == canon(record.counterparty):
                value += len(RECORD_FIELDS) + 1
            return value

        best = max(candidates, key=score)
        remaining.remove(best)
        pairs.append((gold_record, best))
    return pairs, missing, remaining


def amount_value(amount, unit):
    if amount is None or unit not in UNIT_SCALE:
        return None
    return round(amount * UNIT_SCALE[unit], 2)


def canonicalize(rows: list[dict], pairs: list[tuple]) -> list[dict]:
    for row in rows:
        field = row["field"]
        matched = row["matched"] or (field in NAME_FIELDS and canon(row["expected"]) == canon(row["actual"]))
        amount_field = next((a for a, u in AMOUNT_PAIRS.items() if field in (a, u)), None)
        if not matched and amount_field:
            gold, predicted = pairs[row["record_index"]]
            unit_field = AMOUNT_PAIRS[amount_field]
            expected = amount_value(getattr(gold, amount_field), getattr(gold, unit_field))
            matched = expected is not None and expected == amount_value(
                getattr(predicted, amount_field), getattr(predicted, unit_field))
        row["canonical_matched"] = matched
    return rows


def evaluate_document(gold: RelatedPartyDocument, prediction: RelatedPartyDocument) -> dict:
    document_rows = canonicalize(comparison_rows([(gold, prediction)], DOCUMENT_FIELDS, "document"),
                                 [(gold, prediction)])
    pairs, missing, unexpected = pair_records(gold.transactions, prediction.transactions)
    record_rows = canonicalize(comparison_rows(pairs, RECORD_FIELDS, "transaction"), pairs)
    narrative_rows = comparison_rows(pairs, NARRATIVE_FIELDS, "transaction")
    factual = document_rows + record_rows
    return {
        "passed": not missing and not unexpected and all(r["matched"] for r in factual),
        "record_metrics": detection_metrics(pairs, missing, unexpected),
        "document_field_metrics": attribute_metrics(document_rows),
        "record_attribute_metrics": attribute_metrics(record_rows),
        "factual_attribute_metrics": attribute_metrics(factual),
        "canonical_attribute_metrics": attribute_metrics(factual, "canonical_matched"),
        "narrative_attribute_metrics": attribute_metrics(narrative_rows),
        "field_mismatches": [
            {k: row[k] for k in ("record_type", "record_index", "field", "expected", "actual")}
            for row in factual + narrative_rows if not row["matched"]
        ],
        "missing_records": [r.model_dump(include={"transaction_category", "counterparty"}) for r in missing],
        "unexpected_records": [r.model_dump(include={"transaction_category", "counterparty"}) for r in unexpected],
    }


def sum_detection(reports: list[dict]) -> dict:
    tp = sum(r["record_metrics"]["true_positives"] for r in reports)
    fp = sum(r["record_metrics"]["false_positives"] for r in reports)
    fn = sum(r["record_metrics"]["false_negatives"] for r in reports)
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    return {"true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": precision, "recall": recall,
            "f1": 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)}


def sum_attributes(reports: list[dict], name: str) -> dict:
    keys = ("matched", "total", "present_matched", "present_total", "overfilled")
    total = {key: sum(r[name][key] for r in reports) for key in keys}
    total["accuracy"] = ratio(total["matched"], total["total"])
    total["present_accuracy"] = ratio(total["present_matched"], total["present_total"])
    return total


METRICS = (
    ("document_field_metrics", "Document fields"),
    ("record_attribute_metrics", "Record attributes"),
    ("factual_attribute_metrics", "Factual attributes"),
    ("canonical_attribute_metrics", "Factual (canonical names, equal amounts)"),
    ("narrative_attribute_metrics", "Narrative fields (strict)"),
)


def evaluate_directories(gold_dir: Path, prediction_dir: Path) -> dict:
    documents, missing_predictions = {}, []
    for gold_path in sorted(Path(gold_dir).glob("*.json")):
        prediction_path = Path(prediction_dir) / gold_path.name
        if not prediction_path.exists():
            missing_predictions.append(gold_path.name)
            continue
        gold = RelatedPartyDocument.model_validate_json(gold_path.read_text(encoding="utf-8"))
        prediction = RelatedPartyDocument.model_validate_json(prediction_path.read_text(encoding="utf-8"))
        documents[gold_path.stem] = evaluate_document(gold, prediction)
    reports = list(documents.values())
    return {
        "passed": not missing_predictions and all(r["passed"] for r in reports),
        "corpus": {"evaluated_documents": len(reports), "missing_predictions": missing_predictions},
        "record_metrics": sum_detection(reports),
        **{name: sum_attributes(reports, name) for name, _ in METRICS},
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
    e = report["record_metrics"]
    print(f"Documents evaluated: {report['corpus']['evaluated_documents']}")
    print(f"Record TP/FP/FN: {e['true_positives']}/{e['false_positives']}/{e['false_negatives']}  "
          f"P/R/F1: {e['precision']:.2%}/{e['recall']:.2%}/{e['f1']:.2%}")
    for name, label in METRICS:
        m = report[name]
        print(f"{label}: {m['matched']}/{m['total']} ({m['accuracy']:.2%}); overfilled={m['overfilled']}")
    print(f"Report saved to: {args.report}")


if __name__ == "__main__":
    main()
