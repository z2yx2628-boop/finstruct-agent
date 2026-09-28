"""企业档案 recombines existing results; it must agree with the recorded backtest verdicts."""
from pathlib import Path

from src.network_view import filter_paths, key_paths, route
from src.profile import company_signals, fragility_rows, headline, peer_rank, split_paths

ROOT = Path(__file__).resolve().parents[1]


def profile(code: str, day: str, chain: str):
    rows = fragility_rows(day)
    row = next((r for r in rows if r["security_code"] == code), None)
    ranked, _, names = key_paths(ROOT / chain, ROOT / "data" / "snapshots" / day)
    mine = split_paths(filter_paths(ranked, company=code, hide_low_information=True, show_scenarios=False), code)
    return rows, row, mine, names


def test_antai_backtest_profile_shows_the_guarantee_path():
    _, row, mine, names = profile("600408", "2025-01-31", "data/chain/backtest_antai_fix1")
    assert row["tier"] == "weak"
    assert any(route(e, names) == "新泰钢铁 → 安泰集团" for _, e in mine["incoming"])
    level, _ = headline(row["security_name"], row, len(mine["incoming"]), len(mine["outgoing"]), len(mine["absorbed"]))
    assert level == "error"


def test_fangda_negative_case_is_not_an_alert():
    rows, row, mine, _ = profile("600507", "2025-02-28", "data/chain/analysis_v1_fix1")
    assert not mine["incoming"] and not mine["outgoing"]            # the only path is absorbed (score 0)
    level, text = headline(row["security_name"], row, 0, 0, len(mine["absorbed"]))
    assert level == "success" and "被吸收" in text
    assert peer_rank(rows, "600507") == (23, 24)


def test_signals_are_point_in_time_and_sourced():
    sig = company_signals(ROOT / "data" / "chain" / "backtest_linggang_fix1", "600231", "2024-04-30")
    assert sig and all(s["日期"] <= "2024-04-30" and s["来源"] for s in sig)
