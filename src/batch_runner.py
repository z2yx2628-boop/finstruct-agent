import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from src.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    pdf_paths = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found in: {args.pdf_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pdf_count": len(pdf_paths),
        "runs": [],
    }

    for pdf_path in pdf_paths:
        target = args.output_dir / f"{pdf_path.stem}.json"
        if target.exists():
            target.unlink()

        try:
            result = run_pipeline(pdf_path)
            shutil.copy2(result["prediction_path"], target)
            report["runs"].append({
                "pdf": str(pdf_path),
                "status": result["status"],
                "prediction": str(target),
                "run_directory": str(result["run_directory"]),
            })
            print(f"[{result['status']}] {pdf_path.name}")
        except Exception as error:
            report["runs"].append({
                "pdf": str(pdf_path),
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            })
            print(f"[failed] {pdf_path.name}: {error}")

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report_path = args.output_dir.parent / "batch_run.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failures = [item for item in report["runs"] if item["status"] == "failed"]
    print(f"Batch report saved to: {report_path}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
