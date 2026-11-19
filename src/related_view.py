"""企业档案 · 关联风险: what the company is tied to and why risk does (not) travel along those ties.

  relation_summary : disclosed relations still in force, by type, and the largest counterparties
  group_support    : the parent group's proxy tier next to the company's own tier (a weak member of a strong
                     group = expected group support, which is not a legal guarantee)
  no_path_reasons  : an empty result explains itself (relations expired, absorbed by a strong group, immaterial …)
  deposit_reading  : finance-company deposits AND loans read together (net borrower = depends on the group for
                     funding), a stale-data flag, and a newer report seen in the announcement titles

Display only: nothing here changes how paths are found or scored.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLES = ROOT / "data" / "live" / "announcement_titles"
EDGE_CN = {"guarantee": "担保", "supply": "购销", "service": "劳务", "lease": "租赁", "finance": "资金往来", "other": "其他"}
REPORT = re.compile(r"财务(有限)?(责任)?公司.*(风险(持续)?评估|存贷款)|存贷款.*(风险评估|专项说明)")
STALE_DAYS = 365


def relation_summary(active: list[dict], code: str, names: dict[str, str], top: int = 5) -> dict:
    by_type: dict[str, int] = {}
    partners: dict[str, dict] = {}
    for e in active:
        kind = EDGE_CN.get(e["edge_type"], e["edge_type"])
        by_type[kind] = by_type.get(kind, 0) + 1
        other, other_name = (e["dst_id"], e["dst_name"]) if e["src_id"] == code else (e["src_id"], e["src_name"])
        if other == code:
            continue
        p = partners.setdefault(other, {"交易对手": names.get(other) or other_name, "关系": set(), "金额(亿元)": 0.0,
                                        "方向": set()})
        p["关系"].add(kind)
        p["方向"].add("对方→本企业" if e["dst_id"] == code else "本企业→对方")
        p["金额(亿元)"] += float(e.get("amount_wan") or 0) / 1e4
    rows = sorted(partners.values(), key=lambda p: -p["金额(亿元)"])
    out = [{**p, "关系": "、".join(sorted(p["关系"])), "方向": " / ".join(sorted(p["方向"])),
            "金额(亿元)": round(p["金额(亿元)"], 2)} for p in rows[:top]]
    return {"by_type": by_type, "top": out, "partners": len(partners)}


def group_support(own_tier: str, parent: str | None, proxy: dict | None) -> dict | None:
    """-> {'parent', 'tier', 'score', 'text'} or None when the company has no known parent group."""
    if not parent:
        return None
    tier, score = (proxy or {}).get("tier"), (proxy or {}).get("total_score")
    cn = {"weak": "弱", "medium": "中", "strong": "强"}
    if tier is None:
        text = f"控股股东为{parent}；集团没有可用的上市成员数据，无法给出集团参照承压。"
    elif own_tier in ("weak", "medium") and tier == "strong":
        text = (f"自身承压{cn.get(own_tier)}，但所属集团参照承压为**强**（{score} 分）：存在集团支持预期，"
                "风险传到集团层面时可能被吸收。这是隐性支持，不等于法律上的担保责任。")
    elif own_tier == "weak" and tier in ("weak", "medium"):
        text = f"自身承压弱，所属集团参照承压也只是{cn.get(tier)}（{score} 分）：集团兜底能力有限，需关注集团内风险相互传染。"
    else:
        text = f"所属集团参照承压为{cn.get(tier, tier)}（{score} 分）。"
    return {"parent": parent, "tier": tier, "score": score, "text": text}


def no_path_reasons(cov: dict, absorbed: int, support: dict | None) -> list[str]:
    why = []
    if not cov["active"] and cov["expired"]:
        why.append(f"它的 {len(cov['expired'])} 条披露关系都已过期（最近一份相关公告 {cov['latest']}），评估日后还没有抽取到新的公告。")
    elif not cov["active"]:
        why.append("图谱里还没有它披露的关联交易、担保或资金往来，只知道它属于哪个集团。")
    if absorbed:
        why.append(f"有 {absorbed} 条路径经过它，但途经的上市公司或集团承压为强，风险可能被缓释，得分为 0，不预警。")
    if support and support.get("tier") == "strong" and cov["tier"] in ("weak", "medium"):
        why.append("它的主要关系通向承压为强的集团，风险传到那里即被判为可缓释，这正是没有计分路径的主要原因。")
    if cov["active"] and not why:                      # only when nothing more specific explains it
        why.append(f"它有 {len(cov['active'])} 条仍有效的披露关系，但附近没有中高严重度的风险源，或金额低于对方净资产的 1%。")
    if cov["tier"] == "strong":
        why.append("它自身承压为强，路径到它这里不再扩展。")
    return why


def deposit_reading(e: dict, equity_yuan: float | None, as_of: str) -> dict:
    """Net position with the finance company, equity note, staleness."""
    out = {"lines": [], "stale": False, "equity_note": None}
    dep, loan = e.get("deposit_yi"), e.get("loan_yi")
    if dep is not None and loan is not None:
        net = loan - dep
        if net > 0:
            out["lines"].append(f"存款 {dep:.2f} 亿元、借款 {loan:.2f} 亿元，**净借入 {net:.2f} 亿元**：对集团财务公司的资金依赖较高，"
                                "若财务公司收紧授信，流动性压力会上升。")
        else:
            out["lines"].append(f"存款 {dep:.2f} 亿元、借款 {loan:.2f} 亿元，**净存入 {-net:.2f} 亿元**：资金归集在集团，"
                                "若财务公司出现兑付问题，这部分资金可能被困住。")
    if equity_yuan is not None and equity_yuan <= 0:
        out["equity_note"] = "净资产为负，无法计算"
    try:
        days = (date.fromisoformat(as_of) - date.fromisoformat(e["period"])).days
        out["stale"] = days > STALE_DAYS
        out["age_days"] = days
    except (KeyError, ValueError):
        pass
    return out


def newer_report(code: str, after: str, as_of: str) -> dict | None:
    """The newest finance-company risk report in the announcement titles published after `after` and by `as_of`."""
    path = TITLES / f"{code}.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        hits = [r for r in csv.DictReader(f) if after < r.get("notice_date", "") <= as_of and REPORT.search(r.get("title", ""))]
    if not hits:
        return None
    r = max(hits, key=lambda r: r["notice_date"])
    return {"date": r["notice_date"], "title": r["title"], "url": r.get("source_url", ""), "doc_id": r.get("doc_id", "")}
