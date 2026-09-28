"""上下游情景：一个产品或行业冲击，经产品层传到哪些企业（情景路径，不计入正式风险得分）。"""
import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.network_view import SCENARIO_RULE_SCALE, key_paths, overview_chart, route, second_order  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves, scenario_stress  # noqa: E402
from src.scenario import (CAVEAT, KINDS, RULES, build, company_name, core_mills, layout, product_map, sector_links,
                          verified_product_links)  # noqa: E402
from src.sources import titles  # noqa: E402
from src.validity import is_active  # noqa: E402

TIER = {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强", "": "未评分"}
GRADE = {"A": "A 披露确认", "B": "B 部分确认", "C": "C 行业推断", "—": "—"}

from src.ui import page_header  # noqa: E402
page_header("上下游情景", ":material/swap_horiz:", "一次产品价格、停产或需求冲击，会经产品波及哪些企业？", grades=True,
            about=CAVEAT + "  \n**传导链**：冲击 → 暴露于该产品的企业（公司自己披露的分产品收入 B 级；公告披露的采购/销售 A 级）"
                           "→ 企业承压 → 钢材产品 → 下游行业（C 级）→ 下游代表企业（年报点名钢材为主要原材料 B 级，否则 C 级）。  \n"
                           "**企业级具名交易（A 级）**：钢铁集团债券募集说明书“前五大供应商/客户/应付/预付/预收”表中写明名称和金额的非关联交易对手，"
                           "例如鞍钢集团的焦煤供应商；同样只作情景，不计入风险得分。")
st.caption("⚠ 情景提示：跨集团上下游多为 B/C 级证据，不计入风险得分，不代表真实交易或损失预测。")

snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists())

source = st.segmented_control("冲击来源", ["产品与需求", "政策"], default="产品与需求", key="sc_source")
if source == "政策":
    from src.policy_render import render_policy          # noqa: E402
    render_policy(snaps)
    st.stop()

DEMOS = {"演示：2024-09-30 焦炭 20 日 +13%": ("price_up", "P_COKE", None, None, "2024-09-30"),
         "演示：凌钢停产": ("outage", None, "600231", None, None),
         "演示：汽车需求下降": ("demand_down", None, None, "S_AUTO", None)}


def use_demo(kind, pid, company, sector, day):
    st.session_state.update({"sc_kind": kind, "sc_day": date.fromisoformat(day) if day else date.today()})
    if pid:
        st.session_state["sc_product"] = pid
    if company:
        st.session_state["sc_company"] = company
    if sector:
        st.session_state["sc_sector"] = sector


cols = st.columns(len(DEMOS))
for col, (label, args) in zip(cols, DEMOS.items()):
    col.button(label, on_click=use_demo, args=args, width="stretch")

c1, c2, c3 = st.columns([1.2, 2, 1.2])
kind = c1.selectbox("冲击类型", list(KINDS), format_func=KINDS.get, key="sc_kind")
if "sc_day" not in st.session_state:
    st.session_state["sc_day"] = date.today()
day = c3.date_input("评估日", key="sc_day").isoformat()
products = {k: v for k, v in product_map().items() if v["layer"] in ("upstream", "steel") and k not in ("P_STEEL", "P_SEMI")}
sectors = {l["sector_id"]: l["sector"] for l in sector_links()}
product = company = sector = None
if kind in ("price_up", "price_down"):
    product = c2.selectbox("产品", list(products), format_func=lambda k: products[k]["name"], key="sc_product")
elif kind == "outage":
    company = c2.selectbox("停产企业", core_mills(), format_func=company_name, key="sc_company")
else:
    sector = c2.selectbox("下游行业", list(sectors), format_func=sectors.get, key="sc_sector")

moves = price_moves(day)
if moves:
    st.caption(f"近 {WINDOW} 个交易日产品价格（|涨跌| ≥ {THRESHOLD:.0%} 视为冲击）：" + "；".join(
        f"{'**' if m['shock'] else ''}{m['product']} {m['ret']:+.1%}{'**' if m['shock'] else ''}" for m in moves)
        + f"（截至 {moves[0]['date']}）")

price_change = None
if kind in ("price_up", "price_down"):
    observed = next((m["ret"] for m in moves if m["product_id"] == product), None)
    fallback = 0.10 if kind == "price_up" else -0.10
    default_change = observed if observed is not None else fallback
    price_change_pct = st.number_input("情景价格变化（%）", min_value=-80.0, max_value=80.0,
                                       value=round(default_change * 100, 1), step=1.0,
                                       help="默认取评估日前20个交易日实际变化；可改为压力测试假设。")
    price_change = price_change_pct / 100

snap = max((s for s in snaps if s <= day), default=None)
if snap is None:
    st.warning("评估日之前没有承压快照。")
    st.stop()
with (ROOT / "data" / "snapshots" / snap / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
    fragility = {r["security_code"]: r for r in csv.DictReader(f)}
from src.extension import merged as _with_extension  # noqa: E402
fragility = _with_extension(fragility, day)          # 焦煤焦炭、下游龙头按各自组内评分（不进 24 家排名）
with (ROOT / "data" / "chain" / "live" / "edges.csv").open(encoding="utf-8-sig", newline="") as f:
    edges = [e for e in csv.DictReader(f) if is_active(e, day)]
if snap != day:
    st.caption(f"承压等级取评估日前最近的快照 {snap}；产品构成取评估日可得的最新年报。")

verified = verified_product_links(day)
if verified:
    chains = []
    for chain_id in dict.fromkeys(r["chain_id"] for r in verified):
        rows = sorted((r for r in verified if r["chain_id"] == chain_id), key=lambda r: int(r["sequence"]))
        chains.append({"已核实链条": rows[0]["chain_label"], "证据": " + ".join(f"{r['grade']}级" for r in rows),
                       "可证明": "；".join(r["scope_note"].split("；")[0] for r in rows)})
    with st.expander("已核实的企业级上下游链条", expanded=False):
        st.dataframe(pd.DataFrame(chains), hide_index=True, width="stretch")
        st.caption("企业级链条来自官方公司材料；B级表示已披露采购暴露、合作或产品应用，但未披露的金额、份额和损失不作推断。")
        for row in verified:
            page = f"第{row['source_page']}页" if row["source_page"] else "网页"
            st.markdown(f"- **{row['src_name']} → {row['dst_name']}**（{row['grade']}级，{page}）：{row['evidence_text']} "
                        f"[来源]({row['source_url']})  \n  边界：{row['scope_note']}")

result = build(kind, day, fragility, edges, product_id=product, company=company, sector_id=sector)
st.subheader(result["title"], divider="gray")
nodes, links = layout(result)
columns_n = int(max(n["x"] for n in nodes)) + 1
rows_n = max(sum(1 for n in nodes if n["x"] == x) for x in range(columns_n))
st.vega_lite_chart(overview_chart(nodes, links, width=min(1150, max(640, 230 * columns_n)), height=max(300, 70 * rows_n),
                                  rule_scale=SCENARIO_RULE_SCALE), width="content")
st.caption("三角 = 冲击；圆 = 企业（颜色为承压等级）；方块 = 产品；菱形 = 下游行业。线的颜色是关系类型，悬停可看证据等级。")

st.markdown("**暴露企业**（按承压由弱到强、暴露由大到小排序，仅用于提示关注顺序）")
st.dataframe(pd.DataFrame([{"企业": r["name"], "承压": TIER.get(r["tier"], "未评分"), "影响": r["effect"],
                            "证据等级": GRADE.get(r["grade"], r["grade"])} for r in result["companies"]]),
             hide_index=True, width="stretch")

if price_change is not None:
    quantified = scenario_stress(result["companies"], price_change)
    with st.expander("压力暴露指数", expanded=True):
        st.caption("|价格变化| × 产品暴露占比 × 财务缓冲系数 × 100；弱/中/强的系数为 1.0/0.5/0.2。"
                   "这是无单位情景排序，不是利润、现金流或损失预测。")
        st.dataframe(pd.DataFrame([{"企业": r["name"], "价格变化": f"{r['price_change']:+.1%}",
                                    "披露产品占比": f"{r['share']:.1%}" if r["quantifiable"] else "未披露",
                                    "缓冲系数": r["buffer_factor"],
                                    "压力指数": r["stress_index"] if r["quantifiable"] else None}
                                   for r in quantified]), hide_index=True, width="stretch")
        missing = sum(not r["quantifiable"] for r in quantified)
        if missing:
            st.caption(f"{missing} 家企业没有可核验的产品占比，因此不计算指数，不用行业均值补填。")

# ---------------------------------------------------------------- bridge: operating channel -> group credit channel
st.subheader("衔接检查：冲击能否转入集团信用通道", divider="gray")
st.caption("上下游（经营与供需）通道和集团信用与担保通道分开计算、分开验证。只有同时满足下列条件，才把受冲击企业作为起点，"
           "沿**担保或关联交易**（不含仅凭集团名义的“同集团”一步）继续推：① 产品暴露证据为 A/B 级；② 有披露的产品收入占比；"
           "③ 企业承压为弱或中。冲击强度阈值尚未预先登记，因此结果只作线索，不计入风险得分。")
BRIDGE_RULES = {"R1", "R2"}


@st.cache_data(show_spinner="正在检查衔接条件…")
def bridge(snap: str, codes: tuple[str, ...], shock: str):
    chain = ROOT / "data" / "chain" / "live"
    folder = ROOT / "data" / "snapshots" / snap
    _, _, names = key_paths(chain, folder)
    found = second_order(chain, folder, list(codes), shock)
    return {c: [{"路径": route(e, names), "得分(线索)": round(e["score"], 2), "金额(亿元)": round(e.get("amount_yi", 0), 2)}
                for e in found[c] if all(st_.rule in BRIDGE_RULES for st_ in e["steps"])] for c in codes}


listed_hit = [r for r in result["companies"] if r.get("code") in fragility]
eligible = [r for r in listed_hit if r["grade"] in ("A", "B") and (r.get("share") or 0) > 0 and r["tier"] in ("weak", "medium")]
onward = bridge(snap, tuple(r["code"] for r in eligible), "supply" if kind == "outage" else "credit") if eligible else {}
rows_b = []
for r in listed_hit:
    missing = [m for ok, m in ((r["grade"] in ("A", "B"), "证据仅 C 级"), ((r.get("share") or 0) > 0, "无披露占比"),
                               (r["tier"] in ("weak", "medium"), "承压为强或未评分")) if not ok]
    paths_r = onward.get(r["code"], [])
    rows_b.append({"受冲击企业": r["name"], "承压": TIER.get(r["tier"], "未评分"), "证据": GRADE.get(r["grade"], r["grade"]),
                   "披露占比": f"{r['share']:.1%}" if r.get("share") else "—",
                   "未满足的条件": "、".join(missing) or "—",
                   "可衔接路径": len(paths_r) if not missing else None})
if rows_b:
    st.dataframe(pd.DataFrame(rows_b), hide_index=True, width="stretch")
ready = [r for r in eligible if onward.get(r["code"])]
if not ready:
    st.info("本情景下没有满足全部条件、并能沿担保或关联交易继续传导的企业。这说明两条通道目前还缺一个经过检验的联合案例，"
            "而不是说冲击没有影响。", icon=":material/info:")
else:
    b1, b2 = st.columns([2, 1], vertical_alignment="bottom")
    pick = b1.selectbox("查看衔接路径", [r["code"] for r in ready], format_func=lambda c: next(r["name"] for r in ready if r["code"] == c))
    if b2.button("在传导图上看每一步的公告原文", icon=":material/account_tree:"):
        st.session_state["_goto_network"] = {"chain": "data/chain/live", "snapshot": snap, "company": pick}
        st.switch_page("pages/4_风险路径图.py")
    st.dataframe(pd.DataFrame(onward[pick]), hide_index=True, width="stretch")

with st.expander("每条关系的依据", expanded=False):
    names = {n["node"]: n["name"] for n in result["nodes"]}
    for e in result["edges"]:
        evidence = e["evidence"]
        stem = evidence.split(" 第")[0]
        evidence = evidence.replace(stem, titles().get(stem, stem), 1) if stem in titles() else evidence
        st.markdown(f"- **{names[e['src']]} → {names[e['dst']]}**（{RULES[e['rule']]}，{GRADE.get(e['grade'], e['grade'])}）"
                    f"：{e['effect']}  \n  依据：{evidence}")
