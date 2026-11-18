"""Streamlit rendering of the futures layer (盘面利润, scenario, hedging) for the 供需情景 page."""
from __future__ import annotations

import csv
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from src.futures import CAVEAT, LABEL, NAMES, WINDOW, hedge_label, hedging, margin_series, margin_snapshot, ore_cost_exposure, scenario
from src.policy_shock import iron_ore_import
from src.product_layer import ROOT
from src.scenario import company_name, core_mills
from src.ui import TIER_BADGE

TIER = {**TIER_BADGE, "": "未评分"}


def _pct(x):
    return f"{x:.0%}" if x is not None else "—"


def render_futures(snaps: list[str]) -> None:
    st.caption(CAVEAT)
    day = st.date_input("评估日", value=date.today(), key="fut_day").isoformat()

    # ------------------------------------------------ 1. margins now
    st.markdown("#### 期货盘面利润：全行业的压力指标")
    snaps_m = {k: margin_snapshot(k, day) for k in ("rebar", "hrc", "coke")}
    cols = st.columns(3)
    for col, (k, s) in zip(cols, snaps_m.items()):
        if s is None:
            col.metric(LABEL[k], "无数据")
            continue
        unit = "元/吨焦" if k == "coke" else "元/吨钢"
        col.metric(f"{LABEL[k]}（{s['date']}）", f"{s['value']:,.0f} {unit}", f"{s['change']:+,.0f}（{WINDOW} 个交易日）")
        col.caption(f"处于 {s['since'][:4]} 年以来的 {_pct(s['pct_all'])} 分位、近三年的 {_pct(s['pct_3y'])} 分位"
                    f"（区间 {s['min']:,.0f} 至 {s['max']:,.0f}）")
    low = [s for s in snaps_m.values() if s and s["kind"] != "coke" and s["pct_all"] is not None and s["pct_all"] <= 0.2]
    if low:
        st.warning("吨钢盘面利润处于历史低位（≤20% 分位）：全行业利润被原料成本挤压，承压为“弱”的企业更需关注。"
                   "这是行业层面的情景提示，不改变单个企业的评分。", icon=":material/trending_down:")

    days, vals = margin_series("rebar")
    _, hrc = margin_series("hrc")
    hrc_map = dict(zip(margin_series("hrc")[0], hrc))
    start = f"{int(day[:4]) - 3}{day[4:]}"
    rows = [{"日期": d, "螺纹盘面利润": v, "热卷盘面利润": hrc_map.get(d)} for d, v in zip(days, vals) if start <= d <= day]
    if rows:
        long = pd.DataFrame(rows).melt(id_vars="日期", var_name="指标", value_name="元/吨").dropna()
        long["日期"] = pd.to_datetime(long["日期"])
        chart = (alt.Chart(long).mark_line(strokeWidth=1.6)
                 .encode(x=alt.X("日期:T", title=None, axis=alt.Axis(format="%Y-%m")),
                         y=alt.Y("元/吨:Q", scale=alt.Scale(zero=False), title="元/吨"),
                         color=alt.Color("指标:N", legend=alt.Legend(orient="bottom", title=None)),
                         tooltip=[alt.Tooltip("日期:T", format="%Y-%m-%d"), "指标:N", alt.Tooltip("元/吨:Q", format=",.0f")])
                 .properties(height=280))
        st.altair_chart(chart, use_container_width=True)
        st.caption("近三年走势；期货主力连续合约，换月时会有跳动。")

    s = snaps_m["rebar"]
    if s:
        st.markdown(f"**近 {WINDOW} 个交易日螺纹盘面利润变化 {s['change']:+,.0f} 元/吨，来自哪里**（{s['base_date']} → {s['date']}）")
        st.dataframe(pd.DataFrame(s["contrib"]).style.format(
            {f"{WINDOW}日前价格": "{:,.1f}", "最新价格": "{:,.1f}", "价格变化": "{:+.1%}", "对利润的贡献（元/吨）": "{:+,.0f}"}),
            hide_index=True, width="stretch")

    # ------------------------------------------------ 2. scenario
    st.markdown("#### 情景：原料或钢价变动后，吨钢利润会变成多少")
    c1, c2, c3 = st.columns(3)
    ore = c1.slider("铁矿石价格变动", -30, 30, 10, 1, format="%d%%", key="fut_ore")
    coke = c2.slider("焦炭价格变动", -30, 30, 0, 1, format="%d%%", key="fut_coke")
    steel = c3.slider("螺纹钢价格变动", -30, 30, 0, 1, format="%d%%", key="fut_steel")
    sc = scenario("rebar", day, {"I0": ore / 100, "J0": coke / 100, "RB0": steel / 100})
    if sc:
        a, b, c = st.columns(3)
        a.metric("情景前", f"{sc['before']:,.0f} 元/吨")
        b.metric("情景后", f"{sc['after']:,.0f} 元/吨", f"{sc['delta']:+,.0f}")
        c.metric("情景后的历史分位", _pct(sc["pct_after"]))
        st.caption("按 1.6 吨铁矿、0.5 吨焦炭折一吨钢计算；只算盘面，不含加工成本、库存和长协价格。")

    # ------------------------------------------------ 3. who is more exposed, who hedges
    st.markdown("#### 哪些钢厂更暴露、哪些有套期保值")
    snap = max((x for x in snaps if x <= day), default=None)
    fragility = {}
    if snap:
        with (ROOT / "data" / "snapshots" / snap / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
            fragility = {r["security_code"]: r for r in csv.DictReader(f)}
    equity = {}
    if snap:
        qm = ROOT / "data" / "snapshots" / snap / "quarterly_metrics.csv"
        if qm.exists():
            with qm.open(encoding="utf-8-sig", newline="") as f:
                equity = {r["security_code"]: float(r["equity"]) for r in csv.DictReader(f) if r.get("equity")}
    st.caption(f"下表“多付原料成本”按上方情景的铁矿石变动 {ore:+d}% 计算：外购铁矿金额（年报“铁矿石供应情况”表，扣除自有矿）× 变动幅度，"
               "一年口径，假设钢价不跟随、无库存和长协缓冲、不计套保。")
    table = []
    for code in core_mills():
        fr = fragility.get(code, {})
        oc = ore_cost_exposure(code, day, ore / 100, equity.get(code))
        ore_i = iron_ore_import(code, day)
        h = hedging(code, day)
        latest = next((x for x in h["items"] if x["性质"] == "业务公告"), None)
        table.append({"企业": company_name(code), "代码": code, "承压": TIER.get(fr.get("tier", ""), "未评分"),
                      "承压总分": float(fr["total_score"]) if fr.get("total_score") else None,
                      "外购铁矿（亿元/年）": oc["purchased_yi"] if oc else None,
                      f"铁矿{ore:+d}% 多付成本（亿元）": oc["extra_yi"] if oc else None,
                      "占净资产": oc["to_equity"] if oc else None,
                      "备注": ("净资产为负，无法计算占比" if oc and oc["equity_nonpositive"] else (oc["source"] if oc else "年报未披露铁矿石供应表")),
                      "铁矿进口占比（吨）": ore_i["import_share_t"] if ore_i else None,
                      "套期保值（近15个月公告）": hedge_label(h),
                      "最近套保公告": f"{latest['日期']}《{latest['公告标题']}》" if latest else "—",
                      "公告缓存起点": h["cache_from"] or "—"})
    order = {"🔴 弱": 0, "🟡 中": 1, "🟢 强": 2, "未评分": 3}
    table.sort(key=lambda r: (order.get(r["承压"], 3), -(r["占净资产"] if r["占净资产"] is not None else -1)))
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
                 column_config={"承压总分": st.column_config.NumberColumn(format="%.1f"),
                                "外购铁矿（亿元/年）": st.column_config.NumberColumn(format="%.1f"),
                                f"铁矿{ore:+d}% 多付成本（亿元）": st.column_config.NumberColumn(format="%+.2f"),
                                "占净资产": st.column_config.NumberColumn(format="percent"),
                                "铁矿进口占比（吨）": st.column_config.NumberColumn(format="percent")})
    hit = sorted((r for r in table if r["占净资产"] is not None), key=lambda r: -abs(r["占净资产"]))[:3]
    if hit and ore:
        st.markdown("**情景下冲击最大（多付成本占净资产）**：" + "；".join(
            f"{r['企业']}（{r['承压']}）{r[f'铁矿{ore:+d}% 多付成本（亿元）']:+.1f} 亿元，占净资产 {r['占净资产']:.1%}" for r in hit))
    weak_unhedged = [r["企业"] for r in table if r["承压"] == "🔴 弱" and r["套期保值（近15个月公告）"] in ("缓存中未见", "仅有管理制度", "外汇")]
    if weak_unhedged:
        st.info("承压为“弱”且公告缓存中未见商品套保业务公告：" + "、".join(weak_unhedged)
                + "。原料价格上涨时这些企业缺少可见的对冲安排，值得优先核查其定期报告中的套期保值披露。", icon=":material/policy:")
    st.caption("套期保值依据公告标题识别（A 级：公告本身；类别按标题关键词划分）。公告缓存只保存各公司最新若干页，"
               "“缓存中未见”不等于没有套保。铁矿进口占比来自年报“铁矿石供应情况”表。")
