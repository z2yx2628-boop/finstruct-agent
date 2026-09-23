from schemas.capacity import (
    CapacityChange,
    CapacityDocument,
    CapacityEvent,
)
from src.capacity_evidence_validator import validate_capacity_evidence


EVIDENCE = "宝山基地拟新建年产100万吨钢材生产线，总投资10亿元"
PAGE_TEXT = (
    "证券代码：600019 证券简称：宝钢股份 "
    f"{EVIDENCE}。"
)


def make_document(capacity: float = 100) -> CapacityDocument:
    return CapacityDocument(
        security_code="600019",
        security_name="宝钢股份",
        events=[
            CapacityEvent(
                event_type="capacity_construction",
                project_name="宝山基地",
                project_status="approved",
                investment_amount=10,
                investment_unit="亿元",
                investment_currency="CNY",
                capacity_changes=[
                    CapacityChange(
                        action="new",
                        product_name="钢材",
                        capacity=capacity,
                        capacity_unit="万吨/年",
                        source_page=1,
                        evidence_text=EVIDENCE,
                        confidence=0.95,
                    )
                ],
                source_page=1,
                evidence_text=EVIDENCE,
                confidence=0.95,
            )
        ],
    )


def test_capacity_evidence_passes_when_supported():
    report = validate_capacity_evidence(
        make_document(),
        [{"page": 1, "text": PAGE_TEXT}],
    )

    assert report["passed"] is True
    assert report["issues"] == []


def test_capacity_evidence_rejects_unsupported_number():
    report = validate_capacity_evidence(
        make_document(capacity=200),
        [{"page": 1, "text": PAGE_TEXT}],
    )

    assert report["passed"] is False
    assert any(
        item["field"] == "capacity" for item in report["issues"]
    )
