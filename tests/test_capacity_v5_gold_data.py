import hashlib
import json
from collections import Counter
from pathlib import Path

from schemas.capacity import CapacityDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = PROJECT_ROOT / "data" / "gold" / "capacity_v5_dev"
LOCK_PATH = GOLD_DIR / "gold_manifest.lock"
EXPECTED_EVENT_TYPES = {
    "capacity_v5_dev_001_600581_bayi_framework.json": [
        "technical_upgrade"
    ],
    "capacity_v5_dev_002_600569_angang_framework_adjustment.json": [
        "technical_upgrade"
    ],
    "capacity_v5_dev_003_000932_valin_equipment_upgrade.json": [
        "technical_upgrade"
    ],
    "capacity_v5_dev_004_000709_hbis_plate_construction.json": [
        "capacity_construction"
    ],
    "capacity_v5_dev_005_002843_bichamp_multi_delay.json": [
        "delay",
        "delay",
        "delay",
    ],
    "capacity_v5_dev_006_301217_tongguan_multi_delay.json": [
        "delay",
        "delay",
        "delay",
    ],
    "capacity_v5_dev_007_600019_baosteel_overseas_financing.json": [],
    "capacity_v5_dev_008_600282_nangang_overseas_progress.json": [
        "capacity_construction"
    ],
}


def load_gold(filename: str) -> CapacityDocument:
    return CapacityDocument.model_validate_json(
        (GOLD_DIR / filename).read_text(encoding="utf-8")
    )


def test_capacity_v5_gold_file_set_is_complete():
    actual = {path.name for path in GOLD_DIR.glob("*.json")}

    assert actual == set(EXPECTED_EVENT_TYPES)


def test_capacity_v5_gold_lock_matches_frozen_files():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    assert lock["version"] == "capacity-v5-dev-gold-v1"
    assert lock["document_count"] == 8
    assert lock["event_count"] == 11
    assert {item["file"] for item in lock["files"]} == set(
        EXPECTED_EVENT_TYPES
    )

    for item in lock["files"]:
        path = GOLD_DIR / item["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        document = load_gold(item["file"])

        assert digest == item["sha256"]
        assert len(document.events) == item["events"]


def test_capacity_v5_gold_matches_schema_and_distribution():
    event_counts = Counter()

    for filename, expected_types in EXPECTED_EVENT_TYPES.items():
        document = load_gold(filename)
        actual_types = [event.event_type for event in document.events]

        assert actual_types == expected_types
        assert len({event.project_name for event in document.events}) == len(
            document.events
        )
        assert all(event.confidence == 1.0 for event in document.events)
        assert all(
            item.confidence == 1.0
            for event in document.events
            for item in event.capacity_changes
        )
        event_counts.update(actual_types)

    assert event_counts == Counter({
        "delay": 6,
        "technical_upgrade": 3,
        "capacity_construction": 2,
    })


def test_capacity_v5_delay_gold_does_not_overfill_historical_capacity():
    delay_files = [
        "capacity_v5_dev_005_002843_bichamp_multi_delay.json",
        "capacity_v5_dev_006_301217_tongguan_multi_delay.json",
    ]

    for filename in delay_files:
        document = load_gold(filename)
        assert all(not event.capacity_changes for event in document.events)

    exact_date_document = load_gold(delay_files[0])
    assert {
        event.delay_until_date for event in exact_date_document.events
    } == {"2026-09-20"}

    month_only_document = load_gold(delay_files[1])
    assert all(
        event.delay_until_date is None
        for event in month_only_document.events
    )


def test_capacity_v5_financing_notice_is_a_hard_negative():
    document = load_gold(
        "capacity_v5_dev_007_600019_baosteel_overseas_financing.json"
    )

    assert document.events == []


def test_capacity_v5_capacity_records_are_limited_to_project_output():
    records = [
        item
        for filename in EXPECTED_EVENT_TYPES
        for event in load_gold(filename).events
        for item in event.capacity_changes
    ]

    assert [(item.product_name, item.capacity, item.capacity_unit) for item in records] == [
        ("合格成品", 242.0, "万吨/年"),
        ("焦炭", 390.0, "万吨/年"),
    ]
