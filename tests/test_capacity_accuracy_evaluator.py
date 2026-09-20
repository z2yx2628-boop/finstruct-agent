from schemas.capacity import (
    CapacityChange,
    CapacityDocument,
    CapacityEvent,
)
from src.capacity_accuracy_evaluator import evaluate_document


def make_document(capacity: float = 100) -> CapacityDocument:
    return CapacityDocument(
        security_code="600019",
        security_name="宝钢股份",
        events=[
            CapacityEvent(
                event_type="capacity_construction",
                project_name="厚板项目",
                capacity_changes=[
                    CapacityChange(
                        action="new",
                        product_name="厚板",
                        capacity=capacity,
                        capacity_unit="万吨/年",
                        source_page=1,
                        evidence_text="年产100万吨厚板",
                        confidence=1,
                    )
                ],
                source_page=1,
                evidence_text="建设厚板项目",
                confidence=1,
            )
        ],
    )


def test_exact_capacity_document_passes():
    report = evaluate_document(make_document(), make_document())

    assert report["passed"] is True
    assert report["event_metrics"]["f1"] == 1
    assert report["capacity_record_metrics"]["f1"] == 1
    assert report["capacity_attribute_metrics"]["accuracy"] == 1


def test_capacity_value_mismatch_is_reported():
    report = evaluate_document(make_document(), make_document(capacity=120))

    assert report["passed"] is False
    assert report["capacity_record_metrics"]["f1"] == 1
    assert report["capacity_attribute_metrics"]["accuracy"] < 1
    assert any(
        item["field"] == "capacity"
        for item in report["field_mismatches"]
    )


def test_narrative_metrics_are_separate_from_factual_metrics():
    gold = make_document()
    prediction = make_document()
    gold.events[0].timeline_text = "计划于2027年建成"
    prediction.events[0].timeline_text = "预计2027年投产"

    report = evaluate_document(gold, prediction)

    assert report["passed"] is False
    assert report["factual_attribute_metrics"]["accuracy"] == 1
    assert report["narrative_attribute_metrics"]["accuracy"] < 1


def test_safe_formatting_metric_does_not_change_strict_pass():
    gold = make_document()
    prediction = make_document()
    gold.events[0].project_name = "2500m3 HyCROF商业化示范项目"
    prediction.events[0].project_name = "2500m³HyCROF 商业化示范项目"

    report = evaluate_document(gold, prediction)

    assert report["passed"] is False
    assert report["event_attribute_metrics"]["accuracy"] < 1
    assert report["canonical_attribute_metrics"]["accuracy"] == 1
