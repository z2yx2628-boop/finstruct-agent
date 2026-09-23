"""Task registry: one entry per announcement type.

Each task bundles the pieces the pipeline needs, so adding a new
announcement type means registering a TaskSpec here instead of editing
`pipeline.py`, `batch_runner.py` or the web app.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

Pages = list[dict]
ExtractResult = tuple[Any, str, list[dict]]


@dataclass(frozen=True)
class TaskSpec:
    name: str
    label: str
    prompt_path: Path
    extract: Callable[[Pages], ExtractResult]
    normalize: Callable[[Any, Pages], tuple[Any, list[dict]]]
    normalization_tool: str
    validate: Callable[[Any, Pages], dict]
    evaluator_module: str | None = None


def _extract_pledge(pages: Pages) -> ExtractResult:
    from src.llm_extractor import extract_pledge

    document, raw_content = extract_pledge(pages)
    return document, raw_content, []


def _normalize_pledge(document: Any, pages: Pages):
    from src.event_normalizer import normalize_event_fields

    return normalize_event_fields(document)


def _validate_pledge(document: Any, pages: Pages) -> dict:
    from src.evidence_validator import validate_evidence

    return validate_evidence(document, pages)


def _extract_capacity(pages: Pages) -> ExtractResult:
    from src.llm_extractor import extract_capacity

    return extract_capacity(pages)


def _normalize_capacity(document: Any, pages: Pages):
    from src.capacity_normalizer import normalize_capacity_fields

    return normalize_capacity_fields(document, pages)


def _validate_capacity(document: Any, pages: Pages) -> dict:
    from src.capacity_evidence_validator import validate_capacity_evidence

    return validate_capacity_evidence(document, pages)


def _prompt(name: str) -> Path:
    return PROJECT_ROOT / "prompts" / name


TASKS: dict[str, TaskSpec] = {
    "pledge": TaskSpec(
        name="pledge",
        label="股份质押",
        prompt_path=_prompt("pledge_extraction_v6.txt"),
        extract=_extract_pledge,
        normalize=_normalize_pledge,
        normalization_tool="Deterministic semantic and shared-cell normalizer",
        validate=_validate_pledge,
        evaluator_module="src.accuracy_evaluator",
    ),
    "capacity": TaskSpec(
        name="capacity",
        label="产能事件",
        prompt_path=_prompt("capacity_extraction_v5.txt"),
        extract=_extract_capacity,
        normalize=_normalize_capacity,
        normalization_tool="Deterministic capacity overfill normalizer",
        validate=_validate_capacity,
        evaluator_module="src.capacity_accuracy_evaluator",
    ),
}


def get_task(name: str) -> TaskSpec:
    try:
        return TASKS[name]
    except KeyError:
        supported = ", ".join(sorted(TASKS))
        raise ValueError(
            f"Unknown task: {name}. Supported tasks: {supported}"
        ) from None


def task_names() -> tuple[str, ...]:
    return tuple(TASKS)
