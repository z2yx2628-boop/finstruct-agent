import pytest
from pydantic import ValidationError

from schemas.pledge import PledgeDocument, PledgeRecord


def test_valid_pledge_document():
    record = PledgeRecord(
        shareholder_name="昝圣达",
        pledged_shares=1000,
        pledged_shares_unit="万股",
        pledge_start_date="2026-06-11",
        pledge_end_date="2029-06-01",
        pledgee="招商银行股份有限公司南通分行",
        shareholder_holding_ratio=4.17,
        total_share_capital_ratio=0.77,
        pledge_purpose="为其下属企业融资担保",
        source_page=1,
        evidence_text="本次质押股数（万股）1,000",
        confidence=0.99,
    )

    document = PledgeDocument(
        security_code="600770",
        security_name="综艺股份",
        announcement_number="临2026-026",
        company_name="江苏综艺股份有限公司",
        records=[record],
    )

    assert document.security_code == "600770"
    assert len(document.records) == 1


def test_invalid_ratio_is_rejected():
    with pytest.raises(ValidationError):
        PledgeRecord(
            shareholder_name="测试股东",
            shareholder_holding_ratio=120,
        )