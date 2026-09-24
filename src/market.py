"""Market layer: daily-price stress indicators (point-in-time: only prices up to `as_of`)."""
from __future__ import annotations

import math


def market_metrics(prices: list[tuple[str, float]], as_of: str) -> dict:
    """prices: [(YYYY-MM-DD, close)] ascending. Returns returns, drawdown and volatility."""
    series = [c for d, c in prices if d <= as_of and c and c > 0]
    out = {"last_trade_date": max((d for d, _ in prices if d <= as_of), default=""),
           "ret_20d": None, "ret_60d": None, "max_drawdown_60d": None, "vol_20d": None, "dist_52w_low": None}
    if len(series) < 21:
        return out
    last = series[-1]
    out["ret_20d"] = last / series[-21] - 1
    if len(series) >= 61:
        out["ret_60d"] = last / series[-61] - 1
    window = series[-60:]
    peak, worst = window[0], 0.0
    for c in window:
        peak = max(peak, c)
        worst = min(worst, c / peak - 1)
    out["max_drawdown_60d"] = worst
    rets = [math.log(series[i] / series[i - 1]) for i in range(len(series) - 20, len(series))]
    mean = sum(rets) / len(rets)
    out["vol_20d"] = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(250)
    year = series[-250:]
    out["dist_52w_low"] = last / min(year) - 1
    return out


def add_excess_return(rows: list[dict]) -> None:
    """ret_60d minus the peer median, so a sector-wide fall does not flag every mill."""
    values = sorted(r["ret_60d"] for r in rows if r.get("ret_60d") is not None)
    if not values:
        return
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    for r in rows:
        r["excess_ret_60d"] = None if r.get("ret_60d") is None else r["ret_60d"] - median
