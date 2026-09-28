"""Streamlit rendering of the policy-shock library (kept out of the page file so the page stays readable)."""
from __future__ import annotations

import csv
from datetime import date

import pandas as pd
import streamlit as st

from src.policy_shock import CBAM_FACTOR, INTENSITY, KINDS, SOURCES, carbon, export_change, production_cut, steel_price
from src.product_layer import ROOT
from src.ui import TIER_BADGE

TIER = {**TIER_BADGE, "": "未评分"}


def _pct(x):
    return f"{x:.1%}" if x is not None else "未披露"


def render_policy(snaps: list[str]) -> None:
    st.caption("政策冲击按企业计算，不经过产品图。每个数字都来自下方列出的来源或可调整的假设；结果是情景排序，不是利润或损失预测，不计入风险得分。")
    c1, c2 = st.columns([2, 1])
    kind = c1.selectbox("政策类型", list(KINDS), format_func=KINDS.get, key="pol_kind")
    day = c2.date_input("评估日", value=date.today(), key="pol_day").isoformat()
    snap = max((s for s in snaps if s <= day), default=None)
    if snap is None:
        st.warning("评估日之前没有承压快照。")
        return
    with (ROOT / "data" / "snapshots" / snap / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        fragility = {r["security_code"]: r for r in csv.DictReader(f)}

    if kind == "carbon":
        p1, p2, p3, p4 = st.columns(4)
        year = p1.selectbox("CBAM 年份", list(CBAM_FACTOR), index=1, format_func=lambda y: f"{y}（系数 {CBAM_FACTOR[y]:.1%}）")
        eu = p2.number_input("欧盟碳价假设（元/吨 CO₂）", min_value=0.0, value=600.0, step=50.0,
                             help="示例假设，不是行情；可按当时欧元碳价 × 汇率填写")
        dom = p3.number_input("国内碳价假设（元/吨 CO₂）", min_value=0.0, value=60.0, step=10.0,
                              help="示例假设，不是行情；CBAM 可扣除原产地已支付的碳价（此处简化为直接相减）")
        gap = p4.number_input("国内配额缺口", min_value=0.0, max_value=0.5, value=0.03, step=0.01, format="%.2f",
                              help="现行分配方案下配额盈亏封顶约 ±3%")
        rows = carbon(fragility, day, eu, year, dom, gap)
        price = steel_price(day)
        st.markdown(f"**每吨钢碳成本**：长流程 {INTENSITY['BF-BOF']} t CO₂/t × (欧盟碳价 − 国内碳价) × CBAM 系数；"
                    f"热卷价 {price:,.0f} 元/吨（{day} 前最近交易日）。境外收入不等于对欧收入，CBAM 部分是**上限**。")
        table = [{"企业": r["name"], "承压": TIER.get(r["tier"], "未评分"),
                  "工艺路线": r["route"] + ("" if r["route_verified"] else "（默认，未核对）"),
                  "境外收入占比": _pct(r["overseas_share"]), "CBAM 成本(元/吨出口)": r["cbam_per_ton"],
                  "国内碳成本(元/吨)": r["domestic_per_ton"], "压力指数": r["index"]} for r in rows]
        sources = [SOURCES["overseas"], SOURCES["intensity"], SOURCES["cbam"], SOURCES["price"]]
    elif kind == "export":
        change = st.slider("出口退税下调或新增关税（占出口收入）", 0.0, 0.25, 0.05, 0.01, format="%.2f", key="pol_export")
        rows = export_change(fragility, day, change)
        table = [{"企业": r["name"], "承压": TIER.get(r["tier"], "未评分"), "境外收入占比": _pct(r["overseas_share"]),
                  "年报期": r["period"][:4], "压力指数": r["index"]} for r in rows]
        sources = [SOURCES["overseas"]]
    else:
        core = {c: r for c, r in fragility.items() if r.get("peer_group") == "core"}
        picked = st.multiselect("限产企业", list(core), format_func=lambda c: core[c]["security_name"], key="pol_cut_codes")
        cut = st.slider("限产幅度（产量）", 0.0, 0.5, 0.1, 0.05, format="%.2f", key="pol_cut")
        if not picked:
            st.info("选择一家或多家企业。")
            return
        rows = production_cut(fragility, picked, cut)
        table = [{"企业": r["name"], "承压": TIER.get(r["tier"], "未评分"), "限产幅度": f"{r['cut']:.0%}",
                  "压力指数": r["index"]} for r in rows]
        sources = ["限产幅度为用户假设；限产企业作为起点，可在“产品与需求 → 企业停产”情景看它对上下游的影响。"]

    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
                 column_config={"压力指数": st.column_config.ProgressColumn(
                     format="%.2f", min_value=0, max_value=max([r["index"] or 0 for r in rows] + [0.01]))})
    missing = sum(1 for r in rows if r.get("index") is None)
    st.caption("压力指数 = |成本或收入变化占比| × 暴露比例 × 承压缓冲（弱 1.0、中 0.5、强 0.2）× 100，只用于排序。"
               + (f"{missing} 家企业年报未披露分地区收入，不计算，也不用行业均值补填。" if missing else ""))
    with st.expander("数据来源与假设", icon=":material/source:"):
        for s in sources:
            st.markdown(f"- {s}")
        st.markdown("- 工艺路线表：`data/reference/mill_routes.csv`；留空的企业按长流程计算，并在表中标“默认，未核对”。")
