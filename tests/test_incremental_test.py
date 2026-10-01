import math

from scripts.run_incremental_test import auc, leave_one_year_out, permutation_p, reached, stratified_stat


def test_reached_needs_a_disclosed_step_before_the_mill():
    codes = {"A", "B", "C"}
    paths = [{"nodes": "A>G>B", "rules": "R3+R3"},          # group only: E2, not E1
             {"nodes": "A>C>X", "rules": "R1+R3"},          # guarantee reaches C
             {"nodes": "B>I>C", "rules": "R4+R4"},          # industry scenario: ignored
             {"nodes": "C>C", "rules": "R1"}]               # a seed never reaches itself
    assert reached(paths, codes, True) == {"C"}
    assert reached(paths, codes, False) == {"B", "C"}


def test_stratified_stat_and_permutation():
    rows = [{"e": i < 4, "y": i < 3, "s": "a"} for i in range(10)] + [{"e": False, "y": False, "s": "b"} for _ in range(10)]
    assert math.isclose(stratified_stat(rows, "e", "y", "s"), 3 - 4 * 0.3)
    obs, p = permutation_p(rows, "e", "y", "s", draws=2000)
    assert obs > 0 and p < 0.05


def test_auc_and_logistic_cv():
    assert auc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert auc([1, 2], [False, False]) is None
    rows = [{"as_of": f"y{i % 4}", "x": float(i), "y1": i >= 20} for i in range(40)]
    assert leave_one_year_out(rows, ["x"]) > 0.9
