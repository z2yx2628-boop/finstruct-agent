"""Shock-transmission test, pre-registered in docs/shock_transmission_preregistration.md.

T1 upstream cost : iron-ore futures jump (intraday) -> mills that BUY more of their ore (1 - self-supplied share, annual
                   report table 铁矿石供应情况) should do worse than the other mills when ore rises, better when it falls.
T2 exports       : USD/CNY central parity moves -> mills with a larger overseas revenue share (src.policy_shock.overseas_share,
                   the system's own exposure figure) should do better than the other mills when the yuan weakens.

Outcome: a mill's log return on the event day and the next day, minus the equal-weighted mean of the tested mills.
Per event: z = expected sign x Spearman(exposure, relative return). Statistic: mean z over events, compared with the
same statistic on random non-event days (permutation, 10 000 draws, seed 20260930).

    python scripts/run_shock_study.py              # refuses to run while the pre-registration is not committed
    python scripts/run_shock_study.py --self-test  # synthetic data only; reads no stock price
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

PREREG = ROOT / "docs" / "shock_transmission_preregistration.md"
MARKET = ROOT / "data" / "external" / "market"
PRICES = ROOT / "data" / "external" / "prices"
ORE = ROOT / "data" / "reference" / "annual_iron_ore_supply.csv"
FX = PRICES / "USDCNY_parity.csv"
OUT = ROOT / "data" / "shock_study"
SEED, DRAWS, GAP, ALPHA = 20260930, 10_000, 10, 0.025
JUMP = 0.11            # a daily move beyond the 10% price limit is an ex-rights jump in unadjusted closes: drop that mill
END = "2026-09-29"
TESTS = {
    "T1": {"name": "铁矿石价格冲击 × 外购铁矿石比例", "start": "2023-05-01", "min_firms": 8, "sign": -1},
    "T2": {"name": "人民币汇率冲击 × 境外收入占比", "start": "2020-05-01", "min_firms": 10, "sign": 1},
}
ORE_THRESHOLD = 0.03   # |ln(close/open)| of the iron-ore main contract
FX_TOP = 0.05          # the largest 5% of |daily change| of the central parity in the test period


# ---------- pure functions (unit-tested) ----------

def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return sxy / (sx * sy) if sx and sy else None


def daily_returns(close: dict[str, float], calendar: list[str]) -> dict[str, float | None]:
    """Log return on each calendar day whose previous calendar day also has a close; None = ex-rights jump."""
    out = {}
    for prev, day in zip(calendar, calendar[1:]):
        if prev in close and day in close and close[prev] > 0 and close[day] > 0:
            r = math.log(close[day] / close[prev])
            out[day] = None if abs(r) > JUMP else r
    return out


def relative_window(returns: dict[str, dict], calendar: list[str], day: str, firms: list[str],
                    window: tuple[int, int] = (0, 1)) -> dict[str, float]:
    """Sum over the window of (firm return - mean return of the firms valid on every day of the window)."""
    idx = {d: i for i, d in enumerate(calendar)}
    if day not in idx or idx[day] + window[1] >= len(calendar):
        return {}
    days = [calendar[idx[day] + k] for k in range(window[0], window[1] + 1)]
    valid = [f for f in firms if all(returns.get(f, {}).get(d) is not None for d in days)]
    if not valid:
        return {}
    out = {f: 0.0 for f in valid}
    for d in days:
        mean = sum(returns[f][d] for f in valid) / len(valid)
        for f in valid:
            out[f] += returns[f][d] - mean
    return out


def select_events(shock: dict[str, float], threshold: float, calendar: list[str], gap: int = GAP) -> list[tuple[str, float]]:
    """Days with |shock| >= threshold; within `gap` trading days of a larger shock only the larger one is kept."""
    idx = {d: i for i, d in enumerate(calendar)}
    big = sorted(((d, v) for d, v in shock.items() if abs(v) >= threshold and d in idx), key=lambda t: -abs(t[1]))
    kept = []
    for d, v in big:
        if all(abs(idx[d] - idx[k]) > gap for k, _ in kept):
            kept.append((d, v))
    return sorted(kept)


def placebo_days(shock: dict[str, float], threshold: float, events: list[tuple[str, float]], calendar: list[str],
                 gap: int = GAP) -> list[str]:
    idx = {d: i for i, d in enumerate(calendar)}
    near = {calendar[i] for d, _ in events for i in range(max(0, idx[d] - gap), min(len(calendar), idx[d] + gap + 1))}
    return [d for d, v in sorted(shock.items()) if d in idx and d not in near and abs(v) < threshold and v != 0]


def event_z(exposure: dict[str, float], relative: dict[str, float], sign: int, min_firms: int) -> tuple[float | None, int]:
    firms = sorted(set(exposure) & set(relative))
    if len(firms) < min_firms:
        return None, len(firms)
    rho = spearman([exposure[f] for f in firms], [relative[f] for f in firms])
    return (None if rho is None else sign * rho), len(firms)


def permutation_p(observed: float, pool: list[float], n: int, draws: int = DRAWS, seed: int = SEED) -> float:
    rng = random.Random(seed)
    hits = sum(sum(rng.sample(pool, n)) / n >= observed for _ in range(draws))
    return (1 + hits) / (1 + draws)


def verdict(mean_z: float, p: float) -> str:
    if p < ALPHA and mean_z > 0:
        return "通过"
    return "方向一致但未显著" if mean_z > 0 else "未通过"


# ---------- data ----------

def core_mills() -> list[dict]:
    from scripts.fetch_financials import core_mills as mills
    return mills()


def stock_close(code: str) -> dict[str, float]:
    return {r["date"]: float(r["close"]) for r in read(MARKET / f"{code}.csv") if r.get("close")}


def ore_intraday() -> dict[str, float]:
    out = {}
    for r in read(PRICES / "I0.csv"):
        try:
            o, c = float(r["open"]), float(r["close"])
        except (TypeError, ValueError):
            continue
        if o > 0 and c > 0:
            out[r["date"]] = math.log(c / o)
    return out


def ore_exposure(code: str, as_of: str, kind: str = "purchased") -> float | None:
    """purchased = 1 - self-supplied tonnes / total tonnes; import = imported tonnes / total (report only)."""
    from src.policy_shock import usable_from
    rows = [r for r in read(ORE) if r["company_id"] == code and r["check"] == "ok"
            and usable_from(f"{r['fy']}-12-31") <= as_of and r.get("total_t") not in (None, "", "0")]
    if not rows:
        return None
    r = max(rows, key=lambda r: r["fy"])
    total = float(r["total_t"])
    if total <= 0:
        return None
    if kind == "import":
        return float(r["import_t"] or 0) / total
    return 1 - float(r["self_t"] or 0) / total


def overseas_exposure(code: str, as_of: str) -> float | None:
    from src.policy_shock import overseas_share
    got = overseas_share(code, as_of)
    return got["share"] if got else None


def fx_parity() -> tuple[dict[str, float], str]:
    """USD/CNY central parity (yuan per dollar). Cached in data/external/prices/USDCNY_parity.csv."""
    if not FX.exists():
        import akshare as ak
        rows, source = [], ""
        try:
            df = ak.currency_boc_safe()
            col = next(c for c in df.columns if "美元" in str(c))
            rows = [(str(d)[:10], float(v) / 100) for d, v in zip(df[df.columns[0]], df[col]) if v == v and v]
            source = f"akshare {ak.__version__} currency_boc_safe（国家外汇管理局 人民币汇率中间价，美元）"
        except Exception as error:  # the pre-registered fallback
            print(f"  中间价获取失败（{type(error).__name__}），按预登记改用离岸人民币 USDCNH 收盘价")
            df = ak.forex_hist_em(symbol="USDCNH")
            col = next(c for c in df.columns if "收盘" in str(c) or "最新" in str(c))
            rows = [(str(d)[:10], float(v)) for d, v in zip(df[df.columns[0]], df[col]) if v == v and v]
            source = f"akshare {ak.__version__} forex_hist_em USDCNH（离岸人民币收盘价，预登记的备用来源）"
        with FX.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["date", "usdcny", "source"])
            w.writerows((d, v, source) for d, v in sorted(rows))
    rows = read(FX)
    return {r["date"]: float(r["usdcny"]) for r in rows}, (rows[0]["source"] if rows else "")


def fx_changes(parity: dict[str, float], calendar: list[str]) -> dict[str, float]:
    out = {}
    for prev, day in zip(calendar, calendar[1:]):
        if prev in parity and day in parity and parity[prev] > 0:
            out[day] = math.log(parity[day] / parity[prev])
    return out


# ---------- run ----------

def committed() -> bool:
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(PREREG), str(Path(__file__))],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        logged = subprocess.run(["git", "log", "-1", "--format=%H %ci", "--", str(PREREG)],
                                cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return False
    return bool(logged) and not dirty


def run_test(key: str, shock: dict[str, float], threshold: float, exposure, returns: dict, calendar: list[str],
             mills: list[str]) -> dict:
    spec = TESTS[key]
    period = [d for d in calendar if spec["start"] <= d <= END]
    shock = {d: v for d, v in shock.items() if spec["start"] <= d <= END}
    events = select_events(shock, threshold, period)
    rows, zs = [], []
    for day, value in events:
        x = {m: v for m in mills if (v := exposure(m, day)) is not None}
        sign = spec["sign"] * (1 if value > 0 else -1)
        rel = relative_window(returns, calendar, day, sorted(x))
        z, n = event_z(x, rel, sign, spec["min_firms"])
        rel0 = relative_window(returns, calendar, day, sorted(x), (0, 0))
        z0, _ = event_z(x, rel0, sign, spec["min_firms"])
        rows.append({"test": key, "date": day, "shock": round(value, 5), "firms": n,
                     "z": "" if z is None else round(z, 4), "z_day0": "" if z0 is None else round(z0, 4)})
        if z is not None:
            zs.append(z)
    pool = []
    for day in placebo_days(shock, threshold, events, period):
        x = {m: v for m in mills if (v := exposure(m, day)) is not None}
        sign = spec["sign"] * (1 if shock[day] > 0 else -1)
        z, _ = event_z(x, relative_window(returns, calendar, day, sorted(x)), sign, spec["min_firms"])
        if z is not None:
            pool.append(z)
    mean_z = sum(zs) / len(zs) if zs else float("nan")
    p = permutation_p(mean_z, pool, len(zs)) if zs and len(pool) >= len(zs) else float("nan")
    with (OUT / f"events_{key}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["test"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    z0s = [float(r["z_day0"]) for r in rows if r["z_day0"] != ""]
    return {"key": key, "events": len(events), "used": len(zs), "mean_z": mean_z,
            "share_pos": sum(z > 0 for z in zs) / len(zs) if zs else float("nan"), "p": p, "pool": len(pool),
            "mean_z0": sum(z0s) / len(z0s) if z0s else float("nan"), "threshold": threshold}


def main() -> None:
    if "--self-test" in sys.argv:
        return self_test()
    if not committed():
        sys.exit("预登记文件或本脚本还没有提交（或有未提交的修改）。先 git commit 并 push，再运行。")
    OUT.mkdir(parents=True, exist_ok=True)
    mills = [m["security_code"] for m in core_mills()]
    closes = {m: stock_close(m) for m in mills}
    calendar = sorted({d for c in closes.values() for d in c if d <= END})
    returns = {m: daily_returns(c, calendar) for m, c in closes.items()}

    ore = ore_intraday()
    t1 = run_test("T1", ore, ORE_THRESHOLD, ore_exposure, returns, calendar, mills)
    t1_import = run_test("T1", ore, ORE_THRESHOLD, lambda c, d: ore_exposure(c, d, "import"), returns, calendar, mills)
    parity, fx_source = fx_parity()
    changes = fx_changes(parity, calendar)
    period = sorted(abs(v) for d, v in changes.items() if TESTS["T2"]["start"] <= d <= END)
    fx_threshold = period[int(len(period) * (1 - FX_TOP))] if period else float("inf")
    t2 = run_test("T2", changes, fx_threshold, overseas_exposure, returns, calendar, mills)

    def line(t: dict, label: str) -> str:
        return (f"| {label} | {t['events']} 个冲击（可用 {t['used']}） | 平均 z = {t['mean_z']:.3f}；z>0 占 {t['share_pos']:.0%}；"
                f"置换 p = {t['p']:.4f}（安慰剂日 {t['pool']} 个） | {verdict(t['mean_z'], t['p'])} |")
    out = ["", f"## 结果（{__import__('datetime').date.today()} 运行，按上面写定的标准判定）", "",
           f"汇率数据来源：{fx_source}；T2 阈值（前 5% 的 |日变动|）= {fx_threshold:.5f}。", "",
           "| 编号 | 冲击 | 结果 | 判定（α = 0.025，单侧） |", "| --- | --- | --- | --- |",
           line(t1, "T1 铁矿石 × 外购比例"), line(t2, "T2 汇率 × 境外收入占比"), "",
           "只报告、不作判定：", "",
           f"- T1 改用进口比例（网页显示的口径）：平均 z = {t1_import['mean_z']:.3f}，置换 p = {t1_import['p']:.4f}",
           f"- 只看冲击当天（窗口 [0,0]）：T1 平均 z = {t1['mean_z0']:.3f}；T2 平均 z = {t2['mean_z0']:.3f}",
           "- 每个冲击的明细：`data/shock_study/events_T1.csv`、`events_T2.csv`（T1 文件为外购比例口径）"]
    # the import-share run overwrote events_T1.csv last; rerun the primary so the file matches the primary result
    run_test("T1", ore, ORE_THRESHOLD, ore_exposure, returns, calendar, mills)
    with PREREG.open("a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


def self_test() -> None:
    """Synthetic market where exposure truly drives the reaction: T1-style test must pass; with no effect it must not."""
    rng = random.Random(1)
    calendar = [f"2024-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    mills = [f"M{i:02d}" for i in range(14)]
    expo = {m: i / 13 for i, m in enumerate(mills)}
    shock = {d: rng.gauss(0, 0.012) for d in calendar}
    for effect in (0.5, 0.0):
        returns = {m: {d: -effect * expo[m] * shock[d] + rng.gauss(0, 0.004) for d in calendar} for m in mills}
        events = select_events(shock, 0.025, calendar)
        zs = [event_z(expo, relative_window(returns, calendar, d, mills), -1 if v > 0 else 1, 8)[0] for d, v in events]
        pool = [event_z(expo, relative_window(returns, calendar, d, mills), -1 if shock[d] > 0 else 1, 8)[0]
                for d in placebo_days(shock, 0.025, events, calendar)]
        zs, pool = [z for z in zs if z is not None], [z for z in pool if z is not None]
        mean = sum(zs) / len(zs)
        print(f"effect {effect}: {len(zs)} events, mean z {mean:.3f}, p {permutation_p(mean, pool, len(zs), 2000):.4f}")


if __name__ == "__main__":
    main()
