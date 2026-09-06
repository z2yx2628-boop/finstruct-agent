import json
from collections import Counter
from pathlib import Path

import pytest

from schemas.pledge import PledgeDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = PROJECT_ROOT / "data" / "gold" / "sample_pledge_gold.json"
GOLD_CORPUS_DIR = PROJECT_ROOT / "data" / "gold" / "pledge_test"
EXPECTED_EVENT_TYPES = {
    "pledge_01_huayou.json": ["pledge"],
    "pledge_02_yongding.json": ["release", "pledge"],
    "pledge_03_yasha.json": ["release", "pledge"],
    "pledge_04_letong.json": ["extension", "extension"],
    "pledge_05_tongding.json": ["release", "release", "pledge"],
}


def test_gold_data_matches_schema():
    data = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    document = PledgeDocument.model_validate(data)

    assert document.security_code == "600770"
    assert len(document.events) == 1
    assert document.events[0].event_type == "pledge"
    assert document.events[0].shares == 1000


@pytest.mark.parametrize(
    ("filename", "event_types"),
    EXPECTED_EVENT_TYPES.items(),
)
def test_pledge_test_gold_matches_schema(filename, event_types):
    path = GOLD_CORPUS_DIR / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    document = PledgeDocument.model_validate(data)

    assert [event.event_type for event in document.events] == event_types
    assert all(event.confidence == 1.0 for event in document.events)


def test_pledge_test_gold_has_expected_event_distribution():
    event_counts = Counter()

    for filename in EXPECTED_EVENT_TYPES:
        path = GOLD_CORPUS_DIR / filename
        document = PledgeDocument.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        event_counts.update(event.event_type for event in document.events)

    assert event_counts == Counter({
        "pledge": 4,
        "release": 4,
        "extension": 2,
    })
