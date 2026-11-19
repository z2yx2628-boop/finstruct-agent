"""企业档案 · 客户与供应商: readable wording on top of src.supply_relations (display only).

  concentration_reading : one sentence on how the top-five customer / supplier shares moved, and how much of
                          them is related parties (dependence on the group)
  concentration_bars    : rows for a stacked bar per year (related / other / not split)
  share_cell            : a service bought from a related party is not part of 'purchases', so its ratio to the
                          annual purchase total is shown as a size reference, never as a share
  source_label / newer_estimate : the announcement behind a figure, by name and date, and a newer one if any
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLES = ROOT / "data" / "live" / "announcement_titles"
SERVICE = re.compile(r"劳务|服务")
ESTIMATE = re.compile(r"日常关联交易")
SRC = re.compile(r"(?P<file>\S+\.json)\s*(第(?P<page>\d+)页)?\s*[（(](?P<date>\d{4}-\d{2}-\d{2})[)）]")


def _pp(a: float, b: float) -> float:
    return (a - b) * 100


def concentration_reading(conc: list[dict]) -> list[str]:
    out = []
    for side, who, what in (("supplier", "供应商", "采购"), ("customer", "客户", "销售")):
        rows = sorted((c for c in conc if c["side"] == side and c["top5_share"] is not None), key=lambda c: c["fy"])
        if not rows:
            continue
        now = rows[-1]
        text = f"{now['fy']} 年前五大{who}占{what} {now['top5_share']:.1%}"
        if len(rows) > 1:
            prev = rows[-2]
            d = _pp(now["top5_share"], prev["top5_share"])
            if abs(d) >= 3:
                text += f"，比 {prev['fy']} 年{'上升' if d > 0 else '下降'} {abs(d):.1f} 个百分点"
            if now["related_share"] is not None and prev["related_share"] is not None:
                dr = _pp(now["related_share"], prev["related_share"])
                if abs(dr) >= 3:
                    text += f"；其中关联方从 {prev['related_share']:.1%} {'升' if dr > 0 else '降'}到 {now['related_share']:.1%}"
        rel = now["related_share"]
        if rel is not None and now["top5_share"] and rel >= 0.5 * now["top5_share"]:
            if rel >= 0.3:
                text += ("，且以集团内关联方为主：采购高度依赖集团，议价能力和原料供应安全受集团安排影响" if side == "supplier"
                         else "，且以集团内关联方为主：销售渠道高度依赖集团，需关注关联交易定价是否公允")
            else:
                text += "，前五大中以集团内关联方为主，但占总额比重不高"
        elif now["top5_share"] >= 0.5:
            text += f"，集中度较高：单一{who}的变化对经营影响大"
        out.append(text + "。")
    return out


def concentration_bars(conc: list[dict]) -> list[dict]:
    rows = []
    for c in conc:
        if c["top5_share"] is None:
            continue
        side = "前五大客户（占销售）" if c["side"] == "customer" else "前五大供应商（占采购）"
        if c["related_share"] is None:
            rows.append({"方向": side, "年度": str(c["fy"]), "构成": "未区分", "占比": c["top5_share"]})
        else:
            rows.append({"方向": side, "年度": str(c["fy"]), "构成": "关联方", "占比": c["related_share"]})
            rows.append({"方向": side, "年度": str(c["fy"]), "构成": "非关联方", "占比": max(c["top5_share"] - c["related_share"], 0)})
    return rows


def is_service(r: dict) -> bool:
    return bool(SERVICE.search(f"{r.get('counterparty', '')}{r.get('relation', '')}"))


def share_cell(r: dict) -> tuple[float | None, str]:
    """-> (share to show, basis text)."""
    basis = (r.get("share_basis") or "") + (f"（{r['share_method']}）" if r.get("share_method") else "")
    if r.get("share") is not None and is_service(r) and "采购" in (r.get("share_basis") or ""):
        return None, f"劳务不在采购总额内：金额相当于{(r.get('share_basis') or '').replace('占', '')}的 {r['share']:.0%}，仅作量级参考"
    return r.get("share"), basis


def source_label(r: dict) -> str:
    m = SRC.search(r.get("source") or "")
    if not m:
        return f"{r.get('source_type', '')}：{(r.get('source') or '')[:30]}"
    return f"{r.get('source_type', '')}（{m.group('date')}）" + (f" 第{m.group('page')}页" if m.group("page") else "")


def source_date(r: dict) -> str | None:
    m = SRC.search(r.get("source") or "")
    return m.group("date") if m else None


def title_url(code: str, day: str | None, pattern: re.Pattern = ESTIMATE) -> str | None:
    """The announcement link for a document published by `code` on `day` (from the cached titles)."""
    path = TITLES / f"{code}.csv"
    if not day or not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        hit = next((r for r in csv.DictReader(f) if r.get("notice_date") == day and pattern.search(r.get("title", ""))), None)
    return hit.get("source_url") if hit else None


def newer_estimate(code: str, after: str | None, as_of: str) -> dict | None:
    """A daily related-transaction announcement published after `after` (it carries the next year's actual amounts)."""
    path = TITLES / f"{code}.csv"
    if not after or not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        hits = [r for r in csv.DictReader(f) if after < r.get("notice_date", "") <= as_of and ESTIMATE.search(r.get("title", ""))
                and not re.search(r"补充|调整|新增|增加|更正", r.get("title", ""))]
    if not hits:
        return None
    r = max(hits, key=lambda r: r["notice_date"])
    return {"date": r["notice_date"], "title": r["title"], "url": r.get("source_url", "")}
