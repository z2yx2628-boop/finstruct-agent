from schemas.pledge import PledgeDocument, PledgeEvent
from src.evidence_validator import number_supported, validate_evidence


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
本次股份质押基本情况
{EVIDENCE}""",
}]


def make_document(ratio: float) -> PledgeDocument:
    event = PledgeEvent(
        event_type="pledge",
        shareholder_name="昝圣达",
        shares=1000,
        shares_unit="万股",
        shareholder_holding_ratio=ratio,
        total_share_capital_ratio=0.77,
        is_restricted_share=False,
        is_supplementary_pledge=False,
        pledge_start_date="2026-06-11",
        pledge_end_date="2029-06-01",
        pledgee="招商银行股份有限公司南通分行",
        purpose="为其下属企业融资担保",
        source_page=1,
        evidence_text=EVIDENCE,
        confidence=1.0,
    )
    return PledgeDocument(
        security_code="600770",
        security_name="综艺股份",
        announcement_number="临2026-026",
        company_name="江苏综艺股份有限公司",
        events=[event],
    )


def test_supported_evidence_passes():
    report = validate_evidence(make_document(4.17), PAGES)

    assert report["passed"] is True
    assert report["issues"] == []
    assert report["event_counts"]["pledge"] == 1


def test_unsupported_ratio_is_detected():
    report = validate_evidence(make_document(35.98), PAGES)

    assert report["passed"] is False
    assert report["issues"][0]["field"] == "shareholder_holding_ratio"


def test_missing_pledge_end_is_detected():
    document = make_document(4.17)
    document.events[0].pledge_end_date = None

    report = validate_evidence(document, PAGES)

    assert report["passed"] is False
    assert any(
        item["field"] == "pledge_end_date_or_condition"
        for item in report["issues"]
    )


def test_missing_event_type_is_detected():
    pages = [{
        "page": 1,
        "text": PAGES[0]["text"] + "\n本次股份解质押基本情况",
    }]

    report = validate_evidence(make_document(4.17), pages)

    assert report["passed"] is False
    assert report["missing_event_types"] == ["release"]
    assert any(
        item["check"] == "event_type_coverage"
        and item["value"] == "release"
        for item in report["issues"]
    )


def test_release_without_disclosed_pledge_start_date_is_allowed():
    evidence = """永鼎集团有限公司
37,000,000
9.67%
2.53%
2024年12月20日
江苏银行股份有限公司苏州分行"""
    document = PledgeDocument(
        security_code="600105",
        security_name="永鼎股份",
        announcement_number="临2024-109",
        company_name="江苏永鼎股份有限公司",
        events=[
            PledgeEvent(
                event_type="release",
                shareholder_name="永鼎集团有限公司",
                shares=37_000_000,
                shares_unit="股",
                shareholder_holding_ratio=9.67,
                total_share_capital_ratio=2.53,
                pledge_start_date=None,
                release_date="2024-12-20",
                pledgee="江苏银行股份有限公司苏州分行",
                source_page=1,
                evidence_text=evidence,
                confidence=1.0,
            )
        ],
    )
    pages = [{
        "page": 1,
        "text": f"""证券代码：600105
证券简称：永鼎股份
公告编号：临2024-109
江苏永鼎股份有限公司
本次股份解除质押基本情况
{evidence}""",
    }]

    report = validate_evidence(document, pages)

    assert report["passed"] is True
    assert report["issues"] == []


def test_large_share_count_is_supported():
    assert number_supported(32_000_000.0, "32,000,000")


def test_adjacent_table_numbers_are_supported():
    evidence = "14,000,000\n3.19%\n1.04%"

    assert number_supported(14_000_000.0, evidence)
    assert number_supported(3.19, evidence)
    assert number_supported(1.04, evidence)


def test_wrapped_thousands_separators_are_supported():
    assert number_supported(13_000_000.0, "13,00\n0,000")
    assert number_supported(1_700_000.0, "1,700,\n000")


def test_equivalent_decimal_formats_are_supported():
    assert number_supported(25.0, "25.00\n%")


def test_zero_padded_iso_date_is_supported():
    from src.evidence_validator import date_supported

    assert date_supported("2026-05-15", "[发布日期] 2026-05-15")
    assert date_supported("2026-05-15", "2026年5月15日")
    assert not date_supported("2026-05-15", "2024-05-15")
