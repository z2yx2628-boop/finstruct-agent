import pytest
from pydantic import ValidationError

from schemas.capacity import (
    CapacityChange,
    CapacityDocument,
    CapacityEvent,
    EnvironmentalMetric,
)


def test_valid_capacity_replacement_document():
    document = CapacityDocument(
        security_code="600000",
        security_name="测试钢企",
        announcement_date="2026-09-15",
        events=[
            CapacityEvent(
                event_type="capacity_replacement",
                project_name="炼钢产能置换项目",
                project_status="approved",
                investment_amount=12.8,
                investment_unit="亿元",
                investment_currency="CNY",
                capacity_changes=[
                    CapacityChange(
                        action="new",
                        facility_type="转炉",
                        capacity=100,
                        capacity_unit="万吨/年",
                        source_page=2,
                        evidence_text="拟建设100万吨炼钢产能",
                        confidence=0.98,
                    ),
                    CapacityChange(
                        action="retired",
                        facility_type="转炉",
                        capacity=120,
                        capacity_unit="万吨/年",
                        source_page=2,
                        evidence_text="退出炼钢产能120万吨",
                        confidence=0.98,
                    ),
                ],
                source_page=1,
                evidence_text="公司拟实施炼钢产能置换项目",
                confidence=0.96,
            )
        ],
    )

    assert len(document.events) == 1
    assert len(document.events[0].capacity_changes) == 2


def test_investment_amount_requires_unit():
    with pytest.raises(ValidationError):
        CapacityEvent(
            event_type="technical_upgrade",
            investment_amount=10,
            source_page=1,
            evidence_text="项目投资10亿元",
            confidence=0.9,
        )


def test_negative_capacity_is_rejected():
    with pytest.raises(ValidationError):
        CapacityChange(
            action="new",
            capacity=-100,
            capacity_unit="万吨/年",
            source_page=1,
            evidence_text="测试",
            confidence=0.9,
        )


def test_negative_environmental_metric_is_rejected():
    with pytest.raises(ValidationError):
        EnvironmentalMetric(
            metric_type="carbon_reduction",
            metric_name="年度碳减排量",
            value=-10,
            unit="万吨/年",
            source_page=1,
            evidence_text="测试",
            confidence=0.9,
        )


def test_invalid_announcement_date_is_rejected():
    with pytest.raises(ValidationError):
        CapacityDocument(
            announcement_date="2026-9-15",
        )