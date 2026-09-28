"""Sensitivity audit for fragility scores.

This module never changes the official snapshot. It recomputes the same disclosed
dimension scores under alternative thresholds and weight profiles so reviewers can
see whether a conclusion depends on one arbitrary parameter choice.
"""
from __future__ import annotations

from src.fragility import TIERS, WEIGHTS


DIMENSIONS = tuple(WEIGHTS)
THRESHOLDS = (55, 60, 65)
WEIGHT_PROFILES = {
    "当前权重": dict(WEIGHTS),
    "短期偿债偏重": {
        "leverage": 0.20, "liquidity": 0.30, "cash": 0.15,
        "profit": 0.10, "market": 0.10, "contingent": 0.15,
    },
    "盈利偏重": {
        "leverage": 0.20, "liquidity": 0.15, "cash": 0.15,
        "profit": 0.25, "market": 0.10, "contingent": 0.15,
    },
    "市场偏重": {
        "leverage": 0.15, "liquidity": 0.15, "cash": 0.15,
        "profit": 0.10, "market": 0.30, "contingent": 0.15,
    },
}


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_tier(total: float | None, weak_threshold: float = 60, medium_threshold: float = 40) -> str:
    """Return the score-only tier before red-line and post-report-event overrides."""
    if total is None:
        return ""
    return "weak" if total >= weak_threshold else "medium" if total >= medium_threshold else "strong"


def final_tier(row: dict, total: float | None, weak_threshold: float = 60) -> str:
    """Apply snapshot-visible rule overrides to a sensitivity result.

    Red lines always force weak. A post-report event downgrade is preserved only when
    the snapshot proves that the event changed the original base tier.
    """
    tier = score_tier(total, weak_threshold)
    if not tier:
        return ""
    if str(row.get("red_lines") or "").strip():
        return "weak"
    original_base = str(row.get("base_tier") or "")
    original_final = str(row.get("tier") or "")
    event_override = (_number(row.get("events_after_report")) or 0) > 0 and original_final != original_base
    if event_override:
        return TIERS[min(TIERS.index(tier) + 1, len(TIERS) - 1)]
    return tier


def weighted_total(row: dict, weights: dict[str, float]) -> float | None:
    """Reweight available dimension scores, renormalising missing dimensions."""
    available = [(dimension, _number(row.get(f"score_{dimension}"))) for dimension in DIMENSIONS]
    available = [(dimension, value) for dimension, value in available if value is not None]
    denominator = sum(weights[dimension] for dimension, _ in available)
    if not available or denominator <= 0:
        return None
    return round(sum(weights[dimension] * value for dimension, value in available) / denominator, 1)


def threshold_rows(rows: list[dict], thresholds: tuple[int, ...] = THRESHOLDS) -> list[dict]:
    """One display row per company for the requested weak-tier thresholds."""
    out = []
    for row in rows:
        total = _number(row.get("total_score"))
        item = {
            "security_code": row.get("security_code", ""),
            "security_name": row.get("security_name", ""),
            "total_score": total,
            "official_tier": row.get("tier", ""),
        }
        item.update({f"threshold_{threshold}": final_tier(row, total, threshold) for threshold in thresholds})
        item["threshold_stable"] = len({item[f"threshold_{threshold}"] for threshold in thresholds}) <= 1
        out.append(item)
    return out


def profile_rows(rows: list[dict], profiles: dict[str, dict[str, float]] = WEIGHT_PROFILES) -> list[dict]:
    """Recompute score, tier and rank under each disclosed weight profile."""
    results: list[dict] = []
    baseline_rank: dict[str, int] = {}
    for profile, weights in profiles.items():
        calculated = [(row, weighted_total(row, weights)) for row in rows]
        calculated.sort(key=lambda item: (item[1] is not None, item[1] or -1), reverse=True)
        for rank, (row, total) in enumerate(calculated, start=1):
            code = str(row.get("security_code", ""))
            if profile == "当前权重":
                baseline_rank[code] = rank
            results.append({
                "profile": profile,
                "security_code": code,
                "security_name": row.get("security_name", ""),
                "score": total,
                "tier": final_tier(row, total),
                "rank": rank,
                "official_tier": row.get("tier", ""),
            })
    for item in results:
        item["rank_change"] = item["rank"] - baseline_rank.get(item["security_code"], item["rank"])
        item["tier_changed"] = item["tier"] != item["official_tier"]
    return results


def profile_summary(rows: list[dict]) -> list[dict]:
    details = profile_rows(rows)
    out = []
    for profile in WEIGHT_PROFILES:
        group = [item for item in details if item["profile"] == profile]
        shifts = [abs(item["rank_change"]) for item in group]
        out.append({
            "profile": profile,
            "companies": len(group),
            "tier_changes": sum(item["tier_changed"] for item in group),
            "max_rank_shift": max(shifts, default=0),
            "mean_rank_shift": round(sum(shifts) / len(shifts), 2) if shifts else 0,
        })
    return out
