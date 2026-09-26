import streamlit as st


st.set_page_config(
    page_title="FinStruct Agent",
    page_icon=":material/account_tree:",
    layout="wide",
)

page = st.navigation(
    [
        st.Page(
            "pages/3_一键分析.py",
            title="一键风险分析",
            icon=":material/bolt:",
            default=True,
        ),
        st.Page(
            "pages/1_公告结构化.py",
            title="公告结构化",
            icon=":material/description:",
        ),
        st.Page(
            "pages/2_承压评分.py",
            title="企业承压评分",
            icon=":material/monitoring:",
        ),
        st.Page(
            "pages/4_风险路径图.py",
            title="风险路径图",
            icon=":material/account_tree:",
        ),
    ],
    position="top",
)

page.run()
