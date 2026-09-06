import pytest
from pydantic import ValidationError

from schemas.pledge import PledgeDocument, PledgeEvent


def test_valid_pledge_document():
    event = PledgeEvent(
        event_type="pledge",
        shareholder_name="昝圣达",
        shares=1000,
        shares_unit="万股",
        shareholder_holding_ratio=4.17,
        total_share_capital_ratio=0.77,
        is_restricted_share=False,
        is_supplementary_pledge=False,
        pledge_start_date="2026-06-11",
        pledge_end_date="2029-06-01",
        pledgee="招商银行股份有限公司南通分行",
        purpose="为其下属企业融资担保",
        source_page=1,
        evidence_text="本次质押股数（万股）1,000",
        confidence=0.99,
    )

    document = PledgeDocument(
        security_code="600770",
        security_name="综艺股份",
        announcement_number="临2026-026",
        company_name="江苏综艺股份有限公司",
        events=[event],
    )

    assert document.security_code == "600770"
    assert len(document.events) == 1
    assert document.events[0].event_type == "pledge"


def test_invalid_ratio_is_rejected():
    with pytest.raises(ValidationError):
        PledgeEvent(
            event_type="pledge",
            shareholder_name="测试股东",
            shares=1000,
            shares_unit="股",
            shareholder_holding_ratio=120,
            source_page=1,
            evidence_text="测试证据",
            confidence=0.5,
        )


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        PledgeEvent(
            event_type="freeze",
            shareholder_name="测试股东",
            shares=1000,
            shares_unit="股",
            source_page=1,
            evidence_text="测试证据",
            confidence=0.5,
        )


def test_legacy_records_are_migrated_to_pledge_events():
    document = PledgeDocument.model_validate({
        "security_code": "600770",
        "records": [{
            "shareholder_name": "昝圣达",
            "pledged_shares": 1000,
            "pledged_shares_unit": "万股",
            "pledge_purpose": "融资担保",
            "source_page": 1,
            "evidence_text": "昝圣达 1,000 万股",
            "confidence": 0.9,
        }],
    })

    assert len(document.events) == 1
    assert document.events[0].event_type == "pledge"
    assert document.events[0].shares == 1000
    assert document.events[0].purpose == "融资担保"
