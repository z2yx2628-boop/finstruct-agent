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


def test_removes_chinese_unit_equipment_specs_from_construction():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        capacity_changes=[make_capacity_change(
            "new",
            3200,
            "立方米/座",
            "建设1座3200立方米高炉",
            product_name="炼铁产能",
        )],
        source_page=1,
        evidence_text="建设钢铁基地项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "建设1座3200立方米高炉"}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == "remove_nonreplacement_equipment_spec"


def test_recovers_explicit_formal_capacity_and_removes_line_width():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        capacity_changes=[make_capacity_change(
            "new",
            1580,
            "毫米/条",
            "1条1580毫米热轧带钢生产线",
            product_name="热轧带钢",
        )],
        source_page=1,
        evidence_text="建设钢铁基地项目",
        confidence=0.9,
    )])
    pages = [{
        "page": 1,
        "text": (
            "生产规模为铁钢轧综合配套405万吨/年，"
            "建设1条1580毫米热轧带钢生产线"
        ),
    }]

    normalized, changes = normalize_capacity_fields(document, pages)

    assert len(normalized.events[0].capacity_changes) == 1
    record = normalized.events[0].capacity_changes[0]
    assert record.capacity == 405
    assert record.capacity_unit == "万吨/年"
    assert record.product_name == "铁钢轧综合配套产能"
    assert {
        item["action"] for item in changes
    } == {
        "recover_formal_aggregate_capacity",
        "remove_nonreplacement_equipment_spec",
    }


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


def test_replacement_converter_spec_is_not_multiplied():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_replacement",
        capacity_changes=[make_capacity_change(
            "retired",
            105,
            "吨/座×3",
            "凌钢3×35t转炉系统已经停产",
            product_name="炼钢产能",
        )],
        source_page=1,
        evidence_text="凌钢3×35t转炉系统已经停产",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "凌钢3×35t转炉系统已经停产"}],
    )

    record = normalized.events[0].capacity_changes[0]
    assert record.facility_type == "3×35t转炉系统"
    assert record.product_name is None
    assert record.capacity == 35
    assert record.capacity_unit == "t/座"
    assert changes[0]["action"] == "normalize_converter_spec"


def test_environmental_metric_name_is_canonicalized():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="technical_upgrade",
        environmental_metrics=[EnvironmentalMetric(
            metric_type="carbon_reduction",
            metric_name="碳排放",
            value=30,
            unit="%",
            source_page=1,
            evidence_text="项目碳排放降低30%",
            confidence=0.9,
        )],
        source_page=1,
        evidence_text="实施低碳改造",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目碳排放降低30%"}],
    )

    assert normalized.events[0].environmental_metrics[0].metric_name == (
        "碳减排率"
    )
    assert changes[0]["action"] == "normalize_environmental_metric_name"


def test_preproduction_acceptance_is_not_commissioning_date():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_replacement",
        commissioning_date="2023-02-21",
        source_page=1,
        evidence_text="转炉置换项目",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "2023年2月21日完成投产前验收"}],
    )

    assert normalized.events[0].commissioning_date is None
    assert changes[0]["action"] == "clear_unsupported_commissioning_date"


def test_actual_full_line_commissioning_date_is_preserved():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="commissioning",
        commissioning_date="2024-06-06",
        source_page=1,
        evidence_text="项目全线投产",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目于2024年6月6日全线投产"}],
    )

    assert normalized.events[0].commissioning_date == "2024-06-06"
    assert changes == []
def test_month_only_delay_date_is_cleared():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="delay",
        delay_until_date="2024-06-30",
        source_page=1,
        evidence_text="项目延期至2024年6月",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目延期至2024年6月"}],
    )

    assert normalized.events[0].delay_until_date is None
    assert changes[0]["action"] == "clear_unsupported_exact_date"


def test_explicit_month_end_date_is_preserved():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="delay",
        delay_until_date="2021-09-30",
        source_page=1,
        evidence_text="项目延期至2021年9月末",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目延期至2021年9月末"}],
    )

    assert normalized.events[0].delay_until_date == "2021-09-30"
    assert changes == []


def test_removes_planned_capacity_from_delay_event():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="delay",
        capacity_changes=[make_capacity_change(
            "new",
            1000,
            "万米/年",
            "项目计划新增年产1,000万米高速钢双金属带锯条生产能力",
        )],
        source_page=1,
        evidence_text="项目建设进度延期",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": (
            "项目建设进度延期。"
            "项目计划新增年产1,000万米高速钢双金属带锯条生产能力"
        )}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[0]["action"] == "remove_hypothetical_adverse_capacity"
def test_spaced_exact_date_is_preserved():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="delay",
        delay_until_date="2026-09-20",
        source_page=1,
        evidence_text="项目延期至2026 年9 月20 日",
        confidence=0.9,
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "项目延期至2026 年9 月20 日"}],
    )

    assert normalized.events[0].delay_until_date == "2026-09-20"
    assert changes == []