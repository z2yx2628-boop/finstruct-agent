"""方向二：承压评分页面（财报层 + 市场层 + 事件层），带一键更新。"""
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fragility_view import (compared_snapshot, data_sources, events_after_report, explain,  # noqa: E402
                                guarantee_evidence, report_links, snapshot_meta, version_note)
from src.product_layer import exposure_as_of, products  # noqa: E402
SNAP = ROOT / "data" / "snapshots"
TIER_COLOR = {"weak": "🔴", "medium": "🟡", "strong": "🟢"}

from src.ui import page_header  # noqa: E402
page_header("② 企业承压", ":material/monitoring:", "这家企业扛不扛得住冲击？分数从哪来？")
st.caption("财报层（最新法定披露期，同行排名）+ 市场层（60日超额收益、回撤、波动）+ 事件层（财报后的高风险公告）。"
           "每个等级都附原因；红线（资不抵债、负债率≥85%）和财报后事件只会使等级变差。")

col1, col2 = st.columns([1, 3])
with col1:
    as_of = st.date_input("评估日期", value=date.today())
    offline = st.checkbox("只用已缓存数据（历史回测用）", value=as_of < date.today())
    if st.button("更新数据并重新评分", type="primary"):
        cmd = [sys.executable, str(ROOT / "scripts" / "update_all.py"), "--as-of", as_of.isoformat()]
        if offline:
            cmd.append("--offline")
        with st.spinner("正在更新（联网时约3–5分钟）…"):
            run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        st.code((run.stdout or "")[-2000:] + (run.stderr or "")[-1500:])

snapshots = sorted((d for d in SNAP.glob("*") if (d / "fragility.csv").exists()), reverse=True)
if not snapshots:
    st.info("还没有评分快照。点击左侧按钮生成第一份。")
    st.stop()
with col2:
    chosen = st.selectbox("查看快照", [d.name for d in snapshots])
folder = SNAP / chosen
with (folder / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
metrics = {}
if (folder / "quarterly_metrics.csv").exists():
    with (folder / "quarterly_metrics.csv").open(encoding="utf-8-sig", newline="") as f:
        metrics = {r["security_code"]: r for r in csv.DictReader(f)}
meta = snapshot_meta(folder)
version = meta.get("version", "?")
with col2:
    st.caption(f"评分方法 **{version}**：{version_note(version)}"
               + ("（版本由快照字段推断）" if meta.get("inferred") else "")
               + f"；担保与事件来源：{meta.get('signals') or '未记录'}")
if version != "v1":
    st.warning(f"该快照使用评分方法 {version}，与当前方法 v1 不同，不能与 v1 快照直接比较等级。")

counts = {k: sum(1 for r in rows if r["tier"] == k) for k in ("weak", "medium", "strong")}
m1, m2, m3 = st.columns(3)
m1.metric("🔴 弱", counts["weak"])
m2.metric("🟡 中", counts["medium"])
m3.metric("🟢 强", counts["strong"])


def period_label(p: str) -> str:
    return f"{p[:4]}-{p[4:6]}-{p[6:]}" if p and len(p) == 8 else (p or "")


table = [{
    "等级": f"{TIER_COLOR.get(r['tier'], '')} {r['tier_label']}", "企业": r["security_name"], "代码": r["security_code"],
    "总分(越高越弱)": float(r["total_score"]) if r["total_score"] else None,
    "杠杆": r["score_leverage"], "短期偿债": r["score_liquidity"], "造血": r["score_cash"], "盈利": r["score_profit"],
    "市场": r["score_market"], "对外担保": r.get("score_contingent"), "财报后事件": r["events_after_report"],
    "财报期": period_label(r.get("period", "")), "行情截至": metrics.get(r["security_code"], {}).get("last_trade_date", ""),
    "原因": r["reasons"],
} for r in rows]
st.caption("点击一行，查看该企业的评分拆解与数据来源。")
picked = st.dataframe(table, width="stretch", hide_index=True, on_select="rerun",
                      selection_mode="single-row", key=f"frag_{chosen}")
index = picked.selection.rows[0] if picked.selection.rows else 0
code = rows[min(index, len(rows) - 1)]["security_code"]

# ---------------------------------------------------------------- 评分拆解
r = next(x for x in rows if x["security_code"] == code)
st.subheader(f"{TIER_COLOR.get(r['tier'], '')} {r['security_name']}（{code}）：{r['tier_label']}，"
             f"总分 {r['total_score'] or '—'}", divider="gray")
detail = explain(folder, code) if version == "v1" else None
if detail and detail["rules"]:
    st.error("直接判为弱的规则：" + "；".join(detail["rules"]))
if r.get("events_after_report") not in (None, "", "0") and r["tier"] != r.get("base_tier"):
    st.warning("财报后出现高风险事件，等级在分数基础上下调一档（见下方“财报后事件”）。")

left, right = st.columns([3, 2])
with left:
    st.markdown("**各维度如何得出总分**")
    if detail:
        flat = [{"维度": d["dimension"], "指标": m["metric"], "原值": m["value"], "同行位置": m["rank"],
                 "指标得分": m["score"], "维度得分": d["score"], "权重": d["effective_weight"], "对总分贡献": d["contribution"]}
                for d in detail["dimensions"] for m in d["metrics"]]
        st.dataframe(flat, hide_index=True, width="stretch")
        ok = "，与快照一致 ✓" if r["total_score"] and abs(detail["total_recomputed"] - float(r["total_score"])) < 0.05 else ""
        missing = f"；缺少数据的维度（{('、'.join(detail['missing_weight']))}）不计，权重按比例重新分配" if detail["missing_weight"] else ""
        st.caption(f"指标得分 = 在 24 家核心钢厂中的分位（0 最强、100 最弱）；维度得分 = 维度内指标平均；"
                   f"总分 = Σ 权重 × 维度得分 = {detail['total_recomputed']}{ok}{missing}。≥60 为弱，≥40 为中。")
    else:
        st.info("逐项拆解只提供给当前评分方法（v1）的快照。")
with right:
    st.markdown("**数据来源**")
    if code in metrics:
        m = metrics[code]
        for label, value in data_sources({"period": m.get("period"), "available_by": m.get("available_by"),
                                          "last_trade_date": m.get("last_trade_date")}):
            st.markdown(f"- **{label}**：{value}")
    st.markdown("**核对原始定期报告（新浪财经公告列表）**")
    links = st.columns(4)
    for col, (label, url) in zip(links, report_links(code).items()):
        col.link_button(label, url, width="stretch")

exposure = exposure_as_of(code, chosen)
st.markdown("**主要产品构成**（B 级：公司定期报告披露的分产品收入，东方财富主营构成；按评估日可得的最新年报）")
if exposure and exposure.get("products"):
    names = {p["product_id"]: p["name"] for p in products()}
    split = "" if exposure["split_from"] == exposure["period"] else \
        f"；该年报只披露“钢材”合计，品种比例取自 {exposure['split_from'][:4]} 年报"
    st.dataframe([{"产品": names.get(k, k), "占收入": f"{v['share']:.1%}" if v.get("share") is not None else "—",
                   "原文条目": v.get("items", "")} for k, v in sorted(exposure["products"].items(),
                                                             key=lambda kv: -(kv[1].get("share") or 0))],
                 hide_index=True, width="stretch")
    st.caption(f"年报期 {exposure['period'][:4] or '—'}{split}。产品暴露用于价格冲击的情景提示；"
               "经两次预先登记的检验，方向一致但不显著，不作为预测（docs/product_price_validation.md）。")
else:
    st.caption("没有可用的分产品披露。")

if detail is not None or version == "v1":
    g = guarantee_evidence(folder, code)
    st.markdown("**对外担保的依据公告**（评估日有效；取公告披露的累计余额与新增担保合计中的较大者）")
    if g:
        st.dataframe(g, hide_index=True, width="stretch")
    else:
        st.caption("评估日没有有效的非子公司担保记录。")
    ev = events_after_report(folder, code, metrics.get(code, {}).get("period", ""))
    st.markdown("**财报后事件**（财报可使用日之后、评估日之前发布的风险公告）")
    if ev:
        st.dataframe(ev, hide_index=True, width="stretch")
    else:
        st.caption("无。")

if (folder / "changes.md").exists():
    with st.expander("本次变化与弱档说明", expanded=False):
        before = compared_snapshot(folder)
        before_version = snapshot_meta(before)["version"] if before else version
        text = (folder / "changes.md").read_text(encoding="utf-8")
        if before and before_version != version and "评分方法为" not in text:
            st.warning(f"对比的上期快照 {before.name} 使用评分方法 {before_version}（{version_note(before_version)}），"
                       f"本期为 {version}。下列等级变化主要来自评分方法调整，不代表企业经营变化。")
        st.markdown(text)
