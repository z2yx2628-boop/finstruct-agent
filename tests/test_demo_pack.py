"""The offline demo pack must replay without the model and keep the recorded backtest verdicts."""
import hashlib
from pathlib import Path

import pytest

from src.analyze import TaskNotDetected, analyze, demo_cases, replay

ROOT = Path(__file__).resolve().parents[1]
CASES = demo_cases()


def test_manifest_is_not_empty():
    assert len(CASES) >= 5


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_replays_offline(case):
    src = ROOT / case["source"]
    assert hashlib.sha256(src.read_bytes()).hexdigest() == case["source_sha256"]
    card = analyze(src, as_of=case["as_of"], chain=case["chain"], offline=True)
    assert card["extraction_status"] == "offline_replay"
    assert "离线回放" in card["offline_note"]
    assert [p["path"] for p in card["who_is_next"]] == [p["path"] for p in replay(case)["who_is_next"]]


def test_backtest_verdicts_in_demo_pack():
    by_id = {c["id"]: replay(c) for c in CASES}
    assert "新泰钢铁" in by_id["antai_guarantee"]["who_is_next"][0]["path"]
    assert "凌钢集团" in by_id["linggang_guarantee"]["who_is_next"][0]["path"]
    assert by_id["fangda_guarantee"]["who_is_next"] == []


def test_offline_mode_refuses_files_outside_the_pack(tmp_path):
    other = tmp_path / "x.pdf"
    other.write_bytes(b"not in the demo pack")
    with pytest.raises(TaskNotDetected):
        analyze(other, offline=True)
