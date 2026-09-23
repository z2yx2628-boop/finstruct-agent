import pytest

from src.tasks import TASKS, get_task, task_names


def test_existing_tasks_are_registered():
    assert set(task_names()) >= {"pledge", "capacity"}


def test_registered_prompts_exist():
    for spec in TASKS.values():
        assert spec.prompt_path.exists(), spec.prompt_path


def test_capacity_task_keeps_frozen_v5_prompt():
    assert get_task("capacity").prompt_path.name == "capacity_extraction_v5.txt"
    assert get_task("pledge").prompt_path.name == "pledge_extraction_v6.txt"


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError):
        get_task("unknown")


def test_pipeline_routes_through_registry(monkeypatch, tmp_path):
    import src.pipeline as pipeline
    from src.tasks import TaskSpec

    calls = []
    fake = TaskSpec(
        name="capacity",
        label="产能事件",
        prompt_path=get_task("capacity").prompt_path,
        extract=lambda pages: (calls.append("extract") or _Doc(), "{}", []),
        normalize=lambda doc, pages: (calls.append("normalize") or doc, []),
        normalization_tool="fake",
        validate=lambda doc, pages: calls.append("validate") or {
            "passed": True,
            "checks_count": 0,
            "expected_event_types": [],
            "extracted_event_types": [],
            "event_counts": {},
        },
    )
    monkeypatch.setattr(pipeline, "get_task", lambda name: fake)
    monkeypatch.setattr(pipeline, "require_env", lambda name: "test-model")
    monkeypatch.setattr(pipeline, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "parse_document", _fake_parse)

    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 test")
    result = pipeline.run_pipeline(source, task="capacity")

    assert calls == ["extract", "normalize", "validate"]
    assert result["status"] == "success"


class _Doc:
    def model_dump_json(self, indent=None):
        return "{}"


def _fake_parse(path):
    from schemas.common import ParsedDocument, ParsedPage

    return ParsedDocument(
        document_id="doc",
        source_type="pdf_text",
        source_name="doc.pdf",
        source_path=str(path),
        sha256="0" * 64,
        pages=[ParsedPage(page=1, text="正文")],
        metadata={"text_char_count": 2, "needs_ocr": False},
    )
