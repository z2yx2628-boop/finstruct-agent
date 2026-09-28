import streamlit as st


st.set_page_config(
    page_title="链证 · 钢铁产业链风险传导预警",
    page_icon=":material/account_tree:",
    layout="wide",
)

page = st.navigation(
    {
        "总览": [
            st.Page("pages/0_今日看板.py", title="今日看板", icon=":material/dashboard:", default=True),
            st.Page("pages/7_企业档案.py", title="企业档案", icon=":material/badge:"),
            st.Page("pages/3_一键分析.py", title="分析新公告", icon=":material/bolt:"),
        ],
        "分项分析": [
            st.Page("pages/1_公告结构化.py", title="公告事实抽取", icon=":material/description:"),
            st.Page("pages/2_承压评分.py", title="企业承压", icon=":material/monitoring:"),
            st.Page("pages/4_风险路径图.py", title="披露关系传导", icon=":material/account_tree:"),
            st.Page("pages/5_上下游情景.py", title="上下游情景", icon=":material/swap_horiz:"),
        ],
        "可信度": [
            st.Page("pages/6_验证与证据.py", title="验证与证据", icon=":material/verified:"),
        ],
    },
    position="top",
)

page.run()
