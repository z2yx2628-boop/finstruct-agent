"""集团内 / 跨集团关联方 labels (display only) and the gated bridge between the two channels."""
from pathlib import Path

from src.network_view import edge_scope, key_paths, second_order

ROOT = Path(__file__).resolve().parents[1]


def test_subsidiary_is_in_group_even_when_its_group_is_unresolved():
    assert edge_scope({"edge_type": "guarantee", "same_group": "0", "relationship": "wholly_owned_subsidiary"}) == "in_group"
    assert edge_scope({"edge_type": "supply", "same_group": "0", "relationship": "associate_or_joint_venture"}) == "cross_group"
    assert edge_scope({"edge_type": "supply", "same_group": "1", "relationship": "other_related_party"}) == "in_group"
    assert edge_scope({"edge_type": "industry", "same_group": "0", "relationship": ""}) == "industry"


def test_second_order_uses_the_same_engine_and_never_touches_the_ranking():
    chain, snap = ROOT / "data" / "chain" / "live", ROOT / "data" / "snapshots" / "2026-09-27"
    before, _, _ = key_paths(chain, snap)
    found = second_order(chain, snap, ["600231"], "supply")
    after, _, _ = key_paths(chain, snap)
    assert [e["score"] for e in before] == [e["score"] for e in after]
    assert all(e["seed"] == "600231" and e["score"] > 0 for e in found["600231"])
