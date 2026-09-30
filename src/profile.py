"""Company profile (企业档案): one company's own risk and its related-party risk on one page.

Display only: it recombines what the other pages already compute (fragility snapshot, key paths,
product exposure, signals); nothing here changes a score or a ranking.
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.entity_resolver import ROOT
from src.validity import is_active

SIGNAL_LABEL = {"credit_exposure": "新增担保/担保敞口", "credit_event": "信用事件（冻结、违约、风险警示等）", "guarantee_balance": "累计对外担保余额",
                "supply_disruption": "供应中断", "capacity_reduction": "产能减少", "capacity_increase": "产能增加",
                "project_delay": "项目延期/终止", "share_pledge": "股权质押"}
SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低", "info": "提示"}
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强"}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def snapshots() -> list[str]:
    return sorted((p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists()), reverse=True)


def fragility_rows(snapshot: str) -> list[dict]:
    """Core and other companies of the snapshot, plus extension peer groups known on that date (listed last)."""
    from src.extension import rows as extension_rows
    base = _read(ROOT / "data" / "snapshots" / snapshot / "fragility.csv")
    known = {r["security_code"] for r in base}
    return base + [r for c, r in extension_rows(snapshot).items() if c not in known]


def peer_rank(rows: list[dict], code: str) -> tuple[int, int] | None:
    """(rank, n) among the core mills, 1 = weakest (highest total score)."""
    core = [r for r in rows if r.get("peer_group") == "core" and r.get("total_score")]
    order = sorted(core, key=lambda r: -float(r["total_score"]))
    for i, r in enumerate(order, 1):
        if r["security_code"] == code:
            return i, len(order)
    return None


def split_paths(items: list[tuple[int, dict]], code: str) -> dict[str, list[tuple[int, dict]]]:
    """Paths that start at the company (risk goes out), paths that reach or pass it (risk comes in), and
    paths with score 0: every listed company they reach is strong, i.e. the risk is absorbed (not an alert)."""
    out = {"outgoing": [], "incoming": [], "absorbed": []}
    for i, e in items:
        if e["score"] <= 0:
            if e["seed"] == code or any(code in (s.src, s.dst) for s in e["steps"]):
                out["absorbed"].append((i, e))
        elif e["seed"] == code:
            out["outgoing"].append((i, e))
        elif any(code in (s.src, s.dst) for s in e["steps"]):
            out["incoming"].append((i, e))
    return out


def company_signals(chain: Path, code: str, as_of: str, limit: int = 12) -> list[dict]:
    """The company's announcement signals known on the evaluation date, newest first, with their source."""
    from src.sources import titles
    rows = []
    from src.live_events import chain_signals
    for s in chain_signals(chain, as_of):
        if s.get("entity_id") != code or not s.get("date") or s["date"] > as_of:
            continue
        stem = Path(s.get("source_doc", "")).stem
        page = s.get("source_page")
        rows.append({"日期": s["date"], "类型": SIGNAL_LABEL.get(s.get("signal_type", ""), s.get("signal_type", "")),
                     "严重度": SEVERITY_LABEL.get(s.get("severity", ""), s.get("severity", "")),
                     "仍有效": "是" if is_active(s, as_of) else "否",
                     "说明": (s.get("detail") or "")[:50],
                     "来源": (f"公告标题识别：{s.get('evidence_text', '')[:30]}" if s.get("source_doc", "").startswith("http")
                            else f"{titles().get(stem, stem)}{f' 第{page}页' if page else ''}")})
    seen, unique = set(), []
    for r in sorted(rows, key=lambda r: r["日期"], reverse=True):
        key = (r["日期"], r["类型"], r["说明"], r["来源"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:limit]


def headline(name: str, row: dict | None, n_in: int, n_out: int, n_absorbed: int = 0) -> tuple[str, str]:
    """(level, one-sentence conclusion) for the top of the profile. level: error / warning / success / info."""
    if not row:
        return "info", f"{name} 不在该评估日的承压评分范围内；下面只列关联路径与公告信号。"
    tier = row.get("tier", "")
    own = f"自身承压 **{TIER_LABEL.get(tier, tier)}**（{row.get('total_score') or '—'} 分，越高越弱）"
    links = []
    if n_in:
        links.append(f"{n_in} 条关键路径把风险传入或经过它")
    if n_out:
        links.append(f"{n_out} 条由它发出")
    rel = "；".join(links) if links else "没有需要关注的关联或担保传导路径"
    if n_absorbed:
        rel += f"（另有 {n_absorbed} 条路径得分为 0：途经企业承压为强，风险被吸收）"
    level = "error" if tier == "weak" else "warning" if (tier == "medium" or n_in or n_out) else "success"
    return level, f"{name}：{own}；{rel}。"
