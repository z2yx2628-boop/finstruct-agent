from schemas.guarantee import GuaranteeDocument, GuaranteeEvent
from src.guarantee_accuracy_evaluator import evaluate_document
from src.guarantee_evidence_validator import validate_guarantee_evidence
from src.guarantee_normalizer import normalize_guarantee_fields
from src.tasks import get_task

PAGE = """证券代码：000932 证券简称：华菱钢铁 公告编号：2026-30
湖南华菱钢铁股份有限公司关于2026年度为子公司提供担保额度预计的公告
公司拟为下列子公司提供担保额度，担保方式为连带责任保证。
单位：万元
被担保方 与公司关系 最近一期资产负债率 担保额度
湖南华菱涟源钢铁有限公司 全资子公司 58.21% 300,000
华菱钢铁（香港）国际贸易有限公司 全资子公司 72.40% 50,000
合计 350,000
近日，公司与中国银行股份有限公司湘潭分行签署《保证合同》，为湖南华菱湘潭钢铁有限公司提供连带责任保证，担保金额为5亿元。
截至本公告披露日，公司及子公司担保总余额为1,234,567万元，占公司最近一期经审计净资产的25.30%；公司无逾期担保。
湖南华菱钢铁股份有限公司董事会
2026年4月29日"""
PAGES = [{"page": 1, "text": PAGE}]


def event(**fields) -> GuaranteeEvent:
    values = {
        "event_type": "guarantee_limit",
        "guarantor": "湖南华菱钢铁股份有限公司",
        "source_page": 1,
        "evidence_text": "湖南华菱涟源钢铁有限公司 全资子公司 58.21% 300,000",
        "confidence": 0.9,
    }
    values.update(fields)
    return GuaranteeEvent(**values)


def test_guarantee_task_is_registered():
    spec = get_task("guarantee")
    assert spec.prompt_path.name == "guarantee_extraction_v3.txt"
    assert spec.prompt_path.exists()


def test_table_amount_with_unit_header_is_kept():
    document = GuaranteeDocument(events=[event(
        guaranteed_party="湖南华菱涟源钢铁有限公司",
        guarantee_amount=300000, guarantee_unit="万元", guarantee_currency="CNY",
    )])
    normalized, changes = normalize_guarantee_fields(document, PAGES)
    assert normalized.events[0].guarantee_amount == 300000
    assert not [c for c in changes if c["action"] == "clear_unsupported_guarantee_amount"]


def test_converted_amount_is_restored_to_source_unit():
    document = GuaranteeDocument(events=[event(
        event_type="guarantee_provided",
        guaranteed_party="湖南华菱湘潭钢铁有限公司",
        guarantee_amount=50000, guarantee_unit="万元",
        evidence_text="为湖南华菱湘潭钢铁有限公司提供连带责任保证，担保金额为5亿元。",
    )])
    normalized, _ = normalize_guarantee_fields(document, PAGES)
    assert (normalized.events[0].guarantee_amount, normalized.events[0].guarantee_unit) == (5, "亿元")


def test_unsupported_amount_is_cleared():
    document = GuaranteeDocument(events=[event(
        guaranteed_party="湖南华菱涟源钢铁有限公司",
        guarantee_amount=999, guarantee_unit="万元",
    )])
    normalized, _ = normalize_guarantee_fields(document, PAGES)
    assert normalized.events[0].guarantee_amount is None
    assert normalized.events[0].guarantee_unit is None


def test_bank_is_moved_from_guaranteed_party_to_creditor():
    document = GuaranteeDocument(events=[event(
        event_type="guarantee_provided",
        guaranteed_party="中国银行股份有限公司湘潭分行",
    )])
    normalized, changes = normalize_guarantee_fields(document, PAGES)
    assert normalized.events[0].guaranteed_party is None
    assert normalized.events[0].creditor == "中国银行股份有限公司湘潭分行"
    assert "move_financial_institution_to_creditor" in [c["action"] for c in changes]


def test_duplicate_events_are_removed():
    same = dict(guaranteed_party="湖南华菱涟源钢铁有限公司", guarantee_amount=300000, guarantee_unit="万元")
    document = GuaranteeDocument(events=[event(**same), event(**same)])
    normalized, _ = normalize_guarantee_fields(document, PAGES)
    assert len(normalized.events) == 1


def test_validator_passes_supported_document_and_ignores_no_overdue():
    document = GuaranteeDocument(
        security_code="000932",
        announcement_date="2026-04-29",
        total_guarantee_balance=1234567, total_guarantee_unit="万元",
        events=[event(
            guaranteed_party="湖南华菱涟源钢铁有限公司",
            relationship="wholly_owned_subsidiary",
            guarantee_amount=300000, guarantee_unit="万元",
        )],
    )
    report = validate_guarantee_evidence(document, PAGES)
    assert "guarantee_overdue" not in report["expected_event_types"]
    assert report["passed"], report["issues"]


def test_evaluator_pairs_by_guaranteed_party():
    gold = GuaranteeDocument(events=[
        event(guaranteed_party="湖南华菱涟源钢铁有限公司", guarantee_amount=300000, guarantee_unit="万元"),
        event(guaranteed_party="华菱钢铁（香港）国际贸易有限公司", guarantee_amount=50000, guarantee_unit="万元"),
    ])
    prediction = GuaranteeDocument(events=[
        event(guaranteed_party="华菱钢铁(香港)国际贸易有限公司", guarantee_amount=50000, guarantee_unit="万元"),
        event(guaranteed_party="湖南华菱涟源钢铁有限公司", guarantee_amount=300000, guarantee_unit="万元"),
    ])
    report = evaluate_document(gold, prediction)
    assert report["event_metrics"]["true_positives"] == 2
    amounts = [m for m in report["field_mismatches"] if m["field"] == "guarantee_amount"]
    assert amounts == []
    assert report["canonical_attribute_metrics"]["matched"] > report["factual_attribute_metrics"]["matched"]


def test_same_party_and_amount_with_different_creditors_are_kept():
    rows = "被担保方 银行 担保敞口金额（万元）\n方大长力 兴业银行股份有限公司南昌分行 10,000.00\n方大长力 中信银行股份有限公司南昌分行 10,000.00"
    pages = [{"page": 1, "text": rows}]
    document = GuaranteeDocument(events=[
        event(event_type="guarantee_provided", guaranteed_party="方大长力",
              guarantee_amount=10000, guarantee_unit="万元", creditor=bank,
              evidence_text=f"方大长力 {bank} 10,000.00")
        for bank in ("兴业银行股份有限公司南昌分行", "中信银行股份有限公司南昌分行")
    ])
    normalized, _ = normalize_guarantee_fields(document, pages)
    assert [e.creditor for e in normalized.events] == [
        "兴业银行股份有限公司南昌分行", "中信银行股份有限公司南昌分行"]


def test_table_amount_is_not_glued_to_next_row_number():
    from src.guarantee_normalizer import amount_supported
    table = "担保敞口金额\n（万元）\n序号\n被担保方\n银行\n1\n悬架集团\n兴业银行股份有限公司南昌分行\n3,600.00\n2\n济南重弹"
    assert amount_supported(3600, "万元", table) == (3600, "万元")


CUMULATIVE_PAGES = [
    {"page": 1, "text": "近日，公司与中国银行签署《保证合同》，为湖南华菱湘潭钢铁有限公司提供连带责任保证，担保金额为5亿元。"},
    {"page": 2, "text": "七、累计对外担保数量\n公司对外担保逾期金额 4 亿元，系为关联方提供的最高额 4 亿元保证担保。\n二○二五年六月六日"},
]


def test_event_from_cumulative_section_is_dropped():
    document = GuaranteeDocument(events=[event(
        event_type="guarantee_overdue", guaranteed_party="关联方",
        guarantee_amount=4, guarantee_unit="亿元", source_page=2,
        evidence_text="公司对外担保逾期金额 4 亿元")])
    normalized, changes = normalize_guarantee_fields(document, CUMULATIVE_PAGES)
    assert normalized.events == []
    assert changes[-1]["action"] == "drop_cumulative_section_event"


def test_prior_limit_in_progress_announcement_is_dropped():
    pages = [{"page": 1, "text": "南京钢铁股份有限公司\n关于对外提供担保的进展公告\n同意公司为金祥新能源新增不超过 144,000 万元的授信担保额度。"}]
    document = GuaranteeDocument(events=[event(
        guaranteed_party="金祥新能源", guarantee_amount=144000, guarantee_unit="万元",
        evidence_text="同意公司为金祥新能源新增不超过 144,000 万元的授信担保额度")])
    normalized, changes = normalize_guarantee_fields(document, pages)
    assert normalized.events == []
    assert changes[-1]["action"] == "drop_prior_limit_in_progress_announcement"


def test_computed_debt_ratio_is_cleared_but_printed_ratio_kept():
    kept = event(guaranteed_party="湖南华菱涟源钢铁有限公司", guaranteed_party_debt_ratio=58.21)
    computed = event(guaranteed_party="华菱钢铁（香港）国际贸易有限公司", guaranteed_party_debt_ratio=66.66)
    normalized, _ = normalize_guarantee_fields(GuaranteeDocument(events=[kept, computed]), PAGES)
    assert [e.guaranteed_party_debt_ratio for e in normalized.events] == [58.21, None]


def test_chinese_numeral_signature_date_is_supported():
    from src.evidence_validator import date_supported
    assert date_supported("2025-06-06", "山西安泰集团股份有限公司\n二○二五年六月六日")
    assert date_supported("2026-05-07", "董事会\n二〇二六年五月七日")
    assert date_supported("2024-12-31", "二○二四年十二月三十一日")
    assert not date_supported("2025-06-07", "二○二五年六月六日")


def test_validator_ignores_quota_wording_in_cumulative_section():
    from src.guarantee_evidence_validator import detect_expected_event_types
    text = "天管国贸申请2.29亿元授信额度。五、累计对外担保数量及逾期担保的数量\n提供担保额度总金额为749,900万元"
    assert "guarantee_limit" not in detect_expected_event_types(text)


def test_total_next_to_per_creditor_rows_is_dropped():
    text = ("本次拟担保金额不超过 8.26 亿元。续保金额不超过（万元）\n"
            "工商银行 40,650.00\n工商银行 19,350.00\n光大银行 5,750.00\n农银投资 16,820.00")
    pages = [{"page": 1, "text": text}]
    rows = [("工商银行", 40650), ("工商银行", 19350), ("光大银行", 5750), ("农银投资", 16820)]
    document = GuaranteeDocument(events=[
        event(guaranteed_party="新泰钢铁", guarantee_amount=8.26, guarantee_unit="亿元",
              evidence_text="本次拟担保金额不超过 8.26 亿元")
    ] + [
        event(guaranteed_party="新泰钢铁", guarantee_amount=amount, guarantee_unit="万元",
              creditor=bank, evidence_text=f"{bank} {amount:,.2f}")
        for bank, amount in rows
    ])
    normalized, changes = normalize_guarantee_fields(document, pages)
    assert len(normalized.events) == 4
    assert all(e.creditor for e in normalized.events)
    assert changes[0]["action"] == "drop_total_of_row_events"


def test_quota_is_not_taken_as_external_balance():
    text = ("公司及控股子公司对合并报表外公司提供担保额度总金额为 12,000 万元。"
            "公司及控股子公司对外担保总余额为 379,173.41 万元。")
    document = GuaranteeDocument(
        external_guarantee_balance=12000, external_guarantee_unit="万元",
        total_guarantee_balance=379173.41, total_guarantee_unit="万元")
    normalized, _ = normalize_guarantee_fields(document, [{"page": 1, "text": text}])
    assert normalized.external_guarantee_balance is None
    assert normalized.total_guarantee_balance == 379173.41


def test_zero_external_balance_needs_explicit_statement():
    doc = GuaranteeDocument(external_guarantee_balance=0, external_guarantee_unit="万元")
    unsupported, _ = normalize_guarantee_fields(doc, [{"page": 1, "text": "公司未对控股股东提供担保。"}])
    assert unsupported.external_guarantee_balance is None
    supported, _ = normalize_guarantee_fields(doc, [{"page": 1, "text": "公司无对外担保。"}])
    assert supported.external_guarantee_balance == 0
