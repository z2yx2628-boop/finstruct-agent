"""分析新公告：一份公告 → 风险预警卡片（发生了什么 → 扛不扛得住 → 会传给谁）。"""
import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analyze import TaskNotDetected, analyze, build_card, card_markdown, demo_cases, replay  # noqa: E402
from src.ui import page_header, profile_button, verdict  # noqa: E402

TASKS = {"自动识别": None, "日常关联交易": "related_party", "对外担保": "guarantee", "产能/检修": "capacity",
         "股权质押（辅助信号）": "pledge"}
TIER_ICON = {"弱": "🔴", "中": "🟡", "强": "🟢"}
CHAIN_LABEL = {"data/chain/live": "实时图谱（每日更新）", "data/chain/analysis_v1": "真实图谱（84份公告，2024–2026）",
               "data/chain/analysis_v1_fix1": "真实图谱·单位修复后", "data/chain/backtest_antai": "回测图谱（安泰）",
               "data/chain/backtest_antai_fix1": "回测图谱·单位修复后（安泰）", "data/chain/backtest_linggang": "回测图谱（凌钢）",
               "data/chain/backtest_linggang_fix1": "回测图谱·单位修复后（凌钢）"}

page_header("分析新公告", ":material/bolt:", "这份新公告意味着什么：发生了什么、企业扛不扛得住、风险会传给谁？", grades=True,
            about="**演示案例**：6 份真实公告，使用冻结系统当时保存的抽取结果，不联网、不调用模型也能用；评估日和图谱按案例自动设定。  \n"
                  "**上传新公告**：调用冻结版抽取系统（需要模型接口）；打开“离线模式”时只能分析演示包里的文件。  \n"
                  "结果卡片先给一句结论，再分三部分：公告事实、自身风险（承压评分）、关联风险（传导路径），每条都带原文页码。")

chains = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "chain").glob("*")
                if (p / "edges.csv").exists() and p.name != "gold_demo")
default_chain = next((c for c in ("data/chain/live", "data/chain/analysis_v1") if c in chains), chains[0])

tab_demo, tab_new, tab_saved = st.tabs([":material/play_circle: 演示案例（离线可用）", ":material/upload_file: 上传新公告",
                                        ":material/history: 全部已提取结果"])
card = None
with tab_demo:
    cases = demo_cases()
    if not cases:
        st.info("没有演示包。运行 python scripts/build_demo_pack.py 生成。")
    else:
        by_id = {c["id"]: c for c in cases}
        d1, d2 = st.columns([3, 1], vertical_alignment="bottom")
        picked = d1.selectbox("演示案例", list(by_id), format_func=lambda i: by_id[i]["label"])
        run_demo = d2.button("生成风险预警", type="primary", icon=":material/play_arrow:", key="build_pack_card", width="stretch")
        c = by_id[picked]
        st.caption(f"{c['why']} · 评估日 {c['as_of']} · {CHAIN_LABEL.get(c['chain'], c['chain'])}")
        if run_demo:
            card = replay(c)

with tab_new:
    upload = st.file_uploader("公告文件", type=["pdf", "png", "jpg", "jpeg", "html", "htm", "docx", "doc", "xlsx", "xls", "csv"],
                              help="支持文字PDF、扫描PDF、图片、网页、Word和Excel。")
    with st.expander("分析设置（公告类型、评估日、图谱、离线模式）", icon=":material/tune:"):
        s1, s2, s3 = st.columns(3)
        task_label = s1.selectbox("公告类型", list(TASKS))
        as_of = s2.date_input("评估日", value=date.today())
        chain = s3.selectbox("产业链图谱", chains, index=chains.index(default_chain), format_func=lambda c: CHAIN_LABEL.get(c, c))
        offline = st.toggle("离线模式",
                            help="不调用模型、不联网：只能分析演示包（data/demo/）里的公告，结果来自冻结系统此前对同一文件的抽取。"
                                 "关闭时正常调用模型；如果模型调用失败而文件在演示包里，也会自动改用离线回放。")
    if st.button("生成风险预警", type="primary", icon=":material/bolt:", disabled=upload is None, key="run_upload"):
        target = ROOT / "data" / "raw" / "uploads" / upload.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(upload.getvalue())
        with st.status("正在分析公告", expanded=True) as status:
            try:
                st.write("正在提取结构化事件与证据…")
                card = analyze(target, TASKS[task_label], as_of.isoformat(), chain, offline=offline)
                st.session_state["last_card"] = card
                status.update(label="风险预警已生成", state="complete", expanded=False)
            except TaskNotDetected as error:
                status.update(label="需要选择公告类型", state="error", expanded=True)
                st.warning(str(error) + "（在“分析设置”里选择公告类型。）")
            except Exception as error:
                status.update(label="分析失败", state="error", expanded=True)
                st.error(f"分析失败：{type(error).__name__}: {error}")

with tab_saved:
    st.caption("开发与复核用：直接读取 outputs/ 里已保存的抽取结果，使用“上传新公告 → 分析设置”里的评估日和图谱。")
    outputs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "outputs").glob("*_freeze/*/*.json"))
    chosen = st.selectbox("选择一份已提取的公告", outputs) if outputs else None
    if not outputs:
        st.caption("本机没有 outputs/ 目录（新克隆的仓库不含这些文件）；请用“演示案例”。")
    if chosen and st.button("生成风险预警", icon=":material/bolt:", key="build_demo_card"):
        doc = json.loads((ROOT / chosen).read_text(encoding="utf-8"))
        card = build_card(doc, chosen, as_of.isoformat(), ROOT / chain)

if card:
    st.divider()
    absorb = card["can_they_absorb"]
    own = next((c for c in absorb if c.get("code") == card.get("code")), absorb[0] if absorb else None)
    paths = card["who_is_next"]
    level = "error" if paths and own and own["tier"] == "弱" else "warning" if paths else "success"
    summary = (f"**{card['company']}**（评估日 {card['as_of']}）：识别 {card['counts']['signals']} 个风险信号、"
               f"{card['counts']['edges']} 条关系；自身承压 **{own['tier'] if own else '未评分'}**；"
               + (f"**{len(paths)} 条传导路径需要关注**，首条：{paths[0]['path']}。" if paths else
                  "没有需要关注的传导路径（风险被强企业吸收、金额不重大，或只有低严重度信号）。"))
    h1, h2 = st.columns([5, 1.2], vertical_alignment="center")
    with h1:
        verdict(level, summary)
    if card.get("code"):
        with h2:
            profile_button(card["code"], "企业档案", key="card_profile", snapshot=card.get("snapshot"), width="stretch")
    if card.get("offline_note"):
        st.caption(":material/cloud_off: " + card["offline_note"])
    if card.get("extraction_status") == "needs_review":
        st.warning("结构化证据检查发现需人工复核的字段，以下结果不能直接作为最终判断。", icon=":material/rule:")
    st.caption(f"来源 {card['source']} · 公告日 {card['announcement_date']} · 承压快照 {card['snapshot']}")

    t1, t2, t3 = st.tabs([f":material/fact_check: 发生了什么（{len(card['what_happened']) + len(card['relations'])}）",
                          ":material/monitoring: 扛不扛得住（自身风险）",
                          f":material/account_tree: 会传给谁（{len(paths)} 条路径）"])
    with t1:
        if not card["what_happened"] and not card["relations"]:
            st.info("未识别出风险信号或关系。")
        for w in card["what_happened"]:
            st.markdown(f"- **[{w['severity']}] {w['entity']} · {w['type']}**：{w['detail']}（{w['rows']}行）  \n"
                        f"  判定规则：{w['rule']}  \n  依据：{w['evidence']}")
        for r in card["relations"][:10]:
            st.markdown(f"- 关系：**{r['from']} →[{r['type']}] {r['to']}**，合计 {r['amount_yi']} 亿元（{r['relationship']}）  \n"
                        f"  依据：{r['evidence']}")
        if len(card["relations"]) > 10:
            st.caption(f"另有 {len(card['relations']) - 10} 条关系未列出，见下载的预警卡片。")
    with t2:
        if not absorb:
            st.markdown(f"- ⚪ **{card['company']}**：不在承压评分范围内（24家核心钢厂及手动加入的企业）。")
        for c in absorb:
            st.markdown(f"- {TIER_ICON.get(c['tier'], '⚪')} **{c['entity']}：{c['tier']}**（{c['score']}分）  \n  {c['reasons'] or ''}")
    with t3:
        if not paths:
            st.success("未发现需要关注的传导路径：风险被强企业吸收、金额不重大，或本公告只含低严重度信号。")
        for p in paths:
            alt = f"；另有 {p['alternatives']} 条同类路线（经由 {'、'.join(p['alternative_routes'])}）" if p["alternatives"] else ""
            with st.expander(f"{p['rank']}. {p['path']} · 得分 {p['score']}{alt}", expanded=p["rank"] == 1):
                st.markdown(f"起点：{p['reason']}")
                for s in p["steps"]:
                    st.markdown(f"- **{s['rule_label']}**：{s['src_name']} → {s['dst_name']}（{s['tier_label']}），"
                                f"{s['decision_label']}  \n  依据：{s['evidence']}")
    st.download_button("下载预警卡片（Markdown）", card_markdown(card), file_name=f"alert_{card['as_of']}.md",
                       icon=":material/download:")

last = st.session_state.get("last_card")
if last and last.get("task") and (ROOT / last["source"]).exists() and last.get("extraction_status") != "offline_replay":
    with st.expander("把这份公告加入实时图谱", icon=":material/add_link:"):
        st.caption("这份公告目前只用于本次分析。加入后，它的关系和信号会进入实时图谱，参与今后的每日更新与路径推导。")
        if st.button("加入实时图谱"):
            import shutil
            src = ROOT / last["source"]
            dest = ROOT / "outputs" / "manual_freeze" / last["task"] / f"{src.parent.parent.name}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            st.success(f"已加入：{dest.relative_to(ROOT).as_posix()}。下次在今日看板“数据更新”里点“立即更新”（可不联网）后生效。")
