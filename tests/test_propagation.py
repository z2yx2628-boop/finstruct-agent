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
