"""首页风险面板: chart data come straight from the snapshot, key paths and futures series."""
from src.home_panel import margin_chart, margin_rows, ranking_chart, ranking_rows


def test_ranking_keeps_core_mills_weakest_first():
    rows = ranking_rows([{"security_name": "甲", "total_score": "70", "tier": "weak", "peer_group": "core", "reasons": "a；b；c"},
                         {"security_name": "乙", "total_score": "20", "tier": "strong", "peer_group": "core", "reasons": ""},
                         {"security_name": "丙", "total_score": "90", "tier": "weak", "peer_group": "other", "reasons": ""}])
    assert [r["企业"] for r in rows] == ["甲", "乙"] and rows[0]["原因"] == "a；b"
    assert ranking_chart(rows)["data"]["values"] == rows


def test_margin_low_line_is_the_historical_20th_percentile():
    days = tuple(f"2025-{m:02d}-01" for m in range(1, 11))
    values = tuple(float(v) for v in range(100, 1100, 100))
    rows, low = margin_rows(days, values, "2025-10-01", span=120)
    assert low == 200.0 and rows[-1]["利润"] == 1000.0 and len(rows) == 4      # 07-01 … 10-01
    assert len(margin_chart(rows, low)["layer"]) == 2
