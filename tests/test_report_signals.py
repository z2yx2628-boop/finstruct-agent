import src.report_signals as rs


def periods(**over):
    base = {
        "20250630": {"revenue": 100e8, "parent_netprofit": 5e8, "deduct_netprofit": 4.8e8, "ocf": 6e8},
        "20251231": {"revenue": 210e8, "parent_netprofit": 9e8, "deduct_netprofit": 8.5e8, "ocf": 12e8},
        "20260331": {"revenue": 50e8, "parent_netprofit": 1e8, "deduct_netprofit": 0.9e8, "ocf": 1e8},
        "20260630": {"revenue": 110e8, "parent_netprofit": 4e8, "deduct_netprofit": 3.9e8, "ocf": 5e8},
    }
    for k, v in over.items():
        base["20260630"][k] = v
    for p, d in base.items():
        d["period"] = p
    return base


def run(monkeypatch, **over):
    monkeypatch.setattr(rs, "load_periods", lambda code: periods(**over))
    monkeypatch.setattr(rs, "accounting_changes", lambda code, as_of: [])
    return rs.report_signals("000000", "2026-10-14")


def test_latest_public_period_and_growth(monkeypatch):
    out = run(monkeypatch)
    assert out["period"] == "20260630" and out["available_by"] == "2026-08-31"
    rev = out["rows"][0]
    assert abs(rev["同比"] - 0.10) < 1e-9                       # 110 vs 100
    assert abs(rev["单季度（亿元）"] - 60) < 1e-9                  # 110 - 50
    assert abs(rev["单季度环比"] - 0.20) < 1e-9                   # Q2 60 vs Q1 50
    assert out["signals"] == []


def test_loss_growth_uses_absolute_base():
    assert rs.growth(-12, -10) == -0.2                            # a wider loss is a negative change


def test_profit_only_before_non_recurring_items(monkeypatch):
    kinds = [s["kind"] for s in run(monkeypatch, deduct_netprofit=-1e8)["signals"]]
    assert kinds == ["非经常性损益"]


def test_profit_with_negative_operating_cash_flow(monkeypatch):
    sig = run(monkeypatch, ocf=-2e8)["signals"]
    assert [s["kind"] for s in sig] == ["利润与现金流背离"] and "为负" in sig[0]["text"]


def test_low_cash_content(monkeypatch):
    sig = run(monkeypatch, ocf=1e8)["signals"]                   # 1 < 0.5 * 4
    assert [s["kind"] for s in sig] == ["利润与现金流背离"]


def test_accounting_title_pattern():
    assert rs.ACCOUNTING.search("关于会计政策变更公告")
    assert rs.ACCOUNTING.search("关于前期会计差错更正的公告")
    assert not rs.ACCOUNTING.search("2026年半年度报告")
