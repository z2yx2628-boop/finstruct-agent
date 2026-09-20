import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "manifests" / "capacity_v5_dev_v4_run.json"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_capacity_v5_v4_baseline_manifest_is_complete():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    predictions = manifest["predictions"]
    corpus = manifest["corpus"]

    assert manifest["manifest_version"] == 1
    assert manifest["task"] == "capacity"
    assert corpus["documents"] == 8
    assert corpus["gold_events"] == 11
    assert corpus["success"] + corpus["needs_review"] == 8
    assert corpus["failed"] == 0
    assert len(predictions) == 8
    assert len({item["document"] for item in predictions}) == 8
    assert len({item["sha256"] for item in predictions}) == 8
    assert all(len(item["sha256"]) == 64 for item in predictions)
    assert {item["status"] for item in predictions} <= {
        "success",
        "needs_review",
    }


def test_capacity_v5_v4_baseline_prompt_hash_is_frozen():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    prompt = manifest["prompt"]

    assert file_sha256(PROJECT_ROOT / prompt["path"]) == prompt["sha256"]


def test_capacity_v5_v4_outputs_match_manifest_when_available():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    batch_path = PROJECT_ROOT / manifest["batch_report"]["path"]
    report_path = PROJECT_ROOT / manifest["accuracy_report"]["path"]

    if not batch_path.exists() or not report_path.exists():
        return

    assert file_sha256(batch_path) == manifest["batch_report"]["sha256"]
    assert file_sha256(report_path) == manifest["accuracy_report"]["sha256"]

    prediction_dir = batch_path.parent / "predictions"
    for item in manifest["predictions"]:
        path = prediction_dir / f"{item['document']}.json"
        assert file_sha256(path) == item["sha256"]
