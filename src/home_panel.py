"""首页「风险面板」: three small charts under the five numbers.

  承压排行   : the 24 core mills by fragility score (the 60 / 40 tier lines drawn), coloured by tier
  风险走势   : over the last 60 days, how many core mills are weak and how many scored paths there are
  行业利润   : one year of the futures-implied rebar margin, with the historical 20th-percentile line

Only reads files the other pages already use (snapshots, key_paths_*.csv, futures prices); nothing is computed anew.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

TIER_COLOR = {"弱": "#E5484D", "中": "#F5A524", "强": "#30A46C"}
TIER_CN = {"weak": "弱", "medium": "中", "strong": "强"}
FONT = "Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ranking_rows(fragility: list[dict]) -> list[dict]:
    rows = [{"企业": r["security_name"], "总分": float(r["total_score"]), "等级": TIER_CN.get(r["tier"], "未评分"),
             "原因": "；".join((r.get("reasons") or "").split("；")[:2])}
            for r in fragility if r.get("peer_group") == "core" and r.get("total_score")]
    return sorted(rows, key=lambda r: -r["总分"])


def trend_rows(snapshots: list[Path], key_path_files: list[Path], days: int = 60) -> list[dict]:
    if not snapshots:
        return []
    start = (date.fromisoformat(snapshots[-1].name) - timedelta(days=days)).isoformat()
    out = []
    for s in snapshots:
        if s.name >= start:
            core = [r for r in _read(s / "fragility.csv") if r.get("peer_group") == "core"]
            out.append({"日期": s.name, "指标": "弱等级钢厂（家）", "数值": sum(1 for r in core if r["tier"] == "weak")})
    for p in key_path_files:
        day = p.stem.replace("key_paths_", "")
        if day >= start:
            out.append({"日期": day, "指标": "计分传导路径（条）",
                        "数值": sum(1 for r in _read(p) if float(r.get("score") or 0) > 0)})
    return out


def margin_rows(days: tuple[str, ...], values: tuple[float, ...], as_of: str, span: int = 365) -> tuple[list[dict], float | None]:
    """-> (one year of daily margins up to as_of, the 20th percentile of the whole history)."""
    hist = [v for d, v in zip(days, values) if d <= as_of]
    if not hist:
        return [], None
    low = sorted(hist)[int(0.2 * (len(hist) - 1))]
    start = (date.fromisoformat(as_of) - timedelta(days=span)).isoformat()
    return [{"日期": d, "利润": round(v, 1)} for d, v in zip(days, values) if start <= d <= as_of], low


def _base(height: int) -> dict:
    return {"height": height, "width": "container",
            "config": {"view": {"stroke": None}, "font": FONT, "axis": {"labelColor": "#667085", "titleColor": "#667085",
                                                                      "gridColor": "#EEF0F3", "domainColor": "#D0D5DD"},
                       "legend": {"labelColor": "#475467", "orient": "top", "title": None}}}


def ranking_chart(rows: list[dict]) -> dict:
    y = {"field": "企业", "type": "nominal", "sort": None, "title": None,
         "axis": {"labelFontSize": 11, "labelOverlap": False, "labelLimit": 120}}       # every name shown, none skipped
    return {**_base(max(260, 22 * len(rows))), "data": {"values": rows}, "layer": [
        {"mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 10, "color": "#475467"},
         "encoding": {"y": y, "x": {"field": "总分", "type": "quantitative"}, "text": {"field": "总分", "format": ".1f"}}},
        {"mark": {"type": "bar", "cornerRadiusEnd": 3, "height": {"band": 0.72}},
         "encoding": {"y": y,
                      "x": {"field": "总分", "type": "quantitative", "scale": {"domain": [0, 100]}, "title": "承压总分（越高越弱）"},
                      "color": {"field": "等级", "type": "nominal", "legend": None,
                                "scale": {"domain": list(TIER_COLOR), "range": list(TIER_COLOR.values())}},
                      "tooltip": [{"field": "企业"}, {"field": "总分"}, {"field": "等级"}, {"field": "原因"}]}},
        {"data": {"values": [{"x": 60, "t": "弱 ≥ 60"}, {"x": 40, "t": "中 ≥ 40"}]},
         "layer": [{"mark": {"type": "rule", "strokeDash": [3, 3], "color": "#98A2B3"}, "encoding": {"x": {"field": "x", "type": "quantitative"}}},
                   {"mark": {"type": "text", "dy": -6, "dx": 3, "align": "left", "fontSize": 10, "color": "#98A2B3"},
                    "encoding": {"x": {"field": "x", "type": "quantitative"}, "y": {"value": 0}, "text": {"field": "t"}}}]},
    ]}


def trend_chart(rows: list[dict]) -> dict:
    return {**_base(240), "data": {"values": rows},
            "mark": {"type": "line", "point": {"size": 18}, "strokeWidth": 2, "interpolate": "step-after"},
            "encoding": {"x": {"field": "日期", "type": "temporal", "title": None, "axis": {"format": "%m-%d", "labelAngle": 0}},
                         "y": {"field": "数值", "type": "quantitative", "title": None, "axis": {"tickMinStep": 1}},
                         "color": {"field": "指标", "type": "nominal",
                                   "scale": {"range": ["#E5484D", "#7B2CBF"]}},
                         "tooltip": [{"field": "日期", "type": "temporal"}, {"field": "指标"}, {"field": "数值"}]}}


def margin_chart(rows: list[dict], low: float | None) -> dict:
    layers = [
        {"mark": {"type": "area", "line": {"color": "#1C5D99", "strokeWidth": 1.6}, "color": "#1C5D99", "opacity": 0.12},
         "encoding": {"x": {"field": "日期", "type": "temporal", "title": None, "axis": {"format": "%y-%m", "labelAngle": 0}},
                      "y": {"field": "利润", "type": "quantitative", "title": "元/吨", "scale": {"zero": False}},
                      "tooltip": [{"field": "日期", "type": "temporal"}, {"field": "利润", "title": "盘面利润（元/吨）"}]}},
    ]
    if low is not None:
        layers.append({"data": {"values": [{"y": low, "t": f"历史 20% 分位 {low:,.0f}"}]},
                       "layer": [{"mark": {"type": "rule", "strokeDash": [4, 3], "color": "#E5484D"},
                                  "encoding": {"y": {"field": "y", "type": "quantitative"}}},
                                 {"mark": {"type": "text", "align": "left", "dx": 4, "dy": -6, "fontSize": 10, "color": "#E5484D"},
                                  "encoding": {"y": {"field": "y", "type": "quantitative"}, "x": {"value": 0}, "text": {"field": "t"}}}]})
    return {**_base(240), "data": {"values": rows}, "layer": layers}
