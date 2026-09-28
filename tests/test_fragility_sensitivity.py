import pytest

from src.fragility_sensitivity import (final_tier, profile_rows, score_tier,
                                       threshold_rows, weighted_total)


def row(code="A", total=59.1, tier="medium", base_tier="medium", red_lines="", events=0, **scores):
    item = {
        "security_code": code, "security_name": code, "total_score": total,
        "tier": tier, "base_tier": base_tier, "red_lines": red_lines,
        "events_after_report": events,
    }
    for dimension in ("leverage", "liquidity", "cash", "profit", "market", "contingent"):
        item[f"score_{dimension}"] = scores.get(dimension, 50)
    return item


def test_59_1_is_threshold_sensitive_without_changing_official_tier():
    result = threshold_rows([row()])[0]
    assert result["threshold_55"] == "weak"
    assert result["threshold_60"] == "medium"
    assert result["threshold_65"] == "medium"
    assert result["official_tier"] == "medium"
    assert result["threshold_stable"] is False


def test_red_line_remains_weak_under_every_threshold():
    item = row(total=30, tier="weak", base_tier="strong", red_lines="资不抵债")
    assert all(threshold_rows([item])[0][f"threshold_{value}"] == "weak" for value in (55, 60, 65))


def test_event_downgrade_is_preserved_when_snapshot_proves_it():
    item = row(total=30, tier="medium", base_tier="strong", events=1)
    assert final_tier(item, 30, 60) == "medium"


def test_weighted_total_renormalises_missing_dimensions():
    item = row(leverage=100, liquidity=None, cash=None, profit=None, market=0, contingent=None)
    weights = {"leverage": 0.2, "liquidity": 0.2, "cash": 0.15,
               "profit": 0.15, "market": 0.15, "contingent": 0.15}
    assert weighted_total(item, weights) == pytest.approx(57.1, abs=0.1)


def test_weight_profiles_expose_rank_changes():
    leverage_weak = row("L", leverage=100, liquidity=0, cash=0, profit=0, market=0, contingent=0)
    market_weak = row("M", leverage=0, liquidity=0, cash=0, profit=0, market=100, contingent=0)
    details = profile_rows([leverage_weak, market_weak])
    market_profile = {item["security_code"]: item for item in details if item["profile"] == "市场偏重"}
    assert market_profile["M"]["rank"] < market_profile["L"]["rank"]
    assert score_tier(60) == "weak" and score_tier(59.9) == "medium"
