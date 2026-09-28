"""一键分析：上传一份新公告 → 风险预警卡片（方向一 → 二 → 三）。"""
import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analyze import TaskNotDetected, analyze, build_card, card_markdown, demo_cases, replay  # noqa: E402

TASKS = {"自动识别": None, "日常关联交易": "related_party", "对外担保": "guarantee", "产能/检修": "capacity", "股权质押": "pledge"}
TIER_ICON = {"弱": "🔴", "中": "🟡", "强": "🟢"}

from src.ui import page_header  # noqa: E402
page_header("分析新公告", ":material/bolt:", "这份新公告意味着什么：发生了什么、企业扛不扛得住、风险会传给谁？", grades=True)

st.header("分析新公告", icon=":material/upload_file:")

chains = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "chain").glob("*") if (p / "edges.csv").exists())
c1, c2, c3 = st.columns(3)
task_label = c1.selectbox("公告类型", list(TASKS))
as_of = c2.date_input("评估日", value=date.today())
CHAIN_LABEL = {"data/chain/live": "实时图谱（每日更新）", "data/chain/analysis_v1": "真实图谱（84份公告，2024–2026）", "data/chain/backtest_antai": "回测图谱（安泰，评估日选 2025-01-31）",
               "data/chain/backtest_antai_fix1": "回测图谱·单位修复后（安泰）", "data/chain/backtest_linggang": "回测图谱（凌钢）",
               "data/chain/backtest_linggang_fix1": "回测图谱·单位修复后（凌钢）", "data/chain/analysis_v1_fix1": "真实图谱·单位修复后",
               "data/chain/gold_demo": "演示图谱（测试答案，仅开发用）"}
default = next((c for c in ("data/chain/live", "data/chain/analysis_v1") if c in chains), chains[0])
chain = c3.selectbox("产业链图谱", chains, index=chains.index(default),
                     format_func=lambda c: CHAIN_LABEL.get(c, c))

offline = st.toggle(
    "离线演示模式",
    help="开启后不调用模型、不联网：只能分析演示包（data/demo/）里的公告，结果来自冻结系统此前对同一文件的抽取。"
         "关闭时正常调用模型；如果模型调用失败而文件在演示包里，也会自动改用离线回放。",
)
tab_new, tab_demo = st.tabs(
    [
        ":material/upload_file: 上传新公告",
        ":material/history: 使用已提取结果",
    ]
)
card = None
with tab_new:
    upload = st.file_uploader(
        "公告文件",
        type=[
            "pdf", "png", "jpg", "jpeg", "html", "htm",
            "docx", "doc", "xlsx", "xls", "csv",
        ],
        help="支持文字PDF、扫描PDF、图片、网页、Word和Excel。",
    )
    if st.button(
        "生成风险预警",
        type="primary",
        icon=":material/bolt:",
        disabled=upload is None,
    ):
        target = ROOT / "data" / "raw" / "uploads" / upload.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(upload.getvalue())
        with st.status("正在分析公告", expanded=True) as status:
            try:
                st.write("正在提取结构化事件与证据…")
                card = analyze(target, TASKS[task_label], as_of.isoformat(), chain, offline=offline)
                st.session_state["last_card"] = card
                status.update(
                    label="风险预警已生成",
                    state="complete",
                    expanded=False,
                )
            except TaskNotDetected as error:
                status.update(label="需要选择公告类型", state="error", expanded=True)
                st.warning(str(error))
            except Exception as error:
                status.update(
                    label="分析失败",
                    state="error",
                    expanded=True,
                )
                st.error(f"分析失败：{type(error).__name__}: {error}")
with tab_demo:
    cases = demo_cases()
    if cases:
        st.markdown("**演示包**（不联网也能用；评估日和图谱按案例自动设定，忽略上方选择）")
        by_id = {c["id"]: c for c in cases}
        picked = st.selectbox("演示案例", list(by_id), format_func=lambda i: by_id[i]["label"])
        st.caption(f"{by_id[picked]['why']} · 评估日 {by_id[picked]['as_of']} · 图谱 {CHAIN_LABEL.get(by_id[picked]['chain'], by_id[picked]['chain'])}")
        if st.button("生成风险预警", type="primary", icon=":material/play_arrow:", key="build_pack_card"):
            card = replay(by_id[picked])
        st.divider()
    st.markdown("**全部已提取结果**（使用上方的评估日和图谱）")
    outputs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "outputs").glob("*_freeze/*/*.json"))
    chosen = st.selectbox("选择一份已提取的公告", outputs) if outputs else None
    if chosen and st.button(
        "生成风险预警",
        icon=":material/bolt:",
        key="build_demo_card",
    ):
        doc = json.loads((ROOT / chosen).read_text(encoding="utf-8"))
        card = build_card(doc, chosen, as_of.isoformat(), ROOT / chain)

if card:
    st.header("风险预警", icon=":material/warning:")
    st.subheader(f"{card['company']} · 评估日 {card['as_of']}")
    st.caption(f"来源 {card['source']} · 公告日 {card['announcement_date']} · 承压快照 {card['snapshot']}")
    if card.get("offline_note"):
        st.info(card["offline_note"], icon=":material/cloud_off:")
    if card.get("extraction_status") == "needs_review":
        st.warning(
            "结构化证据检查发现需人工复核的字段，以下结果不能直接作为最终判断。",
            icon=":material/rule:",
        )
    m1, m2, m3 = st.columns(3)
    m1.metric("识别的风险信号", card["counts"]["signals"])
    m2.metric("识别的关系", card["counts"]["edges"])
    m3.metric("关键传导路径", len(card["who_is_next"]))

    st.subheader("1. 发生了什么", icon=":material/fact_check:")
    if not card["what_happened"] and not card["relations"]:
        st.info("未识别出风险信号或关系。")
    for w in card["what_happened"]:
        st.markdown(f"- **[{w['severity']}] {w['entity']} · {w['type']}**：{w['detail']}（{w['rows']}行）  \n  判定规则：{w['rule']}  \n  依据：{w['evidence']}")
    for r in card["relations"][:10]:
        st.markdown(f"- 关系：**{r['from']} →[{r['type']}] {r['to']}**，合计 {r['amount_yi']} 亿元（{r['relationship']}）  \n  依据：{r['evidence']}")

    st.subheader("2. 扛不扛得住", icon=":material/monitoring:")
    if not card["can_they_absorb"]:
        st.markdown(f"- ⚪ **{card['company']}**：不在承压评分范围内（24家核心钢厂及手动加入的企业）。")
    for c in card["can_they_absorb"]:
        st.markdown(f"- {TIER_ICON.get(c['tier'], '⚪')} **{c['entity']}：{c['tier']}**（{c['score']}分）  \n  {c['reasons'] or ''}")

    st.subheader("3. 会传给谁", icon=":material/account_tree:")
    if not card["who_is_next"]:
        st.success("未发现需要关注的传导路径：风险被强企业吸收、金额不重大，或本公告只含低严重度信号。")
    for p in card["who_is_next"]:
        alt = f"；另有 {p['alternatives']} 条同类路线（经由 {'、'.join(p['alternative_routes'])}）" if p["alternatives"] else ""
        with st.expander(f"{p['rank']}. {p['path']} · 得分 {p['score']}{alt}", expanded=p["rank"] <= 3):
            st.markdown(f"起点：{p['reason']}")
            for s in p["steps"]:
                st.markdown(f"- **{s['rule_label']}**：{s['src_name']} → {s['dst_name']}（{s['tier_label']}），{s['decision_label']}  \n  依据：{s['evidence']}")
    st.download_button(
        "下载预警卡片",
        card_markdown(card),
        file_name=f"alert_{card['as_of']}.md",
        icon=":material/download:",
    )

last = st.session_state.get("last_card")
if last and last.get("task") and (ROOT / last["source"]).exists():
    st.caption("这份公告目前只用于本次分析。加入图谱后，它的关系和信号会进入实时图谱，参与今后的每日更新与路径推导。")
    if st.button("加入实时图谱", icon=":material/add_link:"):
        import shutil
        src = ROOT / last["source"]
        dest = ROOT / "outputs" / "manual_freeze" / last["task"] / f"{src.parent.parent.name}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        st.success(f"已加入：{dest.relative_to(ROOT).as_posix()}。下次点“风险路径图 → 立即更新”（可不联网）后生效。")
