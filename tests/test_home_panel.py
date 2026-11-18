"""首页风险面板: chart data come straight from the snapshot, key paths and futures series."""
from src.home_panel import margin_chart, margin_rows, path_chart, ranking_chart, ranking_rows, weak_sentence


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
    spec = margin_chart(rows, low, median=600.0)
    assert any(l.get("data", {}).get("values", [{}])[0].get("y") == 600.0 for l in spec["layer"])
    domain = spec["layer"][-3]["encoding"]["y"]["scale"]["domain"]
    assert domain[0] < 200 and domain[1] > 1000            # zoomed to the data, not from zero


def test_weak_line_and_path_bars():
    rows = [{"日期": "2026-10-01", "指标": "弱等级钢厂（家）", "数值": 5}, {"日期": "2026-11-01", "指标": "弱等级钢厂（家）", "数值": 5},
            {"日期": "2026-10-01", "指标": "计分传导路径（条）", "数值": 14}, {"日期": "2026-11-01", "指标": "计分传导路径（条）", "数值": 10}]
    line = weak_sentence(rows, ["甲", "乙", "丙", "丁", "戊"], ["己"])
    assert "保持不变" in line and "**5 家**（甲、乙、丙、丁、戊）" in line and "以外另有 己" in line
    spec = path_chart(rows, notes=[{"日期": "2026-11-01", "t": "三季报", "tip": "x"}, {"日期": "2026-12-01", "t": "无", "tip": "y"}])
    assert spec["layer"][2]["data"]["values"][0]["数值"] == 10
    assert [n["t"] for n in spec["layer"][4]["data"]["values"]] == ["三季报"]      # notes only on days that are drawn
