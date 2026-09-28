import json

from src.network_view import SCENARIO_RULE_SCALE, overview_chart
from src.scenario import CAVEAT, build, layout, verified_product_links

FRAG = {"600231": {"tier": "weak"}, "600408": {"tier": "weak"}, "000761": {"tier": "weak"}}


def test_every_shock_kind_builds_a_graded_scenario_graph():
    cases = [dict(kind="price_up", product_id="P_COKE"), dict(kind="price_down", product_id="P_LONG"),
             dict(kind="outage", company="600231"), dict(kind="demand_down", sector_id="S_AUTO")]
    trade = {"edge_type": "supply", "basis": "disclosed", "src_id": "N_某焦化", "dst_id": "600010", "amount_wan": "150000",
             "category_text": "关联采购：焦炭", "source_doc": "x.json", "source_page": "4", "evidence_text": "焦炭 150,000"}
    for args in cases:
        r = build(as_of="2026-09-27", fragility=FRAG, chain_edges=[trade], **args)
        assert r["caveat"] == CAVEAT and r["edges"] and all(e["grade"] in ("A", "B", "C", "—") for e in r["edges"])
        nodes, edges = layout(r)
        json.dumps(overview_chart(nodes, edges, rule_scale=SCENARIO_RULE_SCALE))
    coke = build("price_up", "2026-09-27", FRAG, [trade], product_id="P_COKE")
    assert any(e["dst"] == "600010" and e["grade"] == "A" for e in coke["edges"])        # disclosed coke purchase
    assert any(e["dst"] == "600408" and e["grade"] == "B" for e in coke["edges"])        # 安泰 sells coke (own disclosure)
    long_down = build("price_down", "2026-09-27", FRAG, [], product_id="P_LONG")
    assert "002541" not in {e["dst"] for e in long_down["edges"]}                         # a steel-structure maker buys steel


def test_downstream_evidence_is_point_in_time():
    early = build("price_up", "2024-09-30", FRAG, [], product_id="P_FLAT")
    late = build("price_up", "2026-09-27", FRAG, [], product_id="P_FLAT")
    grade = lambda r, code: next(e["grade"] for e in r["edges"] if e["dst"] == code)
    assert grade(early, "000651") == "C" and grade(late, "000651") == "B"      # 格力 2025 annual report due 2026-04-30


def test_named_company_chains_are_point_in_time_and_keep_their_boundary():
    before_baosteel = verified_product_links("2024-01-23", "P_IRON_ORE")
    after_baosteel = verified_product_links("2024-01-24", "P_IRON_ORE")
    assert not any(r["dst_id"] == "600019" for r in before_baosteel)
    assert any(r["dst_id"] == "600019" and r["grade"] == "B" and r["scope_note"] for r in after_baosteel)

    result = build("price_up", "2026-09-28", FRAG, [], product_id="P_IRON_ORE")
    pairs = {(e["src"], e["dst"]): e for e in result["edges"]}
    assert pairs[("P_IRON_ORE", "600019")]["grade"] == "B"
    assert pairs[("600019", "600104")]["grade"] == "B"
    assert pairs[("P_IRON_ORE", "000932")]["grade"] == "B"
    assert pairs[("000932", "600031")]["grade"] == "B"
    assert all("边界：" in pairs[p]["evidence"] for p in (("P_IRON_ORE", "600019"), ("600019", "600104"),
                                                             ("P_IRON_ORE", "000932"), ("000932", "600031")))


def test_prospectus_suppliers_enter_coking_coal_scenario_as_a_grade():
    import csv
    from pathlib import Path
    from src.scenario import build
    root = Path(__file__).resolve().parents[1]
    with (root / "data" / "snapshots" / "2026-09-27" / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        fr = {r["security_code"]: r for r in csv.DictReader(f)}
    r = build("price_up", "2026-09-27", fr, [], product_id="P_COKING_COAL")
    s6 = [e for e in r["edges"] if e["rule"] == "S6"]
    assert s6 and all(e["grade"] == "A" and "募集说明书" in e["evidence"] for e in s6)
    assert any("G_ANSTEEL" == e["dst"] for e in s6)
    early = build("price_up", "2024-06-30", fr, [], product_id="P_COKING_COAL")      # 2024-12 tables not yet known
    assert not [e for e in early["edges"] if e["rule"] == "S6" and "2024-12" in e["effect"]]
