"""上下游情景：一个产品或行业冲击，经产品层传到哪些企业（情景路径，不计入正式风险得分）。"""
import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.network_view import SCENARIO_RULE_SCALE, overview_chart  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.scenario import CAVEAT, KINDS, RULES, build, company_name, core_mills, layout, product_map, sector_links  # noqa: E402
from src.sources import titles  # noqa: E402
from src.validity import is_active  # noqa: E402

TIER = {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强", "": "未评分"}
GRADE = {"A": "A 披露确认", "B": "B 部分确认", "C": "C 行业推断", "—": "—"}

st.title("上下游情景", icon=":material/swap_horiz:")
st.info(CAVEAT, icon=":material/info:")
st.caption("冲击 → 暴露于该产品的企业（公司自己披露的分产品收入 B 级；公告披露的采购/销售 A 级）→ 企业承压 → "
           "钢材产品 → 下游行业（C 级）→ 下游代表企业（年报点名钢材为主要原材料 B 级，否则 C 级）。")

snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists())
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
    col.button(label, on_click=use_demo, args=args, use_container_width=True)

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

snap = max((s for s in snaps if s <= day), default=None)
if snap is None:
    st.warning("评估日之前没有承压快照。")
    st.stop()
with (ROOT / "data" / "snapshots" / snap / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
    fragility = {r["security_code"]: r for r in csv.DictReader(f)}
with (ROOT / "data" / "chain" / "live" / "edges.csv").open(encoding="utf-8-sig", newline="") as f:
    edges = [e for e in csv.DictReader(f) if is_active(e, day)]
if snap != day:
    st.caption(f"承压等级取评估日前最近的快照 {snap}；产品构成取评估日可得的最新年报。")

result = build(kind, day, fragility, edges, product_id=product, company=company, sector_id=sector)
st.subheader(result["title"], divider="gray")
nodes, links = layout(result)
columns_n = int(max(n["x"] for n in nodes)) + 1
rows_n = max(sum(1 for n in nodes if n["x"] == x) for x in range(columns_n))
st.vega_lite_chart(overview_chart(nodes, links, width=min(1150, max(640, 230 * columns_n)), height=max(300, 70 * rows_n),
                                  rule_scale=SCENARIO_RULE_SCALE), use_container_width=False)
st.caption("三角 = 冲击；圆 = 企业（颜色为承压等级）；方块 = 产品；菱形 = 下游行业。线的颜色是关系类型，悬停可看证据等级。")

st.markdown("**暴露企业**（按承压由弱到强、暴露由大到小排序，仅用于提示关注顺序）")
st.dataframe(pd.DataFrame([{"企业": r["name"], "承压": TIER.get(r["tier"], "未评分"), "影响": r["effect"],
                            "证据等级": GRADE.get(r["grade"], r["grade"])} for r in result["companies"]]),
             hide_index=True, use_container_width=True)

with st.expander("每条关系的依据", expanded=False):
    names = {n["node"]: n["name"] for n in result["nodes"]}
    for e in result["edges"]:
        evidence = e["evidence"]
        stem = evidence.split(" 第")[0]
        evidence = evidence.replace(stem, titles().get(stem, stem), 1) if stem in titles() else evidence
        st.markdown(f"- **{names[e['src']]} → {names[e['dst']]}**（{RULES[e['rule']]}，{GRADE.get(e['grade'], e['grade'])}）"
                    f"：{e['effect']}  \n  依据：{evidence}")
