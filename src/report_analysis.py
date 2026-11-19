"""财报分析, the analyst layer on top of report_signals: one-line reading, DuPont split, earnings quality and
working capital, an eight-quarter trend, and where each number stands among the 24 core mills.

Everything comes from the same Sina financial abstract the fragility score uses
(data/external/financials/quarterly/<code>_abstract.csv), for the same period for every company (the latest
one past its statutory deadline), so peer comparisons are like-for-like and point in time.

Ratios in the abstract are year-to-date (a Q3 asset turnover covers nine months), so a company is compared
with its own same period last year and with peers in the same period, never with a different period.
The DuPont product (net margin x asset turnover x equity multiplier) is an approximation of the reported
average ROE; both are shown.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from statistics import median

from src.financial_indicators import num

ROOT = Path(__file__).resolve().parents[1]
QDIR = ROOT / "data" / "external" / "financials" / "quarterly"

# abstract name -> (field, scale)
NAMES = {"营业总收入": ("revenue", 1), "营业成本": ("cost", 1), "归母净利润": ("np", 1), "扣非净利润": ("np_deduct", 1),
         "经营现金流量净额": ("ocf", 1), "毛利率": ("gm", 0.01), "销售净利率": ("nm", 0.01),
         "总资产周转率": ("turnover", 1), "权益乘数": ("multiplier", 1), "净资产收益率_平均": ("roe", 0.01),
         "存货周转天数": ("inv_days", 1), "应收账款周转天数": ("ar_days", 1), "期间费用率": ("expense", 0.01)}

# metric -> (label, higher is better, format)
METRICS = {
    "nm": ("销售净利率", True, "pct"), "turnover": ("总资产周转率（年初至今）", True, "x"),
    "multiplier": ("权益乘数", False, "x"), "roe": ("净资产收益率（平均）", True, "pct"),
    "gm": ("毛利率", True, "pct"), "expense": ("期间费用率", False, "pct"),
    "cash_np": ("经营现金流 / 归母净利润", True, "x"), "inv_days": ("存货周转天数", False, "days"),
    "ar_days": ("应收账款周转天数", False, "days"),
}


@lru_cache(maxsize=128)
def periods_of(code: str) -> dict[str, dict]:
    path = QDIR / f"{code}_abstract.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header, first = rows[0], {}
    for row in rows[1:]:
        if len(row) > 1 and row[1] in NAMES and row[1] not in first:
            first[row[1]] = dict(zip(header[2:], row[2:]))
    out: dict[str, dict] = {}
    for p in header[2:]:
        if not (len(p) == 8 and p.isdigit()):
            continue
        m = {}
        for name, (field, scale) in NAMES.items():
            v = num(first.get(name, {}).get(p))
            m[field] = None if v is None else v * scale
        np_, ocf = m.get("np"), m.get("ocf")
        m["cash_np"] = ocf / np_ if (np_ and np_ > 0 and ocf is not None) else None   # meaningless for a loss
        out[p] = m
    return out


def last_year(period: str) -> str:
    return f"{int(period[:4]) - 1}{period[4:]}"


def _prev_q(period: str) -> str:
    order = ["0331", "0630", "0930", "1231"]
    i = order.index(period[4:])
    return f"{int(period[:4]) - 1}1231" if i == 0 else period[:4] + order[i - 1]


def single(periods: dict, period: str, field: str) -> float | None:
    """Single-quarter value from year-to-date figures."""
    cur = (periods.get(period) or {}).get(field)
    if cur is None:
        return None
    if period.endswith("0331"):
        return cur
    prev = (periods.get(_prev_q(period)) or {}).get(field)
    return None if prev is None else cur - prev


def growth(cur, base):
    return None if cur is None or base in (None, 0) else (cur - base) / abs(base)


# ---------------------------------------------------------------- peers
def peer_values(codes: list[str], period: str, field: str) -> dict[str, float]:
    return {c: v for c in codes if (v := (periods_of(c).get(period) or {}).get(field)) is not None}


def peer_growth(codes: list[str], period: str, field: str) -> dict[str, float]:
    out = {}
    for c in codes:
        ps = periods_of(c)
        g = growth((ps.get(period) or {}).get(field), (ps.get(last_year(period)) or {}).get(field))
        if g is not None:
            out[c] = g
    return out


def position(code: str, values: dict[str, float], higher_better: bool) -> str:
    """'24 家中第 3 弱' (or 强): counted from the weak end when the company is in the weaker half."""
    if code not in values or len(values) < 3:
        return "—"
    order = sorted(values, key=lambda c: values[c], reverse=not higher_better)   # weakest first
    k = order.index(code) + 1
    n = len(order)
    return f"{n} 家中第 {k} 弱" if k <= (n + 1) / 2 else f"{n} 家中第 {n - k + 1} 强"


def med(values: dict[str, float]) -> float | None:
    return median(values.values()) if values else None


# ---------------------------------------------------------------- tables
def metric_rows(code: str, period: str, peers: list[str], keys: list[str]) -> list[dict]:
    ps = periods_of(code)
    cur, ly = ps.get(period) or {}, ps.get(last_year(period)) or {}
    rows = []
    for k in keys:
        label, up, kind = METRICS[k]
        vals = peer_values(peers, period, k)
        rows.append({"指标": label, "本期": cur.get(k), "上年同期": ly.get(k),
                     "24 家中位数": med(vals), "同行位置": position(code, vals, up), "_kind": kind, "_up": up})
    return rows


def dupont(code: str, period: str, peers: list[str]) -> dict:
    """Which factor drags ROE most: the one furthest below the peer median, in relative terms."""
    rows = metric_rows(code, period, peers, ["nm", "turnover", "multiplier", "roe"])
    cur = periods_of(code).get(period) or {}
    product = None
    if None not in (cur.get("nm"), cur.get("turnover"), cur.get("multiplier")):
        product = cur["nm"] * cur["turnover"] * cur["multiplier"]
    gaps = {}
    for r in rows[:3]:
        v, m = r["本期"], r["24 家中位数"]
        if v is not None and m:
            gap = (v - m) / abs(m)
            gaps[r["指标"]] = gap if r["_up"] else -gap
    worst = min(gaps, key=gaps.get) if gaps else None
    return {"rows": rows, "product": product, "worst": worst, "gaps": gaps}


def trend(code: str, period: str, n: int = 8) -> list[dict]:
    """Single-quarter gross margin, net margin and operating cash flow / revenue, last n quarters."""
    ps = periods_of(code)
    quarters, p = [], period
    for _ in range(n):
        quarters.append(p)
        p = _prev_q(p)
    out = []
    for q in reversed(quarters):
        rev, cost, np_, ocf = (single(ps, q, f) for f in ("revenue", "cost", "np", "ocf"))
        label = f"{q[2:4]}Q{['0331', '0630', '0930', '1231'].index(q[4:]) + 1}"
        if rev:
            if cost is not None:
                out.append({"季度": label, "指标": "毛利率", "数值": round(1 - cost / rev, 4)})
            if np_ is not None:
                out.append({"季度": label, "指标": "净利率（归母）", "数值": round(np_ / rev, 4)})
            if ocf is not None:
                out.append({"季度": label, "指标": "经营现金流 / 营收", "数值": round(ocf / rev, 4)})
    return out


# ---------------------------------------------------------------- one sentence
def reading(code: str, period: str, peers: list[str]) -> str:
    ps = periods_of(code)
    cur, ly = ps.get(period) or {}, ps.get(last_year(period)) or {}
    rg, ng = growth(cur.get("revenue"), ly.get("revenue")), growth(cur.get("np"), ly.get("np"))
    np_, np_ly = cur.get("np"), ly.get("np")
    if rg is None or np_ is None:
        return ""
    rev = f"营收 {rg:+.1%}"
    if np_ < 0:
        if np_ly is not None and np_ly < 0:
            head = ("亏损收窄" if np_ > np_ly else "亏损扩大") + f"：{rev}，归母净利润 {np_ / 1e8:.2f} 亿元（上年同期 {np_ly / 1e8:.2f} 亿元）"
        else:
            head = f"由盈转亏：{rev}，归母净利润 {np_ / 1e8:.2f} 亿元"
    elif np_ly is not None and np_ly < 0:
        head = f"扭亏为盈：{rev}，归母净利润 {np_ / 1e8:.2f} 亿元"
    else:
        kind = {(True, True): "量利齐升", (True, False): "增收不增利", (False, True): "减收增利",
                (False, False): "量利双降"}[(rg >= 0, (ng or 0) >= 0)]
        head = f"{kind}：{rev}，归母净利润 {ng:+.1%}" if ng is not None else f"{rev}"
    better = np_ly is not None and np_ > np_ly           # did profit improve on the same period last year?
    causes = []                                           # only drivers that point the same way as profit
    if cur.get("gm") is not None and ly.get("gm") is not None:
        d = (cur["gm"] - ly["gm"]) * 100
        if abs(d) >= 0.5 and (d > 0) == better:
            causes.append(f"毛利率{'上升' if d > 0 else '下降'} {abs(d):.1f} 个百分点")
    if cur.get("expense") is not None and ly.get("expense") is not None:
        d = (cur["expense"] - ly["expense"]) * 100
        if abs(d) >= 0.5 and (d < 0) == better:
            causes.append(f"期间费用率{'上升' if d > 0 else '下降'} {abs(d):.1f} 个百分点")
    text = head + ("，主要因为" + "、".join(causes) if causes else "")
    if np_ and cur.get("np_deduct") is not None and np_ > 0 and abs(np_ - cur["np_deduct"]) >= 0.3 * abs(np_):
        text += f"；非经常性损益占净利润 {abs(np_ - cur['np_deduct']) / abs(np_):.0%}，应看扣非利润"
    cash = cur.get("cash_np")
    if cash is not None:
        if cash > 5:
            text += f"；经营现金流远高于微薄的净利润（{cash:.0f} 倍）"
        else:
            text += f"；经营现金流是净利润的 {cash:.1f} 倍" + ("，利润有现金支撑" if cash >= 1 else "，利润含金量偏低" if cash < 0.5 else "")
    d = dupont(code, period, peers)
    if d["worst"] and d["gaps"][d["worst"]] < -0.2:
        text += f"；与同行相比，ROE 主要拖累在{d['worst'].split('（')[0]}"
    return text + "。"


def fmt(value, kind: str) -> str:
    if value is None:
        return "—"
    return {"pct": f"{value:.1%}", "x": f"{value:.2f}", "days": f"{value:.0f} 天"}[kind]
