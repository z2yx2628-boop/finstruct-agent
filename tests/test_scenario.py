import json

from src.network_view import SCENARIO_RULE_SCALE, overview_chart
from src.scenario import CAVEAT, build, layout

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
