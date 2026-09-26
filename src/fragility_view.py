"""Explain one fragility score for the web page: data sources, per-metric ranks, dimension
contributions, rules that fired, and the announcements behind guarantee exposure and events.

Everything is recomputed from the snapshot's own quarterly_metrics.csv with the same functions the
score used (src.fragility), so the page can show *why* a company got its score, not a second opinion.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.entity_resolver import ROOT
from src.fragility import (ABSOLUTE, DIMENSION_LABEL, EVENT_TYPES, EXTREME, EXTREME_DIMS, METRICS, VERSION_NOTES,
                           WEIGHTS, fmt, percentile_scores, red_lines)
from src.quarterly import available_by

SNAP = ROOT / "data" / "snapshots"
# Snapshots made before meta.json existed: which signals file fed them (recorded 2026-09-27 from the run log).
KNOWN_SIGNALS = {"2024-04-30": "data/chain/backtest_linggang/signals.csv",
                 "2025-04-30": "data/chain/backtest_linggang/signals.csv",
                 "2025-01-31": "data/chain/backtest_antai/signals.csv",
                 "2025-02-28": "data/chain/analysis_v1/signals.csv",
                 "2026-09-26": "data/chain/live/signals.csv"}
SOURCES = {"financial": "新浪财经 财务摘要（季度，akshare）；年报三大报表来自东方财富（akshare）",
           "market": "新浪财经 日线行情（失败时东方财富）",
           "quality": "原始财务数据经年报人工抽查 30/30 项一致（docs/financial_indicators.md）"}
REPORT_PAGES = {"年报": "ndbg", "半年报": "zqbg", "一季报": "yjdbg", "三季报": "sjdbg"}
NUMERIC_SKIP = {"security_code", "security_name", "period", "available_by", "last_trade_date", "guarantee_exposure_basis"}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in NUMERIC_SKIP or v in (None, ""):
            out[k] = v if v not in ("",) else None
            continue
        try:
            out[k] = float(v)
        except ValueError:
            out[k] = v
    if out.get("negative_equity") is not None:
        out["negative_equity"] = int(out["negative_equity"])
    return out


def snapshot_meta(folder: Path) -> dict:
    """meta.json when the snapshot has one; otherwise the method version inferred from its columns."""
    meta_path = folder / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    header = (folder / "fragility.csv").read_text(encoding="utf-8-sig").split("\n", 1)[0]
    metrics = (folder / "quarterly_metrics.csv").read_text(encoding="utf-8-sig").split("\n", 1)[0] \
        if (folder / "quarterly_metrics.csv").exists() else ""
    version = "v1" if "guarantee_exposure_basis" in metrics else "v1-early" if "score_contingent" in header else "v0"
    return {"version": version, "inferred": True, "signals": KNOWN_SIGNALS.get(folder.name)}


def version_note(version: str) -> str:
    return VERSION_NOTES.get(version, "对外担保维度的早期版本（未使用累计担保余额）" if version == "v1-early" else version)


def compared_snapshot(folder: Path) -> Path | None:
    """The snapshot that changes.md compared against (the latest earlier one), as update_all does."""
    older = sorted(d for d in SNAP.glob("*") if d.is_dir() and d.name < folder.name and (d / "fragility.csv").exists())
    return older[-1] if older else None


def explain(folder: Path, code: str) -> dict | None:
    fragility = {r["security_code"]: r for r in _read(folder / "fragility.csv")}
    metrics = {r["security_code"]: _num(r) for r in _read(folder / "quarterly_metrics.csv")}
    if code not in fragility or code not in metrics:
        return None
    core = [metrics[c] for c, r in fragility.items() if r.get("peer_group") == "core" and c in metrics]
    is_core = fragility[code].get("peer_group") == "core"
    row = metrics[code]
    dims: dict[str, list[dict]] = {}
    raw: dict[str, list[float]] = {}
    for metric, (dim, direction, label, kind) in METRICS.items():
        value = row.get(metric)
        if value is None:
            continue
        ranked = percentile_scores(core, metric, direction) if is_core else \
            percentile_scores([row], metric, direction, reference=core)
        if code not in ranked:
            continue
        s, rank, n = ranked[code]
        where = f"{n}家中第{rank}弱" if is_core else f"比{n}家核心钢厂中的{n - rank + 1}家更差"
        raw.setdefault(dim, []).append(s)
        dims.setdefault(dim, []).append({"metric": label, "value": fmt(value, kind), "rank": where, "score": round(s, 1),
                                         "direction": "越高越弱" if direction > 0 else "越低越弱"})
    for metric, (dim, label, cap) in ABSOLUTE.items():
        value = row.get(metric)
        if value is not None:
            raw.setdefault(dim, []).append(min(100.0, 100 * value / cap))
            dims.setdefault(dim, []).append({"metric": label, "value": fmt(value, "pct"), "rank": f"绝对值（{fmt(cap, 'pct')}即满分）",
                                             "score": round(min(100.0, 100 * value / cap), 1), "direction": "越高越弱"})
    dim_scores = {d: sum(v) / len(v) for d, v in raw.items()}
    weight = sum(WEIGHTS[d] for d in dim_scores) or 1.0
    table = [{"dimension": DIMENSION_LABEL[d], "score": round(dim_scores[d], 1), "weight": WEIGHTS[d],
              "effective_weight": round(WEIGHTS[d] / weight, 3), "contribution": round(WEIGHTS[d] / weight * dim_scores[d], 1),
              "metrics": dims[d]} for d in WEIGHTS if d in dim_scores]
    rules = red_lines(row) + [f"单一维度极差：{DIMENSION_LABEL[d]} {dim_scores[d]:.0f} 分 ≥ {EXTREME}"
                              for d in EXTREME_DIMS if dim_scores.get(d, 0) >= EXTREME]
    return {"row": row, "result": fragility[code], "dimensions": table, "rules": rules,
            "total_recomputed": round(sum(WEIGHTS[d] / weight * dim_scores[d] for d in dim_scores), 1),
            "missing_weight": [DIMENSION_LABEL[d] for d in WEIGHTS if d not in dim_scores]}


def data_sources(row: dict) -> list[tuple[str, str]]:
    period = str(row.get("period") or "")
    kind = {"0331": "一季报", "0630": "半年报", "0930": "三季报", "1231": "年报"}.get(period[4:], "")
    public = row.get("available_by") or (available_by(period) if period else "")
    return [("财报期", f"{period[:4]}-{period[4:6]}-{period[6:]}（{kind}）" if len(period) == 8 else period or "无"),
            ("可使用日", f"{public}（法定披露截止日，之前不使用该期数据）" if public else "—"),
            ("财报来源", SOURCES["financial"]), ("行情截至", row.get("last_trade_date") or "无"),
            ("行情来源", SOURCES["market"]), ("数据质量", SOURCES["quality"])]


def report_links(code: str) -> dict[str, str]:
    base = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_Bulletin/stockid/{code}/page_type/{page}.phtml"
    return {label: base.format(code=code, page=page) for label, page in REPORT_PAGES.items()}


def _signals(folder: Path) -> list[dict]:
    path = snapshot_meta(folder).get("signals")
    return _read(ROOT / path) if path else []


def _source_of(signal: dict) -> str:
    from src.sources import titles
    stem = Path(signal.get("source_doc", "")).stem
    page = signal.get("source_page")
    return f"{titles().get(stem, stem)}{f' 第{page}页' if page else ''}"


def guarantee_evidence(folder: Path, code: str) -> list[dict]:
    """The announcements behind the guarantee exposure, selected exactly as update_all does."""
    from src.validity import is_active
    as_of = folder.name
    out = []
    for s in _signals(folder):
        if s.get("entity_id") != code or s.get("magnitude") in (None, "") or not is_active(s, as_of):
            continue
        if s.get("signal_type") == "guarantee_balance" or (
                s.get("signal_type") in ("credit_exposure", "credit_event") and s.get("severity") in ("medium", "high")):
            out.append({"日期": s.get("date", ""), "类型": "累计对外担保余额" if s["signal_type"] == "guarantee_balance" else "新增担保",
                        "金额(亿元)": round(float(s["magnitude"]) / 1e4, 2), "说明": (s.get("detail") or "")[:60],
                        "来源": _source_of(s)})
    return sorted(out, key=lambda r: r["日期"], reverse=True)


def events_after_report(folder: Path, code: str, period: str) -> list[dict]:
    public = available_by(period) if period else ""
    return [{"日期": s.get("date", ""), "类型": s.get("signal_type", ""), "严重度": s.get("severity", ""),
             "说明": (s.get("detail") or "")[:60], "来源": _source_of(s)}
            for s in _signals(folder) if s.get("entity_id") == code and public < s.get("date", "") <= folder.name
            and s.get("signal_type") in EVENT_TYPES]
