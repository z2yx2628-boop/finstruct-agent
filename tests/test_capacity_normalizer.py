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



def test_sanitizer_removes_investment_amount_emitted_as_capacity():
    payload = {
        "events": [{
            "capacity_changes": [
                {
                    "action": "new",
                    "facility_type": "7#高炉",
                    "capacity": 76781.0,
                    "capacity_unit": "万元",
                },
                {
                    "action": "new",
                    "capacity": 120,
                    "capacity_unit": "万吨/年",
                },
            ],
            "environmental_metrics": [],
        }],
    }

    cleaned, changes = sanitize_capacity_payload(payload)

    records = cleaned["events"][0]["capacity_changes"]
    assert [record["capacity_unit"] for record in records] == ["万吨/年"]
    assert [change["action"] for change in changes] == [
        "remove_monetary_capacity_change"
    ]

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

def make_event(**fields) -> CapacityEvent:
    values = {
        "event_type": "technical_upgrade",
        "source_page": 1,
        "evidence_text": "项目",
        "confidence": 0.9,
    }
    values.update(fields)
    return CapacityEvent(**values)


def test_v6_investment_accepts_non_standard_wording():
    texts = {
        (19.45, "亿元"): "2024年计划安排投资 19.45 亿元。",
        (500000.0, "万元"): "项目核定投资额：500,000.00 万元",
        (25.0, "亿元"): "5、投资规模：项目概算投资 25.00 亿元。",
    }
    for (amount, unit), text in texts.items():
        document = CapacityDocument(events=[make_event(
            investment_amount=amount,
            investment_unit=unit,
            investment_currency="CNY",
        )])
        normalized, _ = normalize_capacity_fields(
            document, [{"page": 1, "text": text}],
        )
        assert normalized.events[0].investment_amount == amount, text


def test_v6_investment_accepts_table_with_unit_header():
    document = CapacityDocument(events=[make_event(
        investment_amount=55634,
        investment_unit="万元",
    )])
    text = (
        "单位：万元\n项目名称 项目内容 投资金额 建设周期\n"
        "新建生产线 年增加产能 33,080 2023-2024\n合计 / / 55,634 /"
    )

    normalized, _ = normalize_capacity_fields(
        document, [{"page": 1, "text": text}],
    )

    assert normalized.events[0].investment_amount == 55634


def test_v6_investment_restores_source_unit():
    document = CapacityDocument(events=[make_event(
        investment_amount=194500,
        investment_unit="万元",
    )])

    normalized, changes = normalize_capacity_fields(
        document, [{"page": 1, "text": "2024年计划安排投资19.45亿元。"}],
    )

    assert normalized.events[0].investment_amount == 19.45
    assert normalized.events[0].investment_unit == "亿元"
    assert "restore_source_investment_unit" in [c["action"] for c in changes]


def test_v6_investment_rejects_financing_and_loan_amounts():
    for text in (
        "为项目公司提供融资担保，担保金额不超过 12 亿元。",
        "股东借款最高可能至 12 亿元。",
    ):
        document = CapacityDocument(events=[make_event(
            investment_amount=12,
            investment_unit="亿元",
        )])
        normalized, _ = normalize_capacity_fields(
            document, [{"page": 1, "text": text}],
        )
        assert normalized.events[0].investment_amount is None, text


def test_v6_amount_is_not_a_funding_source():
    document = CapacityDocument(events=[make_event(
        investment_amount=38115,
        investment_unit="万元",
        funding_source="资金计划28350.5万元",
    )])

    normalized, changes = normalize_capacity_fields(
        document,
        [{"page": 1, "text": "投资计划38115万元，资金计划28350.5万元"}],
    )

    assert normalized.events[0].funding_source is None
    assert "clear_non_source_funding_text" in [c["action"] for c in changes]


def test_v6_spaced_plain_commissioning_date_is_preserved():
    document = CapacityDocument(events=[make_event(
        event_type="commissioning",
        commissioning_date="2020-04-29",
    )])

    normalized, _ = normalize_capacity_fields(document, [{"page": 1, "text": (
        "公司连续式酸洗线于 2020 年 4 月 29 日投产，成功下线第一卷钢。"
    )}])

    assert normalized.events[0].commissioning_date == "2020-04-29"


def test_v6_post_commissioning_wording_is_not_a_date():
    document = CapacityDocument(events=[make_event(
        event_type="commissioning",
        commissioning_date="2020-04-29",
    )])

    normalized, _ = normalize_capacity_fields(document, [{"page": 1, "text": (
        "项目于2020年4月29日投产后将新增产能。"
    )}])

    assert normalized.events[0].commissioning_date is None


def test_v6_collapses_pdf_spaces_in_names():
    document = CapacityDocument(
        announcement_number="临 2023-017",
        events=[make_event(project_name="抚顺特钢2023 年-2024 年技术改造项目")],
    )

    normalized, _ = normalize_capacity_fields(document, [{"page": 1, "text": (
        "项目名称：《抚顺特钢 2023 年-2024 年技术改造项目》"
    )}])

    assert normalized.announcement_number == "临2023-017"
    assert normalized.events[0].project_name == "抚顺特钢2023年-2024年技术改造项目"


def test_v6_framework_plan_keeps_one_event_without_capacity():
    document = CapacityDocument(events=[
        make_event(
            project_name="板材炼钢厂1号铸机改造",
            capacity_changes=[make_capacity_change(
                "new", 35, "万吨/年", "1#铸机产能由195万吨/年提升至230万吨/年",
            )],
        ),
        make_event(
            project_name="2024 年度投资框架计划",
            capacity_changes=[make_capacity_change(
                "new", 31.5, "万吨/年", "汽车板高强钢产能31.5万吨/年",
            )],
        ),
    ])

    normalized, changes = normalize_capacity_fields(
        document, [{"page": 1, "text": "2024年度投资框架计划"}],
    )

    assert len(normalized.events) == 1
    assert normalized.events[0].project_name == "2024年度投资框架计划"
    assert normalized.events[0].capacity_changes == []
    actions = [c["action"] for c in changes]
    assert "merge_framework_plan_item" in actions
    assert "remove_framework_item_capacity" in actions


def test_v6_removes_planned_capacity_of_delayed_named_project():
    document = CapacityDocument(events=[make_event(
        event_type="delay",
        project_name="年产6000 吨油气输送用不锈钢焊管项目",
        capacity_changes=[make_capacity_change(
            "new", 6000, "吨/年", "年产6,000 吨油气输送用不锈钢焊管项目",
        )],
    )])

    normalized, changes = normalize_capacity_fields(
        document, [{"page": 1, "text": "年产6000吨油气输送用不锈钢焊管项目延期"}],
    )

    assert normalized.events[0].capacity_changes == []
    assert changes[-1]["action"] == "remove_planned_capacity_of_adverse_project"


def test_v6_keeps_capacity_of_construction_named_project():
    document = CapacityDocument(events=[make_event(
        event_type="capacity_construction",
        project_name="年产6000吨焊管项目",
        capacity_changes=[make_capacity_change(
            "new", 6000, "吨/年", "年产6000吨焊管项目",
        )],
    )])

    normalized, _ = normalize_capacity_fields(
        document, [{"page": 1, "text": "投资建设年产6000吨焊管项目"}],
    )

    assert len(normalized.events[0].capacity_changes) == 1


def test_v6_removes_breakdown_components_beside_total():
    evidence = "热轧酸洗板产能将新增约95万吨/年，其中新增酸洗汽车用钢60万吨/年，其他产品共计约35万吨/年"
    document = CapacityDocument(events=[make_event(
        event_type="commissioning",
        capacity_changes=[
            make_capacity_change("new", 95, "万吨/年", evidence, "热轧酸洗板"),
            make_capacity_change("new", 60, "万吨/年", evidence, "酸洗汽车用钢"),
            make_capacity_change("new", 35, "万吨/年", evidence, "其他产品"),
        ],
    )])

    normalized, _ = normalize_capacity_fields(
        document, [{"page": 1, "text": evidence}],
    )

    assert [r.capacity for r in normalized.events[0].capacity_changes] == [95]


def test_v7_temporary_loss_moves_to_impact_fields():
    evidence = "7#高炉计划自2026年12月下旬开始停产65天，预计减少铁水产量60万吨，主要影响2027年一季度。"
    document = CapacityDocument(events=[make_event(
        event_type="technical_upgrade",
        capacity_changes=[CapacityChange(
            action="retired",
            facility_type="7#高炉",
            product_name="铁水",
            capacity=60,
            capacity_unit="万吨",
            source_page=1,
            evidence_text=evidence,
            confidence=0.9,
        )],
    )])

    normalized, changes = normalize_capacity_fields(
        document, [{"page": 1, "text": evidence}],
    )
    event = normalized.events[0]

    assert event.capacity_changes == []
    assert event.output_loss_amount == 60
    assert event.output_loss_unit == "万吨"
    assert event.output_loss_product == "铁水"
    assert event.shutdown_facility == "7#高炉"
    assert event.shutdown_days == 65
    assert "move_temporary_loss_to_impact" in [c["action"] for c in changes]


def test_v7_permanent_retirement_is_kept():
    evidence = "淘汰2座450m³高炉，退出炼铁产能120万吨/年"
    document = CapacityDocument(events=[make_event(
        event_type="capacity_replacement",
        capacity_changes=[make_capacity_change("retired", 120, "万吨/年", evidence, "炼铁产能")],
    )])

    normalized, _ = normalize_capacity_fields(
        document, [{"page": 1, "text": evidence}],
    )

    assert [r.capacity for r in normalized.events[0].capacity_changes] == [120]
    assert normalized.events[0].output_loss_amount is None


def test_v7_maintenance_event_type_is_valid():
    event = make_event(
        event_type="maintenance",
        project_status="temporarily_shut_down",
        shutdown_facility="530m³高炉",
        shutdown_start_date="2026-06-30",
        expected_restart_date="2026-07-20",
        output_loss_amount=0.21,
        output_loss_unit="万吨/日",
        output_loss_product="铁水",
    )

    assert event.event_type == "maintenance"


def test_v7_project_country_is_inferred_from_location():
    from src.capacity_normalizer import infer_project_country

    assert infer_project_country("印度尼西亚共和国中苏拉威西省MOROWALI县青山园区") == "印度尼西亚"
    assert infer_project_country("河北乐亭经济开发区河钢乐亭钢铁有限公司厂区内") == "中国"
    assert infer_project_country("湖州市开发区杨家埠霅水桥路618号") == "中国"
    assert infer_project_country(None) is None
    assert infer_project_country("现有厂区") is None


def test_v7_reason_text_must_be_in_source():
    document = CapacityDocument(events=[make_event(
        event_type="termination",
        project_location="印尼青山园区",
        decision_reasons=["trade_policy", "market_demand"],
        decision_reason_text="因产业政策、贸易政策和市场需求情况等有关因素影响",
    )])

    normalized, _ = normalize_capacity_fields(document, [{"page": 1, "text": (
        "因产业政策、贸易政策和市场需求情况等有关因素影响，双方共同决定终止对该项目的投资。"
    )}])
    event = normalized.events[0]

    assert event.project_country == "印度尼西亚"
    assert event.decision_reasons == ["trade_policy", "market_demand"]
    assert event.decision_reason_text is not None

    fabricated = CapacityDocument(events=[make_event(
        decision_reason_text="为应对欧盟碳关税",
    )])
    normalized, changes = normalize_capacity_fields(
        fabricated, [{"page": 1, "text": "为降低成本实施改造。"}],
    )
    assert normalized.events[0].decision_reason_text is None
    assert "clear_unsupported_reason_text" in [c["action"] for c in changes]


def test_investment_inside_table_is_not_glued_to_next_cell():
    from src.capacity_normalizer import find_supported_investment
    table = "序号 项目名称 投资总额（万元） 已投入金额（万元）\n1 智能化改造项目 8,000.00 6,000.00\n"
    assert find_supported_investment(8000.0, "万元", table) == (8000.0, "万元")
    assert find_supported_investment(5000.0, "万元", "公司注册资本5,000万元") is None

    table_rmb = "单位：人民币元序号项目名称项目投资总额 1 新建无缝钢管项目 262,421,470.16 262,421,470.16 42,793,710.95"
    assert find_supported_investment(262421470.16, "元", table_rmb) == (262421470.16, "元")
