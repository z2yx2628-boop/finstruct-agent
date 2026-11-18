import src.futures as fu


def fake_series(data):
    def series(symbol):
        rows = data[symbol]
        return tuple(d for d, _ in rows), tuple(v for _, v in rows)
    return series


def setup(monkeypatch, n=30):
    days = [f"2026-01-{i:02d}" if i <= 31 else f"2026-02-{i - 31:02d}" for i in range(1, n + 1)]
    data = {"RB0": [(d, 3000.0 + i) for i, d in enumerate(days)],
            "HC0": [(d, 3200.0) for d in days],
            "I0": [(d, 700.0) for d in days],
            "J0": [(d, 2000.0) for d in days],
            "JM0": [(d, 1400.0) for d in days]}
    monkeypatch.setattr(fu, "series", fake_series(data))
    monkeypatch.setattr(fu, "SINCE", "2000-01-01")
    fu.margin_series.cache_clear()
    return days


def test_margin_formula():
    p = {"RB0": 3000, "HC0": 3200, "I0": 700, "J0": 2000, "JM0": 1400}
    assert fu.margin_formula("rebar", p) == 3000 - 1.6 * 700 - 0.5 * 2000
    assert fu.margin_formula("coke", p) == 2000 - 1.33 * 1400


def test_snapshot_change_is_split_by_input(monkeypatch):
    days = setup(monkeypatch)
    s = fu.margin_snapshot("rebar", days[-1])
    assert s["change"] == fu.WINDOW                          # rebar rose 1 yuan a day, inputs flat
    assert abs(sum(c["对利润的贡献（元/吨）"] for c in s["contrib"]) - s["change"]) < 1e-9
    assert s["pct_all"] == 1.0                               # highest margin so far


def test_point_in_time(monkeypatch):
    days = setup(monkeypatch)
    s = fu.margin_snapshot("rebar", days[25])
    assert s["date"] == days[25]
    assert fu.margin_snapshot("rebar", days[5]) is None      # fewer than WINDOW days of history


def test_scenario_ore_up_cuts_margin(monkeypatch):
    days = setup(monkeypatch)
    sc = fu.scenario("rebar", days[-1], {"I0": 0.10})
    assert abs(sc["delta"] - (-1.6 * 70)) < 1e-9


def test_hedge_classification():
    assert fu.classify("关于2026年开展商品期货套期保值业务的公告") == "商品期货"
    assert fu.classify("关于开展外汇套期保值业务的公告") == "外汇"
    assert fu.classify("关于调整外汇衍生品套期保值业务额度的公告") == "外汇"
    assert fu.classify("关于2026年套期保值业务预计的公告") == "未写明品种"
    assert fu.classify("关于召开股东会的通知") is None
    h = {"commodity": False, "unspecified": False, "fx": False, "items": []}
    assert fu.hedge_label(h) == "缓存中未见"
    assert fu.hedge_label({**h, "commodity": True, "fx": True}) == "商品期货 + 外汇"
