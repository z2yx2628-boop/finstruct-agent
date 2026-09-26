from src.propagation import Graph, propagate, seeds_from


def edge(t, s, d, amount=None, **kw):
    return {"edge_type": t, "src_id": s, "dst_id": d, "amount_wan": amount, "basis": kw.get("basis", "disclosed"),
            "source_doc": "doc.pdf", "source_page": 3, "evidence_text": "原文"}


def graph(edges, tiers, equity=None, groups=None, listed=None):
    return Graph(edges, {k: {"tier": v} for k, v in tiers.items()}, equity or {}, groups or {}, set(listed or []))


def test_r1_guarantee_passes_trouble_to_guarantor_with_evidence():
    g = graph([edge("guarantee", "ANTAI", "XINTAI", 280000)], {"ANTAI": "weak"})
    (p,) = propagate(g, "XINTAI", "credit", "high", "被银行起诉")
    s = p.steps[0]
    assert (s.rule, s.src, s.dst, s.dst_tier, s.decision) == ("R1", "XINTAI", "ANTAI", "weak", "continue")
    assert "doc.pdf 第3页" in s.evidence


def test_strong_company_absorbs_and_stops():
    g = graph([edge("guarantee", "BAO", "SUB", 1000), edge("guarantee", "X", "BAO", 1000)], {"BAO": "strong", "X": "weak"})
    (p,) = propagate(g, "SUB", "credit", "high", "")
    assert len(p.steps) == 1 and p.steps[0].decision == "absorbed"


def test_immaterial_amount_stops():
    g = graph([edge("guarantee", "BIG", "SUB", 100)], {"BIG": "weak"}, equity={"BIG": 1e11})
    (p,) = propagate(g, "SUB", "credit", "high", "")
    assert p.steps[0].decision == "immaterial"


def test_medium_weakens_and_low_ends():
    g = graph([edge("supply", "A", "B"), edge("supply", "B", "C")], {"B": "medium", "C": "medium"})
    (p,) = propagate(g, "A", "supply", "medium", "")
    assert [s.decision for s in p.steps] == ["weakened", "end"]


def test_supply_flows_down_credit_flows_up_trade_edges():
    g = graph([edge("supply", "MINE", "MILL")], {"MINE": "weak", "MILL": "weak"})
    assert propagate(g, "MINE", "supply", "high", "")[0].steps[0].dst == "MILL"
    assert propagate(g, "MILL", "credit", "high", "")[0].steps[0].dst == "MINE"


def test_r4_industry_reaches_only_weak_members_one_hop():
    edges = [edge("member_of", "MILL", "S_普钢", basis="industry_approx"),
             edge("industry", "S_普钢", "S_钢管", basis="industry_approx"),
             edge("member_of", "PIPE_WEAK", "S_钢管", basis="industry_approx"),
             edge("member_of", "PIPE_OK", "S_钢管", basis="industry_approx")]
    g = graph(edges, {"PIPE_WEAK": "weak", "PIPE_OK": "medium"})
    paths = propagate(g, "MILL", "supply", "high", "")
    assert [p.steps[-1].dst for p in paths] == ["PIPE_WEAK"] and paths[0].steps[0].basis == "industry_approx"


def test_r3_group_reaches_listed_members_for_credit_only():
    g = graph([], {"B": "strong"}, groups={"A": "G", "B": "G", "E_PARENT": "G"}, listed=["A", "B"])
    (p,) = propagate(g, "A", "credit", "high", "")
    assert p.steps[0].rule == "R3" and p.steps[0].dst == "B" and p.steps[0].decision == "absorbed"
    assert propagate(g, "A", "supply", "high", "") == []


def test_path_length_is_capped():
    edges = [edge("supply", f"N{i}", f"N{i+1}") for i in range(6)]
    g = graph(edges, {f"N{i}": "weak" for i in range(7)})
    (p,) = propagate(g, "N0", "supply", "high", "")
    assert len(p.steps) == 3


def test_seeds_respect_as_of_and_add_weak_companies():
    signals = [{"entity_id": "A", "date": "2026-05-01", "severity": "high", "signal_type": "supply_disruption"},
               {"entity_id": "B", "date": "2026-12-01", "severity": "high", "signal_type": "credit_event"}]
    seeds = seeds_from(signals, {"C": {"tier": "weak", "reasons": "负债率高"}}, "2026-09-24")
    assert {(s[0], s[1]) for s in seeds} == {("A", "supply"), ("C", "credit")}


def test_parallel_rows_between_two_companies_are_one_step():
    g = graph([edge("supply", "A", "B", 100), edge("supply", "A", "B", 300)], {"B": "weak"})
    (p,) = propagate(g, "A", "supply", "high", "")
    assert "共2行" in p.steps[0].evidence


def test_group_rule_is_used_at_most_once_per_path():
    g = graph([], {"B": "weak", "C": "weak"}, groups={"A": "G", "B": "G", "C": "G"}, listed=["A", "B", "C"])
    for p in propagate(g, "A", "credit", "high", ""):
        assert sum(s.rule == "R3" for s in p.steps) == 1


def test_summary_cuts_after_last_listed_company_and_ranks_weak_first():
    from src.propagation import summarize
    edges = [edge("supply", "A", "L1", 10000), edge("supply", "L1", "U1", 500), edge("supply", "L1", "U2", 700),
             edge("supply", "A", "L2", 10000)]
    g = graph(edges, {"L1": "weak", "L2": "medium"})
    ranked, reach = summarize(propagate(g, "A", "supply", "high", "停产"), listed={"A", "L1", "L2"})
    assert [e["steps"][-1].dst for e in ranked] == ["L1", "L2"]          # weak ranks above medium
    assert ranked[0]["beyond"] == {"U1", "U2"}                           # unlisted tail folded in


def test_opaque_guaranteed_party_becomes_a_seed_graded_by_guarantor_equity():
    edges = [{"edge_type": "guarantee", "src_id": "ANTAI", "dst_id": "E_XINTAI", "amount_wan": 280000,
              "relationship": "sister_company", "announcement_date": "2024-04-27"},
             {"edge_type": "guarantee", "src_id": "ANTAI", "dst_id": "SUB", "amount_wan": 280000,
              "relationship": "wholly_owned_subsidiary", "announcement_date": "2024-04-27"}]
    seeds = seeds_from([], {"ANTAI": {"tier": "weak"}}, "2025-01-31", edges, {"ANTAI": 1.6e9})
    assert ("E_XINTAI", "credit", "high") in {(s[0], s[1], s[2]) for s in seeds}
    assert all(s[0] != "SUB" for s in seeds)                           # subsidiaries are consolidated
    assert seeds_from([], {}, "2024-01-01", edges, {"ANTAI": 1.6e9}) == []   # not yet announced


def test_task_is_detected_from_the_title():
    from src.analyze import detect_task
    assert detect_task("关于2026年度日常关联交易预计的公告") == "related_party"
    assert detect_task("关于为全资子公司提供担保的公告") == "guarantee"
    assert detect_task("关于控股股东部分股份质押的公告") == "pledge"
    assert detect_task("关于3号高炉停产检修的公告") == "capacity"


def test_alert_card_renders_with_chinese_labels():
    from src.analyze import build_card, card_markdown
    from pathlib import Path
    doc = {"security_code": "600408", "company_name": "山西安泰集团股份有限公司", "announcement_date": "2024-04-26",
           "external_guarantee_balance": 0.0,
           "events": [{"event_type": "guarantee_limit", "relationship": "sister_company", "guarantee_amount": 10000,
                       "guarantee_unit": "万元", "guarantor": "山西安泰集团股份有限公司", "guaranteed_party": "山西新泰钢铁有限公司",
                       "source_page": 2, "evidence_text": "新泰钢铁\n民生银行"}]}
    card = build_card(doc, "doc.json", "2025-01-31", Path("no_such_chain"))
    text = card_markdown(card)
    assert "担保额度" in text and "同一控制下的兄弟公司" in text and "guarantee_limit" not in text


def test_evidence_is_shown_as_announcement_title_and_group_name():
    from src.sources import readable
    assert readable("data/reference/entities.csv：同属集团 G_ANSTEEL").startswith("同属鞍钢集团")
    text = readable("outputs/analysis_freeze/related_party/no_such_doc.json 第2页：甲\n乙")
    assert "第2页：甲 乙" in text


def test_unlisted_parent_group_gets_equity_weighted_proxy_tier_and_can_absorb():
    from src.propagation import group_proxies
    frag = {"600019": {"tier": "strong", "total_score": "15"}, "600581": {"tier": "weak", "total_score": "70"}}
    equity = {"600019": 2000e8, "600581": 10e8}
    groups = {"600019": "G_BAOWU", "600581": "G_BAOWU", "E_BAOWU": "G_BAOWU"}
    proxies = group_proxies(frag, equity, groups, {"600019", "600581"})
    assert proxies["E_BAOWU"]["tier"] == "strong" and proxies["E_BAOWU"]["proxy"] == 1
    g = Graph([edge("supply", "E_BAOWU", "600581", 10000)], frag, equity, groups, {"600019", "600581"})
    p = next(x for x in propagate(g, "600581", "credit", "high", "资不抵债") if x.steps[0].dst == "E_BAOWU")
    assert p.steps[0].decision == "absorbed" and "集团参照" in p.steps[0].note
