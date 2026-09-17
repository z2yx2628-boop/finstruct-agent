from collections import Counter
from pathlib import Path

from schemas.capacity import CapacityDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = PROJECT_ROOT / "data" / "gold" / "capacity_dev"
EXPECTED_EVENT_TYPES = {
    "capacity_dev_001_600019_baosteel_construction.json": (
        "capacity_construction"
    ),
    "capacity_dev_002_600019_baosteel_construction.json": (
        "capacity_construction"
    ),
    "capacity_dev_003_000709_hbis_construction.json": (
        "capacity_construction"
    ),
    "capacity_dev_004_000709_hbis_commissioning.json": "commissioning",
    "capacity_dev_005_000709_hbis_commissioning.json": "commissioning",
    "capacity_dev_006_000932_valin_technical_upgrade.json": (
        "technical_upgrade"
    ),
    "capacity_dev_007_000932_valin_technical_upgrade.json": (
        "technical_upgrade"
    ),
    "capacity_dev_008_600581_bayi_technical_upgrade.json": (
        "technical_upgrade"
    ),
    "capacity_dev_009_600581_bayi_construction.json": (
        "capacity_construction"
    ),
    "capacity_dev_010_600231_linggang_replacement.json": (
        "capacity_replacement"
    ),
    "capacity_dev_011_600231_linggang_delay.json": "delay",
    "capacity_dev_012_601686_youfa_termination.json": "termination",
}


def test_capacity_gold_file_set_is_complete():
    actual = {path.name for path in GOLD_DIR.glob("*.json")}

    assert actual == set(EXPECTED_EVENT_TYPES)


def test_capacity_gold_documents_match_schema():
    event_counts = Counter()

    for filename, expected_type in EXPECTED_EVENT_TYPES.items():
        document = CapacityDocument.model_validate_json(
            (GOLD_DIR / filename).read_text(encoding="utf-8")
        )

        assert len(document.events) == 1
        event = document.events[0]
        assert event.event_type == expected_type
        assert event.confidence == 1.0
        assert all(item.confidence == 1.0 for item in event.capacity_changes)
        assert all(
            item.confidence == 1.0 for item in event.environmental_metrics
        )
        event_counts.update([event.event_type])

    assert event_counts == Counter({
        "capacity_construction": 4,
        "technical_upgrade": 3,
        "commissioning": 2,
        "capacity_replacement": 1,
        "delay": 1,
        "termination": 1,
    })
