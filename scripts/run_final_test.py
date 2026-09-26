"""Run the frozen extraction system on the final test set, 3 times, and score every run once.

    python scripts/run_final_test.py            # runs r1..r3 (a finished run is never re-run), then scores
    python scripts/run_final_test.py --score    # only (re)compute the summary from existing predictions

Before anything runs it checks, and refuses otherwise:
  * Gold files and source documents match data/gold/final_test/gold_manifest.lock (SHA-256);
  * prompts/, schemas/ and the extraction modules equal tag extraction-freeze-2026-09-24 (content, CR ignored),
    with no uncommitted change in them.
A document the system fails on is scored as an empty prediction (all its records count as missed), not skipped.
Predictions: outputs/final_test/r<N>/<task>/predictions/ (git-ignored).
Summary (committed): experiments/final_test/summary.json and docs/final_test_results.md.
"""
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TAG = "extraction-freeze-2026-09-24"
RAW = ROOT / "data" / "raw" / "final_test"
GOLD = ROOT / "data" / "gold" / "final_test"
OUT = ROOT / "outputs" / "final_test"
EXP = ROOT / "experiments" / "final_test"
RUNS = 3
# Direction 2/3 modules changed after the tag on purpose; they are not used by extraction.
NOT_EXTRACTION = {"src/analyze.py", "src/chain_inputs.py", "src/fragility.py", "src/network_view.py",
                  "src/propagation.py", "src/sources.py", "src/validity.py", "src/quarterly.py", "src/market.py",
                  "src/financial_indicators.py"}
ADDITIVE_OK = {"src/entity_resolver.py"}     # only groups_as_of() added; checked below


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen() -> None:
    lock = json.loads((GOLD / "gold_manifest.lock").read_text(encoding="utf-8"))
    for f in lock["files"]:
        gold = GOLD / f["file"]
        if sha(gold) != f["sha256"]:
            sys.exit(f"Gold changed after locking: {gold.name}")
        src = next(p for p in RAW.glob(Path(f["file"]).stem + ".*") if p.suffix != ".json")
        if sha(src) != f["source_sha256"]:
            sys.exit(f"Source document changed: {src.name}")
    # --name-only ignores --ignore-cr-at-eol, so a file counts as changed only if its content diff is non-empty
    names = git("diff", "--name-only", TAG, "--", "src", "prompts", "schemas").split()
    changed = [p for p in names if p not in NOT_EXTRACTION and not p.endswith(".pyc")
               and git("diff", "--ignore-cr-at-eol", TAG, "--", p).strip()]
    for p in changed:
        if p in ADDITIVE_OK:
            removed = [l for l in git("diff", "--ignore-cr-at-eol", TAG, "--", p).splitlines()
                       if l.startswith("-") and not l.startswith("---")]
            if not removed:
                continue
        sys.exit(f"Extraction code differs from {TAG}: {p}")
    print(f"frozen check ok: Gold and sources match the lock; extraction code equals {TAG}")
    return lock


def split_inputs() -> dict[str, tuple[Path, Path]]:
    """Per-task copies of the inputs and of the Gold (the evaluators read whole directories)."""
    tasks = {}
    for task, pattern in (("related_party", "final_0*"), ("capacity", "final_web_*")):
        inp, gold = OUT / "inputs" / task, OUT / "gold" / task
        inp.mkdir(parents=True, exist_ok=True)
        gold.mkdir(parents=True, exist_ok=True)
        for p in RAW.glob(pattern):
            shutil.copy2(p, inp / p.name)            # .meta.json travels with the webpage
        for p in GOLD.glob(pattern + ".json"):
            shutil.copy2(p, gold / p.name)
        tasks[task] = (inp, gold)
    return tasks


def run(tasks) -> None:
    for r in range(1, RUNS + 1):
        for task, (inp, _) in tasks.items():
            pred = OUT / f"r{r}" / task / "predictions"
            done = pred.parent / "batch_run.json"
            if done.exists():
                print(f"[skip] r{r} {task}: already run")
                continue
            print(f"[run]  r{r} {task}")
            subprocess.run([sys.executable, "-m", "src.batch_runner", str(inp), "--task", task,
                            "--output-dir", str(pred)], cwd=ROOT)
            if not done.exists():
                done.write_text(json.dumps({"note": "batch runner wrote no report"}), encoding="utf-8")


def score(tasks, lock) -> None:
    from src import capacity_accuracy_evaluator as cap
    from src import related_party_accuracy_evaluator as rel
    from schemas.capacity import CapacityDocument
    from schemas.related_party import RelatedPartyDocument
    empty = {"related_party": RelatedPartyDocument(), "capacity": CapacityDocument()}
    runs = []
    for r in range(1, RUNS + 1):
        row = {"run": r}
        for task, (_, gold) in tasks.items():
            pred = OUT / f"r{r}" / task / "predictions"
            if not pred.exists():
                continue
            scored = OUT / f"r{r}" / task / "scored"
            shutil.rmtree(scored, ignore_errors=True)
            shutil.copytree(pred, scored)
            failed = []
            for g in gold.glob("*.json"):
                if not (scored / g.name).exists():
                    failed.append(g.stem)
                    (scored / g.name).write_text(empty[task].model_dump_json(), encoding="utf-8")
            ev = rel if task == "related_party" else cap
            rep = ev.evaluate_directories(gold, scored)
            (OUT / f"r{r}" / task / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
            det = rep["record_metrics"] if task == "related_party" else rep["event_metrics"]
            fact = rep["factual_attribute_metrics"]
            row[task] = {"tp": det["true_positives"], "fp": det["false_positives"], "fn": det["false_negatives"],
                         "precision": det["precision"], "recall": det["recall"], "f1": det["f1"],
                         "factual_matched": fact["matched"], "factual_total": fact["total"], "factual_accuracy": fact["accuracy"],
                         "failed_documents": failed,
                         "per_document": {k: {"tp": v[("record_metrics" if task == "related_party" else "event_metrics")]["true_positives"],
                                              "fp": v[("record_metrics" if task == "related_party" else "event_metrics")]["false_positives"],
                                              "fn": v[("record_metrics" if task == "related_party" else "event_metrics")]["false_negatives"]}
                                          for k, v in rep["documents"].items()}}
        runs.append(row)
    agg = {}
    for task in tasks:
        vals = [x[task] for x in runs if task in x]
        if vals:
            agg[task] = {m: {"mean": statistics.mean(v[m] for v in vals), "min": min(v[m] for v in vals),
                             "max": max(v[m] for v in vals)} for m in ("precision", "recall", "f1", "factual_accuracy")}
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "system_under_test": TAG, "gold": lock["version"], "gold_records": lock["record_count"],
               "commit": git("rev-parse", "--short", "HEAD").strip(), "runs": runs, "aggregate": agg}
    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pct = lambda x: f"{x:.2%}"
    lines = ["# 最终测试结果（final-test-gold-v1）", "",
             f"被测系统 `{TAG}`；Gold {lock['record_count']} 条（AI 预标注、人工抽查 53/178）；每个任务运行 {RUNS} 次，全部报告。", ""]
    for task, name in (("related_party", "关联交易（7 份）"), ("capacity", "检修网页（1 份）")):
        if task not in agg:
            continue
        a = agg[task]
        lines += [f"## {name}", "", "| 运行 | 记录 TP/FP/FN | P | R | F1 | 字段准确率 | 失败文档 |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for x in runs:
            if task in x:
                t = x[task]
                lines.append(f"| r{x['run']} | {t['tp']}/{t['fp']}/{t['fn']} | {pct(t['precision'])} | {pct(t['recall'])} | {pct(t['f1'])} | "
                             f"{t['factual_matched']}/{t['factual_total']} ({pct(t['factual_accuracy'])}) | {', '.join(t['failed_documents']) or '—'} |")
        lines.append(f"| 平均（范围） | | {pct(a['precision']['mean'])} | {pct(a['recall']['mean'])} | "
                     f"{pct(a['f1']['mean'])}（{pct(a['f1']['min'])}–{pct(a['f1']['max'])}） | "
                     f"{pct(a['factual_accuracy']['mean'])}（{pct(a['factual_accuracy']['min'])}–{pct(a['factual_accuracy']['max'])}） | |")
        lines += ["", "按文档（r1 / r2 / r3 的 TP/FP/FN）：", ""]
        docs = sorted({d for x in runs if task in x for d in x[task]["per_document"]})
        for d in docs:
            cells = [f"{x[task]['per_document'][d]['tp']}/{x[task]['per_document'][d]['fp']}/{x[task]['per_document'][d]['fn']}"
                     for x in runs if task in x and d in x[task]["per_document"]]
            lines.append(f"- {d}: " + " · ".join(cells))
        lines.append("")
    (ROOT / "docs" / "final_test_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    lock = check_frozen()
    tasks = split_inputs()
    if "--score" not in sys.argv:
        run(tasks)
    score(tasks, lock)
