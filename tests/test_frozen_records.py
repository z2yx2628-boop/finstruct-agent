"""Frozen Gold labels and archived experiments must never change silently."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCKS = sorted((ROOT / "data" / "gold").glob("*/gold_manifest.lock"))


@pytest.mark.parametrize("lock_path", LOCKS, ids=[p.parent.name for p in LOCKS])
def test_frozen_gold_matches_lock(lock_path):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for item in lock["files"]:
        data = (lock_path.parent / item["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["file"]
    assert len(lock["files"]) == lock["document_count"]


def test_archived_reports_match_registry():
    registry = ROOT / "experiments" / "registry.csv"
    if not registry.exists():
        pytest.skip("no archived experiments")
    with registry.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    for row in rows:
        if not row["report_sha256"]:
            continue
        run = ROOT / "experiments" / row["run"]
        report = next(
            run / name for name in ("report.json", "accuracy_report.json")
            if (run / name).exists()
        )
        assert hashlib.sha256(report.read_bytes()).hexdigest() == row["report_sha256"], row["run"]
