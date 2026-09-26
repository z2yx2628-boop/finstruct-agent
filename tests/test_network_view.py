from src.network_view import evidence_ref, filter_paths, is_low_information, path_rows, score_parts, stop_reason
from src.propagation import Step


def step(rule, src, dst, tier="weak", amount=None, decision="continue", severity="medium", evidence="x"):
    return Step(rule=rule, src=src, dst=dst, shock="credit", severity=severity, dst_tier=tier, decision=decision,
                basis="disclosed", evidence=evidence, amount_wan=amount)


GUARANTEE = {"seed": "E_G", "reason": "r", "score": 2.45, "amount_yi": 27.44, "listed_reach": 0.5,
             "steps": [step("R1", "E_G", "600231", tier="medium", amount=274400.0)], "beyond": set()}
SAME_GROUP = {"seed": "600019", "reason": "r", "score": 2.0, "amount_yi": 0.0, "listed_reach": 1.0,
              "steps": [step("R3", "600019", "600808")], "beyond": set()}
NAMES = {"E_G": "凌钢集团", "600231": "凌钢股份", "600019": "宝钢股份", "600808": "马钢股份"}


def test_filter_is_display_only_and_keeps_original_rank():
    ranked = [SAME_GROUP, GUARANTEE]
    assert [i for i, _ in filter_paths(ranked, hide_low_information=True)] == [1]
    assert [i for i, _ in filter_paths(ranked, rules={"R3"})] == [0]
    assert [i for i, _ in filter_paths(ranked, min_amount_yi=10)] == [1]
    assert [i for i, _ in filter_paths(ranked, company="600808")] == [0]
    assert is_low_information(SAME_GROUP) and not is_low_information(GUARANTEE)
    row = path_rows([(1, GUARANTEE)], NAMES)[0]
    assert row["排名"] == 2 and row["传导路径"] == "凌钢集团 → 凌钢股份" and row["规则"] == "担保"


def test_score_parts_reproduce_the_score():
    p = score_parts(GUARANTEE)
    assert p["severity_weight"] == 2 and p["reach"] == 0.5
    assert abs(p["severity_weight"] * p["amount_factor"] * p["reach"] - GUARANTEE["score"]) < 0.01


def test_evidence_reference_and_stop_reason():
    ref = evidence_ref("outputs/backtest_linggang_freeze/guarantee/backtest_linggang_033_600231_guarantee_backtest.json 第4页：担保明细")
    assert ref == {"stem": "backtest_linggang_033_600231_guarantee_backtest", "page": 4, "quote": "担保明细"}
    assert evidence_ref("data/reference/entities.csv：同属集团 G_BAOWU")["stem"] is None
    absorbed = dict(GUARANTEE, steps=[step("R3", "600581", "E_BAOWU", tier="strong", decision="absorbed")])
    assert "被吸收" in stop_reason(absorbed, NAMES)


def test_overview_layout_is_layered_and_serialisable():
    import json
    from src.network_view import overview_chart, overview_layout
    chain = {"seed": "600231", "reason": "r", "score": 4.0, "amount_yi": 74.8, "listed_reach": 1.0, "beyond": set(),
             "steps": [step("R2", "600231", "E_G", tier="medium", amount=748000.0), step("R3", "E_G", "000761")]}
    back = {"seed": "E_G", "reason": "r", "score": 2.0, "amount_yi": 1.0, "listed_reach": 1.0, "beyond": set(),
            "steps": [step("R1", "E_G", "600231", amount=10000.0)]}
    nodes, edges = overview_layout([(0, chain), (1, back)], {}, NAMES, chosen=0)
    x = {n["node"]: n["x"] for n in nodes}
    assert x["600231"] < x["E_G"] < x["000761"]                      # forward edges go left to right
    assert {e["on"] for e in edges if e["edge"].startswith("E_G|600231")} == {False}
    assert overview_layout([(0, chain), (1, back)], {}, NAMES, chosen=0) == (nodes, edges)   # deterministic
    spec = overview_chart(nodes, edges)
    json.dumps(spec)
    assert [p["name"] for p in spec["params"]] == ["company", "link"]
    assert {v for p in spec["params"] for v in p["views"]} <= {layer["name"] for layer in spec["layer"]}
