"""财报分析: one-line reading, DuPont split, peer position, quarterly trend."""
from src import report_analysis as ra


def _fake(monkeypatch, data):
    monkeypatch.setattr(ra, "periods_of", lambda code: data.get(code, {}))


def test_reading_names_the_pattern_and_only_drivers_pointing_the_same_way(monkeypatch):
    cur = {"revenue": 106e8, "np": 8.5e8, "np_deduct": 8.4e8, "gm": 0.058, "expense": 0.040, "ocf": 26e8, "cash_np": 3.06,
           "nm": 0.08, "turnover": 0.7, "multiplier": 2.0}
    ly = {"revenue": 100e8, "np": 10e8, "np_deduct": 10e8, "gm": 0.072, "expense": 0.030, "nm": 0.1}
    _fake(monkeypatch, {"A": {"20260930": cur, "20250930": ly}})
    text = ra.reading("A", "20260930", ["A"])
    assert text.startswith("增收不增利") and "毛利率下降 1.4 个百分点" in text and "期间费用率上升 1.0 个百分点" in text
    assert "利润有现金支撑" in text


def test_loss_narrowing_does_not_blame_rising_costs(monkeypatch):
    cur = {"revenue": 98e8, "np": -5e8, "gm": 0.02, "expense": 0.05}
    ly = {"revenue": 100e8, "np": -6e8, "gm": 0.01, "expense": 0.04}
    _fake(monkeypatch, {"A": {"20260930": cur, "20250930": ly}})
    text = ra.reading("A", "20260930", ["A"])
    assert text.startswith("亏损收窄") and "毛利率上升" in text and "费用率" not in text


def test_position_counts_from_the_weak_end():
    values = {c: v for c, v in zip("ABCDE", [0.01, 0.02, 0.03, 0.04, 0.05])}
    assert ra.position("A", values, True) == "5 家中第 1 弱"
    assert ra.position("E", values, True) == "5 家中第 1 强"
    assert ra.position("A", values, False) == "5 家中第 1 强"      # lower is better (e.g. inventory days)


def test_dupont_finds_the_drag_and_trend_uses_single_quarters(monkeypatch):
    peers = {c: {"20260930": {"nm": 0.05, "turnover": 0.7, "multiplier": 2.5}} for c in "BCD"}
    a = {"20260930": {"nm": -0.10, "turnover": 0.75, "multiplier": 2.6, "revenue": 300, "cost": 280},
         "20260630": {"revenue": 200, "cost": 190}}
    _fake(monkeypatch, {"A": a, **peers})
    d = ra.dupont("A", "20260930", ["A", "B", "C", "D"])
    assert d["worst"] == "销售净利率" and abs(d["product"] - (-0.10 * 0.75 * 2.6)) < 1e-9
    q3 = [r for r in ra.trend("A", "20260930", n=1) if r["指标"] == "毛利率"]
    assert q3 == [{"季度": "26Q3", "指标": "毛利率", "数值": 0.1}]     # (100 - 90) / 100: the single quarter, not year-to-date
