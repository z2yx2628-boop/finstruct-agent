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
    parser.add_argument(
        "--task",
        choices=("pledge", "capacity"),
        default="pledge",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    pdf_paths = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found in: {args.pdf_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir.parent / "batch_run.json"
    previous_runs = {}
    if args.resume and report_path.exists():
        previous_report = json.loads(
            report_path.read_text(encoding="utf-8")
        )
        previous_runs = {
            Path(item["pdf"]).name: item
            for item in previous_report.get("runs", [])
        }

    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pdf_count": len(pdf_paths),
        "task": args.task,
        "runs": [],
    }

    for pdf_path in pdf_paths:
        target = args.output_dir / f"{pdf_path.stem}.json"
        if args.resume and target.exists():
            previous = previous_runs.get(pdf_path.name, {})
            cached_status = previous.get("status", "cached")
            report["runs"].append({
                **previous,
                "pdf": str(pdf_path),
                "status": cached_status,
                "prediction": str(target),
                "cached": True,
            })
            print(f"[cached:{cached_status}] {pdf_path.name}")
            continue
        if target.exists():
            target.unlink()

        try:
            result = run_pipeline(pdf_path, task=args.task)
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
