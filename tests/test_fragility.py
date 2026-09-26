import pytest

from src.fragility import percentile_scores, score
from src.market import add_excess_return, market_metrics
from src.quarterly import available_by, latest_public_period, parse_abstract


def test_statutory_deadlines():
    assert available_by("20250331") == "2025-04-30"
    assert available_by("20250630") == "2025-08-31"
    assert available_by("20251231") == "2026-04-30"
    assert latest_public_period("2026-09-24") == "20260630"
    assert latest_public_period("2026-04-29") == "20250930"      # annual not due yet
    assert latest_public_period("2025-01-31") == "20240930"


def test_parse_abstract_scales_percentages():
    rows = [["选项", "指标", "20260630", "20251231"],
            ["常用指标", "资产负债率", "39.1", "38.0"],
            ["财务风险", "资产负债率", "39.1", "38.0"],
            ["财务风险", "现金比率", "0.18", "0.2"],
            ["常用指标", "股东权益合计(净资产)", "-5", "10"]]
    p = parse_abstract(rows)
    assert p["20260630"]["debt_ratio"] == pytest.approx(0.391)
    assert p["20260630"]["negative_equity"] == 1 and p["20251231"]["negative_equity"] == 0
    assert p["20251231"]["available_by"] == "2026-04-30"


def test_market_metrics_use_only_prices_up_to_as_of():
    prices = [(f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", 10.0 - 0.05 * i) for i in range(80)]
    m = market_metrics(prices + [("2099-01-01", 1000.0)], "2025-12-31")
    assert m["ret_20d"] < 0 and m["max_drawdown_60d"] < 0 and m["vol_20d"] >= 0
    assert m["last_trade_date"] != "2099-01-01"
    assert market_metrics(prices[:10], "2025-12-31")["ret_20d"] is None


def test_excess_return_removes_sector_move():
    rows = [{"ret_60d": -0.30}, {"ret_60d": -0.20}, {"ret_60d": -0.10}]
    add_excess_return(rows)
    assert [round(r["excess_ret_60d"], 2) for r in rows] == [-0.10, 0.0, 0.10]


def test_percentile_higher_is_worse():
    rows = [{"security_code": c, "debt_ratio": v} for c, v in (("a", 0.4), ("b", 0.6), ("c", 0.9))]
    s = percentile_scores(rows, "debt_ratio", +1)
    assert s["c"][0] == 100 and s["a"][0] == 0 and s["c"][1] == 1


def peers():
    base = dict(current_ratio=1.0, quick_ratio=0.7, cash_ratio=0.3, ocf_to_revenue=0.05,
                net_margin=0.02, gross_margin=0.08, revenue_growth=0.0, excess_ret_60d=0.0,
                max_drawdown_60d=-0.1, vol_20d=0.3, negative_equity=0, period="20260630")
    rows = []
    for i in range(6):
        r = dict(base, security_code=f"c{i}", security_name=f"厂{i}", debt_ratio=0.40 + 0.05 * i)
        r["cash_ratio"] = 0.5 - 0.06 * i
        r["net_margin"] = 0.04 - 0.012 * i
        rows.append(r)
    return rows


def test_weakest_peer_is_weak_with_reasons():
    out = {r["security_code"]: r for r in score(peers(), [], "2026-09-24", "20260630")}
    assert out["c5"]["tier"] == "weak" and "资产负债率" in out["c5"]["reasons"]
    assert out["c0"]["tier"] == "strong"


def test_red_line_overrides_ranking():
    rows = peers()
    rows[0]["negative_equity"] = 1
    out = {r["security_code"]: r for r in score(rows, [], "2026-09-24", "20260630")}
    assert out["c0"]["tier"] == "weak" and "资不抵债" in out["c0"]["reasons"]


def test_event_after_report_downgrades_one_tier_only_inside_window():
    signals = [{"entity_id": "c0", "date": "2026-09-01", "signal_type": "credit_event", "severity": "high", "detail": "逾期担保"},
               {"entity_id": "c1", "date": "2026-10-15", "signal_type": "credit_event", "severity": "high", "detail": "未来"}]
    out = {r["security_code"]: r for r in score(peers(), signals, "2026-09-24", "20260630")}
    assert out["c0"]["base_tier"] == "strong" and out["c0"]["tier"] == "medium" and "逾期担保" in out["c0"]["reasons"]
    assert out["c1"]["tier"] == out["c1"]["base_tier"]            # event after as_of is ignored


def test_company_outside_peer_group_is_placed_without_moving_peers():
    rows = peers()
    before = {r["security_code"]: r["total_score"] for r in score(rows, [], "2026-09-24", "20260630")}
    outsider = dict(rows[-1], security_code="X", security_name="外部公司", debt_ratio=0.99)
    after = {r["security_code"]: r for r in score(rows, [], "2026-09-24", "20260630", extra=[outsider])}
    assert all(after[c]["total_score"] == s for c, s in before.items())
    assert after["X"]["peer_group"] == "other" and after["X"]["tier"] == "weak"
