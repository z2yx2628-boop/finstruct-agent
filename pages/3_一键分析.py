"""一键分析：上传一份新公告 → 风险预警卡片（方向一 → 二 → 三）。"""
import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analyze import analyze, build_card, card_markdown  # noqa: E402

TASKS = {"自动识别": None, "日常关联交易": "related_party", "对外担保": "guarantee", "产能/检修": "capacity", "股权质押": "pledge"}
TIER_ICON = {"弱": "🔴", "中": "🟡", "强": "🟢"}

st.set_page_config(page_title="一键分析 · FinStruct Agent", layout="wide")
st.title("一键分析：这条公告意味着什么风险？")
st.caption("上传公告 → ① 冻结版系统提取事件与关系（带原文证据）→ ② 查询相关企业承压等级 → ③ 沿担保、供需、同集团、行业关系推导风险会传给谁。")

chains = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "chain").glob("*") if (p / "edges.csv").exists())
c1, c2, c3 = st.columns(3)
task_label = c1.selectbox("公告类型", list(TASKS))
as_of = c2.date_input("评估日", value=date.today())
chain = c3.selectbox("产业链图谱", chains, index=chains.index("data/chain/analysis_v1") if "data/chain/analysis_v1" in chains else 0)

tab_new, tab_demo = st.tabs(["上传新公告（调用模型，约30–90秒）", "用已提取结果演示（不调用模型）"])
card = None
with tab_new:
    upload = st.file_uploader("公告文件", type=["pdf", "png", "jpg", "jpeg", "html", "htm", "docx", "doc", "xlsx", "xls", "csv"])
    if upload and st.button("开始分析", type="primary"):
        target = ROOT / "data" / "raw" / "uploads" / upload.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(upload.getvalue())
        with st.spinner("正在提取、评分、推导传导路径…"):
            try:
                card = analyze(target, TASKS[task_label], as_of.isoformat(), chain)
            except Exception as error:
                st.error(f"分析失败：{type(error).__name__}: {error}")
with tab_demo:
    outputs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "outputs").glob("*_freeze/*/*.json"))
    chosen = st.selectbox("选择一份已提取的公告", outputs) if outputs else None
    if chosen and st.button("生成预警卡片"):
        doc = json.loads((ROOT / chosen).read_text(encoding="utf-8"))
        card = build_card(doc, chosen, as_of.isoformat(), ROOT / chain)

if card:
    st.divider()
    st.subheader(f"风险预警 · {card['company']} · 评估日 {card['as_of']}")
    st.caption(f"来源 {card['source']} · 公告日 {card['announcement_date']} · 承压快照 {card['snapshot']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("识别的风险信号", card["counts"]["signals"])
    m2.metric("识别的关系", card["counts"]["edges"])
    m3.metric("关键传导路径", len(card["who_is_next"]))

    st.markdown("#### ① 发生了什么")
    if not card["what_happened"] and not card["relations"]:
        st.info("未识别出风险信号或关系。")
    for w in card["what_happened"]:
        st.markdown(f"- **[{w['severity']}] {w['entity']} · {w['type']}**：{w['detail']}（{w['rows']}行）  \n  判定规则：{w['rule']}  \n  依据：{w['evidence']}")
    for r in card["relations"][:10]:
        st.markdown(f"- 关系：**{r['from']} →[{r['type']}] {r['to']}**，合计 {r['amount_yi']} 亿元（{r['relationship']}）  \n  依据：{r['evidence']}")

    st.markdown("#### ② 扛不扛得住")
    for c in card["can_they_absorb"] or [{"entity": card["company"], "tier": "未评分", "score": "", "reasons": ""}]:
        st.markdown(f"- {TIER_ICON.get(c['tier'], '⚪')} **{c['entity']}：{c['tier']}**（{c['score']}分）  \n  {c['reasons'] or ''}")

    st.markdown("#### ③ 会传给谁")
    if not card["who_is_next"]:
        st.success("未发现需要关注的传导路径：风险被强企业吸收、金额不重大，或本公告只含低严重度信号。")
    for p in card["who_is_next"]:
        alt = f"；另有 {p['alternatives']} 条同类路线（经由 {'、'.join(p['alternative_routes'])}）" if p["alternatives"] else ""
        with st.expander(f"{p['rank']}. {p['path']} · 得分 {p['score']}{alt}", expanded=p["rank"] <= 3):
            st.markdown(f"起点：{p['reason']}")
            for s in p["steps"]:
                st.markdown(f"- **{s['rule_label']}**：{s['src_name']} → {s['dst_name']}（{s['tier_label']}），{s['decision']}  \n  依据：{s['evidence']}")
    st.download_button("下载预警卡片（Markdown）", card_markdown(card), file_name=f"alert_{card['as_of']}.md")
