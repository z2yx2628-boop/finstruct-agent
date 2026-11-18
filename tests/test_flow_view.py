"""风险传导 page: paths regrouped by their far end, middle hops merged into one channel, strongest first."""
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from src.flow_view import conclusion, credit_flows, flow_chart, layered_chart, level, supply_flows, supply_strength

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _step(src, dst, rule="R1", amount=None):
    return SimpleNamespace(src=src, dst=dst, rule=rule, amount_wan=amount, basis="disclosed", evidence="e", dst_tier="")


def test_supply_hops_are_merged_and_disclosed_links_rank_first():
    supply = {"nodes": [{"node": "SHOCK", "name": "冲击", "kind": "冲击"}, {"node": "M", "name": "钢厂", "kind": "企业"},
                        {"node": "P", "name": "板材", "kind": "产品"}, {"node": "S", "name": "汽车", "kind": "行业"},
                        {"node": "U", "name": "车企", "kind": "企业", "tier": "strong"},
                        {"node": "C", "name": "客户", "kind": "企业", "tier": "weak"}],
              "edges": [{"src": "SHOCK", "dst": "M", "grade": "—", "effect": "停产", "evidence": "", "share": None, "amount_wan": None},
                        {"src": "M", "dst": "P", "grade": "B", "effect": "板材供给↓", "evidence": "", "share": 0.6, "amount_wan": None},
                        {"src": "P", "dst": "S", "grade": "C", "effect": "汽车用钢", "evidence": "", "share": None, "amount_wan": None},
                        {"src": "S", "dst": "U", "grade": "C", "effect": "供给↓", "evidence": "", "share": None, "amount_wan": None},
                        {"src": "M", "dst": "C", "grade": "A", "effect": "供货中断（披露销售 20 亿元）", "evidence": "x",
                         "share": None, "amount_wan": 200000}]}
    right = supply_flows(supply, "M")["right"]
    assert [r["name"] for r in right] == ["客户", "车企"]
    assert right[1]["channel"] == "板材 → 汽车 · 供给↓" and right[1]["grade"] == "C"
    assert right[0]["channel"] == "供货中断" and level(right[0]["strength"]) == "高"


def test_credit_paths_split_into_sources_and_targets():
    a_to_b = {"seed": "A", "steps": [_step("A", "B"), _step("B", "C", "R2")], "score": 2.0, "amount_yi": 1.0}
    b_to_d = {"seed": "B", "steps": [_step("B", "D")], "score": 1.0, "amount_yi": 0.0}
    f = credit_flows([a_to_b, b_to_d], {}, {}, focus="B")
    assert [r["node"] for r in f["left"]] == ["A"]
    assert {r["node"] for r in f["right"]} == {"C", "D"}
    assert f["right"][0]["node"] == "C" and f["right"][0]["strength"] == 1.0
    assert conclusion("乙", f, {"left": [], "right": []})[0] == "error"


def test_strength_and_chart_shape():
    assert supply_strength("A", amount_wan=1e6) > supply_strength("B", share=0.3) > supply_strength("C")
    rows = [{"name": f"企业{i}", "tier": "", "channel": "担保", "grade": "A", "strength": 1 - i / 20, "size": "—"} for i in range(12)]
    spec = flow_chart("起点", "weak", [], rows, "credit", top=8)
    edges = spec["layer"][0]["data"]["values"]
    assert len(edges) == 8 and edges[0]["w"] > edges[-1]["w"]


def test_page_switches_between_channels():
    app = AppTest.from_file(APP_PATH, default_timeout=90).run()
    app.switch_page("views/8_风险传导总图.py").run()
    assert not app.exception
    app.session_state["u_channel"] = "supply"
    app.run()
    assert not app.exception


def test_full_graph_has_columns_and_no_line_text():
    result = {"nodes": [{"node": "SHOCK", "name": "冲击", "kind": "冲击"}, {"node": "P", "name": "矿", "kind": "产品"},
                        {"node": "A", "name": "甲", "kind": "企业", "tier": "weak"}, {"node": "B", "name": "乙", "kind": "企业"}],
              "edges": [{"src": "SHOCK", "dst": "P", "grade": "—", "effect": "涨"}, {"src": "P", "dst": "A", "grade": "A", "effect": "成本↑"},
                        {"src": "P", "dst": "B", "grade": "C", "effect": "成本↑"}]}
    spec = layered_chart(result)
    assert [h["label"] for h in spec["layer"][3]["data"]["values"]] == ["冲击", "产品", "企业"]
    assert all(layer["mark"]["type"] != "text" for layer in spec["layer"][:1])
