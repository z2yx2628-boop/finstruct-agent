"""临时承压评分 for a listed company outside the scored universe (图谱外企业), computed in memory:
fetch its quarterly summary and prices (network), then score it AGAINST the 24 core mills of the latest
snapshot on or before the evaluation date, exactly like `update_all.py --extra`. Nothing is written to disk.
The result is labelled 临时 / 图谱外 everywhere it is shown; it never enters a snapshot or the ranking."""
from __future__ import annotations

import csv
import io

from src.entity_resolver import ROOT
from src.fragility import score
from src.fragility_view import _num
from src.market import market_metrics
from src.quarterly import latest_public_period, parse_abstract

SNAP = ROOT / "data" / "snapshots"
PRICE_START = "20190101"


def _frame_rows(frame) -> list[list[str]]:
    buf = io.StringIO()
    frame.to_csv(buf, index=False)
    return list(csv.reader(io.StringIO(buf.getvalue())))


def fetch(code: str, as_of: str) -> tuple[dict, list[tuple[str, float]]]:
    import akshare as ak
    periods = parse_abstract(_frame_rows(ak.stock_financial_abstract(symbol=code)))
    end = as_of.replace("-", "")
    try:
        px = ak.stock_zh_a_daily(symbol=("sh" if code.startswith("6") else "sz") + code, start_date=PRICE_START,
                                 end_date=end, adjust="qfq")[["date", "close"]]
    except Exception:  # noqa: BLE001 - fall back to the second source, as update_all does
        px = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=PRICE_START, end_date=end,
                                adjust="qfq").rename(columns={"日期": "date", "收盘": "close"})[["date", "close"]]
    prices = [(str(d)[:10], float(c)) for d, c in zip(px["date"], px["close"]) if c == c]
    return periods, prices


def peers(as_of: str) -> tuple[str | None, list[dict]]:
    snaps = sorted(p for p in SNAP.glob("*") if (p / "fragility.csv").exists() and p.name <= as_of)
    if not snaps:
        return None, []
    folder = snaps[-1]
    with (folder / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        core = {r["security_code"] for r in csv.DictReader(f) if r.get("peer_group") == "core"}
    with (folder / "quarterly_metrics.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = [_num(r) for r in csv.DictReader(f) if r["security_code"] in core]
    return folder.name, rows


def score_one(code: str, name: str, as_of: str, periods: dict | None = None,
              prices: list[tuple[str, float]] | None = None) -> dict:
    """The company's fragility row (tier, total_score, reasons) scored against the core mills; peer_group='adhoc'."""
    if periods is None or prices is None:
        periods, prices = fetch(code, as_of)
    snap, core = peers(as_of)
    if not core:
        raise ValueError("评估日之前没有核心钢厂的承压快照，无法作为参照。")
    period = latest_public_period(as_of)
    row = {"security_code": code, "security_name": name, **dict(periods.get(period) or {"period": period}),
           **market_metrics(prices, as_of)}
    values = sorted(r["ret_60d"] for r in core if isinstance(r.get("ret_60d"), float))
    median = values[len(values) // 2] if values else None
    row["excess_ret_60d"] = None if median is None or row.get("ret_60d") is None else row["ret_60d"] - median
    result = next(r for r in score(core, [], as_of, period, extra=[row]) if r["security_code"] == code)
    return {**result, "peer_group": "adhoc", "reference_snapshot": snap, "equity": row.get("equity")}
