import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.document_parser import PARSERS, parse_document
from src.llm_extractor import require_env
from src.ocr import LOW_CONFIDENCE_THRESHOLD
from src.tasks import get_task, task_names

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


def run_pipeline(pdf_path: Path, task: str = "pledge") -> dict:
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Document not found: {pdf_path}")
    if pdf_path.suffix.lower() not in PARSERS:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(
            f"Unsupported document type: {pdf_path.suffix}. "
            f"Supported types: {supported}"
        )
    spec = get_task(task)

    load_dotenv(PROJECT_ROOT / ".env")
    model = require_env("LLM_MODEL")
    prompt_path = spec.prompt_path
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = OUTPUT_ROOT / pdf_path.stem / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    parsed_document_path = run_directory / "parsed_document.json"

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
            "path": str(prompt_path),
            "sha256": file_sha256(prompt_path),
        },
        "task": task,
        "model": model,
        "steps": [],
    }
    try:
        step_started = time.perf_counter()
        source_document = parse_document(pdf_path)

        write_json(
            parsed_document_path,
            source_document.model_dump(mode="json"),
        )

        if not source_document.metadata.get("text_char_count"):
            raise ValueError(
                "The document contains no extractable text. For scanned "
                "files install OCR: pip install rapidocr_onnxruntime"
            )
        low_confidence_pages = [
            page.page for page in source_document.pages
            if page.ocr_used
            and page.ocr_confidence is not None
            and page.ocr_confidence < LOW_CONFIDENCE_THRESHOLD
        ]

        pages = [
            {
                "page": page.page,
                "text": page.text,
            }
            for page in source_document.pages
        ]
        write_json(pages_path, pages)

        log["steps"].append({
            "name": "document_parsing",
            "tool": "Unified document parser / PyMuPDF + OCR",
            "source_type": source_document.source_type,
            "page_count": len(pages),
            "text_char_count": source_document.metadata.get(
                "text_char_count",
                0,
            ),
            "needs_ocr": source_document.metadata.get(
                "needs_ocr",
                False,
            ),
            "ocr_pages": source_document.metadata.get("ocr_pages", []),
            "ocr_engine": source_document.metadata.get("ocr_engine"),
            "ocr_confidence": {
                page.page: page.ocr_confidence
                for page in source_document.pages
                if page.ocr_used
            },
            "ocr_low_confidence_pages": low_confidence_pages,
            "duration_seconds": round(
                time.perf_counter() - step_started,
                4,
            ),
        })

        step_started = time.perf_counter()
        document, raw_content, extraction_changes = spec.extract(pages)
        llm_duration = round(time.perf_counter() - step_started, 4)

        step_started = time.perf_counter()
        document, normalization_changes = spec.normalize(document, pages)
        normalization_tool = spec.normalization_tool
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
            "sanitization_changes_count": len(extraction_changes),
            "sanitization_changes": extraction_changes,
            "duration_seconds": llm_duration,
        })

        log["steps"].append({
            "name": "event_normalization",
            "tool": normalization_tool,
            "changes_count": len(normalization_changes),
            "changes": normalization_changes,
            "duration_seconds": normalization_duration,
        })

        step_started = time.perf_counter()
        evidence_report = spec.validate(document, pages)
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
            if evidence_report["passed"] and not low_confidence_pages
            else "needs_review"
        )
        if low_confidence_pages:
            log["review_reasons"] = [
                f"OCR confidence below {LOW_CONFIDENCE_THRESHOLD} on pages "
                f"{low_confidence_pages}; verify numbers against the source."
            ]

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
                parsed_document_path,
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
    parser.add_argument(
        "--task",
        choices=task_names(),
        default="pledge",
    )
    args = parser.parse_args()

    result = run_pipeline(args.pdf_path, task=args.task)

    print(f"Status: {result['status']}")
    print(f"Run directory: {result['run_directory']}")
    print(f"Prediction: {result['prediction_path']}")
    print(f"Audit log: {result['log_path']}")
    print(f"Evidence passed: {result['evidence_report']['passed']}")
    print(f"Evidence report: {result['evidence_path']}")


if __name__ == "__main__":
    main()
