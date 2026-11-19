"""Back end of the company profile's summary features: score history, peer comparison, group background,
raw-material exposure, a rule-based check list, and a downloadable one-page brief.

Nothing here creates a new score: every line restates a result computed elsewhere (fragility snapshots,
risk paths, report signals, futures layer) with its source. The check list is a fixed set of rules
(below), not a model judgement.
"""
from __future__ import annotations

import csv
import html
import statistics
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "data" / "snapshots"
DIMS = [("leverage", "杠杆"), ("liquidity", "短期偿债"), ("cash", "造血"), ("profit", "盈利"), ("market", "市场"),
        ("contingent", "对外担保")]
TIER_LABEL = {"weak": "弱", "medium": "中", "strong": "强"}
ORE_SHOCK = 0.10                    # the check list uses a +10% iron-ore scenario


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def score_history(code: str, upto: str, days: int = 120) -> list[dict]:
    """Total score and tier of `code` in every daily snapshot within `days` before `upto` (inclusive)."""
    start = (date.fromisoformat(upto) - timedelta(days=days)).isoformat()
    out = []
    for folder in sorted(p for p in SNAPS.glob("*") if start <= p.name <= upto):
        row = next((r for r in _read(folder / "fragility.csv") if r["security_code"] == code), None)
        if row and row.get("total_score"):
            out.append({"日期": folder.name, "总分": float(row["total_score"]), "等级": TIER_LABEL.get(row["tier"], row["tier"]),
                        "财报期": row.get("period", "")})
    for prev, cur in zip(out, out[1:]):
        cur["新财报"] = bool(prev["财报期"] and cur["财报期"] and cur["财报期"] != prev["财报期"])
    if out:
        out[0]["新财报"] = False
    return out


PERIOD_NAME = {"0331": "一季报", "0630": "半年报", "0930": "三季报", "1231": "年报"}


def period_label(period: str) -> str:
    return f"{period[:4]} 年{PERIOD_NAME.get(period[4:], period[4:])}" if len(period) == 8 else period


def trend(history: list[dict], days: int = 30) -> dict | None:
    """Change of the total score versus the latest snapshot at least `days` earlier."""
    if len(history) < 2:
        return None
    last = history[-1]
    cutoff = (date.fromisoformat(last["日期"]) - timedelta(days=days)).isoformat()
    earlier = [h for h in history if h["日期"] <= cutoff] or history[:1]
    base = earlier[-1]
    return {"from": base["日期"], "to": last["日期"], "delta": last["总分"] - base["总分"],
            "tier_from": base["等级"], "tier_to": last["等级"]}


def peer_dims(snapshot: str, code: str) -> list[dict]:
    """The company's six dimension scores next to the median of the 24 core mills (0 strongest, 100 weakest)."""
    rows = _read(SNAPS / snapshot / "fragility.csv")
    core = [r for r in rows if r.get("peer_group") == "core"]
    me = next((r for r in rows if r["security_code"] == code), None)
    if not me:
        return []
    out = []
    for key, label in DIMS:
        col = f"score_{key}"
        vals = [float(r[col]) for r in core if r.get(col) not in (None, "")]
        mine = float(me[col]) if me.get(col) not in (None, "") else None
        if mine is None or not vals:
            continue
        out.append({"维度": label, "本企业": mine, "核心钢厂中位数": statistics.median(vals),
                    "差距": mine - statistics.median(vals)})
    return out


def group_background(code: str) -> dict | None:
    """Parent and group from the entity table (data/reference/entities.csv)."""
    rows = {r["entity_id"]: r for r in _read(ROOT / "data" / "reference" / "entities.csv")}
    me = next((r for r in rows.values() if r.get("security_code") == code), None)
    if not me:
        return None
    parent = rows.get(me.get("parent_id") or "")
    members = [r["short_name"] for r in rows.values()
               if me.get("group_id") and r.get("group_id") == me["group_id"] and r.get("security_code") and r["security_code"] != code]
    return {"parent": parent["canonical_name"] if parent else None, "parent_id": parent["entity_id"] if parent else None,
            "group_id": me.get("group_id") or None,
            "listed_peers": members}


def equity_of(snapshot: str, code: str) -> float | None:
    row = next((r for r in _read(SNAPS / snapshot / "quarterly_metrics.csv") if r["security_code"] == code), None)
    return float(row["equity"]) if row and row.get("equity") else None


def checklist(name: str, row: dict | None, detail: dict | None, tr: dict | None, group: dict | None,
              margin: dict | None, ore: dict | None, hedge: str, n_in: int, n_out: int, report: dict | None,
              n_absorbed: int = 0) -> dict:
    """Key points (what is known) and up to three priority checks (what to verify next), by fixed rules."""
    points, checks = [], []
    if row:
        tier = TIER_LABEL.get(row.get("tier", ""), "未评分")
        rules = (detail or {}).get("rules") or []
        points.append(f"自身承压 **{tier}**（{row.get('total_score')} 分）" + (f"：{rules[0]}" if rules else ""))
        if rules:
            checks.append(f"核查偿债安排：{rules[0]}，看短期借款到期、授信余额和续贷情况")
        if int(row.get("events_after_report") or 0):
            checks.append("核查财报后已发生的风险公告（冻结、逾期、风险警示等）")
    if tr:
        word = "上升（变弱）" if tr["delta"] > 0.5 else "下降（变强）" if tr["delta"] < -0.5 else "基本持平"
        points.append(f"评分走势：{tr['from']} 至 {tr['to']} {word} {tr['delta']:+.1f} 分"
                      + (f"，等级 {tr['tier_from']} → {tr['tier_to']}" if tr["tier_from"] != tr["tier_to"] else ""))
    if group and group.get("parent"):
        peers = "、".join(group["listed_peers"][:3])
        points.append(f"集团背景：控股股东 {group['parent']}" + (f"（同集团上市公司：{peers}）" if peers else "")
                      + "；可能获得集团支持，也可能经集团通道传导，不计分")
        if row and row.get("tier") == "weak":
            checks.append(f"核查集团支持：{group['parent']} 的担保、资金拆借或增资安排")
    if margin:
        points.append(f"行业：螺纹吨钢盘面利润 {margin['value']:,.0f} 元/吨，处于 {margin['since'][:4]} 年以来 {margin['pct_all']:.0%} 分位")
    if ore:
        share = f"，占净资产 {ore['to_equity']:.0%}" if ore.get("to_equity") is not None else ""
        points.append(f"原料情景：铁矿涨 {ORE_SHOCK:.0%}，一年多付约 {ore['extra_yi']:.1f} 亿元{share}（{ore['fy']} 年报外购铁矿）")
    points.append(f"套期保值：{hedge}")
    if ore and (ore.get("to_equity") or 0) >= 0.10 and hedge in ("缓存中未见", "仅有管理制度", "外汇"):
        checks.append("核查原料成本对冲：定期报告中的套期保值规模与长协采购比例")
    paths = []
    if n_in:
        paths.append(f"{n_in} 条传入或经过")
    if n_out:
        paths.append(f"{n_out} 条由它发出")
    text = "；".join(paths) if paths else "没有计分路径"
    if n_absorbed:
        text += f"；另有 {n_absorbed} 条传到承压为强的企业，风险可能被缓释"
    points.append("传导路径：" + text)
    if n_in:
        checks.append("核查传入路径上的担保和关联交易（关联风险标签页，每一步有公告原文页码）")
    if report and report.get("signals"):
        checks.append(f"核查财报异常信号：{report['signals'][0]['kind']}")
    return {"points": points, "checks": checks[:3]}


def brief_html(name: str, code: str, snapshot: str, verdict_text: str, summary: dict, dims: list[dict],
               reasons: str, report: dict | None, paths: list[dict]) -> str:
    """A self-contained one-page brief (open in a browser, print to PDF)."""
    e = lambda s: html.escape(str(s))  # noqa: E731
    strip = lambda s: str(s).replace("**", "")  # noqa: E731
    dim_rows = "".join(f"<tr><td>{e(d['维度'])}</td><td>{d['本企业']:.1f}</td><td>{d['核心钢厂中位数']:.1f}</td></tr>" for d in dims)
    rep = ""
    if report and report.get("rows"):
        def cell(v, pct=False):
            if v is None:
                return "—"
            return f"{v:+.1%}" if pct else f"{v:.2f}"
        rep = ("<h2>财报分析</h2><table><tr><th>指标</th><th>本期累计（亿元）</th><th>同比</th><th>单季度环比</th></tr>"
               + "".join(f"<tr><td>{e(r['指标'])}</td><td>{cell(r.get('本期累计（亿元）'))}</td><td>{cell(r.get('同比'), True)}</td>"
                         f"<td>{cell(r.get('单季度环比'), True)}</td></tr>" for r in report["rows"]) + "</table>"
               + "".join(f"<p class='warn'>{e(s['kind'])}：{e(s['text'])}</p>" for s in report.get("signals", [])))
    path_html = ("<h2>关键传导路径</h2><table><tr><th>路径</th><th>得分</th><th>规则与证据等级</th></tr>"
                 + "".join(f"<tr><td>{e(p.get('传导路径', ''))}</td><td>{e(p.get('得分', ''))}</td><td>{e(p.get('规则', ''))}；{e(p.get('证据等级', ''))}</td></tr>"
                           for p in paths[:8]) + "</table>") if paths else "<h2>关键传导路径</h2><p>没有需要关注的路径。</p>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{e(name)} 核查底稿</title>
<style>body{{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;max-width:820px;margin:32px auto;color:#1f2a37;line-height:1.6;padding:0 16px}}
h1{{color:#16324F;margin-bottom:4px}}h2{{color:#16324F;border-bottom:2px solid #F28C28;padding-bottom:2px;margin-top:28px;font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d6dde6;padding:4px 8px;text-align:left}}th{{background:#f2f5f9}}
.meta{{color:#5b6b7c;font-size:13px}}.box{{background:#f6f8fb;border-left:4px solid #16324F;padding:8px 14px}}.warn{{color:#a15c00}}
li{{margin:2px 0}}@media print{{body{{margin:0}}}}</style></head><body>
<h1>{e(name)}（{e(code)}）核查底稿</h1>
<p class="meta">链证 ChainProof · 评估日 {e(snapshot)} · 生成于 {date.today().isoformat()} · 在线版：chainproof-steel.streamlit.app</p>
<div class="box"><b>结论</b>：{e(strip(verdict_text))}</div>
<h2>核查要点</h2><ul>{"".join(f"<li>{e(strip(p))}</li>" for p in summary["points"])}</ul>
<h2>建议优先核查</h2><ol>{"".join(f"<li>{e(c)}</li>" for c in summary["checks"]) or "<li>暂无</li>"}</ol>
<h2>财务脆弱性（承压评分）</h2><p>主要原因：{e(reasons or "—")}</p>
<table><tr><th>维度</th><th>本企业（0 最强，100 最弱）</th><th>24 家核心钢厂中位数</th></tr>{dim_rows}</table>
{rep}{path_html}
<h2>说明</h2><p class="meta">承压评分是 24 家核心钢厂之间的相对比较，是模型预警，不是违约概率；路径得分是优先核查顺序，不等于损失大小；
期货盘面利润与原料情景只作情景，不计入评分；套期保值依据公告标题识别。每条结论的公告原文与页码可在在线版查看。</p>
</body></html>"""
