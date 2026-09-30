"""After the tests: put the test documents' extractions into the live graph.

Many 2026 annual related-party estimates and guarantee limits of the core mills were chosen as TEST documents
(related_test, guarantee_test, final_test). While the tests were open they were kept out of every graph so the
system could not have seen them. The tests are finished and reported, so the live graph may now use them -
otherwise those companies have no relation in force at all.

What is copied is the FROZEN SYSTEM'S OWN OUTPUT from the first test run (run 1), not the Gold answers:
the live graph must show what the system extracts, errors included. The documents stay test documents -
any future evaluation must not reuse them.

Writes outputs/live_testdocs_freeze/<task>/<holdout_id>.json and outputs/live_testdocs_freeze/README.md;
scripts/daily_update.py picks the folder up (its name starts with live_).

    python scripts/reuse_test_predictions.py
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "live_testdocs_freeze"
RUNS = {"related_party": ROOT / "experiments" / "related_test_r1" / "predictions",
        "guarantee": ROOT / "experiments" / "guarantee_test_r1" / "predictions"}
FINAL = ROOT / "data" / "manifests" / "final_test_selection.csv"


def task_of(doc: dict) -> str | None:
    if "transactions" in doc:
        return "related_party"
    if "events" in doc and any("guarant" in json.dumps(e, ensure_ascii=False) for e in doc["events"][:3]):
        return "guarantee"
    return None


def main() -> None:
    copied = []
    for task, folder in RUNS.items():
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            dest = OUT / task / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied.append((task, path.relative_to(ROOT).as_posix()))
    if FINAL.exists():
        with FINAL.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                runs = sorted((ROOT / "outputs").glob(f"{row['holdout_id']}_*/*/prediction.json"))
                if not runs:
                    continue
                first = runs[0]                                   # run 1 of the frozen system
                doc = json.loads(first.read_text(encoding="utf-8"))
                task = task_of(doc)
                if not task:
                    continue                                      # capacity web page: no relation to add
                dest = OUT / task / f"{first.parent.parent.name}.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(first, dest)
                copied.append((task, first.relative_to(ROOT).as_posix()))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README.md").write_text(
        "# 测试文档的冻结系统输出（测试结束后并入实时图谱）\n\n"
        "这些公告曾是关联交易 / 担保测试集和最终测试集，测试期间不进入任何图谱。测试已完成并报告，"
        "为使实时图谱覆盖各钢厂 2026 年度关联交易预计和担保额度，这里复用冻结系统在第 1 次测试运行中的输出"
        "（不是 Gold），错误照样保留。这些文档今后不得再用于任何评测。\n\n"
        + "\n".join(f"- {t}: {p}" for t, p in copied) + "\n", encoding="utf-8")
    by_task = {}
    for t, _ in copied:
        by_task[t] = by_task.get(t, 0) + 1
    print(f"{len(copied)} test-document extractions -> {OUT.relative_to(ROOT)} {by_task}")


if __name__ == "__main__":
    sys.exit(main())
