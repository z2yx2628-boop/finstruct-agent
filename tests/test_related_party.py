from schemas.related_party import RelatedPartyDocument, RelatedTransaction
from src.related_party_accuracy_evaluator import evaluate_document
from src.related_party_evidence_validator import validate_related_party_evidence
from src.related_party_normalizer import normalize_related_party_fields
from src.tasks import get_task

PAGE = """证券代码：600019 证券简称：宝钢股份 公告编号：临2026-013
宝山钢铁股份有限公司2026年度日常关联交易公告
本次日常关联交易尚需提交股东会审议。
二、2026年度日常关联交易预计金额和类别 单位：万元
关联交易类别 关联人 2026年预计金额 2025年实际发生金额
采购燃料和动力 宝武集团及其子公司 1,200,000 1,050,000.5
采购燃料和动力 宝武碳业科技股份有限公司 300,000 260,000
小计 1,500,000
销售产品 宝武集团及其子公司 800,000 750,000
合计 2,300,000
宝山钢铁股份有限公司董事会 2026年4月30日"""
PAGES = [{"page": 1, "text": PAGE}]


def record(**fields) -> RelatedTransaction:
    values = {
        "listed_company": "宝山钢铁股份有限公司",
        "counterparty": "宝武集团及其子公司",
        "transaction_category": "purchase_goods",
        "estimated_amount": 1200000, "estimated_unit": "万元",
        "source_page": 1,
        "evidence_text": "采购燃料和动力 宝武集团及其子公司 1,200,000 1,050,000.5",
        "confidence": 0.9,
    }
    values.update(fields)
    return RelatedTransaction(**values)


def test_related_party_task_is_registered():
    spec = get_task("related_party")
    assert spec.prompt_path.name == "related_party_extraction_v1.txt"
    assert spec.prompt_path.exists()


def test_total_and_subtotal_rows_are_dropped():
    document = RelatedPartyDocument(transactions=[
        record(prior_year_actual_amount=1050000.5, prior_year_actual_unit="万元"),
        record(counterparty="宝武碳业科技股份有限公司", estimated_amount=300000,
               evidence_text="采购燃料和动力 宝武碳业科技股份有限公司 300,000 260,000"),
        record(counterparty="宝武集团（小计）", estimated_amount=1500000, evidence_text="小计 1,500,000"),
        record(counterparty="合计", transaction_category="sell_goods", estimated_amount=2300000,
               evidence_text="合计 2,300,000"),
    ])
    normalized, changes = normalize_related_party_fields(document, PAGES)
    assert [r.counterparty for r in normalized.transactions] == ["宝武集团及其子公司", "宝武碳业科技股份有限公司"]
    actions = {c["action"] for c in changes}
    assert {"drop_category_subtotal", "drop_total_row"} <= actions


def test_unsupported_amount_is_cleared_and_header_unit_kept():
    document = RelatedPartyDocument(transactions=[
        record(prior_year_actual_amount=999999, prior_year_actual_unit="万元"),
        record(transaction_category="sell_goods", estimated_amount=80, estimated_unit="亿元",
               evidence_text="销售产品 宝武集团及其子公司 800,000 750,000"),
    ])
    normalized, _ = normalize_related_party_fields(document, PAGES)
    first, second = normalized.transactions
    assert first.estimated_amount == 1200000 and first.prior_year_actual_amount is None
    assert (second.estimated_amount, second.estimated_unit) == (800000, "万元")


def test_evaluator_pairs_by_category_and_counterparty_with_equal_amounts():
    gold = RelatedPartyDocument(estimate_year=2026, transactions=[
        record(), record(transaction_category="sell_goods", estimated_amount=800000,
                         evidence_text="销售产品 宝武集团及其子公司 800,000 750,000")])
    predicted = RelatedPartyDocument(estimate_year=2026, transactions=[
        record(transaction_category="sell_goods", estimated_amount=80, estimated_unit="亿元",
               evidence_text="销售产品 宝武集团及其子公司 800,000 750,000"),
        record()])
    report = evaluate_document(gold, predicted)
    assert report["record_metrics"]["f1"] == 1.0
    assert report["factual_attribute_metrics"]["matched"] < report["factual_attribute_metrics"]["total"]
    assert report["canonical_attribute_metrics"]["matched"] == report["canonical_attribute_metrics"]["total"]


def test_validator_accepts_supported_document():
    document = RelatedPartyDocument(
        security_code="600019", security_name="宝钢股份", announcement_number="临2026-013",
        announcement_date="2026-04-30", transactions=[record()])
    report = validate_related_party_evidence(document, PAGES)
    assert report["passed"], report["issues"]
    # The pipeline log reads these keys from every validator.
    assert {"expected_event_types", "extracted_event_types", "event_counts"} <= set(report)
    assert report["event_counts"] == {"purchase_goods": 1}


def test_unit_header_applies_to_long_table_until_sentence_end():
    from src.related_party_normalizer import amount_supported
    rows = "\n".join(f"关联方{i:02d}有限公司 销售商品 市场价格及协议价格 {1000 + i:,} {900 + i:,}" for i in range(40))
    table = "（二）2026年预计日常关联交易类别和金额\n单位：万元\n" + rows
    assert amount_supported(1039, "万元", table) == (1039, "万元")
    assert amount_supported(1039, "万元", "单位：万元\n表一结束。说明：\n" + rows) is None


def test_finance_company_deposit_rows_are_dropped_but_group_interest_kept():
    text = "单位：百万元\n贷款 利息支出 按市场利率确定 人民币 107 9\n单位：万元\n首钢集团有限公司及下属企业 利息收入 市场价格及协议价格 7,999 7,717"
    pages = [{"page": 1, "text": text}]
    document = RelatedPartyDocument(transactions=[
        record(counterparty="宝武集团财务有限责任公司", transaction_category="financial_services",
               estimated_amount=107, estimated_unit="百万元", evidence_text="利息支出 按市场利率确定 人民币 107 9"),
        record(counterparty="首钢集团有限公司及下属企业", transaction_category="financial_services",
               estimated_amount=7999, estimated_unit="万元",
               evidence_text="首钢集团有限公司及下属企业 利息收入 市场价格及协议价格 7,999 7,717"),
    ])
    normalized, changes = normalize_related_party_fields(document, pages)
    assert [r.counterparty for r in normalized.transactions] == ["首钢集团有限公司及下属企业"]
    assert changes[0]["action"] == "drop_finance_company_service"
