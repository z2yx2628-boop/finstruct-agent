import json
from pathlib import Path

from schemas.pledge import PledgeDocument
from src.accuracy_evaluator import evaluate_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = PROJECT_ROOT / "data" / "gold" / "sample_pledge_gold.json"
PREDICTION_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_prediction.json"
REPORT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_evaluation.json"


def main() -> None:
    gold = PledgeDocument.model_validate_json(
        GOLD_PATH.read_text(encoding="utf-8")
    )
    prediction = PledgeDocument.model_validate_json(
        PREDICTION_PATH.read_text(encoding="utf-8")
    )
    report = evaluate_document(gold, prediction)

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    events = report["event_metrics"]
    attributes = report["event_attribute_metrics"]
    print(f"Passed: {report['passed']}")
    print(
        "Event precision/recall/F1: "
        f"{events['precision']:.2%}/"
        f"{events['recall']:.2%}/"
        f"{events['f1']:.2%}"
    )
    print(f"Present attribute accuracy: {attributes['present_accuracy']:.2%}")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
