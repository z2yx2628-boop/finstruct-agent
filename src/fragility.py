"""Fragility score (承压评分): can the company absorb a shock right now?

Three layers, all point-in-time for a given `as_of` date:
  financial - latest public quarterly period, ranked against the peer group (24 core mills)
  market    - 60-day excess return, drawdown, volatility, ranked against peers
  events    - high-severity risk signals published after that period (direction 1)
Score 0 (strongest) .. 100 (weakest) per metric = peer percentile; dimension = mean of its
metrics; total = weighted mean of available dimensions. Tiers: >=60 weak, >=40 medium, else
strong; absolute red lines and events can only make the tier worse. Every tier comes with the
reasons that produced it.
"""
from __future__ import annotations

from src.quarterly import available_by

# metric -> (dimension, +1 if higher is worse / -1 if lower is worse, label, format)
METRICS = {
    "debt_ratio": ("leverage", +1, "资产负债率", "pct"),
    "current_ratio": ("liquidity", -1, "流动比率", "x"),
    "quick_ratio": ("liquidity", -1, "速动比率", "x"),
    "cash_ratio": ("liquidity", -1, "现金比率", "x"),
    "ocf_to_revenue": ("cash", -1, "经营现金流/收入", "pct"),
    "net_margin": ("profit", -1, "净利率", "pct"),
    "gross_margin": ("profit", -1, "毛利率", "pct"),
    "revenue_growth": ("profit", -1, "收入增长", "pct"),
    "excess_ret_60d": ("market", -1, "60日超额收益", "pct"),
    "max_drawdown_60d": ("market", -1, "60日最大回撤", "pct"),
    "vol_20d": ("market", +1, "20日波动率", "pct"),
}
WEIGHTS = {"leverage": 0.2, "liquidity": 0.25, "cash": 0.15, "profit": 0.2, "market": 0.2}
DIMENSION_LABEL = {"leverage": "杠杆", "liquidity": "短期偿债", "cash": "造血", "profit": "盈利", "market": "市场"}
TIERS = ["strong", "medium", "weak"]
TIER_LABEL = {"strong": "强", "medium": "中", "weak": "弱"}
EVENT_TYPES = {"credit_event", "supply_disruption", "share_pledge", "credit_exposure"}


def fmt(value: float, kind: str) -> str:
    return f"{value * 100:.1f}%" if kind == "pct" else f"{value:.2f}"


def percentile_scores(rows: list[dict], metric: str, direction: int,
                      reference: list[dict] | None = None) -> dict[str, tuple[float, int, int]]:
    """code -> (score 0..100 where 100 = weakest, rank from weakest, n).

    Ranked against `reference` (default: the rows themselves). A company outside the peer group
    is placed within the peers' distribution without changing the peers' own scores."""
    ref = [r[metric] for r in (reference if reference is not None else rows) if r.get(metric) is not None]
    n = len(ref)
    if n < 2:
        return {}
    out = {}
    for r in rows:
        value = r.get(metric)
        if value is None:
            continue
        worse = sum(1 for v in ref if direction * v > direction * value)
        ties = sum(1 for v in ref if v == value) - (1 if reference is None else 0)
        score = 100 * (1 - (worse + max(ties, 0) / 2) / (n - 1 if reference is None else n))
        out[r["security_code"]] = (max(0.0, min(100.0, score)), 1 + worse, n)
    return out


def red_lines(row: dict) -> list[str]:
    reasons = []
    if row.get("negative_equity") == 1:
        reasons.append("资不抵债（净资产为负）")
    if row.get("debt_ratio") is not None and row["debt_ratio"] >= 0.85:
        reasons.append(f"资产负债率{fmt(row['debt_ratio'], 'pct')}≥85%")
    return reasons


def score(rows: list[dict], signals: list[dict], as_of: str, period_public: str,
          extra: list[dict] | None = None) -> list[dict]:
    """rows: one dict per peer company (security_code, security_name, metric fields).
    extra: companies outside the peer group, scored against the peers' distribution."""
    per_metric = {m: percentile_scores(rows, m, d) for m, (_, d, _, _) in METRICS.items()}
    for m, (_, d, _, _) in METRICS.items():
        per_metric[m].update(percentile_scores(extra or [], m, d, reference=rows))
    peer_codes = {r["security_code"] for r in rows}
    rows = rows + list(extra or [])
    report_public = available_by(period_public)  # events after this date are not in the financials
    results = []
    for row in rows:
        code = row["security_code"]
        dims, notes = {}, []
        for metric, (dim, _, label, kind) in METRICS.items():
            if code in per_metric[metric]:
                s, rank, n = per_metric[metric][code]
                dims.setdefault(dim, []).append(s)
                where = f"{n}家中第{rank}弱" if code in peer_codes else f"弱于{n}家核心钢厂中的{n - rank + 1}家"
                notes.append((s, f"{label}{fmt(row[metric], kind)}（{where}）"))
        dim_scores = {d: sum(v) / len(v) for d, v in dims.items()}
        weight = sum(WEIGHTS[d] for d in dim_scores)
        total = sum(WEIGHTS[d] * s for d, s in dim_scores.items()) / weight if weight else None
        tier = None if total is None else ("weak" if total >= 60 else "medium" if total >= 40 else "strong")
        reasons = [t for s, t in sorted(notes, reverse=True)[:3] if s >= 60]
        base_tier = tier
        lines = red_lines(row)
        if lines:
            tier = "weak"
            reasons = lines + reasons
        events = [s for s in signals if s.get("entity_id") == code and report_public < s.get("date", "") <= as_of
                  and s.get("signal_type") in EVENT_TYPES]
        serious = [s for s in events if s.get("severity") == "high" or s.get("signal_type") == "credit_event"]
        if serious and tier is not None:
            tier = TIERS[min(TIERS.index(tier) + 1, 2)]
            reasons.append("财报后事件：" + "；".join(f"{s['date']} {s['signal_type']}（{s.get('detail', '')}）"
                                                  for s in serious[:2]))
        results.append({
            "as_of": as_of, "security_code": code, "security_name": row.get("security_name", ""),
            "peer_group": "core" if code in peer_codes else "other",
            "period": row.get("period", ""), "total_score": None if total is None else round(total, 1),
            **{f"score_{d}": round(dim_scores[d], 1) if d in dim_scores else None for d in WEIGHTS},
            "base_tier": base_tier or "", "tier": tier or "", "tier_label": TIER_LABEL.get(tier, ""),
            "red_lines": "；".join(lines), "events_after_report": len(events),
            "reasons": "；".join(reasons),
        })
    return sorted(results, key=lambda r: -(r["total_score"] or 0))
