from schemas.pledge import PledgeDocument, PledgeEvent
from src.accuracy_evaluator import evaluate_document


def event(
    event_type: str,
    shares: float,
    pledgee: str = "测试银行",
) -> PledgeEvent:
    common = {
        "event_type": event_type,
        "shareholder_name": "测试股东",
        "shares": shares,
        "shares_unit": "股",
        "shareholder_holding_ratio": 1,
        "total_share_capital_ratio": 0.5,
        "pledgee": pledgee,
        "source_page": 1,
        "evidence_text": "测试证据",
        "confidence": 1,
    }
    if event_type == "pledge":
        common.update({
            "pledge_start_date": "2026-01-01",
            "pledge_end_condition": "至解除质押为止",
            "purpose": "融资",
        })
    else:
        common.update({
            "pledge_start_date": "2025-01-01",
            "release_date": "2026-01-01",
        })
    return PledgeEvent(**common)


def document(events: list[PledgeEvent]) -> PledgeDocument:
    return PledgeDocument(
        security_code="000001",
        security_name="测试股份",
        announcement_number="2026-001",
        company_name="测试股份有限公司",
        events=events,
    )


def test_event_matching_is_independent_of_output_order():
    gold = document([event("pledge", 100), event("release", 50)])
    prediction = document([event("release", 50), event("pledge", 100)])

    report = evaluate_document(gold, prediction)

    assert report["passed"] is True
    assert report["event_metrics"]["f1"] == 1


def test_missing_event_reduces_recall():
    gold = document([event("pledge", 100), event("release", 50)])
    prediction = document([event("pledge", 100)])

    report = evaluate_document(gold, prediction)

    assert report["event_metrics"]["precision"] == 1
    assert report["event_metrics"]["recall"] == 0.5
    assert len(report["missing_events"]) == 1


def test_wrong_attribute_reduces_present_attribute_accuracy():
    gold = document([event("pledge", 100)])
    prediction = document([event("pledge", 100, pledgee="错误银行")])

    report = evaluate_document(gold, prediction)

    assert report["event_metrics"]["f1"] == 1
    assert report["event_attribute_metrics"]["present_accuracy"] < 1
    assert report["field_mismatches"][0]["field"] == "pledgee"
