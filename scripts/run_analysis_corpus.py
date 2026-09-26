"""Run the FROZEN extraction system over the analysis corpus, one task per document type.

    python scripts/run_analysis_corpus.py            # resumable: finished documents are skipped
Then build the real direction-3 inputs:
    python scripts/build_chain_inputs.py --src outputs/analysis_freeze --out data/chain/analysis_v1

The task comes from the file name written at selection time (related_estimate -> related_party,
guarantee_* -> guarantee, capacity -> capacity, pledge -> pledge). The run log records the git
commit, the freeze tag it descends from and each prediction's SHA-256, so every edge in the
graph can be traced to the exact system version that produced it. Refuses to run with
uncommitted changes in src/, schemas/ or prompts/ (the system must be the frozen one).
"""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCES = ROOT / "data" / "manifests" / "analysis_sources.csv"
RAW = ROOT / "data" / "raw" / "analysis"
OUT = ROOT / "outputs" / "analysis_freeze"
LOG = OUT / "run_log.json"
FREEZE_TAG = "extraction-freeze-2026-09-24"


def task_for(pattern: str) -> str:
    if pattern.startswith("related"):
        return "related_party"
    if pattern.startswith("guarantee"):
        return "guarantee"
    return pattern  # capacity, pledge


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load_log() -> dict:
    """A log cut off by a shutdown (e.g. filled with NUL bytes) is set aside, not trusted."""
    if not LOG.exists():
        return {"runs": {}}
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        broken = LOG.with_name(f"run_log.broken.{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json")
        LOG.replace(broken)
        print(f"run log was damaged (interrupted write); moved to {broken.name}, finished documents will rerun")
        return {"runs": {}}


def save_log(log: dict) -> None:
    """Write to a temporary file first, so an interruption can never leave a half-written log."""
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LOG)


def main() -> None:
    # Compare content, ignoring line endings: Windows checkouts may show CRLF-only "changes".
    dirty = "\n".join(filter(None, [
        git("diff", "--ignore-cr-at-eol", "--name-only", "--", "src", "schemas", "prompts"),
        git("diff", "--cached", "--ignore-cr-at-eol", "--name-only", "--", "src", "schemas", "prompts"),
    ]))
    if dirty:
        sys.exit("Uncommitted changes in src/schemas/prompts - the corpus must run on the frozen system:\n" + dirty)
    from src.pipeline import run_pipeline

    with SOURCES.open(encoding="utf-8-sig", newline="") as f:
        docs = [r for r in csv.DictReader(f) if (RAW / r["file_name"]).exists()]
    log = load_log()
    log.update({"commit": git("rev-parse", "HEAD"), "freeze_tag": FREEZE_TAG,
                "tag_commit": git("rev-list", "-n", "1", FREEZE_TAG),
                "started_at": datetime.now(timezone.utc).isoformat()})
    counts = {}
    for row in docs:
        pdf, task = RAW / row["file_name"], task_for(row["target_pattern"])
        target = OUT / task / f"{pdf.stem}.json"
        if target.exists() and log["runs"].get(pdf.name, {}).get("status") in ("success", "needs_review"):
            counts["cached"] = counts.get("cached", 0) + 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = run_pipeline(pdf, task=task)
            shutil.copy2(result["prediction_path"], target)
            entry = {"task": task, "status": result["status"], "prediction": target.relative_to(ROOT).as_posix(),
                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                     "run_directory": str(result["run_directory"])}
        except Exception as error:
            entry = {"task": task, "status": "failed", "error": f"{type(error).__name__}: {str(error)[:300]}"}
        log["runs"][pdf.name] = entry
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        print(f"[{entry['status']}] {task:13s} {pdf.name}")
        save_log(log)  # save progress after every document
    log["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_log(log)
    print(f"\n{len(docs)} documents: {counts}")
    if counts.get("failed"):
        print("Rerun the same command to retry only the failed ones.")


if __name__ == "__main__":
    main()
