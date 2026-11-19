"""企业档案 · 公告信号: the company's announcement signals as a story, not a list (display only).

  signal_rows     : one row per signal with the specific event as its type, the rule that keeps it in force,
                    and a link to the announcement when the signal came from a title
  escalation      : one sentence on how the events moved (a warning, then the real thing …)
  price_window    : the share price around the events, for a timeline chart
  event_reaction  : the 5-day return after each event against the equal-weighted 24 core mills (an event-study
                    style reading of one company, not a test)
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from src.network_view import SEVERITY_LABEL
from src.validity import is_active

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "data" / "external" / "market"
TYPE_LABEL = {"credit_event": "信用事件", "credit_exposure": "担保敞口", "guarantee_balance": "担保余额",
              "share_pledge": "股权质押", "capacity_reduction": "减产 / 检修", "capacity_increase": "扩产"}
VALID_RULE = {"credit_event": "信用事件：发生后 12 个月内视为有效", "credit_exposure": "担保：按合同期限，未写明的按 12 个月",
              "guarantee_balance": "担保余额：到下一期披露为止", "share_pledge": "质押：到解除质押公告为止，未披露的按 12 个月",
              "capacity_reduction": "检修 / 减产：按公告写明的期间"}
ORDER = {"high": 0, "medium": 1, "low": 2}


def signal_rows(signals: list[dict], code: str, as_of: str) -> list[dict]:
    out, seen = [], set()
    for s in signals:
        if s.get("entity_id") != code or not s.get("date") or s["date"] > as_of:
            continue
        detail = s.get("detail") or ""
        event = detail.split("：")[0] if "：" in detail else TYPE_LABEL.get(s.get("signal_type", ""), s.get("signal_type", ""))
        text = detail.split("：", 1)[1] if "：" in detail else detail
        key = (s["date"], event, text)
        if key in seen:
            continue
        seen.add(key)
        src = s.get("source_doc") or ""
        out.append({"日期": s["date"], "事件": event, "类别": TYPE_LABEL.get(s.get("signal_type", ""), s.get("signal_type", "")),
                    "严重度": SEVERITY_LABEL.get(s.get("severity", ""), s.get("severity", "")), "_sev": s.get("severity", ""),
                    "仍有效": "是" if is_active(s, as_of) else "否", "有效期至": s.get("valid_to") or "—",
                    "有效期规则": VALID_RULE.get(s.get("signal_type", ""), ""), "公告": text[:60],
                    "原文": src if src.startswith("http") else None})
    return sorted(out, key=lambda r: (r["日期"], -ORDER.get(r["_sev"], 3)), reverse=True)


def escalation(rows: list[dict]) -> str:
    """'风险在升级：… → …' when a later event is more severe than an earlier one, else a plain summary."""
    if not rows:
        return ""
    seq = sorted(rows, key=lambda r: r["日期"])
    high = [r for r in seq if r["_sev"] == "high"]
    steps = []
    for r in seq:
        label = f"{r['日期'][5:]} {r['事件']}"
        if steps and steps[-1].startswith(r["日期"][5:]):
            steps[-1] += f"、{r['事件']}"
        else:
            steps.append(label)
    worse = len(seq) > 1 and ORDER.get(seq[-1]["_sev"], 3) < ORDER.get(seq[0]["_sev"], 3)
    if worse:
        return "风险在升级：" + " → ".join(steps[-4:]) + "。"
    if high:
        return f"共 {len(seq)} 条信号，其中高严重度 {len(high)} 条：" + " → ".join(steps[-4:]) + "。"
    return f"共 {len(seq)} 条信号，没有高严重度事件。"


@lru_cache(maxsize=128)
def closes(code: str) -> tuple[tuple[str, float], ...]:
    path = MARKET / f"{code}.csv"
    if not path.exists():
        return ()
    with path.open(encoding="utf-8-sig", newline="") as f:
        return tuple((r["date"][:10], float(r["close"])) for r in csv.DictReader(f) if r.get("close"))


def price_window(code: str, as_of: str, days: int = 365) -> list[dict]:
    start = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
    return [{"日期": d, "收盘价": v} for d, v in closes(code) if start <= d <= as_of]


def _ret(series: tuple[tuple[str, float], ...], day: str, n: int) -> float | None:
    """Return from the last close before `day` to the n-th trading day from `day` on."""
    dates = [d for d, _ in series]
    before = [i for i, d in enumerate(dates) if d < day]
    after = [i for i, d in enumerate(dates) if d >= day]
    if not before or len(after) < n:
        return None
    return series[after[n - 1]][1] / series[before[-1]][1] - 1


def event_reaction(code: str, day: str, peers: list[str], n: int = 5) -> dict | None:
    """5-day return after `day`, and the same against the equal-weighted peers (excess return)."""
    own = _ret(closes(code), day, n)
    if own is None:
        return None
    rs = [r for p in peers if p != code and (r := _ret(closes(p), day, n)) is not None]
    bench = sum(rs) / len(rs) if rs else None
    return {"ret": own, "bench": bench, "excess": own - bench if bench is not None else None, "n_peers": len(rs)}
