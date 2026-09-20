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
