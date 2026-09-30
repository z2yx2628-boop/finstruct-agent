import streamlit as st


st.set_page_config(
    page_title="钢铁上市公司上下游冲击传导与经营风险智能体 · 链证 ChainProof",
    page_icon=":material/account_tree:",
    layout="wide",
)

# Five pages in the order a first-time reader follows the story (flat links in the top bar), and the
# detailed tools behind them in one dropdown. Streamlit shows pages under the "" section as plain links.
page = st.navigation(
    {
        "": [
            st.Page("pages/0_今日看板.py", title="今日预警", icon=":material/dashboard:", default=True),
            st.Page("pages/7_企业档案.py", title="企业档案", icon=":material/badge:"),
            st.Page("pages/8_风险传导总图.py", title="风险传导", icon=":material/hub:"),
            st.Page("pages/3_一键分析.py", title="分析新公告", icon=":material/bolt:"),
            st.Page("pages/6_验证与证据.py", title="可信度", icon=":material/verified:"),
        ],
        "明细工具": [
            st.Page("pages/2_承压评分.py", title="承压评分全表", icon=":material/monitoring:"),
            st.Page("pages/4_风险路径图.py", title="信用通道明细", icon=":material/account_tree:"),
            st.Page("pages/5_上下游情景.py", title="供需情景与政策冲击", icon=":material/swap_horiz:"),
            st.Page("pages/1_公告结构化.py", title="公告事实抽取", icon=":material/description:"),
        ],
    },
    position="top",
)

page.run()
