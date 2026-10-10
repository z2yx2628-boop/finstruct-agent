"""Blind test of 问一句's question routing on 30 questions written by a teammate who had not used the feature.

The questions and the teammate's expected type are in data/eval/ask_blind_30.csv (types 1-10 as in the instructions:
1 企业风险概况 … 9 系统可信度, 10 不支持). Questions 21-25 were marked by the teammate as ambiguous; accuracy is
reported on the 25 clear questions and on all 30. The router (src/ask.py) is evaluated as committed; it must not be
changed in response to these questions and then re-scored as a test result.

    python scripts/eval_ask.py               # rules only (no model call)
    python scripts/eval_ask.py --model       # rules, then the model for questions the rules cannot place
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ask import INTENTS, model_available, model_route, rule_route  # noqa: E402

DATA = ROOT / "data" / "eval" / "ask_blind_30.csv"
TYPES = {1: "company", 2: "spread", 3: "exposure", 4: "today", 5: "ranking", 6: "price", 7: "export",
         8: "document", 9: "trust", 10: "unsupported"}
AMBIGUOUS = {21, 22, 23, 24, 25}
BLIND_COMMIT = "c1bae17"   # src/ask.py as committed before the questions were written; any later version saw them


def route(question: str, use_model: bool) -> dict:
    r = rule_route(question)
    if r["intent"] == "unsupported" and use_model:
        try:
            r = model_route(question) or r
        except Exception as error:  # noqa: BLE001
            r = dict(r, by=f"模型调用失败（{type(error).__name__}）")
    return r


def main() -> None:
    use_model = "--model" in sys.argv
    if use_model and not model_available():
        sys.exit("没有模型配置（.env 里的 LLM_API_KEY / LLM_MODEL）。")
    rows = []
    with DATA.open(encoding="utf-8") as f:
        for q in csv.DictReader(f):
            qid, expected = int(q["id"]), TYPES[int(q["expected_type"])]
            r = route(q["question"], use_model)
            names = "、".join(n for _, n in r["companies"])
            rows.append({"id": qid, "question": q["question"], "expected": expected, "got": r["intent"],
                         "correct": r["intent"] == expected, "ambiguous": qid in AMBIGUOUS, "by": r["by"],
                         "companies": names, "expected_entity": q["entity"]})
    clear = [r for r in rows if not r["ambiguous"]]
    acc = lambda rs: f"{sum(r['correct'] for r in rs)}/{len(rs)}（{sum(r['correct'] for r in rs) / len(rs):.0%}）"  # noqa: E731
    out_scope = [r for r in rows if r["expected"] == "unsupported"]
    in_scope = [r for r in rows if r["expected"] != "unsupported"]
    commit = subprocess.run(["git", "log", "-1", "--format=%h %ci", "--", "src/ask.py"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src/ask.py"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    blind = commit.startswith(BLIND_COMMIT) and not dirty
    label = ("规则 + 模型" if use_model else "仅规则") + ("，盲测" if blind else "，修改后：这 30 题已用于修改规则，结果只是开发集成绩，不是盲测")
    lines = [f"## {label}（{date.today()} 运行；src/ask.py 版本 {commit}）", "",
             f"- 清晰问题（25 题）准确率：{acc(clear)}",
             f"- 全部 30 题准确率：{acc(rows)}",
             f"- 应拒绝的问题被正确拒绝：{sum(r['correct'] for r in out_scope)}/{len(out_scope)}",
             f"- 范围内问题被错误拒绝：{sum(r['got'] == 'unsupported' for r in in_scope)}/{len(in_scope)}", "",
             "| 类型 | 正确 / 题数 |", "| --- | --- |"]
    for key, label_cn in [(v, INTENTS.get(v, ('不支持',))[0]) for v in TYPES.values()]:
        sub = [r for r in clear if r["expected"] == key]
        if sub:
            lines.append(f"| {label_cn} | {sum(r['correct'] for r in sub)}/{len(sub)} |")
    lines += ["", "| 编号 | 问题 | 期望 | 系统 | 对错 | 识别到的企业 | 路由 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']}{'（模棱两可）' if r['ambiguous'] else ''} | {r['question']} | {r['expected']} | {r['got']} | "
                     f"{'✓' if r['correct'] else '✗'} | {r['companies'] or '—'} | {r['by']} |")
    report = ROOT / "docs" / "ask_eval.md"
    head = "" if report.exists() else ("# 问一句：盲测问题的意图识别准确率\n\n30 个问题由未使用过该功能的队友编写并标注期望类型"
                                       "（`data/eval/ask_blind_30.csv`），路由器在问题写好之前已提交，未针对这些问题修改。\n\n")
    with report.open("a", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n\n")
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()
