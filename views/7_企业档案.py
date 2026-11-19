"""企业档案：一家企业一页 —— 财务脆弱性、风险传入与传出路径、每条依据的出处。"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fragility_view import events_after_report, explain, guarantee_evidence, report_links, snapshot_meta  # noqa: E402
from src.network_view import edge_index, filter_paths, key_paths, name_of, path_rows, snapshot_equity  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.product_layer import exposure_as_of, products  # noqa: E402
from src.report_signals import report_signals  # noqa: E402
from src.profile import company_signals, fragility_rows, headline, peer_rank, snapshots, split_paths  # noqa: E402
from src.ui import TIER_BADGE, UNIFIED_PAGE, deposit_block, next_step, page_header, verdict  # noqa: E402
from src.futures import (STEEL_FUTURE, company_scenario, hedge_label, hedging, margin_series, margin_snapshot,  # noqa: E402
                         ore_cost_exposure, steel_revenue_exposure)
from src.profile_extras import (ORE_SHOCK, brief_html, checklist, equity_of, group_background, peer_dims,  # noqa: E402
                                period_label, score_history, trend)
import altair as alt  # noqa: E402

page_header("企业档案", ":material/badge:", "这家企业的财务脆弱性如何？风险可能从哪里传入、向哪里传出？", grades=True,
            about="把其他页面的结果按企业重新组合：**自身风险**来自企业承压评分；**关联风险**来自集团信用通道的路径"
                  "（只含公告披露的关系，C 级情景不计入）；**产品暴露**是 B 级情景信息；**公告信号**列出抽取到的原始事件。"
                  "本页不产生新的分数或排名。  \n"
                  "右上角“数据版本”可切换评估日和关系图谱；“回测案例”一键载入三个预注册回测当时的状态。",
            step=2)

CHAINS = {"data/chain/live": "实时图谱（每日更新）", "data/chain/backtest_antai_fix1": "安泰回测图谱",
          "data/chain/backtest_linggang_fix1": "凌钢回测图谱", "data/chain/analysis_v1_fix1": "84 份公告图谱（方大回测用）"}
DEMOS = [("安泰集团 · 回测 2025-01-31", "600408", "2025-01-31", "data/chain/backtest_antai_fix1"),
         ("凌钢股份 · 回测 2024-04-30", "600231", "2024-04-30", "data/chain/backtest_linggang_fix1"),
         ("方大特钢 · 回测 2025-02-28", "600507", "2025-02-28", "data/chain/analysis_v1_fix1")]
SECTIONS = ["自身风险", "财报分析", "关联风险", "客户与供应商", "期货与原料", "产品暴露", "公告信号"]
SECTION_ICON = {"自身风险": ":material/monitoring:", "财报分析": ":material/receipt_long:", "关联风险": ":material/account_tree:",
                "客户与供应商": ":material/swap_horiz:", "期货与原料": ":material/candlestick_chart:",
                "产品暴露": ":material/inventory_2:", "公告信号": ":material/feed:"}
snaps = snapshots()
if not snaps:
    st.info("还没有承压评分快照。")
    st.stop()


def choose(code: str, snapshot: str | None, chain: str | None) -> None:
    st.session_state["pf_code"] = code
    if snapshot in snaps:
        st.session_state["pf_snap"] = snapshot
    if chain in CHAINS:
        st.session_state["pf_chain"] = chain


goto = st.session_state.pop("_goto_profile", None)          # arriving from another page's "档案" button
if goto:
    choose(goto["code"], goto.get("snapshot") or snaps[0], goto.get("chain") or "data/chain/live")
    if goto.get("tab") in SECTIONS:
        st.session_state["pf_tab"] = goto["tab"]
st.session_state.setdefault("pf_snap", snaps[0])
st.session_state.setdefault("pf_chain", "data/chain/live")

rows = fragility_rows(st.session_state["pf_snap"])
by_code = {r["security_code"]: r for r in rows}
order = sorted(by_code, key=lambda c: (by_code[c].get("peer_group") != "core", by_code[c].get("peer_group", "").startswith("extension"),
                                      -float(by_code[c]["total_score"] or 0)))
if st.session_state.get("pf_code") not in order:
    st.session_state["pf_code"] = order[0] if order else None

c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
code = c1.selectbox("企业（按承压由弱到强排列）", order, key="pf_code",
                    format_func=lambda c: f"{TIER_BADGE.get(by_code[c]['tier'], '')} {by_code[c]['security_name']}（{c}）"
                    + ("·扩展组" if by_code[c].get("peer_group", "").startswith("extension") else ""))
with c2.popover("数据版本", icon=":material/tune:", width="stretch"):
    snap = st.selectbox("评估日（承压快照）", snaps, key="pf_snap")
    chain = st.selectbox("关系图谱", list(CHAINS), key="pf_chain", format_func=CHAINS.get)
with c3.popover("回测案例", icon=":material/history:", width="stretch"):
    st.caption("载入预注册回测当时的企业、评估日和图谱")
    for label, demo_code, day, demo_chain in DEMOS:
        st.button(label, on_click=choose, args=(demo_code, day, demo_chain), width="stretch", key=f"demo_{demo_code}")
if snap != snaps[0] or chain != "data/chain/live":
    st.caption(f"当前数据版本：评估日 {snap} · {CHAINS[chain]}")
if code is None:
    st.stop()
rows = fragility_rows(snap)                                   # the snapshot may just have changed
row = next((r for r in rows if r["security_code"] == code), None)
name = row["security_name"] if row else code
folder = ROOT / "data" / "snapshots" / snap
if chain != "data/chain/live" and snap > "2025-12-31":
    st.warning("回测图谱应配合回测评估日使用，否则会用到当时还不存在的信息。")


@st.cache_data(show_spinner="正在推导传导路径…")
def load_paths(chain: str, snap: str):
    ranked, _, names = key_paths(ROOT / chain, ROOT / "data" / "snapshots" / snap)
    return ranked, names, edge_index(ROOT / chain)


ranked, names, eindex = load_paths(chain, snap)
mine = split_paths(filter_paths(ranked, company=code, hide_low_information=True, show_scenarios=False), code)
level, text = headline(name, row, len(mine["incoming"]), len(mine["outgoing"]), len(mine["absorbed"]))
verdict(level, text)

# ---------------------------------------------------------------- key points: every tab's conclusion in one place
detail = explain(folder, code) if (row and snapshot_meta(folder).get("version") == "v1") else None
history = score_history(code, snap)
tr = trend(history)
group = group_background(code)
margin = margin_snapshot("rebar", snap)
ore_x = ore_cost_exposure(code, snap, ORE_SHOCK, equity_of(snap, code))
hg = hedging(code, snap)
rs = report_signals(code, snap) if row else None
summary_ = checklist(name, row, detail, tr, group, margin, ore_x, hedge_label(hg),
                     len(mine["incoming"]), len(mine["outgoing"]), rs)
with st.container(border=True):
    k1, k2 = st.columns([3, 2], gap="large")
    with k1:
        st.markdown("**核查要点**（汇总下方各标签页的结论，不产生新分数）")
        st.markdown("\n".join(f"- {p_}" for p_ in summary_["points"]))
    with k2:
        st.markdown("**建议优先核查**（固定规则生成）")
        st.markdown("\n".join(f"{i}. {c_}" for i, c_ in enumerate(summary_["checks"], 1)) if summary_["checks"] else "暂无需要优先核查的事项。")
        brief = brief_html(name, code, snap, text, summary_, peer_dims(snap, code), row["reasons"] if row else "", rs,
                           path_rows(mine["incoming"] + mine["outgoing"], names, eindex, snapshot_equity(folder)))
        st.download_button("下载核查底稿（可打印为 PDF）", brief.encode("utf-8"), file_name=f"{name}_核查底稿_{snap}.html",
                           mime="text/html", icon=":material/download:", width="stretch")

st.session_state.setdefault("pf_tab", "自身风险")
section = st.segmented_control("查看", SECTIONS, key="pf_tab", label_visibility="collapsed",
                               format_func=lambda x: f"{SECTION_ICON[x]} {x}" + ("（情景）" if x in ("期货与原料", "产品暴露") else "")) or "自身风险"

# ---------------------------------------------------------------- own risk
if section == "自身风险":
    st.caption("自身风险 = 这家企业是否可能成为**风险源**。财务脆弱性（承压评分）：在 24 家核心钢厂中比较杠杆、短期偿债、造血、盈利、市场、"
               "对外担保六方面，0–100 分，**越高越脆弱**，≥ 60 为弱；它是模型预警，不是违约概率。公告中已发生的冻结、逾期、风险警示等事件会直接下调等级。")
    if not row:
        st.caption("该企业不在这一期承压评分范围内。")
    else:
        if row.get("peer_group", "").startswith("extension"):
            st.info(f"扩展组企业：只在本组内排名（{row.get('snapshot', '')} 评分），不进入 24 家核心钢厂排名。{row.get('caveat', '')}",
                    icon=":material/info:")
        rank = peer_rank(rows, code)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("财务脆弱性", TIER_BADGE.get(row["tier"], row.get("tier_label", "")))
        m2.metric("总分（越高越弱）", row["total_score"] or "—",
                  delta=f"{tr['delta']:+.1f}（较 {tr['from']}）" if tr else None, delta_color="inverse")
        m3.metric("核心钢厂中排名", f"第 {rank[0]} 弱 / {rank[1]}" if rank else "非核心样本")
        m4.metric("财报后风险事件", row.get("events_after_report") or "0")
        if detail and detail["rules"]:
            st.error("直接判为弱的规则：" + "；".join(detail["rules"]), icon=":material/gpp_bad:")
        st.markdown(f"**主要原因**：{row['reasons'] or '—'}")
        if detail:
            st.markdown("**各维度得分**（0 最强、100 最弱；贡献 = 权重 × 维度得分）")
            st.dataframe(pd.DataFrame([{"维度": d["dimension"], "维度得分": d["score"], "权重": d["effective_weight"],
                                        "对总分贡献": d["contribution"],
                                        "主要指标": "；".join(f"{m['metric']} {m['value']}（{m['rank']}）" for m in d["metrics"][:2])}
                                       for d in detail["dimensions"]]), hide_index=True, width="stretch")
        ch1, ch2 = st.columns(2, gap="large")
        if len(history) > 1:
            with ch1:
                st.markdown("**评分走势**（每日快照；红虚线 60 分以上为弱；▲ 新财报开始使用）")
                hdf = pd.DataFrame(history)
                hdf["日期"] = pd.to_datetime(hdf["日期"])
                hdf["财报"] = hdf["财报期"].map(period_label)
                line = alt.Chart(hdf).mark_line(point=True, color="#16324F").encode(
                    x=alt.X("日期:T", title=None, axis=alt.Axis(format="%m-%d")),
                    y=alt.Y("总分:Q", scale=alt.Scale(zero=False), title="总分（越高越弱）"),
                    tooltip=[alt.Tooltip("日期:T", format="%Y-%m-%d"), "总分:Q", "等级:N", alt.Tooltip("财报:N", title="所用财报")])
                rule = alt.Chart(pd.DataFrame({"y": [60]})).mark_rule(color="#d9534f", strokeDash=[4, 4]).encode(y="y:Q")
                marks = alt.Chart(hdf[hdf["新财报"]]).mark_point(shape="triangle-up", size=160, filled=True, color="#F28C28").encode(
                    x="日期:T", y="总分:Q", tooltip=[alt.Tooltip("日期:T", format="%Y-%m-%d"), alt.Tooltip("财报:N", title="开始使用")])
                st.altair_chart((line + rule + marks).properties(height=230), use_container_width=True)
                jumps = hdf[hdf["新财报"]]
                if not jumps.empty:
                    st.caption("；".join(f"{d:%m-%d} 开始使用{p_}" for d, p_ in zip(jumps["日期"], jumps["财报"]))
                               + "。两个 ▲ 之间的变化来自股价（市场维度）和同业相对位置。")
        pdims = peer_dims(snap, code)
        if pdims and row.get("peer_group") == "core":
            with ch2:
                st.markdown("**和 24 家核心钢厂比**（柱：本企业维度得分，越高越弱；灰色竖线：24 家中位数）")
                pdf = pd.DataFrame(pdims)
                order_ = [d["维度"] for d in pdims]
                pdf["颜色"] = pdf["差距"].map(lambda g: "明显更差" if g >= 15 else "接近或更好")
                bar = alt.Chart(pdf).mark_bar(height=18).encode(
                    y=alt.Y("维度:N", sort=order_, title=None),
                    x=alt.X("本企业:Q", scale=alt.Scale(domain=[0, 100]), title=None),
                    color=alt.Color("颜色:N", scale=alt.Scale(domain=["明显更差", "接近或更好"], range=["#d9534f", "#9fb3c8"]),
                                    legend=alt.Legend(orient="bottom", title=None)),
                    tooltip=["维度:N", alt.Tooltip("本企业:Q", format=".1f"), alt.Tooltip("核心钢厂中位数:Q", format=".1f"),
                             alt.Tooltip("差距:Q", format="+.1f")])
                tick = alt.Chart(pdf).mark_tick(color="#33475b", thickness=3, size=26).encode(
                    y=alt.Y("维度:N", sort=order_), x="核心钢厂中位数:Q")
                bars = bar + tick
                st.altair_chart(bars.properties(height=230), use_container_width=True)
        g = guarantee_evidence(folder, code)
        if g:
            st.markdown("**对外担保的依据公告**")
            st.dataframe(pd.DataFrame(g), hide_index=True, width="stretch")
        ev = events_after_report(folder, code, row.get("period", ""))
        if ev:
            st.markdown("**财报后的风险公告**（会使等级下调一档）")
            st.dataframe(pd.DataFrame(ev), hide_index=True, width="stretch")
        st.caption("财报同比环比与异常信号见“财报分析”；期货、原料成本情景和套期保值见“期货与原料”。")
        st.page_link("views/2_承压评分.py", label="完整评分拆解、敏感性与数据来源", icon=":material/monitoring:")

# ---------------------------------------------------------------- financial report analysis
if section == "财报分析":
    if not rs or not rs["period"]:
        st.caption("没有可用的季度财务摘要。")
    else:
        if rs and rs["period"]:
            p = rs["period"]
            st.markdown(f"**财报分析**（最近一期 {p[:4]} 年{ {'0331': '一季报', '0630': '半年报', '0930': '三季报', '1231': '年报'}[p[4:]] }，"
                        f"法定披露截止 {rs['available_by']}；同比为累计值，环比为单季度值；亏损时按绝对值计算，负数表示恶化）")
            from src import report_analysis as ra
            core = [r["security_code"] for r in rows if r.get("peer_group") == "core"]
            line = ra.reading(code, p, core)
            if line:
                st.info(f"**一句话解读**：{line}", icon=":material/insights:")
            # ⑤ where each growth rate stands among the 24 core mills
            field_of = {"营业总收入": "revenue", "归母净利润": "np", "扣非净利润": "np_deduct", "经营现金流量净额": "ocf"}
            table_ = [dict(r_, **{"同比在同行中": ra.position(code, ra.peer_growth(core, p, field_of[r_["指标"]]), True)})
                      for r_ in rs["rows"]]
            fmt = {"本期累计（亿元）": "{:.2f}", "上年同期（亿元）": "{:.2f}", "单季度（亿元）": "{:.2f}",
                   "同比": "{:+.1%}", "单季度环比": "{:+.1%}"}
            st.dataframe(pd.DataFrame(table_).style.format(fmt, na_rep="—"), hide_index=True, width="stretch")

            def _show(rows_):
                st.dataframe(pd.DataFrame([{"指标": r_["指标"], "本期": ra.fmt(r_["本期"], r_["_kind"]),
                                            "上年同期": ra.fmt(r_["上年同期"], r_["_kind"]),
                                            "24 家中位数": ra.fmt(r_["24 家中位数"], r_["_kind"]), "同行位置": r_["同行位置"]}
                                           for r_ in rows_]), hide_index=True, width="stretch")

            # ② DuPont
            dp = ra.dupont(code, p, core)
            st.markdown("**杜邦分析**　:gray[ROE = 销售净利率 × 总资产周转率 × 权益乘数，回答 ROE 高低来自盈利、周转还是杠杆]")
            _show(dp["rows"])
            roe_now = dp["rows"][3]["本期"]
            note = (f"三项相乘 ≈ {dp['product']:.1%}（报告的平均 ROE {ra.fmt(roe_now, 'pct')}，口径差异来自平均资产与净资产的取法）"
                    if dp["product"] is not None else "")
            if dp["worst"] and dp["gaps"][dp["worst"]] < -0.2:
                note += f"；与 24 家中位数相比，最大拖累是**{dp['worst'].split('（')[0]}**"
            if note:
                st.caption(note + "。周转率为年初至今口径，只与上年同期和同行同期比较。")
            # ③ earnings quality and working capital
            st.markdown("**盈利质量与营运能力**　:gray[现金流比利润更难粉饰；钢厂最怕存货跌价和回款变慢]")
            _show(ra.metric_rows(code, p, core, ["gm", "expense", "cash_np", "inv_days", "ar_days"]))
            st.caption("经营现金流 / 归母净利润只在盈利时有意义，亏损企业显示“—”，同行位置只在盈利企业中比较。")
            # ④ eight quarters
            tr = ra.trend(code, p)
            if tr:
                st.markdown("**近 8 个季度趋势**　:gray[单季度口径：持续走低才是真恶化，一个季度的波动不必过度解读]")
                chart = alt.Chart(pd.DataFrame(tr)).mark_line(point=True, strokeWidth=2).encode(
                    x=alt.X("季度:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("数值:Q", title=None, axis=alt.Axis(format="%")),
                    color=alt.Color("指标:N", scale=alt.Scale(range=["#1C5D99", "#E5484D", "#30A46C"]),
                                    legend=alt.Legend(orient="top", title=None)),
                    tooltip=["季度", "指标", alt.Tooltip("数值:Q", format=".1%")]).properties(height=240)
                zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#98A2B3", strokeDash=[3, 3]).encode(y="y:Q")
                st.altair_chart(chart + zero, width="stretch")
            if rs["signals"]:
                for s_ in rs["signals"]:
                    st.warning(f"**{s_['kind']}**：{s_['text']}", icon=":material/report:")
            else:
                st.caption("未发现财报异常信号（非经常性损益占比 ≥ 30%、盈利但经营现金流为负或不足净利润 50%、会计政策或估计变更公告）。")
            st.caption("财报异常信号是核查提示，不计入承压评分；阈值为筛查规则，未经校准。")
    st.caption("核对原始定期报告（新浪财经公告列表）")
    links = st.columns(4)
    for col, (label, url) in zip(links, report_links(code).items()):
        col.link_button(label, url, width="stretch")

# ---------------------------------------------------------------- related-party risk
if section == "关联风险":
    if not (mine["incoming"] or mine["outgoing"]):
        st.success(f"在{CHAINS[chain]}、评估日 {snap} 下，没有经过 {name} 的关键传导路径"
                   "（途经企业承压为强、风险可能受到缓释，金额不重大，或没有中高严重度的起点）。", icon=":material/check_circle:")
    for key, title, note in (("incoming", "风险传入或经过", "其他企业发生信用事件后，风险可能沿担保、购销或同集团关系传导至本企业"),
                             ("outgoing", "由它发出", "本企业的风险信号可能沿关系传导至其他企业"),
                             ("absorbed", "风险可能受到缓释（不预警）", "途经的上市公司承压为强，路径不再扩展，得分为 0，不计入预警")):
        if mine[key]:
            st.markdown(f"**{title}**（{len(mine[key])} 条）：{note}")
            st.dataframe(pd.DataFrame(path_rows(mine[key], names, eindex, snapshot_equity(ROOT / "data" / "snapshots" / snap))), hide_index=True, width="stretch",
                         column_config={"金额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                                        "得分": st.column_config.NumberColumn(format="%.2f")})
    st.divider()
    deposit_block(code, snap)
    if mine["incoming"] or mine["outgoing"] or mine["absorbed"]:
        if st.button("在传导图上查看每一步的公告原文", icon=":material/account_tree:"):
            st.session_state["_goto_network"] = {"chain": chain, "snapshot": snap, "company": code}
            st.switch_page("views/4_风险路径图.py")

# ---------------------------------------------------------------- customers and suppliers: how much, what share, how long
if section == "客户与供应商":
    from src.policy_shock import iron_ore_import, overseas_share
    from src.supply_relations import SIDE, concentration, summary
    ov, ore = overseas_share(code, snap), iron_ore_import(code, snap)
    if ov or ore:
        st.markdown("**对外贸易暴露**（出口端看境外收入，进口端看铁矿石来源）")
        e1, e2, e3 = st.columns(3)
        if ov:
            e1.metric(f"境外收入占比（{ov['period'][:4]}）", f"{ov['share']:.1%}", help=f"{ov['source']}，{ov['grade']} 级；{ov['items']}")
        if ore:
            e2.metric(f"铁矿石进口占比（{ore['fy']}，按吨）", f"{ore['import_share_t']:.1%}" if ore["import_share_t"] is not None else "—",
                      help=ore["source"])
            e3.metric("按金额", f"{ore['import_share_amount']:.1%}" if ore["import_share_amount"] is not None else "—",
                      help="进口铁矿石支出 ÷ 铁矿石总支出")
        st.caption("出口受海外关税、反倾销和碳关税影响（可在“市场冲击：期货、供需与政策 → 政策”模拟）；进口受海外矿价和汇率影响。")
    conc = concentration(code, snap)
    if conc:
        st.markdown("**客户与供应商集中度**（年报“前五名客户 / 供应商”，A 级：公司自己披露）")
        latest = {side: max((c for c in conc if c["side"] == side), key=lambda c: c["fy"]) for side in ("customer", "supplier")
                  if any(c["side"] == side for c in conc)}
        cols = st.columns(4)
        for col, side, label in ((cols[0], "customer", "前五大客户占销售"), (cols[2], "supplier", "前五大供应商占采购")):
            c = latest.get(side)
            if not c:
                continue
            col.metric(f"{label}（{c['fy']}）", f"{c['top5_share']:.1%}" if c["top5_share"] is not None else "—",
                       help=f"前五名合计 {c['top5_yi']:.2f} 亿元" if c["top5_yi"] else None)
            nxt = cols[1] if side == "customer" else cols[3]
            nxt.metric("其中关联方" if c["related_share"] is not None else "最大单一对象",
                       f"{c['related_share']:.1%}" if c["related_share"] is not None else
                       (f"{c['largest_share']:.1%}" if c["largest_share"] is not None else "—"),
                       help=(f"最大单一{'客户' if side == 'customer' else '供应商'}占 {c['largest_share']:.1%}；"
                             if c["largest_share"] is not None else "") +
                            (f"年度{'销售' if side == 'customer' else '采购'}总额约 {c['total_yi']:.0f} 亿元（前五名金额 ÷ 其占比）"
                             if c["total_yi"] else ""))
        st.dataframe(pd.DataFrame([{"年度": c["fy"], "方向": "客户（销售）" if c["side"] == "customer" else "供应商（采购）",
                                    "前五名合计(亿元)": c["top5_yi"], "占总额": c["top5_share"], "其中关联方": c["related_share"],
                                    "最大单一": c["largest_share"], "年度总额(亿元)": c["total_yi"],
                                    "出处": f"{c['source']} 第{c['page']}页" + ("" if c["check"] == "ok" else f"（{c['check']}）")}
                                   for c in conc]), hide_index=True, width="stretch",
                     column_config={k: st.column_config.NumberColumn(format="percent") for k in ("占总额", "其中关联方", "最大单一")} |
                                   {k: st.column_config.NumberColumn(format="%.2f") for k in ("前五名合计(亿元)", "年度总额(亿元)")})
    partners = summary(code, snap)
    if not (conc or partners):
        st.caption("还没有该企业的年报前五名表、募集说明书或关联交易金额。")
    for side in ("upstream", "downstream"):
        part = [r for r in partners if r["direction"] == side]
        if not part:
            continue
        st.markdown(f"**{SIDE[side]}**（按占比排序；金额统一为亿元，销量单列）")
        st.dataframe(pd.DataFrame([{
            "对方": r["counterparty"], "披露主体": "本公司" if r["company_id"] == code else r["company_name"],
            "关联方": r["related_party"], "年份": r["year"], "口径": r["amount_type"],
            "金额(亿元)": r["amount_yi"], "销量": r["quantity"], "占比": r["share"],
            "占比口径": (r["share_basis"] or "") + (f"（{r['share_method']}）" if r["share_method"] else ""),
            "实际发生年数": r["years_seen"] or None, "连续年数": r["run_years"] or None,
            "来源": f"{r['source_type']}：{r['source'][:40]}"} for r in part]),
            hide_index=True, width="stretch",
            column_config={"金额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                           "占比": st.column_config.NumberColumn(format="percent")})
    if partners:
        st.caption("口径说明：“预计额度”是关联交易公告给出的下一年上限，不算作实际发生的年份；“期末余额”是应收、预付等余额，"
                   "不是全年交易额；占比优先用原表披露，没有时用公司当年营业收入（销售）或年度采购总额（采购；缺年报时用营业成本近似）计算。"
                   "匿名的“客户一”无法跨年追踪，不计入连续年数。")

# ---------------------------------------------------------------- futures and raw materials (scenario)
if section == "期货与原料":
    st.caption("期货视角：钢材和原料的期货价格变动，会从收入端和成本端同时影响这家企业。只作情景，不计入承压评分"
               "（铁矿石冲击的预先登记检验未达显著）。")
    steel_x = steel_revenue_exposure(code, snap)
    f1, f2, f3, f4 = st.columns(4)
    if margin:
        f1.metric("行业：螺纹吨钢盘面利润", f"{margin['value']:,.0f} 元/吨", f"{margin['change']:+,.0f}（{WINDOW} 日）",
                  help=f"{margin['date']}；处于 {margin['since'][:4]} 年以来 {margin['pct_all']:.0%} 分位。螺纹 − 1.6×铁矿 − 0.5×焦炭")
        f1.caption(f"{margin['since'][:4]} 年以来 {margin['pct_all']:.0%} 分位")
    f2.metric(f"外购铁矿（{ore_x['fy']} 年报）" if ore_x else "外购铁矿", f"{ore_x['purchased_yi']:.1f} 亿元/年" if ore_x else "未披露",
              help=ore_x["source"] if ore_x else "年报未披露铁矿石供应情况表")
    if steel_x:
        tracked = sum(steel_x["shares"].values())
        f3.metric("收入中跟踪钢材期货的部分", f"{tracked:.0%}",
                  help="；".join(f"{STEEL_FUTURE[k]} {v:.0%}" for k, v in steel_x["shares"].items())
                       + f"（{steel_x['mix_period'][:4]} 年报分产品收入，B 级）")
    else:
        f3.metric("收入中跟踪钢材期货的部分", "未披露")
    f4.metric("套期保值（近 15 个月公告）", hedge_label(hg))

    st.markdown("**情景：期货价格变动后，这家企业一年的利润会受多大影响**")
    s1, s2 = st.columns(2)
    ore_mv = s1.slider("铁矿石价格变动", -30, 30, 10, 1, format="%d%%", key="pf_fut_ore")
    steel_mv = s2.slider("钢材价格变动（螺纹、热卷同幅）", -30, 30, 0, 1, format="%d%%", key="pf_fut_steel")
    eq_ = equity_of(snap, code)
    sc_ = company_scenario(ore_x, steel_x, ore_mv / 100, steel_mv / 100, eq_)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("成本端：多付原料", f"{sc_['cost_yi']:+.1f} 亿元" if sc_["cost_yi"] is not None else "无法计算")
    r2.metric("收入端：钢材收入变动", f"{sc_['revenue_yi']:+.1f} 亿元" if sc_["revenue_yi"] is not None else "无法计算")
    r3.metric("合计对利润", f"{sc_['profit_yi']:+.1f} 亿元" if sc_["profit_yi"] is not None else "无法计算")
    r4.metric("占净资产", f"{sc_['to_equity']:+.1%}" if sc_["to_equity"] is not None else ("净资产为负" if eq_ is not None and eq_ <= 0 else "—"))
    notes = []
    if ore_x:
        notes.append(f"成本端 = 外购铁矿 {ore_x['purchased_yi']:.1f} 亿元 × 铁矿变动（{ore_x['source']}）")
    if steel_x and steel_x.get("revenue_annual_yi"):
        notes.append(f"收入端 = 年化收入 {steel_x['revenue_annual_yi']:.0f} 亿元（按 {steel_x['revenue_period'][:4]} 年"
                     f"{ {'0331': '一季报', '0630': '半年报', '0930': '三季报', '1231': '年报'}.get(steel_x['revenue_period'][4:], '')}年化）"
                     f" × 跟踪钢材期货的收入占比 {sum(steel_x['shares'].values()):.0%} × 钢价变动")
    st.caption("；".join(notes) + "。一年口径、其他条件不变：不含库存、长协定价、产量调整和套保效果；焦炭、焦煤缺少企业级采购数据，未计入。")

    days_, rebar_ = margin_series("rebar")
    start_ = f"{int(snap[:4]) - 1}{snap[4:]}"
    mdf = pd.DataFrame([{"日期": d, "元/吨": v} for d, v in zip(days_, rebar_) if start_ <= d <= snap])
    if not mdf.empty:
        mdf["日期"] = pd.to_datetime(mdf["日期"])
        st.markdown("**行业背景：近一年螺纹吨钢盘面利润**")
        st.altair_chart(alt.Chart(mdf).mark_area(line={"color": "#16324F"}, color="#dbe5f0").encode(
            x=alt.X("日期:T", title=None, axis=alt.Axis(format="%Y-%m")),
            y=alt.Y("元/吨:Q", scale=alt.Scale(zero=False), title="元/吨"),
            tooltip=[alt.Tooltip("日期:T", format="%Y-%m-%d"), alt.Tooltip("元/吨:Q", format=",.0f")]).properties(height=200),
            use_container_width=True)

    biz = [x for x in hg["items"] if x["性质"] == "业务公告"]
    if biz:
        st.markdown(f"**套期保值公告**：{hedge_label(hg)}")
        st.dataframe(pd.DataFrame(biz)[["日期", "类别", "公告标题"]], hide_index=True, width="stretch")
        st.caption("有商品套保的企业，原料价格冲击可能部分被对冲；套保规模和效果需看定期报告。")
    else:
        st.caption(f"套期保值：{hedge_label(hg)}（公告缓存起点 {hg['cache_from'] or '—'}；未见不等于没有套保，需核对定期报告）。")
    if st.button("打开全行业期货情景（24 家钢厂对比）", icon=":material/candlestick_chart:", key="pf_to_futures"):
        st.session_state["sc_source"] = "期货与套保"
        st.switch_page("views/5_上下游情景.py")

# ---------------------------------------------------------------- product exposure
if section == "产品暴露":
    exposure = exposure_as_of(code, snap)
    if not (exposure and exposure.get("products")):
        st.caption("没有可用的分产品披露。")
    else:
        pnames = {p["product_id"]: p["name"] for p in products()}
        move = {m["product_id"]: m for m in price_moves(snap)}
        st.dataframe(pd.DataFrame([{
            "产品": pnames.get(k, k), "占收入": f"{v['share']:.1%}" if v.get("share") is not None else "—",
            f"近 {WINDOW} 日价格": f"{move[k]['ret']:+.1%}{' ⚠ 冲击' if move[k]['shock'] else ''}" if k in move else "—",
            "原文条目": v.get("items", "")}
            for k, v in sorted(exposure["products"].items(), key=lambda kv: -(kv[1].get("share") or 0))]),
            hide_index=True, width="stretch")
        st.caption(f"B 级：公司年报披露的分产品收入（{exposure['period'][:4]} 年报，东方财富主营构成）。"
                   f"价格涨跌 ≥ {THRESHOLD:.0%} 标为冲击。两次预注册检验方向一致但不显著，只作情景提示，不计入风险得分。")
        st.page_link("views/5_上下游情景.py", label="模拟一次价格或停产冲击", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- announcement signals
if section == "公告信号":
    sig = company_signals(ROOT / chain, code, snap)
    if sig:
        st.dataframe(pd.DataFrame(sig), hide_index=True, width="stretch")
        st.caption(f"来自{CHAINS[chain]}中已抽取的公告，截至评估日 {snap}，最新在前，最多 12 条。")
    else:
        st.caption(f"{CHAINS[chain]}中没有 {name} 在评估日前的公告信号。")
    st.page_link("views/3_一键分析.py", label="分析这家企业的一份新公告", icon=":material/bolt:")

# ---------------------------------------------------------------- where next
next_step(f"看 {name} 发生风险时，可能沿集团信用通道和供需通道传导至哪些企业", "风险传导", UNIFIED_PAGE, key="pf_next",
          state={"code": code, "snapshot": snap if chain == "data/chain/live" else None}, state_key="_goto_unified")
