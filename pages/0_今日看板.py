"""今日看板：今天有什么风险、该先看哪家企业、这个系统有多可信（首页）。"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fragility_view import snapshot_meta  # noqa: E402
from src.network_view import NATURE_COLOR, risk_sources, seed_nature  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.ui import (UNIFIED_PAGE, glossary, next_step, online_model, open_unified, page_header,  # noqa: E402
                    profile_button, public_mode, verdict)

page_header("链证 · 钢铁产业链风险传导预警", ":material/dashboard:", "今天谁可能先出问题？会传给谁？",
            step=1, fresh=True)
glossary(intro="链证分两段预警：**① 风险源预警**——谁可能先出问题（公告中的风险事件 + 抗冲击能力评分）；"
               "**② 风险传导预警**——它的问题会沿担保、关联交易和集团关系传给谁、涉及多少钱。"
               "页面上的每个结论都能点回公告原文和页码。  \n"
               "**建议阅读顺序**（顶部导航从左到右）：① 今日预警 → ② 企业档案 → ③ 风险传导 → ④ 分析新公告 → ⑤ 可信度。"
               "“明细工具”里是每一层的完整表格与参数，供深入核查。  \n"
               "**监测边界**：风险源限于 42 家 A 股上市公司及其公告中点名的非上市、境外企业；非上市企业自身发生的事件不在监测范围。"
               "马钢股份、重庆钢铁、武进不锈、广大特材、常宝股份 5 家目前没有仍有效的披露关系"
               "（未找到它们单独发布的 2026 年度关联交易预计或担保公告），经过它们的传导可能被低估。")


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


snaps = sorted(p for p in (ROOT / "data" / "snapshots").glob("2026-*") if (p / "fragility.csv").exists())
live = [p for p in snaps if snapshot_meta(p).get("version") == "v1"]
now = read(live[-1] / "fragility.csv") if live else []
before = {r["security_code"]: r for r in read(live[-2] / "fragility.csv")} if len(live) > 1 else {}
weak = sorted((r for r in now if r["tier"] == "weak"), key=lambda r: -float(r["total_score"] or 0))
new_weak = [r for r in weak if before and before.get(r["security_code"], {}).get("tier") != "weak"]
paths = sorted(ROOT.joinpath("data", "chain", "live").glob("key_paths_*.csv"))
key_now = [r for r in (read(paths[-1]) if paths else []) if float(r["score"]) > 0]
key_before = {r["path"] for r in read(paths[-2])} if len(paths) > 1 else set()
new_paths = [r for r in key_now if key_before and r["path"] not in key_before]
moves = price_moves(live[-1].name if live else "9999-12-31")


@st.cache_data(show_spinner="正在识别风险源…")
def sources(snapshot: str) -> list[dict]:
    return risk_sources(ROOT / "data" / "chain" / "live", ROOT / "data" / "snapshots" / snapshot)


src_all = sources(live[-1].name) if live else []
facts = [r for r in src_all if r["nature"] == "已发生事件"]
exposures = [r for r in src_all if r["nature"] == "风险敞口"]
shocks = [m for m in moves if m["shock"]]

RULE_WORD = {"R1": "担保", "R2": "关联交易", "R3": "同集团", "R4": "集团名义"}


def short_reasons(text: str, n: int = 2) -> str:
    """The first n reasons, cut at the separator rather than in the middle of a number."""
    parts = [p for p in (text or "").split("；") if p]
    return "；".join(parts[:n]) + ("…" if len(parts) > n else "")


def badge(nature: str) -> str:
    return f":{NATURE_COLOR.get(nature, 'gray')}-badge[{nature}]"


# ---------------------------------------------------------------- the day in one sentence
day = live[-1].name if live else "—"
said = []
if facts:
    said.append(f"**{len(facts)} 起已发生的风险事件**（" + "；".join(f"{r['name']}：{r['kind_label']}"
                                                     for r in facts[:2]) + ("等" if len(facts) > 2 else "") + "）")
said.append(f"**{len(exposures)} 个风险敞口**" if exposures else "没有新的风险敞口")
said.append(f"**{len(weak)} 家企业抗冲击能力弱**" + (f"（新进入 {len(new_weak)} 家）" if new_weak else ""))
top = key_now[0] if key_now else None
tail = f"；得分最高的传导路径是 **{top['path']}**" if top else "；暂无得分为正的传导路径"
verdict("error" if facts or new_weak or new_paths else "warning" if weak or key_now else "success",
        f"**今日结论**（{day}）：" + "，".join(said) + tail + "。")

# ---------------------------------------------------------------- the four questions, left to right
steps = [("① 发生了什么", len(facts), "已发生事件", "公告里已公开的事实：冻结、风险警示、违约、停产等"),
         ("② 谁有敞口", len(exposures), "风险敞口", "别人出事才会变成损失：担保、质押、不透明的借款方"),
         ("③ 扛不扛得住", len(weak), "模型预警", "抗冲击能力弱：负债、偿债、现金流、盈利、股价、担保"),
         ("④ 会传给谁", len(key_now), None, "沿担保、关联交易、同集团关系传给其他上市公司")]
cols = st.columns([1, 0.08, 1, 0.08, 1, 0.08, 1], vertical_alignment="center")
for k, (title, n, nature, note) in enumerate(steps):
    with cols[2 * k].container(border=True, height=150):
        st.markdown(f"**{title}**" + (f"　{badge(nature)}" if nature else "　:gray-badge[传导]"))
        st.markdown(f"<span style='font-size:2rem;font-weight:700'>{n}</span>", unsafe_allow_html=True)
        st.caption(note)
    if k < 3:
        cols[2 * k + 1].markdown("<div style='text-align:center;font-size:1.6rem;color:#999'>→</div>", unsafe_allow_html=True)
reports = sorted((ROOT / "data" / "live").glob("report_*.md"))

# ---------------------------------------------------------------- sources (stage 1) and where they go (stage 2)
left, right = st.columns([1.05, 1], gap="large")
with left:
    st.subheader("风险源：谁可能先出问题", divider="red")
    for nature, rows, empty in (("已发生事件", facts, "评估日前 12 个月内，公告中没有已发生的信用事件或停产。"),
                                ("风险敞口", exposures, "没有中、高严重度的风险敞口。")):
        st.markdown(f"{badge(nature)}　" + ("公告中已公开的事实" if nature == "已发生事件" else "别人出事才会变成损失的承诺"))
        if not rows:
            st.caption(empty)
        for i, r in enumerate(rows[:5]):
            with st.container(border=True):
                a, b = st.columns([5, 1.3], vertical_alignment="center")
                reach = ("　→ 可能波及 " + "、".join(r["reached"][:3]) + ("等" if len(r["reached"]) > 3 else "")) if r["reached"] else ""
                a.markdown(f"**{r['name']}** · {r['kind_label']} · 严重度{r['severity']}  \n"
                           f"<small>{r['reason'][:80]}{reach}</small>", unsafe_allow_html=True)
                if r["listed"] and r["node"].isdigit():
                    with b:
                        profile_button(r["node"], "档案", key=f"home_src_{nature}_{i}", width="stretch")
    st.markdown(f"{badge('模型预警')}　尚未出事，但抗冲击能力弱（0–100 分，≥ 60 为弱，越高越脆弱）")
    if not weak:
        st.caption("今天没有抗冲击能力弱的企业。")
    for r in weak:
        with st.container(border=True):
            a, b = st.columns([5, 1.3], vertical_alignment="center")
            tag = " · **新进入**" if r in new_weak else ""
            a.markdown(f"**{r['security_name']}** · {r['total_score']} 分{tag}  \n<small>{short_reasons(r['reasons'])}</small>",
                       unsafe_allow_html=True)
            with b:
                profile_button(r["security_code"], "档案", key=f"home_{r['security_code']}", width="stretch")
with right:
    st.subheader("传导：会传给谁", divider="violet")
    st.caption("从左边的风险源出发，沿担保、关联交易和集团关系推出的得分最高的路径；标签是起点的性质")
    if not key_now:
        st.caption("没有需要关注的传导路径。")
    for i, r in enumerate(key_now[:6]):
        with st.container(border=True):
            a, b = st.columns([5, 1.3], vertical_alignment="center")
            tag = "　:green-badge[新增]" if r in new_paths else ""
            via = " → ".join(RULE_WORD.get(x, x) for x in (r.get("rules") or "").split("+") if x)
            amount = f" · 涉及 {float(r['amount_yi']):.2f} 亿元" if float(r.get("amount_yi") or 0) > 0 else ""
            a.markdown(f"{badge(seed_nature(r.get('reason', '')))}{tag}  \n**{r['path']}**  \n"
                       f"<small>得分 {r['score']} · 经 {via}{amount}</small>", unsafe_allow_html=True)
            if b.button("传导图", key=f"home_path_{i}", icon=":material/hub:", width="stretch"):
                open_unified(r["seed"], live[-1].name if live else None)
                st.switch_page(UNIFIED_PAGE)
    st.markdown(f"{badge('情景假设')}　产品价格（近 {WINDOW} 个交易日，加粗为涨跌 ≥ {THRESHOLD:.0%}）")
    st.caption("；".join(f"{'**' if m['shock'] else ''}{m['product']} {m['ret']:+.1%}{'**' if m['shock'] else ''}" for m in moves)
               or "无价格数据")
    st.page_link("pages/5_上下游情景.py", label="假设一次价格、停产或政策冲击，看会波及谁", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- trust (one line of numbers; details on 可信度)
st.subheader("凭什么可信", divider="gray")
summary = ROOT / "experiments" / "final_test" / "summary.json"
final = json.loads(summary.read_text(encoding="utf-8"))["aggregate"]["related_party"] if summary.exists() else None
t1, t5, t2, t3, t4 = st.columns(5)
t1.metric("公告抽取 · 最终盲测 F1", f"{final['f1']['mean']:.1%}" if final else "—",
          help="关联交易 7 份 × 3 次，记录级 F1；冻结系统、Gold 在运行前锁定（AI 预标注、人工抽查 53/178）。修复单位缺陷后（非盲）为 92.15%")
t5.metric("承压评分 · 预注册事件研究", "44.9% vs 12.6%",
          help="2019–2025 年 7 个评估日 × 24 家核心钢厂：被判为“弱”的企业 12 个月内发生信用事件（硬事件或年度亏损 ≥ 净资产 5%）"
               "的比例 vs 其他企业；提升 3.6 倍，AUC 0.75（企业重抽样区间 0.64–0.85）；2019–2023 样本外提升 2.6 倍（p = 0.035）。"
               "事后分析：以亏损为主的事件上不优于净利率单指标")
t2.metric("财务数据 · 年报抽查", "30 / 30", help="6 家企业 × 5 个科目，与年报原文逐位一致")
t3.metric("风险传导 · 预注册回测", "3 个案例", help="安泰（标准 1、3 通过，2 部分通过）、凌钢（2、3 通过，1 部分通过）、方大（全部通过，无误报）")
t4.metric("上下游产品层 · 预注册检验", "2 次未显著", help="利润检验未通过；股价检验方向一致但 p = 0.28。因此只作情景提示")
st.caption("股份质押保留为辅助风险信号，不作为主宣传指标；其独立盲测事件 F1 为 73.85%。全部验证结果（包括没通过的）见顶部“可信度”。")

next_step("选一家企业，看它自身扛不扛得住、风险从哪里传进来", "企业档案", "pages/7_企业档案.py", key="home_next",
          state={"code": weak[0]["security_code"]} if weak else None, state_key="_goto_profile" if weak else None)

# ---------------------------------------------------------------- maintenance (folded)
if public_mode():
    st.caption("公开演示版：数据截至最近一次提交，不在线更新；" +
               ("“分析新公告”可在线分析少量新公告（有次数限制）。" if online_model() else "现场抽取新公告需在本机运行（见 README）。"))
    if reports:
        with st.expander(f"最新日报 {reports[-1].stem[7:]}", icon=":material/article:"):
            st.markdown(reports[-1].read_text(encoding="utf-8"))
else:
    with st.expander("数据更新（查新公告并重算，联网约 5–15 分钟；演示时不要点）", icon=":material/refresh:"):
        st.caption("查 40 家企业的新公告 → 冻结版系统抽取 → 更新图谱（过期关系自动失效）→ 更新承压评分 → 对比风险路径。")
        online = st.checkbox("联网查新公告（需本机网络与模型接口）", value=True)
        if st.button("立即更新", type="primary"):
            cmd = [sys.executable, str(ROOT / "scripts" / "daily_update.py")] + ([] if online else ["--no-network"])
            with st.spinner("正在更新…"):
                out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
            st.cache_data.clear()
            st.code((out.stdout or "")[-1500:] + (out.stderr or "")[-800:])
        if reports:
            st.markdown(f"**最新日报 {reports[-1].stem[7:]}**")
            st.markdown(reports[-1].read_text(encoding="utf-8"))
