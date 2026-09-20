from schemas.capacity import (
    CapacityDocument,
    CapacityEvent,
    EnvironmentalMetric,
)
from src.capacity_normalizer import (
    normalize_capacity_fields,
    sanitize_capacity_payload,
)


def make_document() -> CapacityDocument:
    return CapacityDocument(
        events=[
            CapacityEvent(
                event_type="capacity_construction",
                project_name="原文不存在的项目名",
                investment_amount=2_000_000_000,
                investment_unit="美元",
                investment_currency="USD",
                funding_source="现金出资",
                environmental_metrics=[
                    EnvironmentalMetric(
                        metric_type="carbon_reduction",
                        metric_name="绿色低碳",
                        value=0,
                        unit="定性表述",
                        source_page=1,
                        evidence_text="建设绿色低碳厚板工厂",
                        confidence=0.6,
                    )
                ],
                source_page=1,
                evidence_text="建设绿色低碳厚板工厂",
                confidence=0.9,
            )
        ]
    )


def test_normalizer_removes_unsupported_overfill():
    document, changes = normalize_capacity_fields(
        make_document(),
        [{"page": 1, "text": "注册资本20亿美元，建设绿色低碳工厂"}],
    )

    event = document.events[0]
    assert event.project_name is None
    assert event.investment_amount is None
    assert event.investment_unit is None
    assert event.investment_currency is None
    assert event.funding_source is None
    assert event.environmental_metrics == []
    assert len(changes) == 3


def test_normalizer_preserves_supported_values():
    document = make_document()
    event = document.events[0]
    event.project_name = "厚板项目"
    event.investment_amount = 20
    event.investment_unit = "亿美元"
    event.environmental_metrics[0].value = 30
    event.environmental_metrics[0].unit = "%以上"
    event.environmental_metrics[0].evidence_text = "碳排放降低30%以上"

    normalized, changes = normalize_capacity_fields(
        document,
        [{
            "page": 1,
            "text": (
                "厚板项目的项目总投资20亿美元，"
                "碳排放降低30%以上"
            ),
        }],
    )

    assert normalized.events[0].investment_amount == 20
    assert len(normalized.events[0].environmental_metrics) == 1
    assert changes == []


def test_registration_capital_is_not_project_investment():
    document = make_document()
    event = document.events[0]
    event.project_name = None
    event.investment_amount = 20
    event.investment_unit = "亿美元"
    event.environmental_metrics = []

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "合资公司注册资本20亿美元"}],
    )

    assert normalized.events[0].investment_amount is None
    assert changes[0]["action"] == "clear_unsupported_investment"


def test_sanitizer_removes_incomplete_nested_records():
    payload = {
        "events": [{
            "capacity_changes": [{
                "capacity": None,
                "capacity_unit": None,
            }],
            "environmental_metrics": [{
                "value": 30,
                "unit": "",
            }],
        }],
    }

    cleaned, changes = sanitize_capacity_payload(payload)

    assert cleaned["events"][0]["capacity_changes"] == []
    assert cleaned["events"][0]["environmental_metrics"] == []
    assert len(changes) == 2
