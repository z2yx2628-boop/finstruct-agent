"""风险传导总图：一张图、两条通道——集团信用通道（计分）与供需情景通道（情景），共用企业与承压等级。"""
import csv
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extension import merged as with_extension  # noqa: E402
from src.flow_view import TOP, conclusion, credit_flows, disclosed_suppliers, flow_chart, supply_flows, table_rows  # noqa: E402
from src.network_view import filter_paths, key_paths, second_order  # noqa: E402
from src.policy_flow import (POLICY_KINDS, POLICY_NOTE, bridge_candidates, margin_context, mark_hedging,  # noqa: E402
                             policy_flows, policy_rows)
from src.scenario import KINDS, build, company_name, core_mills, product_map, sector_links  # noqa: E402
from src.ui import TIER_BADGE, next_step, page_header, verdict  # noqa: E402
from src.validity import is_active  # noqa: E402

page_header("风险传导", ":material/hub:", "一家企业发生信用事件或出现一次外部冲击时，风险可能沿哪些通道传导至哪些企业？", grades=True,
            about="**先选通道，再看图。** 图分三栏：左边是风险从谁传来（或它的上游供应商），中间是起点，右边是会传给谁，"
                  "从上到下按影响强度排列，线越粗影响越强。**集团信用通道**：公告披露的担保、关联交易和集团关系，经过盲测与 3 个预注册回测，"
                  "**计入风险得分**。蓝色系是**供需情景通道**：产品暴露、公告与债券募集说明书中的具名采购和销售、行业推断，"
                  "两次预注册检验不显著，**只作情景、不计分**。虚线表示仅凭集团名义或行业推断的连接。  \n"
                  "两条通道共用同一批企业和同一份承压评分。冲击从供需通道转入信用通道，必须满足衔接条件："
                  "暴露证据为 A/B 级、有披露的收入占比、企业承压为弱或中，且只沿担保或关联交易继续推。",
            step=3)
snaps = sorted((p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists()), reverse=True)
CHAIN = ROOT / "data" / "chain" / "live"


@st.cache_data(show_spinner="正在推导集团信用通道…")
def credit(snap: str):
    ranked, fragility, names = key_paths(CHAIN, ROOT / "data" / "snapshots" / snap)
    return ranked, fragility, names


@st.cache_data(show_spinner=False)
def chain_rows(snap: str) -> list[dict]:
    with (CHAIN / "edges.csv").open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if is_active(r, snap)]


@st.cache_data(show_spinner="正在检查冲击能否转入信用通道…")
def bridge(snap: str, codes: tuple[str, ...], shock: str):
    found = second_order(CHAIN, ROOT / "data" / "snapshots" / snap, list(codes), shock)
    return {c: [e for e in found[c] if all(s.rule in ("R1", "R2") for s in e["steps"])] for c in codes}


goto = st.session_state.pop("_goto_unified", None)             # arriving from 企业档案, the home page or the search bar
if goto and goto.get("shock"):                                     # back from 市场冲击 with its shock
    st.session_state["u_mode"] = "从一次冲击出发"
    st.session_state.update({k: v for k, v in goto["shock"].items() if v is not None})
elif goto:
    st.session_state["u_mode"] = "从一家企业出发"
    if goto.get("code"):
        st.session_state["u_company"] = goto["code"]
    if goto.get("snapshot") in snaps:
        st.session_state["u_snap"] = goto["snapshot"]

mode = st.segmented_control("起点", ["从一家企业出发", "从一次冲击出发"], default="从一家企业出发", key="u_mode")
c1, c2, c3 = st.columns([2, 1.2, 1.2])
snap = c3.selectbox("评估日（承压快照）", snaps, key="u_snap")
ranked, fragility, names = credit(snap)
fragility = with_extension(dict(fragility), snap)
edges_now = chain_rows(snap)

if mode == "从一家企业出发":
    options = sorted(fragility, key=lambda c: (fragility[c].get("peer_group") != "core", -float(fragility[c].get("total_score") or 0)))
    if st.session_state.get("u_company") not in options:
        st.session_state.pop("u_company", None)
    code = c1.selectbox("企业", options, key="u_company",
                        format_func=lambda c: f"{TIER_BADGE.get(fragility[c].get('tier', ''), '')} {fragility[c]['security_name']}（{c}）")
    # same-group links without amounts and paths ending at strong companies are shown too (flagged), so a weak
    # company never reads as "no credit link at all" when its risk does travel and is only absorbed
    items = filter_paths(ranked, company=code, hide_low_information=False, show_scenarios=False)
    entries = [e for _, e in items]
    supply = build("outage", snap, fragility, edges_now, company=code)
    credit_f = credit_flows(entries, names, fragility, focus=code)
    supply_f = supply_flows(supply, code, disclosed_suppliers(edges_now, code, names, fragility))
    center, center_tier = fragility[code]["security_name"], fragility[code].get("tier", "")
    level_, text = conclusion(center, credit_f, supply_f)
    bridged = []
else:
    ALL_KINDS = {**KINDS, **POLICY_KINDS}
    if st.session_state.get("u_kind") not in ALL_KINDS:
        st.session_state.pop("u_kind", None)
    kind = c1.selectbox("冲击类型", list(ALL_KINDS), format_func=ALL_KINDS.get, key="u_kind",
                        help="产品价格、企业停产、下游需求沿产品图逐层传导；政策冲击直接作用于每家钢厂，按暴露和承压排序。")
    entries, pid, notes = [], None, []
    if kind in POLICY_KINDS:
        # a policy hits each mill directly: one hop from the policy to the mills, ranked by the stress index
        supply_f = policy_flows(kind, policy_rows(kind, fragility, snap))
        hit_codes = bridge_candidates(supply_f)
        onward = bridge(snap, tuple(hit_codes), "credit") if hit_codes else {}
        hit = [{"code": c, "name": names.get(c) or fragility[c]["security_name"]} for c in hit_codes]
        center = POLICY_KINDS[kind]
        notes.append(POLICY_NOTE[kind])
    else:
        if kind in ("price_up", "price_down"):
            products = {k: v for k, v in product_map().items() if v["layer"] in ("upstream", "steel") and k not in ("P_STEEL", "P_SEMI")}
            pid = c2.selectbox("产品", list(products), format_func=lambda k: products[k]["name"], key="u_product")
            supply = build(kind, snap, fragility, edges_now, product_id=pid)
        elif kind == "outage":
            comp = c2.selectbox("停产企业", core_mills(), format_func=company_name, key="u_outage")
            supply = build(kind, snap, fragility, edges_now, company=comp)
            entries = [e for e in ranked if e["seed"] == comp and e["score"] > 0]
        else:
            sectors = {l["sector_id"]: l["sector"] for l in sector_links()}
            sid = c2.selectbox("下游行业", list(sectors), format_func=sectors.get, key="u_sector")
            supply = build(kind, snap, fragility, edges_now, sector_id=sid)
        # a supply shock continues into the credit channel only through the gated bridge
        hit = [r for r in supply["companies"] if r.get("code") in fragility and r["grade"] in ("A", "B")
               and (r.get("share") or 0) > 0 and r["tier"] in ("weak", "medium")]
        onward = bridge(snap, tuple(r["code"] for r in hit), "supply" if kind == "outage" else "credit") if hit else {}
        supply_f = supply_flows(supply, "SHOCK")
        center = supply["title"]
        if kind in ("price_up", "price_down"):
            # futures: where the industry-wide board margin stands, and which exposed mills disclose hedging
            margins = margin_context(pid, snap)
            if margins:
                notes.append("**期货盘面利润（行业压力背景）**：" + "；".join(margins) + "。")
            n_hedged = mark_hedging(supply_f["right"], snap)
            if n_hedged:
                notes.append(f"受影响企业中 {n_hedged} 家近 15 个月披露过套期保值（表中“通道”已标注），价格冲击对它们的实际影响可能更小。")
    bridged = [e for r in hit for e in onward.get(r["code"], [])]
    credit_f = credit_flows(entries + bridged, names, fragility, focus=None)
    center_tier = ""
    level_, text = conclusion(center, credit_f, supply_f, shock=True)
    if kind in POLICY_KINDS:
        text = text.replace("**供需上**波及", "**政策上**直接影响")
    if hit:
        text += ("　满足衔接条件、能沿担保/关联交易继续传导的企业：" + "、".join(r["name"] for r in hit if onward.get(r["code"])) + "。"
                 if any(onward.values()) else "　没有受冲击企业满足转入信用通道的衔接条件。")

verdict(level_, text)
if mode != "从一家企业出发":
    for n_ in notes:
        st.caption(n_)

# ---------------------------------------------------------------- one channel at a time
n_credit = sum(1 for r in credit_f["left"] + credit_f["right"] if not r.get("absorbed"))
n_absorbed = sum(1 for r in credit_f["left"] + credit_f["right"] if r.get("absorbed"))
n_supply = len(supply_f["left"]) + len(supply_f["right"])
CHANNELS = {"credit": f"信用传导（计分）· {n_credit}" + (f"（另 {n_absorbed} 条缓释）" if n_absorbed else ""),
            "supply": ("政策冲击（情景）" if mode != "从一家企业出发" and kind in POLICY_KINDS else "供需传导（情景）") + f" · {n_supply}"}
if st.session_state.get("u_channel_for") != (mode, center):          # a new start picks the channel that has content
    st.session_state["u_channel_for"] = (mode, center)
    st.session_state["u_channel"] = "credit" if (n_credit or n_absorbed) or not n_supply else "supply"
channel = st.segmented_control("看哪种传导", list(CHANNELS), format_func=CHANNELS.get, key="u_channel") or "credit"
flows = credit_f if channel == "credit" else supply_f
show_all = st.toggle("显示全部", value=False, key="u_all", help=f"默认每侧只画最强的 {TOP} 条，其余见下表")
top = 99 if show_all else TOP

if not flows["left"] and not flows["right"]:
    st.info("信用通道上没有经过它的计分路径：它没有通过担保或关联交易与其他企业形成可计分的连接。可切换到「供需传导」查看情景。"
            if channel == "credit" else "供需通道上没有找到受影响的企业。")
else:
    head_l, head_c, head_r = st.columns([1, 1, 1])
    head_l.markdown(":gray[**← 风险来自 / 上游**]" if flows["left"] else "")
    head_r.markdown(":gray[**会传给 / 受影响 →**]", help="按影响强度从上到下排列")
    st.vega_lite_chart(flow_chart(center, center_tier, flows["left"], flows["right"], channel, top=top), width="stretch")
    st.caption(("线越粗 = 路径得分越高（相对本图最高分）；灰色虚线 = 对方承压为强、风险可能被缓释（不计分）" if channel == "credit" else "线越粗 = 证据越强、暴露越大（披露金额或收入占比）")
               + "　实线 = 公告披露（A/B 级）　虚线 = 行业推断（C 级）　圆点颜色越深 = 影响越强　括号内 = 企业自身承压"
               + ("" if channel == "credit" else "　·　情景，不计入风险得分"))

    for side, label in (("right", "会传给 / 受影响"), ("left", "风险来自 / 上游")):
        if flows[side]:
            st.markdown(f"**{label}**（{len(flows[side])} 家）")
            st.dataframe(pd.DataFrame(table_rows(flows[side])), hide_index=True, width="stretch",
                         column_config={"影响强度": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                                        "依据": st.column_config.TextColumn(width="large")})
    if channel == "credit" and bridged:
        st.caption("含“衔接线索”：冲击经衔接条件转入信用通道后推出的路径，假设严重度为中，只作线索，不进入正式排名。")

# ---------------------------------------------------------------- the parts behind this picture
from datetime import date as _date  # noqa: E402
in_company = mode == "从一家企业出发"
who = fragility[code]["security_name"] if in_company else None


def go(page: str, state_key: str, state: dict) -> None:
    st.session_state[state_key] = state
    st.switch_page(page)


st.markdown("##### 这张图背后的明细")
st.caption("图上的每个元素都有一页明细：节点颜色来自承压评分，紫色线来自信用通道，蓝色线来自市场冲击情景，每条线的依据来自公告事实抽取。"
           "跳转时会带上当前企业或冲击，明细页顶部可以一键返回。")
p1, p2, p3, p4 = st.columns(4)
with p1.container(border=True):
    st.markdown("**① 节点颜色 · 承压评分**")
    st.caption("括号里的弱 / 中 / 强：决定风险全额传递、减半还是被缓释。")
    if st.button(f"看{who}的评分拆解" if who else "看承压评分全表", icon=":material/monitoring:", width="stretch", key="u_to_score"):
        go("views/2_承压评分.py", "_goto_score", {"code": code if in_company else None, "snapshot": snap})
with p2.container(border=True):
    st.markdown("**② 紫色线 · 信用通道明细**")
    st.caption("逐条路径：得分 = 起点严重度 × 金额系数 × 途经企业承压，附每一步公告原文。")
    if st.button("打开信用通道明细", icon=":material/account_tree:", width="stretch", key="u_to_credit",
                 type="primary" if channel == "credit" else "secondary"):
        go("views/4_风险路径图.py", "_goto_network", {"chain": "data/chain/live", "snapshot": snap,
                                                    "company": code if in_company else None})
with p3.container(border=True):
    st.markdown("**③ 蓝色线 · 市场冲击情景**")
    st.caption("调整冲击幅度和政策假设、看期货盘面利润与套保，以及冲击怎样转入信用通道；不计分。")
    if in_company:
        shock = {"sc_kind": "outage", "sc_company": code if code in core_mills() else None}
    elif kind in POLICY_KINDS:
        shock = {"sc_source": "政策", "pol_kind": {"policy_carbon": "carbon", "policy_export": "export"}[kind]}
    else:
        shock = {"sc_kind": kind, "sc_product": st.session_state.get("u_product"),
                 "sc_company": st.session_state.get("u_outage"), "sc_sector": st.session_state.get("u_sector")}
    if not (not in_company and kind in POLICY_KINDS):
        shock["sc_day"] = _date.fromisoformat(snap)
    if st.button("打开市场冲击", icon=":material/swap_horiz:", width="stretch", key="u_to_shock",
                 type="primary" if channel == "supply" else "secondary"):
        go("views/5_上下游情景.py", "_goto_shock", shock)
with p4.container(border=True):
    st.markdown("**④ 连线依据 · 公告事实抽取**")
    st.caption("每条担保、关联交易线都是从公告里抽出来的，字段标注原文页码。")
    if st.button("打开公告事实抽取", icon=":material/description:", width="stretch", key="u_to_extract"):
        st.switch_page("views/1_公告结构化.py")

next_step("分析一份新公告：系统抽取事实、评估相关企业的财务脆弱性，并推导可能的传导路径", "分析新公告", "views/3_一键分析.py",
          key="u_next")
