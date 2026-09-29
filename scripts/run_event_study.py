"""Run the pre-registered event study (docs/event_study_preregistration.md, section 5).

Inputs (all must exist; the review file must be complete and committed before this runs):
  data/event_study/events_reviewed.csv      hard events, include = Y/N for every row
  data/event_study/loss_events.csv          soft events (annual loss >= 5% of equity)
  data/event_study/snapshots/<date>/fragility.csv   historical scores (update_all.py --no-guarantee --out ...)

Writes data/event_study/panel.csv (one row per company x assessment date) and docs/event_study_results.md.

    python scripts/run_event_study.py
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import core_mills  # noqa: E402

OUT = ROOT / "data" / "event_study"
DATES = [f"{y}-04-30" for y in range(2019, 2026)]
OUT_OF_SAMPLE = {d for d in DATES if d < "2024-01-01"}   # v1 thresholds were calibrated on 2025-01-31 and live data
LIFT_BAR, P_BAR, AUC_BAR = 1.5, 0.05, 0.60
SEED, DRAWS = 20260929, 2000


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def plus_year(day: str) -> str:
    d = date.fromisoformat(day)
    return d.replace(year=d.year + 1).isoformat()


def fisher_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher exact p for [[a, b], [c, d]] (a = weak with event): P(X >= a) under the hypergeometric."""
    n1, n2, k = a + b, c + d, a + c
    total = comb(n1 + n2, k)
    return sum(comb(n1, x) * comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / total


def auc(rows: list[dict]) -> float | None:
    pos = [r["score"] for r in rows if r["y1"]]
    neg = [r["score"] for r in rows if not r["y1"]]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def cluster_ci(rows: list[dict]) -> tuple[float, float] | None:
    """95% interval of the AUC, resampling companies (all their dates together)."""
    by_company: dict[str, list[dict]] = {}
    for r in rows:
        by_company.setdefault(r["security_code"], []).append(r)
    codes = sorted(by_company)
    rng = random.Random(SEED)
    values = []
    for _ in range(DRAWS):
        sample = [r for c in (rng.choice(codes) for _ in codes) for r in by_company[c]]
        v = auc(sample)
        if v is not None:
            values.append(v)
    if len(values) < DRAWS // 2:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


def table(rows: list[dict], key: str = "y1") -> dict:
    weak = [r for r in rows if r["weak"]]
    other = [r for r in rows if not r["weak"]]
    a, c = sum(r[key] for r in weak), sum(r[key] for r in other)
    rw = a / len(weak) if weak else None
    ro = c / len(other) if other else None
    lift = (rw / ro) if rw is not None and ro else (float("inf") if rw else None)
    p = fisher_greater(a, len(weak) - a, c, len(other) - c) if weak and other else None
    return {"n_weak": len(weak), "ev_weak": a, "rate_weak": rw, "n_other": len(other), "ev_other": c, "rate_other": ro,
            "lift": lift, "p": p}


def pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def verdict(t: dict) -> str:
    if t["lift"] is None or t["lift"] < LIFT_BAR:
        return "未通过"
    return "通过" if t["p"] is not None and t["p"] < P_BAR else "方向一致但不显著"


def main() -> None:
    reviewed = OUT / "events_reviewed.csv"
    if not reviewed.exists():
        sys.exit("events_reviewed.csv is missing: review event_candidates.csv first (include = Y/N), commit it, then run.")
    hard = read(reviewed)
    if any(r.get("include", "").strip().upper() not in ("Y", "N") for r in hard):
        sys.exit("events_reviewed.csv has rows without include = Y/N; finish the review first.")
    hard = [r for r in hard if r["include"].strip().upper() == "Y"]
    soft = read(OUT / "loss_events.csv")
    mills = {m["security_code"]: m["security_name"] for m in core_mills()}
    from src.entity_resolver import groups_as_of

    panel, dropped = [], []
    for day in DATES:
        path = OUT / "snapshots" / day / "fragility.csv"
        if not path.exists():
            sys.exit(f"missing snapshot {path.relative_to(ROOT)}: run update_all.py --as-of {day} --offline --no-guarantee "
                     "--out data/event_study/snapshots")
        scores = {r["security_code"]: r for r in read(path)}
        end = plus_year(day)
        groups = groups_as_of(day)
        weak_by_group: dict[str, set[str]] = {}
        for code, r in scores.items():
            if r.get("tier") == "weak" and groups.get(code):
                weak_by_group.setdefault(groups[code], set()).add(code)
        for code, name in mills.items():
            r = scores.get(code)
            if not r or r.get("total_score") in (None, ""):
                dropped.append(f"{day} {name}")
                continue
            h = [e for e in hard if e["security_code"] == code and day < e["notice_date"] <= end]
            s = [e for e in soft if e["security_code"] == code and day < e["event_date"] <= end]
            g = groups.get(code, "")
            panel.append({"as_of": day, "security_code": code, "security_name": name, "score": float(r["total_score"]),
                          "tier": r["tier"], "weak": r["tier"] == "weak", "hard": bool(h), "soft": bool(s), "y1": bool(h or s),
                          "group": g, "group_peer_weak": bool(g and (weak_by_group.get(g, set()) - {code})),
                          "hard_events": "；".join(f"{e['notice_date']} {e['event_type']}" for e in h),
                          "soft_events": "；".join(f"{e['period'][:4]}年亏损{float(e['loss_to_equity']):.0%}" for e in s)})
    with (OUT / "panel.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(panel[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(panel)

    main_t, hard_t = table(panel), table(panel, "hard")
    a, ci = auc(panel), cluster_ci(panel)
    oos = [r for r in panel if r["as_of"] in OUT_OF_SAMPLE]
    oos_t = table(oos)
    lines = ["# 事件研究结果：承压评分能否事前区分信用事件", "",
             f"按 `docs/event_study_preregistration.md` 运行（{date.today().isoformat()}）。判定标准在运行前写定，结果照实报告。", "",
             "## 主检验（复合 Y1 = 硬事件或年度亏损 ≥ 净资产 5%）", "",
             "| 组 | 企业×评估日 | 发生 Y1 | 事件率 |", "| --- | --- | --- | --- |",
             f"| 弱 | {main_t['n_weak']} | {main_t['ev_weak']} | {pct(main_t['rate_weak'])} |",
             f"| 非弱 | {main_t['n_other']} | {main_t['ev_other']} | {pct(main_t['rate_other'])} |", "",
             f"提升倍数 {main_t['lift']:.2f}，单侧 Fisher p = {main_t['p']:.4f}。**判定：{verdict(main_t)}**"
             f"（标准：提升倍数 ≥ {LIFT_BAR} 且 p < {P_BAR}）。" if main_t["lift"] not in (None, float("inf")) and main_t["p"] is not None
             else f"提升倍数或 p 无法计算（{main_t}）。", "",
             "## 次要结果", "",
             f"1. 总分对 Y1 的 AUC = {a:.3f}" + (f"（按企业重抽样 95% 区间 {ci[0]:.3f}–{ci[1]:.3f}）" if ci else "") +
             f"；预期 ≥ {AUC_BAR}。" if a is not None else "1. AUC 无法计算。",
             f"2. 只看硬事件：弱组 {hard_t['ev_weak']}/{hard_t['n_weak']}（{pct(hard_t['rate_weak'])}），"
             f"非弱组 {hard_t['ev_other']}/{hard_t['n_other']}（{pct(hard_t['rate_other'])}）。事件少，只作描述。",
             f"3. 样本外（2019–2023 评估日）：弱组 {pct(oos_t['rate_weak'])}（{oos_t['ev_weak']}/{oos_t['n_weak']}），"
             f"非弱组 {pct(oos_t['rate_other'])}（{oos_t['ev_other']}/{oos_t['n_other']}），"
             f"提升倍数 {oos_t['lift']:.2f}，p = {oos_t['p']:.4f}。" if oos_t["lift"] not in (None, float("inf")) and oos_t["p"] is not None
             else f"3. 样本外无法计算（{oos_t}）。", "",
             "### 按评估日", "", "| 评估日 | 弱组事件率 | 非弱组事件率 |", "| --- | --- | --- |"]
    for day in DATES:
        t = table([r for r in panel if r["as_of"] == day])
        lines.append(f"| {day} | {pct(t['rate_weak'])}（{t['ev_weak']}/{t['n_weak']}） | {pct(t['rate_other'])}（{t['ev_other']}/{t['n_other']}） |")
    others = [r for r in panel if not r["weak"]]
    with_peer = [r for r in others if r["group_peer_weak"]]
    without = [r for r in others if not r["group_peer_weak"]]
    lines += ["", "### 探索：同集团另有上市成员为弱（只作描述）", "",
              f"非弱企业中，同集团有弱成员：{sum(r['y1'] for r in with_peer)}/{len(with_peer)}（{pct(sum(r['y1'] for r in with_peer) / len(with_peer) if with_peer else None)}）；"
              f"没有：{sum(r['y1'] for r in without)}/{len(without)}（{pct(sum(r['y1'] for r in without) / len(without) if without else None)}）。"
              "集团归属按 `groups_as_of`；2019–2021 年多次集团重组未全部录入历史表，只作参考。", "",
              "## 弱组中发生与未发生事件的企业", "", "| 评估日 | 企业 | 总分 | Y1 | 事件 |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['as_of']} | {r['security_name']} | {r['score']:.1f} | {'是' if r['y1'] else '否'} | "
              f"{'；'.join(x for x in (r['hard_events'], r['soft_events']) if x) or '—'} |" for r in panel if r["weak"]]
    lines += ["", "## 剔除", "", ("、".join(dropped) or "无") + "。", "",
              "明细：`data/event_study/panel.csv`。局限见预注册文件第 6 节。"]
    (ROOT / "docs" / "event_study_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:16]))
    print(f"\n-> docs/event_study_results.md, data/event_study/panel.csv ({len(panel)} rows)")


if __name__ == "__main__":
    main()
