"""Credit events that have already happened (facts), found in announcement TITLES and kept for 12 months.

The extraction system reads four announcement types (related-party trade, guarantee, capacity, pledge). Frozen
accounts, defaults, risk warnings, qualified audit opinions, rating cuts and bankruptcy proceedings are rarer and
their titles say what happened, so they are recognised from the title with the pre-registered event-study patterns
(scripts/collect_credit_events.py) by scripts/scan_credit_events.py -> data/live/credit_events.csv.

They enter the LIVE chain only (never a backtest chain): as seeds of the propagation and as events in the
fragility score, like any other high-severity signal.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "live" / "credit_events.csv"
LIVE = (ROOT / "data" / "chain" / "live").resolve()
EVENT_CN = {"guarantee_default": "担保逾期或代偿", "debt_default": "债务逾期或违约", "freeze": "资产、账户或股份被司法冻结",
            "st": "被实施风险警示", "st_warning": "可能被实施风险警示（预告）", "audit": "非标准审计意见",
            "rating": "评级下调", "restructuring": "破产重整或清算"}
FIELDS = ["security_code", "security_name", "date", "event_type", "event_label", "severity", "title", "source_url",
          "status", "valid_to"]


def read(path: Path = TABLE) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def active(as_of: str) -> list[dict]:
    return [r for r in read() if r["date"] <= as_of <= r["valid_to"]]


def as_signals(as_of: str) -> list[dict]:
    """The events in the signals.csv layout, so seeds_from() and the fragility score treat them like extracted signals."""
    return [{"entity_id": r["security_code"], "entity_name": r["security_name"], "group_id": "", "date": r["date"],
             "signal_type": "credit_event", "severity": r["severity"], "severity_rule": "公告标题识别的已发生信用事件",
             "magnitude": "", "magnitude_unit": "", "detail": f"{r['event_label']}：{r['title']}",
             "source_doc": r["source_url"], "source_page": "", "evidence_text": r["title"],
             "valid_from": r["date"], "valid_to": r["valid_to"]} for r in active(as_of)]


def chain_signals(chain: Path, as_of: str) -> list[dict]:
    """signals.csv of a chain, plus the title-recognised credit events when the chain is the live one."""
    rows = read(chain / "signals.csv")
    if chain.resolve() == LIVE:
        rows += as_signals(as_of)
    return rows
