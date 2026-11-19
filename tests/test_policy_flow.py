from src.policy_flow import POLICY_KINDS, bridge_candidates, margin_context, policy_flows


def rows():
    return [{"code": "000761", "name": "本钢板材", "tier": "weak", "overseas_share": 0.2, "overseas_source": "年报分地区收入（B）",
             "cbam_per_ton": 63.0, "route": "BF-BOF", "route_verified": False, "index": 4.0},
            {"code": "600019", "name": "宝钢股份", "tier": "strong", "overseas_share": 0.1, "overseas_source": "年报分地区收入（A）",
             "cbam_per_ton": 63.0, "route": "BF-BOF", "route_verified": True, "index": 1.0},
            {"code": "600231", "name": "凌钢股份", "tier": "medium", "overseas_share": None, "overseas_source": "",
             "cbam_per_ton": 63.0, "route": "BF-BOF", "route_verified": False, "index": None}]


def test_policy_flows_rank_and_scale():
    f = policy_flows("policy_export", rows())
    assert [r["name"] for r in f["right"]] == ["本钢板材", "宝钢股份"]        # undisclosed share is left out, not filled
    assert f["right"][0]["strength"] == 1.0 and f["right"][1]["strength"] == 0.25
    assert f["right"][1]["grade"] == "A" and f["left"] == []
    assert "CBAM 63 元/吨出口" in policy_flows("policy_carbon", rows())["right"][0]["channel"]


def test_bridge_only_weak_or_medium_with_share():
    assert bridge_candidates(policy_flows("policy_export", rows())) == ["000761"]
    assert set(POLICY_KINDS) == {"policy_carbon", "policy_export"}


def test_margin_context_reads_futures():
    lines = margin_context("P_COKING_COAL", "2026-11-18")
    assert lines and lines[0].startswith("焦化吨焦盘面利润") and "分位" in lines[0]
