from schemas.capacity import (
    CapacityChange,
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


def make_capacity_change(
    action: str,
    capacity: float,
    unit: str,
    evidence: str,
    product_name: str | None = None,
) -> CapacityChange:
    return CapacityChange(
        action=action,
        product_name=product_name,
        capacity=capacity,
        capacity_unit=unit,
        source_page=1,
        evidence_text=evidence,
        confidence=0.9,
    )


def test_merges_replacement_records_into_same_project_event():
    project_name = "钢铁基地二期项目"
    document = CapacityDocument(events=[
        CapacityEvent(
            event_type="capacity_construction",
            project_name=project_name,
            capacity_changes=[make_capacity_change(
                "new",
                405,
                "万吨/年",
                "钢铁基地二期项目生产规模405万吨/年",
            )],
            source_page=1,
            evidence_text="拟建设钢铁基地二期项目",
            confidence=0.9,
        ),
        CapacityEvent(
            event_type="capacity_replacement",
            project_name=project_name,
            capacity_changes=[make_capacity_change(
                "retired",
                334,
                "万吨",
                "淘汰334万吨炼铁产能",
            )],
            source_page=1,
            evidence_text="钢铁基地二期项目需淘汰334万吨炼铁产能",
            confidence=0.9,
        ),
    ])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "拟建设钢铁基地二期项目，生产规模405万吨/年，"
            "钢铁基地二期项目需淘汰334万吨炼铁产能"
        )}],
    )

    assert len(normalized.events) == 1
    assert len(normalized.events[0].capacity_changes) == 2
    assert normalized.events[0].capacity_changes[1].capacity_unit == (
        "万吨/年"
    )
    assert any(
        item["action"] == "merge_project_replacement_event"
        for item in changes
    )


def test_removes_projected_breakdown_when_formal_scale_exists():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        project_name="二期项目",
        capacity_changes=[
            make_capacity_change(
                "new",
                405,
                "万吨/年",
                "二期项目生产规模为405万吨/年",
            ),
            make_capacity_change(
                "new",
                246,
                "万吨/年",
                "二期项目整体建成投产后预计可年产铁水246万吨",
            ),
        ],
        source_page=1,
        evidence_text="拟建设二期项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "拟建设二期项目，生产规模为405万吨/年。"
            "二期项目整体建成投产后预计可年产铁水246万吨"
        )}],
    )

    assert len(normalized.events[0].capacity_changes) == 1
    assert normalized.events[0].capacity_changes[0].capacity == 405
    assert changes[-1]["action"] == "remove_projected_product_breakdown"


def test_removes_commissioning_equipment_specs():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="commissioning",
        capacity_changes=[make_capacity_change(
            "new",
            3700,
            "m3/座",
            "1座3700m3高炉于近日全部完工并顺利出铁",
        )],
        source_page=1,
        evidence_text="1座3700m3高炉顺利出铁",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "1座3700m3高炉于近日全部完工并顺利出铁"}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == "remove_nonreplacement_equipment_spec"


def test_removes_existing_asset_without_retirement_action():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="technical_upgrade",
        capacity_changes=[make_capacity_change(
            "retired",
            130,
            "㎡",
            "车间现有1台130㎡烧结机，设备已老化",
        )],
        source_page=1,
        evidence_text="实施烧结机节能环保升级改造项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "实施烧结机节能环保升级改造项目，"
            "车间现有1台130㎡烧结机，设备已老化"
        )}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == "remove_existing_asset_background"


def test_removes_historical_planned_capacity_from_termination():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="termination",
        capacity_changes=[make_capacity_change(
            "new",
            540,
            "万吨/年",
            "募投项目完全达产后将形成年产540万吨钢管的能力",
        )],
        source_page=1,
        evidence_text="公司拟终止该募投项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "公司拟终止该募投项目。"
            "募投项目完全达产后将形成年产540万吨钢管的能力"
        )}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == "remove_hypothetical_adverse_capacity"


def test_removes_regulatory_environmental_threshold():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="technical_upgrade",
        environmental_metrics=[EnvironmentalMetric(
            metric_type="pollutant_emission",
            metric_name="颗粒物排放浓度",
            value=10,
            unit="mg/Nm³",
            source_page=1,
            evidence_text="颗粒物排放浓度不高于10mg/Nm³",
            confidence=0.9,
        )],
        source_page=1,
        evidence_text="实施节能环保升级改造项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "根据《超低排放改造实施方案》要求，其中明确"
            "颗粒物排放浓度不高于10mg/Nm³。"
            "公司实施节能环保升级改造项目"
        )}],
    )

    assert normalized.events[0].environmental_metrics == []
    assert changes[0]["action"] == (
        "remove_regulatory_environmental_threshold"
    )


def test_project_investment_survives_pdf_line_break():
    document = make_document()
    event = document.events[0]
    event.project_name = None
    event.investment_amount = 107382
    event.investment_unit = "万元"
    event.investment_currency = "CNY"
    event.environmental_metrics = []

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目\n投资总额107,382 万元。"}],
    )

    assert normalized.events[0].investment_amount == 107382
    assert changes == []


def test_classifies_existing_asset_rebuild_as_technical_upgrade():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        project_name="低碳冶金示范项目",
        capacity_changes=[make_capacity_change(
            "new",
            2500,
            "m³",
            "2500m³低碳冶金示范项目",
        )],
        source_page=1,
        evidence_text="投资建设低碳冶金示范项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "将成熟技术移植到现有高炉，实施主工艺改造、"
            "系统改造和高炉大修，投资建设低碳冶金示范项目。"
        )}],
    )

    assert normalized.events[0].event_type == "technical_upgrade"
    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == (
        "classify_existing_asset_technical_upgrade"
    )


def test_moves_capacity_object_out_of_facility_type():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_replacement",
        capacity_changes=[CapacityChange(
            action="retired",
            facility_type="炼铁产能",
            product_name=None,
            capacity=334,
            capacity_unit="万吨",
            source_page=1,
            evidence_text="淘汰334万吨炼铁产能",
            confidence=0.9,
        )],
        source_page=1,
        evidence_text="项目需要淘汰334万吨炼铁产能",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目需要淘汰334万吨炼铁产能"}],
    )

    record = normalized.events[0].capacity_changes[0]
    assert record.facility_type is None
    assert record.product_name == "炼铁产能"
    assert record.capacity_unit == "万吨/年"
    assert len(changes) == 2


def test_removes_equipment_counts_when_aggregate_capacity_exists():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        capacity_changes=[
            make_capacity_change(
                "new",
                405,
                "万吨/年",
                "项目生产规模为405万吨/年",
            ),
            make_capacity_change(
                "new",
                1,
                "座",
                "建设1座3200立方米高炉",
            ),
        ],
        source_page=1,
        evidence_text="拟建设钢铁基地项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "拟建设钢铁基地项目，项目生产规模为405万吨/年，"
            "建设1座3200立方米高炉"
        )}],
    )

    assert len(normalized.events[0].capacity_changes) == 1
    assert normalized.events[0].capacity_changes[0].capacity == 405
    assert changes[0]["action"] == "remove_equipment_breakdown"


def test_keeps_standalone_new_equipment_count_without_aggregate():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        capacity_changes=[make_capacity_change(
            "new",
            1,
            "套",
            "拟新建1套干熄焦装置",
        )],
        source_page=1,
        evidence_text="拟新建1套干熄焦装置",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "拟新建1套干熄焦装置"}],
    )

    assert len(normalized.events[0].capacity_changes) == 1
    assert changes == []
