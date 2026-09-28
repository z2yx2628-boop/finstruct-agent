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
from src.ui import TIER_BADGE, deposit_block, page_header, verdict  # noqa: E402

page_header("企业档案", ":material/badge:", "这家企业自身扛不扛得住？风险会从哪里传进来、传到哪里去？", grades=True,
            about="把其他页面的结果按企业重新组合：**自身风险**来自企业承压评分；**关联风险**来自集团信用通道的路径"
                  "（只含公告披露的关系，C 级情景不计入）；**产品暴露**是 B 级情景信息；**公告信号**列出抽取到的原始事件。"
                  "本页不产生新的分数或排名。")

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

cols = st.columns(len(DEMOS) + 1)
cols[0].caption("回测演示")
for col, (label, code, day, chain) in zip(cols[1:], DEMOS):
    col.button(label, on_click=choose, args=(code, day, chain), width="stretch")

rows = fragility_rows(st.session_state["pf_snap"])
by_code = {r["security_code"]: r for r in rows}
order = sorted(by_code, key=lambda c: (by_code[c].get("peer_group") != "core", by_code[c].get("peer_group", "").startswith("extension"),
                                      -float(by_code[c]["total_score"] or 0)))
if st.session_state.get("pf_code") not in order:
    st.session_state["pf_code"] = order[0] if order else None

c1, c2, c3 = st.columns([2, 1, 1.4])
code = c1.selectbox("企业（按承压由弱到强排列）", order, key="pf_code",
                    format_func=lambda c: f"{TIER_BADGE.get(by_code[c]['tier'], '')} {by_code[c]['security_name']}（{c}）"
                    + ("·扩展组" if by_code[c].get("peer_group", "").startswith("extension") else ""))
snap = c2.selectbox("评估日（承压快照）", snaps, key="pf_snap")
chain = c3.selectbox("关系图谱", list(CHAINS), key="pf_chain", format_func=CHAINS.get)
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
    if not row:
        st.caption("该企业不在这一期承压评分范围内。")
    else:
        if row.get("peer_group", "").startswith("extension"):
            st.info(f"扩展组企业：只在本组内排名（{row.get('snapshot', '')} 评分），不进入 24 家核心钢厂排名。{row.get('caveat', '')}",
                    icon=":material/info:")
        rank = peer_rank(rows, code)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("承压等级", TIER_BADGE.get(row["tier"], row.get("tier_label", "")))
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

# ---------------------------------------------------------------- named trading partners (bond prospectuses)
with tab_chain:
    from src.prospectus_links import DIRECTION, ROLE_LABEL, for_company
    partners = for_company(code, snap)
    if not partners:
        st.caption("还没有收集到该企业或其集团的债券募集说明书。已收集：河钢、鞍钢、包钢、沙钢的集团或上市公司说明书。")
    else:
        st.caption("来源：该企业或其所属集团的债券募集说明书中“前五大”表（A 级：写明对方名称和金额）。"
                   "“是否关联方”照抄原表；非关联方就是公开材料里少见的**跨集团真实交易对手**。数字尚未逐行人工核对。")
        for side, label in (("upstream", "上游：供应商、预付与应付"), ("downstream", "下游：客户、应收与合同负债")):
            part = [r for r in partners if DIRECTION.get(r["role"]) == side]
            if part:
                st.markdown(f"**{label}**")
                st.dataframe(pd.DataFrame([{"表": ROLE_LABEL.get(r["role"], r["role"]), "对方": r["counterparty"],
                                            "上市代码": r["counterparty_code"], "金额": f"{r['amount']} {r['unit']}",
                                            "期末": r["period"], "关联方": r["related_party"], "说明": r["note"],
                                            "出处": f"{r['issuer']}·{r['source_title'][:22]}… 第{r['page']}页"} for r in part]),
                             hide_index=True, width="stretch")

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
