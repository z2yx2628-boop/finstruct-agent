"""企业档案 · 公告信号: specific event names, escalation sentence, 5-day excess return."""
from src import signal_view as sv


def _s(day, sev, detail, src="http://x/1.PDF"):
    return {"entity_id": "A", "date": day, "signal_type": "credit_event", "severity": sev, "detail": detail,
            "source_doc": src, "valid_from": day, "valid_to": "2027-12-31"}


def test_rows_name_the_event_and_link_the_announcement():
    rows = sv.signal_rows([_s("2026-03-30", "high", "被实施风险警示：关于股票被实施退市风险警示暨停牌的公告"),
                           _s("2026-01-26", "medium", "可能被实施风险警示（预告）：关于股票可能被实施退市风险警示的风险提示公告")], "A", "2026-11-18")
    assert rows[0]["事件"] == "被实施风险警示" and rows[0]["原文"] == "http://x/1.PDF" and rows[0]["仍有效"] == "是"
    assert sv.escalation(rows).startswith("风险在升级：01-26 可能被实施风险警示（预告） → 03-30 被实施风险警示")


def test_excess_return_against_peers(monkeypatch):
    series = {"A": (("2026-01-23", 10.0), ("2026-01-26", 9.0), ("2026-01-27", 8.0)),
              "B": (("2026-01-23", 10.0), ("2026-01-26", 10.0), ("2026-01-27", 10.5))}
    monkeypatch.setattr(sv, "closes", lambda code: series.get(code, ()))
    r = sv.event_reaction("A", "2026-01-26", ["A", "B"], n=2)
    assert abs(r["ret"] - (-0.2)) < 1e-9 and abs(r["bench"] - 0.05) < 1e-9 and abs(r["excess"] - (-0.25)) < 1e-9
