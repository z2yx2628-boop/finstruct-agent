import math

from scripts.run_shock_study import (daily_returns, event_z, placebo_days, ranks, relative_window, select_events,
                                     spearman, verdict)


def test_ranks_average_ties():
    assert ranks([3, 1, 3, 2]) == [3.5, 1, 3.5, 2]


def test_spearman_perfect_and_reverse():
    assert math.isclose(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
    assert math.isclose(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
    assert spearman([1, 2], [1, 2]) is None


def test_daily_returns_need_previous_day_and_drop_jumps():
    cal = ["d1", "d2", "d3", "d4"]
    r = daily_returns({"d1": 10, "d2": 11, "d4": 11}, cal)
    assert math.isclose(r["d2"], math.log(1.1))
    assert "d3" not in r and "d4" not in r          # d3 missing, so d4 has no previous close
    assert daily_returns({"d1": 10, "d2": 7}, cal)["d2"] is None   # -35%: ex-rights jump


def test_relative_window_removes_the_common_move():
    cal = ["a", "b", "c"]
    ret = {"X": {"b": 0.03, "c": 0.01}, "Y": {"b": 0.01, "c": 0.01}, "Z": {"b": 0.02}}
    rel = relative_window(ret, cal, "b", ["X", "Y", "Z"])
    assert set(rel) == {"X", "Y"}                   # Z has no return on day c
    assert math.isclose(rel["X"], 0.01) and math.isclose(rel["Y"], -0.01)
    assert relative_window(ret, cal, "c", ["X"]) == {}   # the window runs past the calendar


def test_select_events_keeps_the_larger_of_close_shocks():
    cal = [f"d{i:02d}" for i in range(40)]
    shock = {"d05": 0.04, "d08": -0.06, "d30": 0.035, "d31": 0.01}
    assert select_events(shock, 0.03, cal) == [("d08", -0.06), ("d30", 0.035)]
    pool = placebo_days(shock, 0.03, [("d08", -0.06), ("d30", 0.035)], cal)
    assert "d31" not in pool and "d05" not in pool


def test_event_z_sign_and_minimum():
    x = {f"M{i}": i for i in range(10)}
    y = {f"M{i}": -i for i in range(10)}
    assert math.isclose(event_z(x, y, -1, 8)[0], 1.0)
    assert event_z(x, {"M1": 1}, 1, 8) == (None, 1)


def test_verdict():
    assert verdict(0.2, 0.01) == "通过"
    assert verdict(0.2, 0.2) == "方向一致但未显著"
    assert verdict(-0.1, 0.9) == "未通过"
