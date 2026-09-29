"""企业档案：一家企业一页 —— 自身扛不扛得住、风险从哪里传进来/传到哪里去、每条依据在哪。"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fragility_view import events_after_report, explain, guarantee_evidence, report_links, snapshot_meta  # noqa: E402
from src.network_view import edge_index, filter_paths, key_paths, name_of, path_rows  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.product_layer import exposure_as_of, products  # noqa: E402
from src.profile import company_signals, fragility_rows, headline, peer_rank, snapshots, split_paths  # noqa: E402
from src.ui import TIER_BADGE, UNIFIED_PAGE, deposit_block, next_step, page_header, verdict  # noqa: E402

page_header("企业档案", ":material/badge:", "这家企业自身扛不扛得住？风险会从哪里传进来、传到哪里去？", grades=True,
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

tab_own, tab_links, tab_chain, tab_products, tab_events = st.tabs(
    [":material/monitoring: 自身风险", ":material/account_tree: 关联风险", ":material/swap_horiz: 主要客户与供应商",
     ":material/inventory_2: 产品暴露（情景）", ":material/feed: 公告信号"])

# ---------------------------------------------------------------- own risk
with tab_own:
    st.caption("自身风险 = 这家企业会不会成为**风险源**。抗冲击能力（承压评分）：在 24 家核心钢厂中比较杠杆、短期偿债、造血、盈利、市场、"
               "对外担保六方面，0–100 分，**越高越脆弱**，≥ 60 为弱；它是模型预警，不是违约概率。公告中已发生的冻结、逾期、风险警示等事件会直接下调等级。")
    if not row:
        st.caption("该企业不在这一期承压评分范围内。")
    else:
        if row.get("peer_group", "").startswith("extension"):
            st.info(f"扩展组企业：只在本组内排名（{row.get('snapshot', '')} 评分），不进入 24 家核心钢厂排名。{row.get('caveat', '')}",
                    icon=":material/info:")
        rank = peer_rank(rows, code)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("抗冲击能力", TIER_BADGE.get(row["tier"], row.get("tier_label", "")))
        m2.metric("总分（越高越弱）", row["total_score"] or "—")
        m3.metric("核心钢厂中排名", f"第 {rank[0]} 弱 / {rank[1]}" if rank else "非核心样本")
        m4.metric("财报后风险事件", row.get("events_after_report") or "0")
        detail = explain(folder, code) if snapshot_meta(folder).get("version") == "v1" else None
        if detail and detail["rules"]:
            st.error("直接判为弱的规则：" + "；".join(detail["rules"]), icon=":material/gpp_bad:")
        st.markdown(f"**主要原因**：{row['reasons'] or '—'}")
        if detail:
            st.markdown("**各维度得分**（0 最强、100 最弱；贡献 = 权重 × 维度得分）")
            st.dataframe(pd.DataFrame([{"维度": d["dimension"], "维度得分": d["score"], "权重": d["effective_weight"],
                                        "对总分贡献": d["contribution"],
                                        "主要指标": "；".join(f"{m['metric']} {m['value']}（{m['rank']}）" for m in d["metrics"][:2])}
                                       for d in detail["dimensions"]]), hide_index=True, width="stretch")
        g = guarantee_evidence(folder, code)
        if g:
            st.markdown("**对外担保的依据公告**")
            st.dataframe(pd.DataFrame(g), hide_index=True, width="stretch")
        ev = events_after_report(folder, code, row.get("period", ""))
        if ev:
            st.markdown("**财报后的风险公告**（会使等级下调一档）")
            st.dataframe(pd.DataFrame(ev), hide_index=True, width="stretch")
        st.caption("核对原始定期报告（新浪财经公告列表）")
        links = st.columns(4)
        for col, (label, url) in zip(links, report_links(code).items()):
            col.link_button(label, url, width="stretch")
        st.page_link("pages/2_承压评分.py", label="完整评分拆解、敏感性与数据来源", icon=":material/monitoring:")

# ---------------------------------------------------------------- related-party risk
with tab_links:
    if not (mine["incoming"] or mine["outgoing"]):
        st.success(f"在{CHAINS[chain]}、评估日 {snap} 下，没有经过 {name} 的关键传导路径"
                   "（风险被强企业吸收、金额不重大，或没有中高严重度的起点）。", icon=":material/check_circle:")
    for key, title, note in (("incoming", "风险传入或经过", "别的企业出事后，风险沿担保、购销或同集团关系传到它"),
                             ("outgoing", "由它发出", "它自己的风险信号沿关系传给别人"),
                             ("absorbed", "被吸收（不预警）", "途经的上市公司承压为强，得分为 0，不计入预警")):
        if mine[key]:
            st.markdown(f"**{title}**（{len(mine[key])} 条）：{note}")
            st.dataframe(pd.DataFrame(path_rows(mine[key], names, eindex)), hide_index=True, width="stretch",
                         column_config={"金额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                                        "得分": st.column_config.NumberColumn(format="%.2f")})
    st.divider()
    deposit_block(code, snap)
    if mine["incoming"] or mine["outgoing"] or mine["absorbed"]:
        if st.button("在传导图上查看每一步的公告原文", icon=":material/account_tree:"):
            st.session_state["_goto_network"] = {"chain": chain, "snapshot": snap, "company": code}
            st.switch_page("pages/4_风险路径图.py")

# ---------------------------------------------------------------- customers and suppliers: how much, what share, how long
with tab_chain:
    from src.supply_relations import SIDE, concentration, summary
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

# ---------------------------------------------------------------- product exposure
with tab_products:
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
        st.page_link("pages/5_上下游情景.py", label="模拟一次价格或停产冲击", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- announcement signals
with tab_events:
    sig = company_signals(ROOT / chain, code, snap)
    if sig:
        st.dataframe(pd.DataFrame(sig), hide_index=True, width="stretch")
        st.caption(f"来自{CHAINS[chain]}中已抽取的公告，截至评估日 {snap}，最新在前，最多 12 条。")
    else:
        st.caption(f"{CHAINS[chain]}中没有 {name} 在评估日前的公告信号。")
    st.page_link("pages/3_一键分析.py", label="分析这家企业的一份新公告", icon=":material/bolt:")

# ---------------------------------------------------------------- where next
next_step(f"看 {name} 出事时，风险会沿集团信用通道和供需通道传给谁", "风险传导", UNIFIED_PAGE, key="pf_next",
          state={"code": code, "snapshot": snap if chain == "data/chain/live" else None}, state_key="_goto_unified")
