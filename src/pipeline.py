import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.event_normalizer import normalize_event_fields
from src.llm_extractor import PROMPT_PATH, extract_pledge, require_env
from src.pdf_parser import extract_pages
from src.evidence_validator import validate_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_pipeline(pdf_path: Path) -> dict:
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("The input file must be a PDF.")

    load_dotenv(PROJECT_ROOT / ".env")
    model = require_env("LLM_MODEL")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = OUTPUT_ROOT / pdf_path.stem / run_id
    run_directory.mkdir(parents=True, exist_ok=True)

    pages_path = run_directory / "pages.json"
    raw_path = run_directory / "llm_raw.json"
    prediction_path = run_directory / "prediction.json"
    evidence_path = run_directory / "evidence_report.json"
    log_path = run_directory / "run_log.json"

    started_clock = time.perf_counter()
    log = {
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": str(pdf_path),
            "size_bytes": pdf_path.stat().st_size,
            "sha256": file_sha256(pdf_path),
        },
        "prompt": {
            "path": str(PROMPT_PATH),
            "sha256": file_sha256(PROMPT_PATH),
        },
        "model": model,
        "steps": [],
    }

    try:
        step_started = time.perf_counter()
        pages = extract_pages(pdf_path)
        write_json(pages_path, pages)
        log["steps"].append({
            "name": "pdf_text_extraction",
            "tool": "PyMuPDF",
            "page_count": len(pages),
            "duration_seconds": round(time.perf_counter() - step_started, 4),
        })

        step_started = time.perf_counter()
        document, raw_content = extract_pledge(pages)
        llm_duration = round(time.perf_counter() - step_started, 4)

        step_started = time.perf_counter()
        document, normalization_changes = normalize_event_fields(document)
        normalization_duration = round(
            time.perf_counter() - step_started,
            4,
        )
        raw_path.write_text(raw_content, encoding="utf-8")
        prediction_path.write_text(
            document.model_dump_json(indent=2),
            encoding="utf-8",
        )
        log["steps"].append({
            "name": "llm_structured_extraction",
            "tool": "OpenAI-compatible Chat Completions",
            "model": model,
            "duration_seconds": llm_duration,
        })

        log["steps"].append({
            "name": "event_normalization",
            "tool": "Deterministic semantic and shared-cell normalizer",
            "changes_count": len(normalization_changes),
            "changes": normalization_changes,
            "duration_seconds": normalization_duration,
        })

        step_started = time.perf_counter()
        evidence_report = validate_evidence(document, pages)
        write_json(evidence_path, evidence_report)
        log["steps"].append({
            "name": "evidence_validation",
            "tool": "Deterministic evidence validator",
            "passed": evidence_report["passed"],
            "checks_count": evidence_report["checks_count"],
            "expected_event_types": evidence_report[
                "expected_event_types"
            ],
            "extracted_event_types": evidence_report[
                "extracted_event_types"
            ],
            "event_counts": evidence_report["event_counts"],
            "duration_seconds": round(
                time.perf_counter() - step_started,
                4,
            ),
        })

        log["status"] = (
            "success"
            if evidence_report["passed"]
            else "needs_review"
        )

    except Exception as error:
        log["status"] = "failed"
        log["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        raise

    finally:
        log["completed_at"] = datetime.now(timezone.utc).isoformat()
        log["duration_seconds"] = round(
            time.perf_counter() - started_clock, 4
        )
        log["files_written"] = [
            str(path)
            for path in (
                pages_path,
                raw_path,
                prediction_path,
                evidence_path,
            )
            if path.exists()
        ]
        write_json(log_path, log)
    return {
        "status": log["status"],
        "run_directory": run_directory,
        "document": document,
        "evidence_report": evidence_report,
        "log": log,
        "prediction_path": prediction_path,
        "evidence_path": evidence_path,
        "log_path": log_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    args = parser.parse_args()

    result = run_pipeline(args.pdf_path)

    print(f"Status: {result['status']}")
    print(f"Run directory: {result['run_directory']}")
    print(f"Prediction: {result['prediction_path']}")
    print(f"Audit log: {result['log_path']}")
    print(f"Evidence passed: {result['evidence_report']['passed']}")
    print(f"Evidence report: {result['evidence_path']}")


if __name__ == "__main__":
    main()
