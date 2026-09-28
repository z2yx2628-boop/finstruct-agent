"""风险传导总图：一张图、两条通道——集团信用通道（计分）与供需情景通道（情景），共用企业与承压等级。"""
import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extension import merged as with_extension  # noqa: E402
from src.network_view import filter_paths, key_paths, overview_chart, path_rows, second_order  # noqa: E402
from src.scenario import KINDS, build, company_name, core_mills, product_map, sector_links  # noqa: E402
from src.ui import TIER_BADGE, page_header, verdict  # noqa: E402
from src.unified import SCALE, credit_edges, layout, merge  # noqa: E402

page_header("风险传导总图", ":material/hub:", "一家企业出事或一次冲击发生，风险会沿哪些通道、传给谁？", grades=True,
            about="**一张图，两条通道。** 红色系是**集团信用通道**：公告披露的担保、关联交易和集团关系，经过盲测与 3 个预注册回测，"
                  "**计入风险得分**。蓝色系是**供需情景通道**：产品暴露、公告与债券募集说明书中的具名采购和销售、行业推断，"
                  "两次预注册检验不显著，**只作情景、不计分**。虚线表示仅凭集团名义或行业推断的连接。  \n"
                  "两条通道共用同一批企业和同一份承压评分。冲击从供需通道转入信用通道，必须满足衔接条件："
                  "暴露证据为 A/B 级、有披露的收入占比、企业承压为弱或中，且只沿担保或关联交易继续推。")
st.caption("🟥 红色系 = 集团信用通道（计分）　🟦 蓝色系 = 供需情景通道（情景，不计分）　┄ 虚线 = 集团名义或行业推断")

snaps = sorted((p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists()), reverse=True)
CHAIN = ROOT / "data" / "chain" / "live"


@st.cache_data(show_spinner="正在推导集团信用通道…")
def credit(snap: str):
    ranked, fragility, names = key_paths(CHAIN, ROOT / "data" / "snapshots" / snap)
    return ranked, fragility, names


@st.cache_data(show_spinner="正在检查冲击能否转入信用通道…")
def bridge(snap: str, codes: tuple[str, ...], shock: str):
    found = second_order(CHAIN, ROOT / "data" / "snapshots" / snap, list(codes), shock)
    return {c: [e for e in found[c] if all(s.rule in ("R1", "R2") for s in e["steps"])] for c in codes}


mode = st.segmented_control("起点", ["从一家企业出发", "从一次冲击出发"], default="从一家企业出发", key="u_mode")
c1, c2, c3 = st.columns([2, 1.2, 1.2])
snap = c3.selectbox("评估日（承压快照）", snaps, key="u_snap")
ranked, fragility, names = credit(snap)
fragility = with_extension(dict(fragility), snap)

credit_entries, bridged, supply, bridge_note = [], [], None, ""
if mode == "从一家企业出发":
    options = sorted(fragility, key=lambda c: (fragility[c].get("peer_group") != "core", -float(fragility[c].get("total_score") or 0)))
    code = c1.selectbox("企业", options, key="u_company",
                        format_func=lambda c: f"{TIER_BADGE.get(fragility[c].get('tier', ''), '')} {fragility[c]['security_name']}（{c}）")
    show_absorbed = c2.toggle("显示被吸收的路径", value=False, help="途经企业承压为强、得分为 0 的路径")
    items = filter_paths(ranked, company=code, hide_low_information=True, show_scenarios=False)
    credit_entries = [e for _, e in items if e["score"] > 0 or show_absorbed]
    supply = build("outage", snap, fragility, [], company=code) if code in core_mills() or code in fragility else None
    title = f"{fragility[code]['security_name']}：信用通道 {sum(1 for e in credit_entries if e['score'] > 0)} 条计分路径；供需通道列出它停产时波及的产品与客户"
else:
    kind = c1.selectbox("冲击类型", list(KINDS), format_func=KINDS.get, key="u_kind")
    if kind in ("price_up", "price_down"):
        products = {k: v for k, v in product_map().items() if v["layer"] in ("upstream", "steel") and k not in ("P_STEEL", "P_SEMI")}
        pid = c2.selectbox("产品", list(products), format_func=lambda k: products[k]["name"], key="u_product")
        supply = build(kind, snap, fragility, [], product_id=pid)
    elif kind == "outage":
        comp = c2.selectbox("停产企业", core_mills(), format_func=company_name, key="u_outage")
        supply = build(kind, snap, fragility, [], company=comp)
        credit_entries = [e for e in ranked if e["seed"] == comp and e["score"] > 0]
    else:
        sectors = {l["sector_id"]: l["sector"] for l in sector_links()}
        sid = c2.selectbox("下游行业", list(sectors), format_func=sectors.get, key="u_sector")
        supply = build(kind, snap, fragility, [], sector_id=sid)
    hit = [r for r in supply["companies"] if r.get("code") in fragility and r["grade"] in ("A", "B")
           and (r.get("share") or 0) > 0 and r["tier"] in ("weak", "medium")]
    onward = bridge(snap, tuple(r["code"] for r in hit), "supply" if kind == "outage" else "credit") if hit else {}
    for r in hit:
        bridged += onward.get(r["code"], [])
    bridge_note = (f"满足衔接条件并能沿担保/关联交易继续传导的企业：{'、'.join(r['name'] for r in hit if onward.get(r['code']))}。"
                   if any(onward.values()) else "本冲击没有满足衔接条件、能转入信用通道的企业（缺少 A/B 级暴露、披露占比，或受冲击企业承压为强）。")
    title = supply["title"]

cn, ce = credit_edges(credit_entries + bridged, names, fragility)
graph = merge(supply, cn, ce)
if not graph["edges"]:
    st.info("这个起点在两条通道上都没有可展示的连接。")
    st.stop()
level = "error" if any(e["score"] > 0 for e in credit_entries) else "warning" if supply and supply["companies"] else "success"
verdict(level, f"**{title}**" + (f"　{bridge_note}" if bridge_note else ""))

nodes, edges = layout(graph)
cols = int(max(n["x"] for n in nodes)) + 1
rows_n = max(sum(1 for n in nodes if n["x"] == x) for x in range(cols))
st.vega_lite_chart(overview_chart(nodes, edges, width=min(1200, max(680, 230 * cols)), height=max(320, 70 * rows_n), rule_scale=SCALE),
                   width="content")

left, right = st.columns(2, gap="large")
with left:
    st.subheader("集团信用通道（计分）", divider="red")
    rows = [dict(r, 性质="正式计分") for r in path_rows(list(enumerate(credit_entries)), names)] + \
           [dict(r, 性质="衔接线索（不计分）") for r in path_rows(list(enumerate(bridged)), names)]
    if rows:
        st.dataframe(pd.DataFrame(rows).drop(columns=["排名"]), hide_index=True, width="stretch",
                     column_config={"得分": st.column_config.NumberColumn(format="%.2f")})
        if bridged:
            st.caption("“衔接线索”是冲击经衔接条件转入信用通道后推出的路径：假设严重度为中，得分只作线索，不进入正式排名。")
    else:
        st.caption("没有经过它的计分路径。")
    if st.button("看每一步的公告原文", icon=":material/article:", key="u_to_credit"):
        target = code if mode == "从一家企业出发" else None
        st.session_state["_goto_network"] = {"chain": "data/chain/live", "snapshot": snap, "company": target}
        st.switch_page("pages/4_风险路径图.py")
with right:
    st.subheader("供需情景通道（不计分）", divider="blue")
    if supply and supply["companies"]:
        st.dataframe(pd.DataFrame([{"企业": r["name"], "承压": TIER_BADGE.get(r["tier"], "未评分"), "影响": r["effect"][:40],
                                    "证据": r["grade"]} for r in supply["companies"]]), hide_index=True, width="stretch")
    else:
        st.caption("没有供需通道上的暴露企业。")
    st.page_link("pages/5_上下游情景.py", label="调整冲击幅度、看压力指数与政策冲击", icon=":material/tune:")
