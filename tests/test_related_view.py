"""企业档案 · 关联风险: relation summary, group support, reasons for an empty result, finance-company reading."""
from src.related_view import deposit_reading, group_support, no_path_reasons, relation_summary


def test_relation_summary_merges_a_counterparty_and_sorts_by_amount():
    active = [{"edge_type": "supply", "src_id": "A", "dst_id": "P", "src_name": "甲", "dst_name": "母公司", "amount_wan": 50000},
              {"edge_type": "service", "src_id": "P", "dst_id": "A", "src_name": "母公司", "dst_name": "甲", "amount_wan": 10000},
              {"edge_type": "guarantee", "src_id": "A", "dst_id": "S", "src_name": "甲", "dst_name": "子公司", "amount_wan": 20000}]
    r = relation_summary(active, "A", {})
    assert r["by_type"] == {"购销": 1, "劳务": 1, "担保": 1} and r["partners"] == 2
    assert r["top"][0] == {"交易对手": "母公司", "关系": "劳务、购销", "金额(亿元)": 6.0, "方向": "对方→本企业 / 本企业→对方"}


def test_weak_member_of_strong_group_reads_as_support_not_guarantee():
    s = group_support("weak", "某集团", {"tier": "strong", "total_score": 20.7})
    assert "集团支持预期" in s["text"] and "不等于法律上的担保" in s["text"]
    assert "兜底能力有限" in group_support("weak", "某集团", {"tier": "medium", "total_score": 45})["text"]
    assert group_support("weak", None, None) is None


def test_empty_result_is_explained_by_the_most_specific_reason():
    cov = {"active": [{}] * 52, "expired": [], "latest": "", "tier": "weak"}
    why = no_path_reasons(cov, 0, {"tier": "strong"})
    assert len(why) == 1 and "承压为强的集团" in why[0]
    assert "都已过期" in no_path_reasons({"active": [], "expired": [{}], "latest": "2025-12-31", "tier": "weak"}, 0, None)[0]


def test_finance_company_net_borrower_negative_equity_and_stale_data():
    r = deposit_reading({"deposit_yi": 1.88, "loan_yi": 15.98, "period": "2025-06-30"}, -1.0, "2026-11-18")
    assert "净借入 14.10 亿元" in r["lines"][0] and r["equity_note"] == "净资产为负，无法计算" and r["stale"]
    r = deposit_reading({"deposit_yi": 100.0, "loan_yi": 3.0, "period": "2025-12-31"}, 5e10, "2026-11-18")
    assert "净存入 97.00 亿元" in r["lines"][0] and not r["stale"]
