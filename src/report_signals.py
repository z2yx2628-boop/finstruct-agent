"""Financial-report signals (财报异常信号) for one company at an evaluation date.

Rules only, from the Sina financial abstract already used by the fragility score
(data/external/financials/quarterly/<code>_abstract.csv) and the cached announcement titles
(data/live/announcement_titles/<code>.csv). Point in time: a period is used only after its statutory
deadline (src/quarterly.available_by), so nothing here uses information the market did not have.

  1. 同比 / 环比: revenue and net profit attributable to the parent, year-on-year (cumulative) and
     quarter-on-quarter (single quarter = cumulative minus the previous cumulative of the same year)
  2. 非经常性损益: net profit minus net profit excluding non-recurring items; flagged when the
     difference is at least 30% of |net profit|, or when the company is profitable only before deduction
  3. 利润与现金流背离: profitable but operating cash flow negative, or operating cash flow below half of
     net profit
  4. 会计口径变化: announcements in the last 12 months whose titles mention a change of accounting policy
     or estimate, or a correction of prior-period errors

Thresholds (30%, 0.5) are screening rules written here, not calibrated estimates.
"""
from __future__ import annotations

import csv
import re
from datetime import date, timedelta
from pathlib import Path

from src.quarterly import available_by, parse_abstract

ROOT = Path(__file__).resolve().parents[1]
QDIR = ROOT / "data" / "external" / "financials" / "quarterly"
TITLES = ROOT / "data" / "live" / "announcement_titles"
NONRECURRING_SHARE = 0.30
CASH_CONTENT = 0.5
ACCOUNTING = re.compile(r"会计政策变更|会计估计变更|前期会计差错|差错更正|追溯调整")


def load_periods(code: str) -> dict[str, dict]:
    path = QDIR / f"{code}_abstract.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return parse_abstract(list(csv.reader(f)))


def _prev_period(period: str) -> str | None:
    """Previous quarter-end in the same fiscal year (None for Q1)."""
    md = period[4:]
    order = ["0331", "0630", "0930", "1231"]
    i = order.index(md)
    return None if i == 0 else period[:4] + order[i - 1]


def single_quarter(periods: dict, period: str, field: str) -> float | None:
    cur = (periods.get(period) or {}).get(field)
    prev = _prev_period(period)
    if cur is None:
        return None
    if prev is None:
        return cur
    p = (periods.get(prev) or {}).get(field)
    return None if p is None else cur - p


def _last_quarter(period: str) -> str:
    """The quarter before `period` (crossing the year end)."""
    prev = _prev_period(period)
    return prev if prev else f"{int(period[:4]) - 1}1231"


def growth(cur: float | None, base: float | None) -> float | None:
    if cur is None or base is None or base == 0:
        return None
    return (cur - base) / abs(base)


def latest_period(periods: dict, as_of: str) -> str | None:
    usable = [p for p in periods if available_by(p) <= as_of and periods[p].get("revenue") is not None]
    return max(usable) if usable else None


def accounting_changes(code: str, as_of: str) -> list[dict]:
    path = TITLES / f"{code}.csv"
    if not path.exists():
        return []
    start = (date.fromisoformat(as_of) - timedelta(days=365)).isoformat()
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if start <= r.get("notice_date", "") <= as_of and ACCOUNTING.search(r.get("title", ""))]
    return [{"date": r["notice_date"], "title": r["title"], "url": r.get("source_url", "")} for r in rows]


def report_signals(code: str, as_of: str) -> dict:
    """-> {'period', 'available_by', 'rows': [metric rows], 'signals': [{'kind','text'}], 'accounting': [...]}."""
    periods = load_periods(code)
    period = latest_period(periods, as_of)
    out = {"period": period, "available_by": available_by(period) if period else None, "rows": [], "signals": [],
           "accounting": accounting_changes(code, as_of)}
    if not period:
        return out
    cur = periods[period]
    last_year = periods.get(f"{int(period[:4]) - 1}{period[4:]}", {})
    lq = _last_quarter(period)
    for field, label in (("revenue", "营业总收入"), ("parent_netprofit", "归母净利润"),
                         ("deduct_netprofit", "扣非净利润"), ("ocf", "经营现金流量净额")):
        q, q_prev = single_quarter(periods, period, field), single_quarter(periods, lq, field)
        out["rows"].append({"指标": label, "本期累计（亿元）": _yi(cur.get(field)),
                            "上年同期（亿元）": _yi(last_year.get(field)),
                            "同比": growth(cur.get(field), last_year.get(field)),
                            "单季度（亿元）": _yi(q), "单季度环比": growth(q, q_prev)})
    np_, dn, ocf = cur.get("parent_netprofit"), cur.get("deduct_netprofit"), cur.get("ocf")
    if np_ is not None and dn is not None and np_ != 0:
        gap = np_ - dn
        if np_ > 0 and dn < 0:
            out["signals"].append({"kind": "非经常性损益", "text": f"归母净利润 {_yi(np_):.2f} 亿元为正，扣非后亏损 {_yi(dn):.2f} 亿元：盈利来自非经常性损益"})
        elif abs(gap) >= NONRECURRING_SHARE * abs(np_):
            out["signals"].append({"kind": "非经常性损益", "text": f"非经常性损益 {_yi(gap):.2f} 亿元，占归母净利润的 {abs(gap) / abs(np_):.0%}（≥ 30%）"})
    if np_ is not None and ocf is not None and np_ > 0:
        if ocf < 0:
            out["signals"].append({"kind": "利润与现金流背离", "text": f"归母净利润 {_yi(np_):.2f} 亿元为正，经营现金流 {_yi(ocf):.2f} 亿元为负"})
        elif ocf < CASH_CONTENT * np_:
            out["signals"].append({"kind": "利润与现金流背离", "text": f"经营现金流仅为归母净利润的 {ocf / np_:.0%}（< 50%）"})
    for a in out["accounting"]:
        out["signals"].append({"kind": "会计口径变化", "text": f"{a['date']}《{a['title']}》"})
    return out


def _yi(v: float | None) -> float | None:
    return None if v is None else v / 1e8
