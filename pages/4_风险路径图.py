"""风险路径图：全产业链的关键传导路径，节点按承压等级着色，边附公告证据。"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.network_view import RULE_LABEL, key_paths, name_of, to_dot  # noqa: E402
from src.sources import readable  # noqa: E402

TIER = {"weak": "弱", "medium": "中", "strong": "强", "unknown": "未评分"}
DECISION = {"continue": "继续传导", "weakened": "继续传导（减弱）", "absorbed": "被吸收，停止",
            "immaterial": "金额不重大，停止", "end": "已减弱至最低，停止"}
CHAIN_LABEL = {"data/chain/live": "实时图谱（每日更新）", "data/chain/analysis_v1": "真实图谱（84份公告，2024–2026）",
               "data/chain/backtest_antai": "回测图谱（安泰）", "data/chain/gold_demo": "演示图谱（仅开发用）"}

import subprocess  # noqa: E402

with st.sidebar:
    st.markdown("**每日更新**")
    st.caption("查40家企业的新公告 → 冻结版系统提取 → 更新图谱（过期关系自动失效）→ 更新承压评分 → 对比风险路径。")
    online = st.checkbox("联网查新公告（需本机网络与模型接口）", value=True)
    if st.button("立即更新", type="primary"):
        cmd = [sys.executable, str(ROOT / "scripts" / "daily_update.py")] + ([] if online else ["--no-network"])
        with st.spinner("正在更新，联网时约5–15分钟…"):
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        st.cache_data.clear()
        st.code((out.stdout or "")[-1500:] + (out.stderr or "")[-800:])
    reports = sorted((ROOT / "data" / "live").glob("report_*.md"), reverse=True)
    if reports:
        with st.expander(f"最新日报 {reports[0].stem[7:]}"):
            st.markdown(reports[0].read_text(encoding="utf-8"))
st.title("风险路径图", icon=":material/account_tree:")
st.caption("节点颜色 = 承压等级（🔴弱 🟡中 🟢强 ⚪未评分），粗边框 = 风险起点；边的颜色 = 传导规则"
           "（红=担保，蓝=供需，紫=同集团，灰虚线=行业近似），边上数字为交易或担保金额。")

chains = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "chain").glob("*") if (p / "edges.csv").exists())
snaps = sorted((p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists()), reverse=True)
c1, c2, c3 = st.columns([2, 1, 1])
default = next((c for c in ("data/chain/live", "data/chain/analysis_v1") if c in chains), chains[0])
chain = c1.selectbox("产业链图谱", chains, index=chains.index(default),
                     format_func=lambda c: CHAIN_LABEL.get(c, c))
snap = c2.selectbox("评估日（承压快照）", snaps)
top = c3.slider("显示前 N 条关键路径", 3, 30, 10)
if "backtest" in chain and snap > "2025-02-05":
    st.warning("回测图谱应配合事件发生前的评估日（安泰为 2025-01-31），否则会用到当时还不存在的信息。")
if "analysis" in chain and snap < "2025-06-01":
    st.info("真实图谱的公告多发布于 2025–2026 年；评估日较早时，大部分关系会按日期被过滤掉。")


@st.cache_data(show_spinner="正在推导传导路径…")
def load(chain: str, snap: str):
    ranked, fragility, names = key_paths(ROOT / chain, ROOT / "data" / "snapshots" / snap)
    return ranked, fragility, names


ranked, fragility, names = load(chain, snap)
if not ranked:
    st.info("该评估日下没有需要关注的传导路径。")
    st.stop()
shown = ranked[:top]
options = ["全部"] + [f"{i + 1}. " + " → ".join([name_of(e["seed"], names)] + [name_of(s.dst, names) for s in e["steps"]])
                      for i, e in enumerate(shown)]
choice = st.selectbox("高亮一条路径（其余淡化）", options)
highlight = None if choice == "全部" else options.index(choice) - 1
st.graphviz_chart(to_dot(shown, fragility, names, highlight), use_container_width=True)

st.subheader("路径明细与证据")
for i, e in enumerate(shown):
    if highlight is not None and i != highlight:
        continue
    title = " → ".join([name_of(e["seed"], names)] + [f"[{RULE_LABEL[s.rule]}] {name_of(s.dst, names)}({TIER.get(s.dst_tier, s.dst_tier)})"
                                                      for s in e["steps"]])
    with st.expander(f"{i + 1}. {title} · 得分 {e['score']}", expanded=highlight is not None):
        st.markdown(f"**起点：** {e['reason']}")
        if e.get("alternatives"):
            st.markdown(f"另有 {e['alternatives']} 条经不同集团子公司的同类路线。")
        for s in e["steps"]:
            amount = f"，金额 {s.amount_wan / 1e4:.2f} 亿元" if s.amount_wan else ""
            st.markdown(f"- **{RULE_LABEL[s.rule]}**：{name_of(s.src, names)} → {name_of(s.dst, names)}"
                        f"（{TIER.get(s.dst_tier, s.dst_tier)}）{amount}，{DECISION.get(s.decision, s.decision)}  \n"
                        f"  依据：{readable(s.evidence)}")
        if e["beyond"]:
            st.caption(f"其后还波及 {len(e['beyond'])} 家集团内非上市公司，合计约 {e['beyond_amount_wan'] / 1e4:.2f} 亿元。")
