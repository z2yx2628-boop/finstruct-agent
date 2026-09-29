"""Event study helpers: pre-registered title patterns, loss events, statistics."""
from scripts.collect_credit_events import classify
from scripts.run_event_study import auc, fisher_greater, plus_year, table


def test_titles_are_classified_by_the_preregistered_patterns():
    assert classify("关于控股股东所持公司股份被司法冻结的公告") == "freeze"
    assert classify("关于公司股票被实施退市风险警示的公告") == "st"
    assert classify("关于为关联方提供担保逾期的公告") == "guarantee_default"
    assert classify("关于公司债券未能按期兑付的公告") == "debt_default"
    assert classify("关于主体信用评级下调的公告") == "rating"
    assert classify("关于法院裁定受理公司重整暨预重整的公告") == "restructuring"
    assert classify("2023年度审计报告（保留意见）") == "audit"


def test_releases_and_routine_titles_are_not_events():
    assert classify("关于控股股东所持公司股份解除司法冻结的公告") is None
    assert classify("关于撤销其他风险警示的公告") is None
    assert classify("关于为全资子公司提供担保的公告") is None
    assert classify("2024年年度报告摘要") is None


def test_fisher_matches_a_known_value():
    # [[3, 1], [1, 3]]: one-sided p = 17/70
    assert abs(fisher_greater(3, 1, 1, 3) - 17 / 70) < 1e-12


def test_auc_and_table():
    rows = [{"score": s, "y1": y, "weak": s >= 60, "hard": False} for s, y in
            ((80, True), (70, True), (65, False), (50, True), (40, False), (30, False))]
    assert abs(auc(rows) - 8 / 9) < 1e-12
    t = table(rows)
    assert (t["n_weak"], t["ev_weak"], t["n_other"], t["ev_other"]) == (3, 2, 3, 1)
    assert abs(t["lift"] - 2.0) < 1e-12


def test_window_is_twelve_months():
    assert plus_year("2023-04-30") == "2024-04-30"
