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

st.markdown("<style>.block-container{padding-top:2.2rem}</style>", unsafe_allow_html=True)
page_header("钢铁上市公司上下游冲击传导与经营风险智能体", ":material/dashboard:", "链证 ChainProof · 今日风险源与传导路径",
            step=1, fresh=True)
glossary(intro="链证分两段预警：**① 风险源预警**——可能率先出现风险的企业（公告中的风险事件 + 财务脆弱性评分）；"
               "**② 风险传导预警**——风险可能沿担保、关联交易和集团关系传导至哪些企业、涉及多少金额。"
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
top = key_now[0] if key_now else None
from src.futures import margin_snapshot          # noqa: E402
ms = margin_snapshot("rebar", live[-1].name if live else "9999-12-31")
low_margin = bool(ms and ms["pct_all"] is not None and ms["pct_all"] <= 0.2)
head = f"**今日结论**（{day}）：{len(facts)} 起已发生事件、{len(weak)} 家财务脆弱"
if low_margin:
    head += "，行业利润处于历史低位"
head += f"；首要核查路径 **{top['path']}**。" if top else "；暂无需要核查的传导路径。"
verdict("error" if facts or new_weak or new_paths else "warning" if weak or key_now else "success", head)

# ---------------------------------------------------------------- five numbers: same height, each opens its detail
def _src_lines(rows, limit=12):
    if not rows:
        st.caption("暂无。")
    for r in rows[:limit]:
        st.markdown(f"- **{r['name']}** · {r['kind_label']} · 严重度{r['severity']}  \n  <small>{r['reason'][:90]}</small>",
                    unsafe_allow_html=True)
    if len(rows) > limit:
        st.caption(f"另有 {len(rows) - limit} 条，见下方“风险源”。")


def _detail_events():
    st.markdown("**已发生事件**：公告中已公开的事实（冻结、风险警示、违约、停产、非标审计意见等）")
    _src_lines(facts)


def _detail_exposures():
    st.markdown("**风险敞口**：关联方违约时可能转化为损失的或有义务（担保、质押、财务不透明的被担保方）")
    _src_lines(exposures)


def _detail_weak():
    st.markdown("**财务脆弱**：承压评分 ≥ 60 或触发直接判弱规则（24 家核心钢厂相对比较，不是违约概率）")
    for r in weak:
        st.markdown(f"- **{r['security_name']}** · {r['total_score']} 分" + (" · 新进入" if r in new_weak else "")
                    + f"  \n  <small>{short_reasons(r['reasons'])}</small>", unsafe_allow_html=True)
    st.page_link("views/2_承压评分.py", label="24 家完整评分表", icon=":material/monitoring:")


def _detail_paths():
    st.markdown("**传导路径**：从风险源出发，沿担保、关联交易、集团关系排序的优先核查路径（得分不等于损失）")
    for r in key_now[:10]:
        via = " → ".join(RULE_WORD.get(x, x) for x in (r.get("rules") or "").split("+") if x)
        st.markdown(f"- **{r['path']}**  \n  <small>得分 {r['score']} · 经 {via}</small>", unsafe_allow_html=True)
    st.page_link(UNIFIED_PAGE, label="在传导图上查看", icon=":material/hub:")


def _detail_margin():
    if not ms:
        st.caption("期货价格不可用。")
        return
    st.markdown("**行业压力 = 吨钢盘面利润**：卖一吨螺纹钢，扣掉 1.6 吨铁矿石和 0.5 吨焦炭后剩下的钱（期货主力连续合约）")
    p_ = ms["prices"]
    st.markdown(f"- 螺纹钢 {p_['RB0']:,.1f} − 1.6 × 铁矿石 {p_['I0']:,.1f} − 0.5 × 焦炭 {p_['J0']:,.1f} = **{ms['value']:,.0f} 元/吨**（{ms['date']}）\n"
                f"- 近 {WINDOW} 个交易日变化 {ms['change']:+,.0f} 元："
                + "；".join(f"{c['品种']} {c['价格变化']:+.1%}，影响 {c['对利润的贡献（元/吨）']:+,.0f}" for c in ms["contrib"]) + "\n"
                f"- 在 {ms['since'][:4]} 年以来约 3,000 个交易日中处于 **{ms['pct_all']:.0%} 分位**"
                f"（区间 {ms['min']:,.0f} 至 {ms['max']:,.0f}）；≤ 20% 视为历史低位")
    st.caption("未扣加工、人工、折旧等其他成本，不是任何企业的实际利润；只作行业情景，不计入承压评分。")
    if st.button("期货情景与套保", key="kpi_futures", icon=":material/candlestick_chart:"):
        st.session_state["sc_source"] = "期货与套保"
        st.switch_page("views/5_上下游情景.py")


# five numbers; each card is one big click target that opens its details (no separate "查看详情" button).
# The card is one HTML block; a transparent Streamlit button is stretched over it to catch the click.
ACCENT = {"red": "#C63F45", "orange": "#D9822B", "violet": "#7B2CBF", "blue": "#1C5D99"}
cards = [("已发生事件", "red", f"{len(facts)}", "", "冻结、风险警示、违约、停产", _detail_events),
         ("风险敞口", "orange", f"{len(exposures)}", "", "担保、质押等或有义务", _detail_exposures),
         ("财务脆弱", "red", f"{len(weak)}", "", "承压评分为弱" + (f"，新进入 {len(new_weak)} 家" if new_weak else ""), _detail_weak),
         ("传导路径", "violet", f"{len(key_now)}", "",
          "沿担保、关联交易、集团关系" + (f"，新增 {len(new_paths)}" if new_paths else ""), _detail_paths),
         ("行业压力", "blue", f"{ms['value']:,.0f}" if ms else "—", "元/吨" if ms else "",
          (f"吨钢盘面利润 · 历史 {ms['pct_all']:.0%} 分位" + ("（低位）" if low_margin else "") + f" · 20 日 {ms['change']:+,.0f}")
          if ms else "期货价格不可用", _detail_margin)]
st.html("""<style>
[class*="st-key-kpi_card_"] {position: relative; gap: 0 !important;}
.cp-kpi {box-sizing: border-box; height: 172px; padding: 16px 18px 14px 20px; border: 1px solid var(--cp-line, #E4E7EC);
  border-radius: 14px; background: #fff; position: relative; overflow: hidden;
  box-shadow: 0 1px 2px rgba(16,24,40,.04); transition: border-color .15s, box-shadow .15s, transform .15s;}
.cp-kpi::before {content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--kpi);}
.cp-kpi-t {font-size: .95rem; font-weight: 600; color: #1D2433; display: flex; justify-content: space-between; align-items: center;}
.cp-kpi-t span {color: #98A2B3; font-size: 1.3rem; line-height: 1; transition: transform .15s, color .15s;}
.cp-kpi-v {margin-top: 10px; font-size: 2.3rem; font-weight: 650; line-height: 1.05; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; color: #1D2433; white-space: nowrap;}
.cp-kpi-v small {font-size: .9rem; font-weight: 500; color: #667085; margin-left: .3rem; letter-spacing: 0;}
.cp-kpi-n {margin-top: 8px; font-size: .82rem; line-height: 1.45; color: #667085;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;}
[class*="st-key-kpi_card_"]:hover .cp-kpi {border-color: var(--kpi); box-shadow: 0 8px 24px rgba(16,24,40,.10); transform: translateY(-2px);}
[class*="st-key-kpi_card_"]:hover .cp-kpi-t span {color: var(--kpi); transform: translateX(3px);}
/* the click layer: the button's container and everything inside it fill the whole card */
[class*="st-key-kpi_open_"] {position: absolute !important; inset: 0; z-index: 5; margin: 0 !important; width: 100% !important; height: 100% !important;}
[class*="st-key-kpi_open_"] *, [class*="st-key-kpi_open_"] button {width: 100% !important; height: 100% !important; max-width: none !important;}
[class*="st-key-kpi_open_"] button {opacity: 0; cursor: pointer; border: 0; padding: 0;}
</style>""")
cols = st.columns(5)
for i, (col, (title, color, value, unit, note, detail)) in enumerate(zip(cols, cards)):
    with col.container(key=f"kpi_card_{i}"):
        st.markdown(f"<div class='cp-kpi' style='--kpi:{ACCENT[color]}'><div class='cp-kpi-t'>{title}<span>›</span></div>"
                    f"<div class='cp-kpi-v'>{value}<small>{unit}</small></div><div class='cp-kpi-n'>{note}</div></div>",
                    unsafe_allow_html=True)
        if st.button(f"查看{title}明细", key=f"kpi_open_{i}"):
            st.dialog(title, width="large")(detail)()

# ---------------------------------------------------------------- risk panel: three small charts
from src.futures import margin_series                   # noqa: E402
from src.home_panel import (margin_chart, margin_rows, ranking_chart, ranking_rows, trend_chart,  # noqa: E402
                            trend_rows)


@st.cache_data(show_spinner=False)
def _panel_trend(last: str, n_paths: int):
    return trend_rows(live, paths)


p_left, p_right = st.columns([1.1, 1], gap="large")
with p_left.container(border=True):
    st.markdown("**承压排行**　:gray[24 家核心钢厂，越长越弱；虚线是弱 / 中分界]")
    st.vega_lite_chart(ranking_chart(ranking_rows(now)), width="stretch")
with p_right.container(border=True):
    st.markdown("**风险走势**　:gray[近 60 天：弱等级钢厂数与计分传导路径数]")
    st.vega_lite_chart(trend_chart(_panel_trend(day, len(paths))), width="stretch")
with p_right.container(border=True):
    m_rows, m_low = margin_rows(*margin_series("rebar"), day)
    st.markdown("**行业利润**　:gray[近一年吨钢盘面利润；红虚线以下 = 历史低位]")
    if m_rows:
        st.vega_lite_chart(margin_chart(m_rows, m_low), width="stretch")
    else:
        st.caption("期货价格不可用。")

reports = sorted((ROOT / "data" / "live").glob("report_*.md"))

# ---------------------------------------------------------------- sources (stage 1) and where they go (stage 2)
left, right = st.columns([1, 1], gap="large")
with left:
    st.subheader("风险源：可能率先出现风险的企业", divider="red")
    t_fact, t_exp, t_weak = st.tabs([f"已发生事件 {len(facts)}", f"风险敞口 {len(exposures)}", f"财务脆弱 {len(weak)}"])

    def source_cards(rows, key, limit=4):
        if not rows:
            st.caption("暂无。")
        for i, r in enumerate(rows[:limit]):
            with st.container(border=True):
                a, b = st.columns([5, 1.3], vertical_alignment="center")
                reach = ("　→ 可能波及 " + "、".join(r["reached"][:3]) + ("等" if len(r["reached"]) > 3 else "")) if r["reached"] else ""
                a.markdown(f"**{r['name']}** · {r['kind_label']} · 严重度{r['severity']}  \n"
                           f"<small>{r['reason'][:70]}{reach}</small>", unsafe_allow_html=True)
                if r["listed"] and r["node"].isdigit():
                    with b:
                        profile_button(r["node"], "档案", key=f"home_src_{key}_{i}", width="stretch")
        if len(rows) > limit:
            with st.expander(f"其余 {len(rows) - limit} 条"):
                for r in rows[limit:]:
                    st.markdown(f"- **{r['name']}** · {r['kind_label']} · 严重度{r['severity']}")

    with t_fact:
        st.caption("公告中已公开的事实")
        source_cards(facts, "fact")
    with t_exp:
        st.caption("关联方违约时可能转化为损失的或有义务")
        source_cards(exposures, "exp")
    with t_weak:
        st.caption("尚未发生信用事件，但财务脆弱性较高（0–100 分，≥ 60 为弱，越高越脆弱）")
        if not weak:
            st.caption("今天没有财务脆弱性较高的企业。")
        for r in weak:
            with st.container(border=True):
                a, b = st.columns([5, 1.3], vertical_alignment="center")
                tag = " · **新进入**" if r in new_weak else ""
                a.markdown(f"**{r['security_name']}** · {r['total_score']} 分{tag}  \n<small>{short_reasons(r['reasons'])}</small>",
                           unsafe_allow_html=True)
                with b:
                    profile_button(r["security_code"], "档案", key=f"home_{r['security_code']}", width="stretch")
with right:
    st.subheader("传导：优先核查的路径", divider="violet")
    st.caption("从风险源出发，沿担保、关联交易和集团关系排序的优先核查路径（得分不等于损失大小）；标签是起点的性质")
    if not key_now:
        st.caption("没有需要关注的传导路径。")
    for i, r in enumerate(key_now[:5]):
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
    if len(key_now) > 5:
        st.caption(f"另有 {len(key_now) - 5} 条，见顶部“风险传导”。")
    with st.container(border=True):
        st.markdown(f"{badge('情景假设')}　**市场冲击**：期货与产品价格只作情景，不计入评分")
        if ms:
            st.markdown(f"<small>螺纹吨钢盘面利润 {ms['value']:,.0f} 元/吨，{ms['since'][:4]} 年来 {ms['pct_all']:.0%} 分位"
                        + ("（历史低位：全行业利润被原料成本挤压）" if low_margin else "") + "；近 "
                        + f"{WINDOW} 日产品价格：" + "；".join(f"{m['product']} {m['ret']:+.1%}" for m in moves[:5]) + "</small>",
                        unsafe_allow_html=True)
        m1_, m2_ = st.columns(2)
        if m1_.button("期货情景与套保", key="home_futures", icon=":material/candlestick_chart:", width="stretch"):
            st.session_state["sc_source"] = "期货与套保"
            st.switch_page("views/5_上下游情景.py")
        if m2_.button("产品与政策冲击", key="home_scenario", icon=":material/swap_horiz:", width="stretch"):
            st.session_state["sc_source"] = "产品与需求"
            st.switch_page("views/5_上下游情景.py")

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

next_step("选择一家企业，查看其财务脆弱性及风险传入路径", "企业档案", "views/7_企业档案.py", key="home_next",
          state={"code": weak[0]["security_code"]} if weak else None, state_key="_goto_profile" if weak else None)

# ---------------------------------------------------------------- maintenance (folded)
if public_mode():
    st.caption("公开演示版：数据由 GitHub 定时任务每天北京时间 06:30 自动更新（冻结版抽取系统，结果提交到代码仓库后网站自动重新部署）；"
               "网页本身不提供更新按钮；" +
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
