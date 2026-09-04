from schemas.pledge import PledgeDocument, PledgeRecord
from src.evidence_validator import validate_evidence


EVIDENCE = """昝圣达
否
1,000
否
否
2026-6-11
2029-6-1
招商银行股份有限公司南通分行
4.17%
0.77%
为其下属企业融资担保"""

PAGES = [{
    "page": 1,
    "text": f"""证券代码：600770
证券简称：综艺股份
公告编号：临2026-026
江苏综艺股份有限公司
本次质押股数（万股）
{EVIDENCE}""",
}]


def make_document(ratio: float) -> PledgeDocument:
    record = PledgeRecord(
        shareholder_name="昝圣达",
        pledged_shares=1000,
        pledged_shares_unit="万股",
        pledge_start_date="2026-06-11",
        pledge_end_date="2029-06-01",
        pledgee="招商银行股份有限公司南通分行",
        shareholder_holding_ratio=ratio,
        total_share_capital_ratio=0.77,
        pledge_purpose="为其下属企业融资担保",
        source_page=1,
        evidence_text=EVIDENCE,
        confidence=1.0,
    )
    return PledgeDocument(
        security_code="600770",
        security_name="综艺股份",
        announcement_number="临2026-026",
        company_name="江苏综艺股份有限公司",
        records=[record],
    )


def test_supported_evidence_passes():
    report = validate_evidence(make_document(4.17), PAGES)

    assert report["passed"] is True
    assert report["checks_count"] == 14
    assert report["issues"] == []


def test_unsupported_ratio_is_detected():
    report = validate_evidence(make_document(35.98), PAGES)

    assert report["passed"] is False
    assert report["passed_checks"] == 13
    assert report["issues"][0]["check"] == "shareholder_holding_ratio"