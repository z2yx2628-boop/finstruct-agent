"""Post-test fix 1 (2026-09-27): re-run the deterministic related-party steps on the saved model output.

The final test found that the related-party normalizer did not recognise unit declarations with
"人民币" ("金额单位：人民币百万元", "单位：人民币万元") and blanked every amount in such tables.
The model output of every run is saved (llm_raw.json) together with the parsed pages (pages.json),
so the fix is applied without calling the model again: parse -> validate_with_repair -> normalize ->
evidence check, exactly as src/pipeline.py does after the model call.

    python scripts/renormalize_related.py --check      # with the pre-fix rule, must reproduce every saved prediction
    python scripts/renormalize_related.py              # dry run with the current code: what would change
    python scripts/renormalize_related.py --apply      # archive old predictions, write new, log it
    python scripts/renormalize_related.py --final-test # score the final-test runs again ("post-fix, not blind")

Results after this fix are "修复后", never blind or pre-registered results.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARCHIVE = ROOT / "outputs" / "_before_fix1"
FIX = "fix1: related-party unit declaration accepts 人民币 (UNIT_DECLARATION)"


def local(path: str) -> Path:
    """Windows run_directory from a log ('E:\\...\\outputs\\x\\ts') -> this checkout."""
    parts = Path(path.replace("\\", "/")).parts
    return ROOT.joinpath(*parts[parts.index("outputs"):])


def renormalize(run_dir: Path):
    from schemas.related_party import RelatedPartyDocument
    from src.related_party_evidence_validator import validate_related_party_evidence
    from src.related_party_normalizer import normalize_related_party_fields
    from src.structured_extractor import validate_with_repair
    pages = json.loads((run_dir / "pages.json").read_text(encoding="utf-8"))
    raw = (run_dir / "llm_raw.json").read_text(encoding="utf-8")
    document, _ = validate_with_repair(RelatedPartyDocument, json.loads(raw))
    document, changes = normalize_related_party_fields(document, pages)
    report = validate_related_party_evidence(document, pages)
    return document, ("success" if report["passed"] else "needs_review")


def amounts(doc: dict) -> int:
    return sum(1 for t in doc.get("transactions", []) if t.get("estimated_amount") is not None)


def corpus(mode: str) -> None:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    total = same = changed = 0
    for log_path in sorted((ROOT / "outputs").glob("*_freeze/run_log.json")):
        log = json.loads(log_path.read_text(encoding="utf-8"))
        dirty = False
        for name, run in log["runs"].items():
            if run.get("task") != "related_party" or run.get("status") == "failed" or not run.get("run_directory"):
                continue
            run_dir, target = local(run["run_directory"]), ROOT / run["prediction"]
            if not (run_dir / "llm_raw.json").exists() or not target.exists():
                print(f"[skip] {name}: saved model output not found")
                continue
            total += 1
            old_text = target.read_text(encoding="utf-8")
            document, status = renormalize(run_dir)
            new_text = document.model_dump_json(indent=2)
            old, new = json.loads(old_text), json.loads(new_text)
            if old == new:
                same += 1
                continue
            changed += 1
            print(f"[{'differs' if mode == 'check' else 'change'}] {name}: amounts {amounts(old)} -> {amounts(new)} "
                  f"of {len(new.get('transactions', []))}; status {run['status']} -> {status}")
            if mode == "apply":
                backup = ARCHIVE / target.relative_to(ROOT / "outputs")
                backup.parent.mkdir(parents=True, exist_ok=True)
                if not backup.exists():
                    shutil.copy2(target, backup)
                target.write_text(new_text, encoding="utf-8")
                run.setdefault("renormalized", []).append({
                    "fix": FIX, "commit": commit, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "old_sha256": run.get("sha256"), "old_status": run["status"],
                    "archived": backup.relative_to(ROOT).as_posix()})
                run["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                run["status"] = status
                dirty = True
        if dirty:
            tmp = log_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(log_path)
    print(f"\n{total} related-party predictions: {same} unchanged, {changed} {'differ' if mode == 'check' else 'changed'}"
          + (" (applied)" if mode == "apply" else ""))
    if mode == "check" and changed:
        sys.exit("check failed: the saved predictions are not reproduced; do not apply.")


def final_test() -> None:
    """Re-normalize the three final-test runs into predictions_fix1/ and score them (not blind)."""
    from src import related_party_accuracy_evaluator as rel
    gold = ROOT / "outputs" / "final_test" / "gold" / "related_party"
    lines = ["", "## 修复后（非盲，fix1：单位声明允许“人民币”；不改变盲测成绩）", "",
             "| 运行 | 记录 TP/FP/FN | P | R | F1 | 字段准确率 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in (1, 2, 3):
        base = ROOT / "outputs" / "final_test" / f"r{r}" / "related_party"
        batch = json.loads((base / "batch_run.json").read_text(encoding="utf-8"))
        out = base / "predictions_fix1"
        out.mkdir(exist_ok=True)
        for run in batch["runs"]:
            if run.get("status") == "failed" or not run.get("run_directory"):
                continue
            document, _ = renormalize(local(run["run_directory"]))
            (out / Path(run["prediction"].replace("\\", "/")).name).write_text(document.model_dump_json(indent=2), encoding="utf-8")
        rep = rel.evaluate_directories(gold, out)
        e, f = rep["record_metrics"], rep["factual_attribute_metrics"]
        lines.append(f"| r{r} | {e['true_positives']}/{e['false_positives']}/{e['false_negatives']} | {e['precision']:.2%} | "
                     f"{e['recall']:.2%} | {e['f1']:.2%} | {f['matched']}/{f['total']} ({f['accuracy']:.2%}) |")
    text = "\n".join(lines) + "\n"
    print(text)
    doc = ROOT / "docs" / "final_test_results.md"
    if "## 修复后（非盲，fix1" not in doc.read_text(encoding="utf-8"):
        with doc.open("a", encoding="utf-8") as fh:
            fh.write(text)


def use_unfixed_rule() -> None:
    """--check runs the pre-fix rule, so it proves the saved model output reproduces the saved predictions."""
    import re
    import src.related_party_normalizer as n
    n.UNIT_DECLARATION = re.compile(r"单位[:：](千元|百万元|万元|亿元|元)|[（(](千元|百万元|万元|亿元|元)[）)]")


if __name__ == "__main__":
    if "--check" in sys.argv:
        use_unfixed_rule()
    if "--final-test" in sys.argv:
        final_test()
    else:
        corpus("check" if "--check" in sys.argv else "apply" if "--apply" in sys.argv else "dry")
