from schemas.pledge import PledgeDocument, PledgeEvent
from src.event_normalizer import inherit_shared_table_values


PLEDGEE = "江苏江阴农村商业银行股份有限公司苏州分行"


def release_event(
    shares: float,
    evidence_text: str,
    pledgee: str | None,
    shareholder_name: str = "通鼎集团",
) -> PledgeEvent:
    return PledgeEvent(
        event_type="release",
        shareholder_name=shareholder_name,
        shares=shares,
        shares_unit="股",
        shareholder_holding_ratio=1,
        total_share_capital_ratio=1,
        pledge_start_date="2025-01-01",
        release_date="2026-01-07",
        pledgee=pledgee,
        source_page=1,
        evidence_text=evidence_text,
        confidence=1,
    )


def test_inherits_evidenced_pledgee_from_adjacent_merged_cell():
    document = PledgeDocument(events=[
        release_event(20_400_000, PLEDGEE, PLEDGEE),
        release_event(11_200_000, f"11,200,000\n{PLEDGEE}", None),
    ])

    normalized, changes = inherit_shared_table_values(document)

    assert document.events[1].pledgee is None
    assert normalized.events[1].pledgee == PLEDGEE
    assert changes == [{
        "event_index": 1,
        "event_type": "release",
        "field": "pledgee",
        "value": PLEDGEE,
        "source_event_index": 0,
        "reason": "adjacent_merged_cell_with_exact_evidence",
    }]


def test_does_not_inherit_without_exact_evidence():
    document = PledgeDocument(events=[
        release_event(20_400_000, PLEDGEE, PLEDGEE),
        release_event(11_200_000, "11,200,000", None),
    ])

    normalized, changes = inherit_shared_table_values(document)

    assert normalized.events[1].pledgee is None
    assert changes == []


def test_does_not_inherit_across_different_shareholders():
    document = PledgeDocument(events=[
        release_event(20_400_000, PLEDGEE, PLEDGEE),
        release_event(
            11_200_000,
            f"11,200,000\n{PLEDGEE}",
            None,
            shareholder_name="其他股东",
        ),
    ])

    normalized, changes = inherit_shared_table_values(document)

    assert normalized.events[1].pledgee is None
    assert changes == []


def test_does_not_inherit_when_adjacent_values_conflict():
    other_pledgee = "另一家银行"
    document = PledgeDocument(events=[
        release_event(20_400_000, PLEDGEE, PLEDGEE),
        release_event(
            11_200_000,
            f"11,200,000\n{PLEDGEE}\n{other_pledgee}",
            None,
        ),
        release_event(5_000_000, other_pledgee, other_pledgee),
    ])

    normalized, changes = inherit_shared_table_values(document)

    assert normalized.events[1].pledgee is None
    assert changes == []
