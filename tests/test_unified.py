"""风险传导总图: one graph, two channels, labels keep the channels apart."""
from pathlib import Path

from src.network_view import filter_paths, key_paths, overview_chart
from src.scenario import build
from src.unified import CREDIT, SCALE, SUPPLY, credit_edges, layout, merge

ROOT = Path(__file__).resolve().parents[1]


def test_company_view_draws_both_channels_with_separate_labels():
    ranked, fr, names = key_paths(ROOT / "data" / "chain" / "live", ROOT / "data" / "snapshots" / "2026-09-27")
    entries = [e for _, e in filter_paths(ranked, company="600231", hide_low_information=True, show_scenarios=False) if e["score"] > 0]
    cn, ce = credit_edges(entries, names, fr)
    supply = build("outage", "2026-09-27", fr, [], company="600231")
    nodes, edges = layout(merge(supply, cn, ce))
    labels = {e["rule"] for e in edges}
    assert labels & set(CREDIT.values()) and labels & set(SUPPLY.values())
    assert all(e["rule"] in SCALE[0] for e in edges)
    assert overview_chart(nodes, edges, rule_scale=SCALE)["layer"]


def test_shock_view_without_credit_channel_still_lays_out():
    supply = build("price_up", "2026-09-27", {}, [], product_id="P_COKING_COAL")
    nodes, edges = layout(merge(supply, [], []))
    assert nodes and edges and min(n["x"] for n in nodes) == 0
