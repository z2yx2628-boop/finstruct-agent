"""Does being reached by a disclosed-relation risk path add to a mill's own condition? (docs/history_graph_preregistration.md)

Exposure on each event-study date, from data/chain/hist/key_paths_<date>.csv (scripts/build_history_graph.py):
  E1 (primary)   the mill is reached, from a seed other than itself, by a key path whose steps UP TO that mill include a
                 guarantee (R1) or supply / related-trade (R2) step; industry-level (R4) paths are ignored.
  E2 (secondary) reached by any non-R4 key path from another seed (group-only routes included).
Outcome: Y1 of data/event_study/panel.csv (credit event within 12 months), frozen before this test was written.
Primary statistic: events among exposed mills minus their expected number, stratified by the mill's own tier (weak /
not weak); one-sided permutation p (exposure shuffled within strata, 10 000 draws, seed 20260930).

    python scripts/run_incremental_test.py     # refuses to run while the pre-registration is not committed
"""
from __future__ import annotations

import csv
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PREREG = ROOT / "docs" / "history_graph_preregistration.md"
CHAIN = ROOT / "data" / "chain" / "hist"
ES = ROOT / "data" / "event_study"
PRIMARY_DATES = [f"{y}-04-30" for y in range(2020, 2026)]
ALL_DATES = ["2019-04-30"] + PRIMARY_DATES
SUBSIDIARY = {("600808", "2023-11-15"), ("000717", "2019-07-03"), ("600022", "2025-11-21")}
SEED, DRAWS, ALPHA, MIN_COVERAGE, MIN_EXPOSED = 20260930, 10_000, 0.05, 0.5, 10


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def reached(paths: list[dict], codes: set[str], primary: bool = True) -> set[str]:
    """Mills reached from another seed. Primary: a guarantee (R1) or supply (R2) step on the way to that mill."""
    out = set()
    for p in paths:
        rules = [r for r in (p.get("rules") or "").split("+") if r]
        nodes = [n for n in (p.get("nodes") or "").split(">") if n]
        if not nodes or "R4" in rules or len(nodes) != len(rules) + 1:
            continue
        seed = nodes[0]
        for k, node in enumerate(nodes[1:]):
            if node in codes and node != seed and (not primary or {"R1", "R2"} & set(rules[:k + 1])):
                out.add(node)
    return out


def stratified_stat(rows: list[dict], expo: str, outcome: str, stratum: str) -> float:
    s = 0.0
    for key in {r[stratum] for r in rows}:
        group = [r for r in rows if r[stratum] == key]
        rate = sum(r[outcome] for r in group) / len(group)
        s += sum(r[outcome] - rate for r in group if r[expo])
    return s


def permutation_p(rows: list[dict], expo: str, outcome: str, stratum: str, draws: int = DRAWS, seed: int = SEED) -> tuple[float, float]:
    observed = stratified_stat(rows, expo, outcome, stratum)
    rng, hits = random.Random(seed), 0
    groups = {}
    for r in rows:
        groups.setdefault(r[stratum], []).append(r)
    for _ in range(draws):
        s = 0.0
        for group in groups.values():
            labels = [r[expo] for r in group]
            rng.shuffle(labels)
            rate = sum(r[outcome] for r in group) / len(group)
            s += sum(r[outcome] - rate for r, e in zip(group, labels) if e)
        hits += s >= observed - 1e-12
    return observed, (1 + hits) / (1 + draws)


def auc(scores: list[float], y: list[bool]) -> float | None:
    pos = [s for s, t in zip(scores, y) if t]
    neg = [s for s, t in zip(scores, y) if not t]
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def logistic(x: list[list[float]], y: list[bool], ridge: float = 1e-2, steps: int = 50) -> list[float]:
    """Newton-Raphson logistic regression with a small ridge; x rows without the intercept."""
    k = len(x[0]) + 1
    b = [0.0] * k
    for _ in range(steps):
        g, h = [0.0] * k, [[0.0] * k for _ in range(k)]
        for row, t in zip(x, y):
            z = [1.0] + row
            p = 1 / (1 + math.exp(-max(-30, min(30, sum(bi * zi for bi, zi in zip(b, z))))))
            for i in range(k):
                g[i] += (t - p) * z[i]
                for j in range(k):
                    h[i][j] += p * (1 - p) * z[i] * z[j]
        for i in range(1, k):
            g[i] -= ridge * b[i]
            h[i][i] += ridge
        step = solve(h, g)
        b = [bi + si for bi, si in zip(b, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return b


def solve(a: list[list[float]], v: list[float]) -> list[float]:
    n = len(v)
    m = [row[:] + [v[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def leave_one_year_out(rows: list[dict], features: list[str]) -> float | None:
    preds, ys = [], []
    for day in sorted({r["as_of"] for r in rows}):
        train = [r for r in rows if r["as_of"] != day]
        test = [r for r in rows if r["as_of"] == day]
        if not test or not any(r["y1"] for r in train):
            continue
        mean = {f: sum(r[f] for r in train) / len(train) for f in features}
        sd = {f: (math.sqrt(sum((r[f] - mean[f]) ** 2 for r in train) / len(train)) or 1.0) for f in features}
        z = lambda r: [(r[f] - mean[f]) / sd[f] for f in features]  # noqa: E731
        b = logistic([z(r) for r in train], [r["y1"] for r in train])
        preds += [sum(bi * zi for bi, zi in zip(b, [1.0] + z(r))) for r in test]
        ys += [r["y1"] for r in test]
    return auc(preds, ys)


def committed() -> bool:
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(PREREG), str(Path(__file__))],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        logged = subprocess.run(["git", "log", "-1", "--format=%H", "--", str(PREREG)],
                                cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return False
    return bool(logged) and not dirty


def load_panel() -> list[dict]:
    panel = read(ES / "panel.csv")
    hard = {(e["security_code"], e["notice_date"]) for e in read(ES / "events_reviewed.csv") if e["include"] == "Y"}
    metrics = {(d, m["security_code"]): m for d in ALL_DATES for m in read(ES / "snapshots" / d / "quarterly_metrics.csv")}
    for r in panel:
        r["score"] = float(r["score"])
        for k in ("weak", "hard", "soft", "y1"):
            r[k] = r[k] == "True"
        dates = [x.split(" ")[0] for x in (r.get("hard_events") or "").split("；") if x]
        r["y1b"] = any((r["security_code"], d) in hard - SUBSIDIARY for d in dates) or r["soft"]
        m = metrics.get((r["as_of"], r["security_code"]), {})
        r["net_margin"] = float(m["net_margin"]) if m.get("net_margin") not in (None, "") else None
    return panel


def main() -> None:
    if not committed():
        sys.exit("预登记文件或本脚本还没有提交（或有未提交的修改）。先 git commit 并 push，再运行。")
    panel = load_panel()
    codes = {r["security_code"] for r in panel}
    for r in panel:
        paths = read(CHAIN / f"key_paths_{r['as_of']}.csv")
        if paths and "nodes" not in paths[0]:
            sys.exit(f"key_paths_{r['as_of']}.csv 没有 nodes 列：先运行 scripts/build_history_graph.py")
        r["e1"] = r["security_code"] in reached(paths, codes, True)
        r["e2"] = r["security_code"] in reached(paths, codes, False)
        r["tier_year"] = f"{r['weak']}|{r['as_of']}"
    cov = {r["as_of"]: float(r["share"]) for r in read(CHAIN / "coverage.csv")}
    rows = [r for r in panel if r["as_of"] in PRIMARY_DATES]
    mean_cov = sum(cov.get(d, 0) for d in PRIMARY_DATES) / len(PRIMARY_DATES)
    n_exp = sum(r["e1"] for r in rows)
    informative = mean_cov >= MIN_COVERAGE and n_exp >= MIN_EXPOSED

    def rate(sub: list[dict], key: str = "y1") -> str:
        return f"{sum(r[key] for r in sub)}/{len(sub)}（{sum(r[key] for r in sub) / len(sub):.1%}）" if sub else "—"

    out = ["", f"## 结果（{__import__('datetime').date.today()} 运行；结果变量此前已知，属非盲检验）", "",
           f"图谱覆盖：2020–2025 年各评估日平均 {mean_cov:.0%} 的核心钢厂至少有一条生效的披露关系（`data/chain/hist/coverage.csv`）；"
           f"被 E1 波及的企业×评估日 {n_exp} 个。", ""]
    if not informative:
        out += [f"**覆盖不足（门槛：平均覆盖 ≥ {MIN_COVERAGE:.0%} 且被波及 ≥ {MIN_EXPOSED} 个），按预登记不作判定。**", ""]
    s, p = permutation_p(rows, "e1", "y1", "weak")
    verdict = ("通过" if p < ALPHA and s > 0 else "方向一致但未显著" if s > 0 else "未通过") if informative else "不判定"
    out += ["| 检验 | 结果 | 判定（α = 0.05，单侧） |", "| --- | --- | --- |",
            f"| 主检验：E1 波及者的 Y1 超出按自身档位分层的预期 | 超出 {s:+.2f} 个事件；置换 p = {p:.4f} | {verdict} |", "",
            "| 分层 | 被 E1 波及 | 未被波及 |", "| --- | --- | --- |"]
    for weak in (True, False):
        sub = [r for r in rows if r["weak"] == weak]
        out.append(f"| 自身{'弱' if weak else '非弱'} | {rate([r for r in sub if r['e1']])} | {rate([r for r in sub if not r['e1']])} |")
    s2, p2 = permutation_p(rows, "e2", "y1", "weak")
    s3, p3 = permutation_p(rows, "e1", "y1b", "weak")
    s4, p4 = permutation_p(rows, "e1", "y1", "tier_year")
    with_2019 = [r for r in panel if r["as_of"] in ALL_DATES]
    s5, p5 = permutation_p(with_2019, "e1", "y1", "weak")
    have = [r for r in rows if r["net_margin"] is not None]
    for r in have:
        r["e1f"] = float(r["e1"])
        r["neg_margin"] = -r["net_margin"]
    out += ["", "只报告、不作判定：", "",
            f"- E2（含只经集团关系的路线）：超出 {s2:+.2f}，p = {p2:.4f}",
            f"- 去掉 3 条控股子公司破产事件：超出 {s3:+.2f}，p = {p3:.4f}",
            f"- 按“自身档位 × 评估日”分层：超出 {s4:+.2f}，p = {p4:.4f}",
            f"- 加入 2019-04-30（该日缺 2018 年公告的关系）：超出 {s5:+.2f}，p = {p5:.4f}",
            f"- 逐年留出的逻辑回归 AUC（{len(have)} 个企业×评估日）：只用净利率 {leave_one_year_out(have, ['neg_margin']) or float('nan'):.3f}；"
            f"净利率 + 承压评分 {leave_one_year_out(have, ['neg_margin', 'score']) or float('nan'):.3f}；"
            f"再加 E1 {leave_one_year_out(have, ['neg_margin', 'score', 'e1f']) or float('nan'):.3f}",
            "- 明细：`data/chain/hist/incremental_panel.csv`"]
    with (CHAIN / "incremental_panel.csv").open("w", encoding="utf-8", newline="") as f:
        keys = ["as_of", "security_code", "security_name", "weak", "score", "net_margin", "e1", "e2", "y1", "y1b"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(panel)
    with PREREG.open("a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
