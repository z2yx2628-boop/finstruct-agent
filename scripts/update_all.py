"""One command to refresh direction 2: quarterly financials, annual statements, market data,
then recompute the fragility score and save a dated snapshot.

    python scripts/update_all.py                      # today, 24 core mills, with network
    python scripts/update_all.py --offline            # recompute from cached data only
    python scripts/update_all.py --as-of 2025-01-31 --offline   # point-in-time (backtest)
    python scripts/update_all.py --signals data/chain/<run>/signals.csv
    python scripts/update_all.py 000708 000825        # re-fetch only these; scoring still uses all peers

Writes data/snapshots/<as_of>/fragility.csv, quarterly_metrics.csv and changes.md.
Snapshots are never overwritten by later runs of another date, so any past judgement can be
re-read; frozen test results and backtests do not depend on data fetched later.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import RAW, main as fetch_statements, select  # noqa: E402
from src.financial_indicators import annual_rows  # noqa: E402
from src.fragility import TIER_LABEL, score  # noqa: E402
from src.market import add_excess_return, market_metrics  # noqa: E402
from src.quarterly import latest_public_period, parse_abstract  # noqa: E402

QDIR = ROOT / "data" / "external" / "financials" / "quarterly"
MDIR = ROOT / "data" / "external" / "market"
SNAP = ROOT / "data" / "snapshots"
PRICE_START = "20190101"  # long enough for 2020+ backtests


def read_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def refresh_abstract(code: str) -> str:
    import akshare as ak

    frame = ak.stock_financial_abstract(symbol=code)
    QDIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(QDIR / f"{code}_abstract.csv", index=False, encoding="utf-8-sig")
    return "ok"


def refresh_prices(code: str, as_of: str) -> str:
    import akshare as ak

    end = as_of.replace("-", "")
    symbol = ("sh" if code.startswith("6") else "sz") + code
    try:
        frame = ak.stock_zh_a_daily(symbol=symbol, start_date=PRICE_START, end_date=end, adjust="qfq")
        frame = frame[["date", "close"]]
    except Exception:
        frame = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=PRICE_START, end_date=end, adjust="qfq")
        frame = frame.rename(columns={"日期": "date", "收盘": "close"})[["date", "close"]]
    MDIR.mkdir(parents=True, exist_ok=True)
    frame.assign(date=frame["date"].astype(str).str[:10]).to_csv(MDIR / f"{code}.csv", index=False)
    return "ok"


def prices(code: str) -> list[tuple[str, float]]:
    path = MDIR / f"{code}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [(r["date"], float(r["close"])) for r in csv.DictReader(f) if r.get("close")]


def needs_new_annual(code: str, periods: dict) -> bool:
    """True when the abstract shows an annual report the downloaded statements do not have."""
    latest_annual = max((int(p[:4]) for p in periods if p.endswith("1231")), default=0)
    balance = RAW / f"{code}_balance.csv"
    if not balance.exists():
        return True
    with balance.open(encoding="utf-8-sig", newline="") as f:
        have = max(annual_rows(csv.DictReader(f)), default=0)
    return latest_annual > have


def load_signals(path: str | None) -> list[dict]:
    candidates = [path] if path else sorted(glob.glob(str(ROOT / "data" / "chain" / "*" / "signals.csv")))
    out = []
    for p in candidates:
        if p and Path(p).exists():
            with open(p, encoding="utf-8", newline="") as f:
                out += list(csv.DictReader(f))
    return out


def previous_snapshot(as_of: str) -> dict[str, dict]:
    older = sorted(d for d in SNAP.glob("*") if d.is_dir() and d.name < as_of and (d / "fragility.csv").exists())
    if not older:
        return {}
    with (older[-1] / "fragility.csv").open(encoding="utf-8", newline="") as f:
        return {r["security_code"]: r for r in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--signals")
    args = ap.parse_args()
    as_of = args.as_of
    mills = select([], False)                      # the peer group is always the full core set
    to_fetch = select(args.codes, False) if args.codes else mills
    failures = []

    if not args.offline:
        for m in to_fetch:
            code, name = m["security_code"], m["security_name"]
            for label, job in (("quarterly", lambda: refresh_abstract(code)), ("prices", lambda: refresh_prices(code, as_of))):
                for attempt in range(3):
                    try:
                        job()
                        break
                    except Exception as error:
                        if attempt == 2:
                            failures.append(f"{code} {name} {label}: {type(error).__name__}: {str(error)[:80]}")
                        time.sleep(5 * (attempt + 1))
                time.sleep(1.5)  # the sources start refusing after many quick requests
            print(f"[updated] {code} {name}")

    missing = [m["security_name"] for m in mills if not (QDIR / f"{m['security_code']}_abstract.csv").exists()]
    rows, new_annual = [], []
    period = latest_public_period(as_of)
    for m in mills:
        code = m["security_code"]
        path = QDIR / f"{code}_abstract.csv"
        periods = parse_abstract(read_rows(path)) if path.exists() else {}
        if periods and needs_new_annual(code, periods):
            new_annual.append(code)
        metrics = dict(periods.get(period) or {"period": period})
        metrics.update(market_metrics(prices(code), as_of))
        rows.append({"security_code": code, "security_name": m["security_name"], **metrics})
    add_excess_return(rows)

    if new_annual and not args.offline:
        print(f"new annual reports for {', '.join(new_annual)}: refreshing full statements")
        fetch_statements(new_annual, refresh=True)
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_financial_indicators.py")], check=False)

    results = score(rows, load_signals(args.signals), as_of, period)
    out = SNAP / as_of
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("quarterly_metrics.csv", rows), ("fragility.csv", results)):
        fields = list(dict.fromkeys(k for r in data for k in r))
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(data)

    prev = previous_snapshot(as_of)
    lines = [f"# 承压评分 {as_of}（财报期 {period}，行情截至 {max((r.get('last_trade_date') or '') for r in rows)}）", ""]
    changed = [r for r in results if r["security_code"] in prev and prev[r["security_code"]]["tier"] != r["tier"]]
    lines.append(f"## 等级变化（对比 {sorted(d.name for d in SNAP.glob('*') if d.name < as_of)[-1] if prev else '无上期'}）")
    lines += [f"- {r['security_name']}：{TIER_LABEL.get(prev[r['security_code']]['tier'], '-')} → {r['tier_label']}；{r['reasons']}"
              for r in changed] or ["- 无"]
    lines += ["", "## 当前弱档企业"]
    lines += [f"- {r['security_name']}（{r['total_score']}分）：{r['reasons']}" for r in results if r["tier"] == "weak"] or ["- 无"]
    if failures:
        lines += ["", "## 更新失败（使用缓存数据）", *[f"- {x}" for x in failures]]
    (out / "changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = {TIER_LABEL[t]: sum(1 for r in results if r["tier"] == t) for t in TIER_LABEL}
    print(f"\nas of {as_of}: period {period}; tiers {counts}; tier changes {len(changed)}")
    print(f"snapshot -> {out.relative_to(ROOT)}")
    if failures:
        print("FAILED (cached data used):", *failures, sep="\n  ")
    if missing:
        print("no quarterly data at all for:", "、".join(missing), "-> rerun with their codes")


if __name__ == "__main__":
    main()
