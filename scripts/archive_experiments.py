"""Archive evaluation runs from outputs/ (git-ignored) into experiments/ (tracked).

For every run directory that has a batch_run.json, this copies the report,
batch record and predictions, plus the per-document run_log.json files the
batch points to (prompt path and SHA-256, model, timings). A registry CSV
summarises every archived run.

Archived files are append-only: if a file already exists in experiments/
with different content, the script stops instead of overwriting it.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\archive_experiments.py
"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
ARCHIVE = ROOT / "experiments"
REPORT_NAMES = ("report.json", "accuracy_report.json", "attribute_analysis.json", "batch_run.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_immutable(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != sha256(source):
            raise SystemExit(
                f"Refusing to overwrite archived file with different content: {target}"
            )
        return "kept"
    shutil.copy2(source, target)
    return "added"


def run_directory(entry: dict) -> Path | None:
    raw = entry.get("run_directory")
    if not raw:
        return None
    parts = raw.replace("\\", "/").split("outputs/")
    return OUTPUTS / parts[-1] if len(parts) > 1 else None


def headline(report: dict) -> dict:
    def f1(name):
        metric = report.get(name) or {}
        return round(metric["f1"], 4) if "f1" in metric else ""

    def acc(name):
        metric = report.get(name) or {}
        if "matched" in metric:
            return f"{metric['matched']}/{metric['total']}"
        return ""

    return {
        "event_f1": f1("event_metrics"),
        "capacity_record_f1": f1("capacity_record_metrics"),
        "document_fields": acc("document_field_metrics"),
        "factual_attributes": acc("factual_attribute_metrics") or acc("event_attribute_metrics"),
    }


def main() -> int:
    rows, added = [], 0
    for run in sorted(p for p in OUTPUTS.iterdir() if (p / "batch_run.json").exists()):
        target = ARCHIVE / run.name
        for name in REPORT_NAMES:
            if (run / name).exists():
                added += copy_immutable(run / name, target / name) == "added"
        for prediction in sorted((run / "predictions").glob("*.json")):
            added += copy_immutable(prediction, target / "predictions" / prediction.name) == "added"

        batch = json.loads((run / "batch_run.json").read_text(encoding="utf-8"))
        prompt_hashes, models = set(), set()
        for entry in batch.get("runs", []):
            directory = run_directory(entry)
            if directory and (directory / "run_log.json").exists():
                log_target = target / "run_logs" / f"{directory.parent.name}__{directory.name}.json"
                added += copy_immutable(directory / "run_log.json", log_target) == "added"
                log = json.loads((directory / "run_log.json").read_text(encoding="utf-8"))
                prompt_hashes.add(log.get("prompt", {}).get("sha256", "")[:12])
                models.add(log.get("model", ""))

        report_path = next((run / n for n in ("report.json", "accuracy_report.json") if (run / n).exists()), None)
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path else {}
        statuses = [entry.get("status") for entry in batch.get("runs", [])]
        rows.append({
            "run": run.name,
            "task": batch.get("task", ""),
            "started_at": batch.get("started_at", ""),
            "documents": len(statuses),
            "failed": statuses.count("failed"),
            "model": ";".join(sorted(m for m in models if m)),
            "prompt_sha256_prefix": ";".join(sorted(h for h in prompt_hashes if h)),
            **headline(report),
            "report_sha256": sha256(report_path) if report_path else "",
        })

    ARCHIVE.mkdir(exist_ok=True)
    with (ARCHIVE / "registry.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} runs registered, {added} new files archived in {ARCHIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
