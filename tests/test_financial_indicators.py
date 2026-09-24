import pytest

from src.financial_indicators import annual_rows, build, num, total


def bal(date, **kw):
    base = {"REPORT_DATE": f"{date} 00:00:00", "NOTICE_DATE": "2026-04-30 00:00:00",
            "TOTAL_ASSETS": 1000, "TOTAL_LIABILITIES": 700, "TOTAL_CURRENT_ASSETS": 400,
            "TOTAL_CURRENT_LIAB": 500, "INVENTORY": 100, "MONETARYFUNDS": 90, "SHORT_LOAN": 100,
            "NONCURRENT_LIAB_1YEAR": 50, "SHORT_BOND_PAYABLE": "", "LONG_LOAN": 200, "BOND_PAYABLE": "",
            "CIP": 80, "TOTAL_PARENT_EQUITY": 250}
    base.update(kw)
    return base


def inc(date, **kw):
    base = {"REPORT_DATE": f"{date} 00:00:00", "TOTAL_OPERATE_INCOME": 1200, "OPERATE_INCOME": 1200,
            "OPERATE_COST": 1100, "NETPROFIT": -30, "PARENT_NETPROFIT": -25, "DEDUCT_PARENT_NETPROFIT": -40,
            "TOTAL_PROFIT": -20, "FE_INTEREST_EXPENSE": 20}
    base.update(kw)
    return base


def cf(date, **kw):
    base = {"REPORT_DATE": f"{date} 00:00:00", "NETCASH_OPERATE": 60, "CONSTRUCT_LONG_ASSET": 90}
    base.update(kw)
    return base


def test_num_handles_blanks_and_text():
    assert num("") is None and num("nan") is None and num("--") is None
    assert num("1.5") == 1.5


def test_total_treats_missing_items_as_zero_but_all_missing_as_none():
    assert total(1, None, 2) == 3
    assert total(None, None) is None


def test_only_annual_reports_are_used():
    rows = [bal("2025-06-30"), bal("2025-12-31"), bal("2024-12-31")]
    assert sorted(annual_rows(rows)) == [2024, 2025]


def test_indicators_on_a_stressed_mill():
    out = build([bal("2025-12-31"), bal("2024-12-31", TOTAL_ASSETS=900, TOTAL_PARENT_EQUITY=250)],
                [inc("2025-12-31"), inc("2024-12-31", TOTAL_OPERATE_INCOME=1500)],
                [cf("2025-12-31")], [2025])
    r = out[0]
    assert r["fiscal_year"] == 2025 and r["notice_date"] == "2026-04-30"
    assert r["debt_ratio"] == pytest.approx(0.7)
    assert r["current_ratio"] == pytest.approx(0.8)
    assert r["quick_ratio"] == pytest.approx(0.6)
    assert r["cash_to_short_debt"] == pytest.approx(90 / 150)       # short debt = 100 + 50 (+ blank bond)
    assert r["interest_bearing_debt_yi"] == pytest.approx(350 / 1e8)
    assert r["fcf_yi"] == pytest.approx(-30 / 1e8)
    assert r["gross_margin"] == pytest.approx(100 / 1200)
    assert r["roa"] == pytest.approx(-30 / 950)                     # average of 1000 and 900
    assert r["interest_coverage"] == pytest.approx(0 / 20)          # (-20 + 20) / 20
    assert r["revenue_yoy"] == pytest.approx(-0.2)
    assert r["loss_flag"] == 1
    assert r["raw_SHORT_LOAN"] == 100                               # raw inputs kept for audit


def test_year_without_balance_sheet_is_skipped():
    assert build([], [inc("2025-12-31")], [], [2025]) == []


def test_first_year_uses_end_balance_when_prior_missing():
    r = build([bal("2021-12-31")], [inc("2021-12-31")], [cf("2021-12-31")], [2021])[0]
    assert r["roa"] == pytest.approx(-30 / 1000)
    assert r["revenue_yoy"] is None


def test_negative_equity_is_flagged_and_roe_left_blank():
    r = build([bal("2025-12-31", TOTAL_PARENT_EQUITY=-50)], [inc("2025-12-31")], [cf("2025-12-31")], [2025])[0]
    assert r["negative_equity"] == 1 and r["roe"] is None
