"""问一句：用一句话提问，智能体选择一个现有工具作答，并给出完整的调用轨迹。"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ask import EXAMPLES, INTENTS, ask, model_available  # noqa: E402
from src.network_view import NATURE_COLOR  # noqa: E402
from src.ui import open_profile, open_unified, page_header, public_mode, verdict  # noqa: E402

MAX_MODEL_CALLS = 20       # per session, public site

page_header("问一句", ":material/forum:", "用一句话问系统：它会选一个工具作答，并告诉你用了哪些数据、怎么得出的。",
            about="**它怎么工作**：先用规则识别问题里的企业、产品和数字，归入固定的几类问题；规则判断不了时，"
                  "才请大模型在同一张工具清单里选一类（只做分类，不写答案）。答案里的每个数字都来自与其他页面相同的计算，"
                  "并标明性质：已发生事件（事实）、风险敞口、模型预警或情景假设。超出范围的问题会直接说明不支持。  \n"
                  "**能回答的问题**：" + "；".join(f"{v[0]}（{v[1]}）" for v in INTENTS.values()) + "。")

if "ask_q" not in st.session_state:
    st.session_state["ask_q"] = ""
picked = st.pills("试试这些问题", EXAMPLES, key="ask_example")
if picked and picked != st.session_state.get("_ask_last_pick"):
    st.session_state["ask_q"] = picked
    st.session_state["_ask_last_pick"] = picked
question = st.text_input("你的问题", key="ask_q", placeholder="例如：凌钢股份出事会传给谁？")

if question.strip():
    calls = st.session_state.get("_ask_model_calls", 0)
    use_model = model_available() and (not public_mode() or calls < MAX_MODEL_CALLS)
    with st.spinner("正在选择工具并计算 …"):
        result = ask(question, use_model=use_model)
    if any(s["kind"] == "model" for s in result["trace"]):
        st.session_state["_ask_model_calls"] = calls + 1

    head = f"**问题类型：{result['label']}**"
    for nature in filter(None, (n.strip() for n in result["nature"].split("/"))):
        head += f"　:{NATURE_COLOR.get(nature, 'gray')}-badge[{nature}]"
    st.markdown(head + f"　·　数据截至 {result['snapshot']}")
    verdict(*result["verdict"])
    for caption, rows in result["tables"]:
        if rows:
            st.markdown(f"**{caption}**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if result["note"]:
        st.caption(result["note"])
    if result.get("goto"):
        page, label, code = result["goto"]
        if st.button(label, icon=":material/arrow_forward:", key="ask_goto"):
            if code and page.endswith("7_企业档案.py"):
                open_profile(code)
            elif code and page.endswith("8_风险传导总图.py"):
                open_unified(code)
            st.switch_page(page)
    with st.expander("智能体调用轨迹（每一步用了什么工具、得到什么）", icon=":material/route:"):
        trace = pd.DataFrame([{"步骤": s["step"], "工具": s["tool"], "类型": s["kind"], "结果": s["output"],
                               "理由": s["reason"], "耗时(ms)": s["ms"]} for s in result["trace"]])
        st.dataframe(trace, hide_index=True, use_container_width=True)
        route = result["route"]
        move = "无" if route["move"] is None else format(route["move"], "+.0%")
        companies = "、".join(route["companies"]) or "无"
        st.caption(f"路由方式：{route['by']}；识别到的企业：{companies}；产品：{route['product'] or '无'}；幅度：{move}")
