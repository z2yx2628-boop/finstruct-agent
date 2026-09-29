"""Post-hoc checks on the event study (written AFTER seeing docs/event_study_results.md; reported as 事后分析,
never as the pre-registered result).

  1. Without the three controlled-subsidiary bankruptcies (the weakest kind of hard event).
  2. Is the score more than "last year's loss persists"?
     - baselines: last annual report already public on the assessment date shows a loss (yes/no);
       debt ratio alone; latest quarterly net margin alone - AUC of each vs the score
     - among company-dates WITHOUT a loss in the last public annual report: does weak vs not-weak still separate?
  3. AUC within each assessment year (the downturn from 2022 on concentrates events in a few years).

Reads data/event_study/panel.csv, data/event_study/snapshots/<date>/quarterly_metrics.csv and the Sina abstract.
Writes docs/event_study_posthoc.md.

    python scripts/event_study_posthoc.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_event_study import DATES, auc, pct, table  # noqa: E402
from src.quarterly import parse_abstract  # noqa: E402

OUT = ROOT / "data" / "event_study"
QDIR = ROOT / "data" / "external" / "financials" / "quarterly"
SUBSIDIARY = {("600808", "2023-11-15"), ("000717", "2019-07-03"), ("600022", "2025-11-21")}


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def last_annual_loss(code: str, as_of: str, cache: dict) -> bool | None:
    """Loss in the latest annual report whose statutory deadline (30 April) is on or before as_of."""
    if code not in cache:
        path = QDIR / f"{code}_abstract.csv"
        cache[code] = parse_abstract(list(csv.reader(path.open(encoding="utf-8-sig")))) if path.exists() else {}
    year = int(as_of[:4]) - 1 if as_of[5:] >= "04-30" else int(as_of[:4]) - 2
    p = cache[code].get(f"{year}1231", {})
    return None if p.get("parent_netprofit") is None else p["parent_netprofit"] < 0


def auc_of(rows: list[dict], key: str, sign: int = 1) -> float | None:
    usable = [dict(r, score=sign * r[key]) for r in rows if r.get(key) is not None]
    return auc(usable)


def line_table(t: dict) -> str:
    lift = "—" if t["lift"] in (None, float("inf")) else f"{t['lift']:.2f}"
    p = "—" if t["p"] is None else f"{t['p']:.4f}"
    return (f"弱组 {t['ev_weak']}/{t['n_weak']}（{pct(t['rate_weak'])}），非弱组 {t['ev_other']}/{t['n_other']}（{pct(t['rate_other'])}），"
            f"提升倍数 {lift}，单侧 p = {p}")


def main() -> None:
    panel = read(OUT / "panel.csv")
    for r in panel:
        r["score"] = float(r["score"])
        for k in ("weak", "hard", "soft", "y1"):
            r[k] = r[k] == "True"
    metrics = {}
    for day in DATES:
        for m in read(OUT / "snapshots" / day / "quarterly_metrics.csv"):
            metrics[(day, m["security_code"])] = m
    cache: dict = {}
    for r in panel:
        m = metrics.get((r["as_of"], r["security_code"]), {})
        r["debt_ratio"] = float(m["debt_ratio"]) if m.get("debt_ratio") not in (None, "") else None
        r["net_margin"] = float(m["net_margin"]) if m.get("net_margin") not in (None, "") else None
        loss = last_annual_loss(r["security_code"], r["as_of"], cache)
        r["prior_loss"] = None if loss is None else float(loss)

    lines = ["# 事件研究：事后分析", "",
             "以下检验在看到预注册结果（`docs/event_study_results.md`）**之后**设计，只作补充说明，不是预注册成绩。", ""]

    # 1. without subsidiary bankruptcies
    hard_ev = {(e["security_code"], e["notice_date"]) for e in read(OUT / "events_reviewed.csv") if e["include"] == "Y"}
    kept = hard_ev - SUBSIDIARY
    for r in panel:
        dates = [x.split(" ")[0] for x in r["hard_events"].split("；") if x]
        r["hard2"] = any((r["security_code"], d) in kept for d in dates)
        r["y1b"] = r["hard2"] or r["soft"]
    lines += ["## 1. 去掉 3 条控股子公司破产事件", "",
              "马钢 MG-VALDUNES、中南股份子公司、山东钢铁子公司的破产程序按预注册规则计入，但比母公司自身的信用事件弱。去掉后：", "",
              f"- 复合 Y1：{line_table(table(panel, 'y1b'))}", ""]

    # 2. beyond loss persistence
    have = [r for r in panel if r["prior_loss"] is not None]
    a_score, a_loss = auc(have), auc_of(have, "prior_loss")
    a_debt, a_margin = auc_of(have, "debt_ratio"), auc_of(have, "net_margin", -1)
    no_loss = [r for r in have if r["prior_loss"] == 0.0]
    lines += ["## 2. 评分是否只是“去年亏损，今年还亏”", "",
              f"同一批 {len(have)} 个企业×评估日上的 AUC（越接近 1 越能区分）：", "",
              "| 预测变量 | AUC |", "| --- | --- |",
              f"| 承压评分总分 | {a_score:.3f} |" if a_score is not None else "| 承压评分总分 | — |",
              f"| 评估日已公开的最近年报是否亏损（是/否） | {a_loss:.3f} |" if a_loss is not None else "| 最近年报是否亏损 | — |",
              f"| 资产负债率 | {a_debt:.3f} |" if a_debt is not None else "| 资产负债率 | — |",
              f"| 最近季报净利率（越低越差） | {a_margin:.3f} |" if a_margin is not None else "| 最近季报净利率 | — |", "",
              f"**最近年报没有亏损的 {len(no_loss)} 个企业×评估日**中：{line_table(table(no_loss))}。"
              f"总分 AUC = {auc(no_loss):.3f}。" if auc(no_loss) is not None else "", "",
              "**结论（照实）**：在以“年度大额亏损”为主的事件上，承压评分**不如**单一盈利指标——最近季报净利率的 AUC 更高，"
              "“最近年报是否亏损”也更高。这在机制上不意外：软事件就是“下一年大额亏损”，与当期净利率几乎是同一变量的延续。"
              "在最近年报没有亏损的企业中，评分仍有方向一致的区分（见上一行），但样本小、未达显著。"
              "因此对外只说“承压为弱的企业事后信用事件率明显更高（预注册通过）”，不说评分优于简单指标；"
              "评分的用处在于把杠杆、偿债、担保和市场信号放在一起给出可核对的理由，并作为传导路径的节点状态。"
              "不据此事后改权重：任何按本结果调整的评分只能称为“校准后”，且需新的样本检验。", ""]

    # 3. within-year AUC
    lines += ["## 3. 分年度的区分力", "", "| 评估日 | 发生 Y1 | AUC |", "| --- | --- | --- |"]
    for day in DATES:
        rows = [r for r in panel if r["as_of"] == day]
        a = auc(rows)
        lines.append(f"| {day} | {sum(r['y1'] for r in rows)}/{len(rows)} | {'—（无事件）' if a is None else f'{a:.3f}'} |")
    lines += ["", "2019–2021 年钢铁景气，窗口内几乎没有事件，这三年被判为“弱”的企业在 12 个月内都没有出事；其中安阳钢铁、八一钢铁、"
              "酒钢宏兴在 2022 年行业下行后发生了事件。结论是“承压为弱的企业在下行期更先出事”，不是“弱就一定在 12 个月内出事”。", ""]
    (ROOT / "docs" / "event_study_posthoc.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
