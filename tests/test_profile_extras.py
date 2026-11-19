import src.profile_extras as pe


def test_trend_compares_with_snapshot_a_month_earlier():
    h = [{"日期": "2026-09-20", "总分": 50.0, "等级": "中"}, {"日期": "2026-10-15", "总分": 55.0, "等级": "中"},
         {"日期": "2026-11-01", "总分": 58.0, "等级": "中"}, {"日期": "2026-11-17", "总分": 62.0, "等级": "弱"}]
    t = pe.trend(h)
    assert t["from"] == "2026-10-15" and abs(t["delta"] - 7.0) < 1e-9
    assert (t["tier_from"], t["tier_to"]) == ("中", "弱")
    assert pe.trend(h[:1]) is None


def test_checklist_rules():
    row = {"tier": "weak", "total_score": "70.1", "events_after_report": "1"}
    s = pe.checklist("某钢厂", row, {"rules": ["资不抵债（净资产为负）"]}, None,
                     {"parent": "某集团有限公司", "group_id": "G_X", "listed_peers": []},
                     None, {"fy": "2025", "extra_yi": 5.0, "to_equity": 0.2}, "缓存中未见", 2, 0, None)
    assert any("资不抵债" in p for p in s["points"])
    assert len(s["checks"]) == 3                               # capped at three
    assert s["checks"][0].startswith("核查偿债安排")


def test_checklist_strong_company_has_no_solvency_check():
    s = pe.checklist("某钢厂", {"tier": "strong", "total_score": "10"}, {"rules": []}, None, None, None, None,
                     "商品期货", 0, 0, None)
    assert not s["checks"]
    assert "传导路径：没有计分路径" in s["points"]


def test_brief_is_standalone_html_and_escaped():
    out = pe.brief_html("A&B 钢铁", "600000", "2026-11-17", "A&B：自身承压 **弱**",
                        {"points": ["自身承压 **弱**"], "checks": ["核查 <x>"]},
                        [{"维度": "杠杆", "本企业": 90.0, "核心钢厂中位数": 50.0}], "资产负债率高", None, [])
    assert out.startswith("<!doctype html>") and "A&amp;B 钢铁" in out and "核查 &lt;x&gt;" in out and "**" not in out


def test_history_marks_the_day_a_new_report_comes_into_use():
    h = pe.score_history("600581", "2026-11-17")
    if not h:                                              # snapshots not available in this checkout
        return
    assert h[0]["新财报"] is False
    for prev, cur in zip(h, h[1:]):
        assert cur["新财报"] == (cur["财报期"] != prev["财报期"])
    assert pe.period_label("20260930") == "2026 年三季报"
