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
    assert spec.prompt_path.name == "guarantee_extraction_v1.txt"
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
