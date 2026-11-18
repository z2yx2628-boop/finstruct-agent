"""Shared page furniture: a short header (title + the question the page answers + data freshness),
one folded "说明" box for scope, method and the evidence-grade legend, a conclusion banner, and
navigation into the company profile."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PAGE = "views/7_企业档案.py"
GRADES = ("**证据等级**  \n"
          "- **A 披露确认**：公告或年报写明双方（和金额），或股权关系已核对来源；计入风险得分。\n"
          "- **B 部分确认**：公司自己披露的产品暴露、未逐一核对的集团归属；证据为部分确认。\n"
          "- **C 行业推断**：按行业推断的潜在关系，只作情景提示，不计入风险得分。")
GLOSSARY = """
**风险预警的逻辑**：已发生事件（风险源）→ 风险敞口 → 财务脆弱性 → 是否继续传导。每一条都标明性质：

- :red-badge[已发生事件] 公告里已经公开的事实：账户或股份被冻结、被实施风险警示、债务或担保逾期、非标审计意见、破产重整、停产检修等。
- :orange-badge[风险敞口] 关联方发生信用事件时才可能转化为损失的或有义务：对外担保、股权质押、获大额担保但自身财务不公开的企业。
- :violet-badge[模型预警] 尚未发生信用事件，但模型判断企业财务脆弱性较高。
- :blue-badge[情景假设] “如果价格涨跌、停产或政策变化会怎样”，是假设，不是现实事件。

**财务脆弱性（承压评分）**：企业当前财务状况的相对脆弱程度，用于同行比较和风险筛查。在 24 家核心钢厂中比较六个维度——杠杆、短期偿债、
经营现金流、盈利、市场表现和对外担保——得到 0–100 分，**分数越高越脆弱**，≥ 60 为“弱”。
它不是违约概率，也不直接衡量企业对某一特定冲击的承受能力；在传导中，它决定路径经过这家企业时是否继续扩展。
检验：2019–2025 年被判为“弱”的钢厂，12 个月内发生信用事件（冻结、风险警示、非标意见、大额亏损等）的比例是 44.9%，其他钢厂 12.6%。

**风险传导**：风险源的问题沿**有合同或资金约束的关系**（担保、关联交易、同一集团）传给其他上市公司。
路径得分 = 起点严重度 × 涉及金额 × 途经企业的脆弱程度，表示按当前规则排序的优先核查顺序，不等于损失大小；途经企业承压为强时，路径不再继续扩展（风险可能受到缓释）。关联交易金额是交易额，不等于风险敞口。

**证据等级**：A = 公告写明双方和金额，计入得分；B = 公司自己披露的产品构成等，证据为部分确认；C = 行业推断，只作情景，不计分。

**可追溯（可解释的风险分析）**：每个结论都能点回公告原文页码、评分指标、传导规则和停止原因，可以逐条复算；
这说明分析过程透明，不代表结论一定正确。
"""


def glossary(expanded: bool = False, intro: str | None = None) -> None:
    """The one explanation box of a page: what the page does (intro) and how to read the system."""
    with st.expander("说明：怎么读这个系统（风险源、财务脆弱性、传导、证据等级）", icon=":material/menu_book:", expanded=expanded):
        if intro:
            st.markdown(intro)
            st.divider()
        st.markdown(GLOSSARY)


TIER_BADGE = {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强"}


def public_mode() -> bool:
    """Public read-only deployment (e.g. Streamlit Community Cloud with secret CHAINPROOF_PUBLIC = "1"):
    no model calls, no data updates, no writes; the offline demo pack and the committed data only."""
    return os.environ.get("CHAINPROOF_PUBLIC", "").strip().lower() in ("1", "true", "yes")


def online_model() -> bool:
    """Public deployment WITH a model key in its secrets: new announcements can be analysed, within quotas."""
    return public_mode() and bool(os.environ.get("LLM_API_KEY", "").strip())


def _limit(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def quota_check(data: bytes, name: str) -> str | None:
    """None if this online analysis may run; otherwise the reason it may not (size, pages, per-session, per-day)."""
    import datetime
    import tempfile
    max_mb, max_pages = _limit("CHAINPROOF_MAX_MB", 10), _limit("CHAINPROOF_MAX_PAGES", 60)
    if len(data) > max_mb * 1024 * 1024:
        return f"文件超过 {max_mb} MB。"
    if name.lower().endswith(".pdf"):
        try:
            import fitz
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.page_count > max_pages:
                    return f"PDF 超过 {max_pages} 页（本文件 {doc.page_count} 页）；长文件请在本机运行。"
        except Exception:  # noqa: BLE001 - unreadable PDFs are left to the parser's own error message
            pass
    if st.session_state.get("_online_runs", 0) >= _limit("CHAINPROOF_SESSION_LIMIT", 3):
        return "本次访问的在线分析次数已用完（防止额度被滥用）。可以用“演示案例”，或在本机运行。"
    counter = Path(tempfile.gettempdir()) / f"chainproof_runs_{datetime.date.today().isoformat()}.txt"
    used = int(counter.read_text() or 0) if counter.exists() else 0
    if used >= _limit("CHAINPROOF_DAILY_LIMIT", 30):
        return "今日在线分析总次数已达上限，请明天再试，或使用“演示案例”。"
    return None


def quota_consume() -> None:
    import datetime
    import tempfile
    st.session_state["_online_runs"] = st.session_state.get("_online_runs", 0) + 1
    counter = Path(tempfile.gettempdir()) / f"chainproof_runs_{datetime.date.today().isoformat()}.txt"
    used = int(counter.read_text() or 0) if counter.exists() else 0
    counter.write_text(str(used + 1))


PUBLIC_NOTE = ("公开演示版：不调用模型、不联网更新，数据截至最近一次提交。现场抽取新公告需在本机运行（见 README）。")


def freshness() -> dict[str, str]:
    snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").glob("2026-*") if (p / "fragility.csv").exists())
    state = ROOT / "data" / "live" / "state.json"
    prices = ROOT / "data" / "external" / "prices" / "J0.csv"
    last_price = ""
    if prices.exists():
        with prices.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        last_price = rows[-1]["date"][:10] if rows else ""
    return {"snapshot": snaps[-1] if snaps else "—",
            "announcements": json.loads(state.read_text(encoding="utf-8")).get("last_checked", "—") if state.exists() else "—",
            "prices": last_price or "—"}


STORY = ["今日预警", "企业档案", "风险传导", "分析新公告", "可信度"]
UNIFIED_PAGE = "views/8_风险传导总图.py"


@st.cache_data(ttl=600, show_spinner=False)
def _command_companies() -> list[dict]:
    from src.command import load_companies
    from src.profile import fragility_rows, snapshots
    snaps = snapshots()
    return load_companies(fragility_rows(snaps[0])) if snaps else []


def _queue_command() -> None:
    st.session_state["_cmd_pending"] = st.session_state.get("cmd_bar")
    st.session_state["cmd_bar"] = None


GLOBAL_CSS = """
<style>
:root {--cp-ink: #1D2433; --cp-muted: #667085; --cp-line: #E4E7EC; --cp-card: #FFFFFF; --cp-soft: #F5F6F8; --cp-accent: #C63F45;}
.stApp {font-family: "Inter", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
        color: var(--cp-ink); -webkit-font-smoothing: antialiased;}
.stApp h1 {font-weight: 700; letter-spacing: -.015em;}
.stApp h2, .stApp h3 {font-weight: 650; letter-spacing: -.01em;}
[data-testid="stCaptionContainer"] {color: var(--cp-muted);}
[data-testid="stMetricValue"] {font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -.01em;}
[data-testid="stMetricLabel"] p {color: var(--cp-muted); font-size: .85rem;}
.stButton button, .stDownloadButton button, .stPageLink a {border-radius: 10px; font-weight: 500; transition: border-color .15s, box-shadow .15s;}
.stButton button[kind="secondary"]:hover, .stDownloadButton button:hover {border-color: var(--cp-accent); color: var(--cp-accent);}
[data-testid="stExpander"] details {border-radius: 12px; border-color: var(--cp-line);}
[data-testid="stExpander"] summary:hover {color: var(--cp-accent);}
[data-testid="stAlert"] {border-radius: 12px;}
/* the search bar: one quiet field with a magnifier, highlighted only when used */
.st-key-cmd_bar [data-baseweb="select"] > div {border-radius: 12px; background-color: var(--cp-soft); border: 1px solid transparent;
  padding-left: 34px; min-height: 44px; transition: border-color .15s, background-color .15s, box-shadow .15s;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23667085' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m20 20-3.5-3.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: 12px center; background-size: 18px;}
.st-key-cmd_bar [data-baseweb="select"] > div:hover {border-color: var(--cp-line);}
.st-key-cmd_bar [data-baseweb="select"] > div:focus-within {background-color: #fff; border-color: var(--cp-accent);
  box-shadow: 0 0 0 3px rgba(198,63,69,.12);}
</style>
"""


def global_style() -> None:
    """One stylesheet for every page (called from app.py)."""
    st.html(GLOBAL_CSS)


def command_bar() -> None:
    """Bloomberg-style command line on every page: "<company> <function>", a page name, or a question."""
    from src.command import FUNCS, parse, suggestion
    companies = _command_companies()
    st.selectbox("命令行", [suggestion(c) for c in companies], index=None, key="cmd_bar", accept_new_options=True,
                 on_change=_queue_command, label_visibility="collapsed",
                 placeholder="输入公司、代码、命令或问题后回车　例：凌钢　600231 FA　安泰 RELS　鞍钢 客户　期货　可信度　?凌钢会传给谁")
    note = st.session_state.pop("_cmd_note", None)
    if note:
        st.toast(note, icon=":material/info:")
    pending = st.session_state.pop("_cmd_pending", None)
    if not pending:
        return
    cmd = parse(pending, companies)
    if cmd["kind"] == "company":
        c = cmd["company"]
        if cmd["others"]:
            st.session_state["_cmd_note"] = (f"匹配到多家：{'、'.join([c['name']] + [o['name'] for o in cmd['others'][:4]])}；"
                                             f"已打开 {c['name']}，可输入全称或代码精确定位")
        if cmd["target"] == "unified":
            st.session_state["_goto_unified"] = {"code": c["code"]}
            st.switch_page(UNIFIED_PAGE)
        st.session_state["_goto_profile"] = {"code": c["code"], "tab": cmd["section"]}
        st.switch_page("views/7_企业档案.py")
    elif cmd["kind"] == "page":
        st.session_state.update(cmd["state"])
        st.switch_page(cmd["page"])
    elif cmd["kind"] == "ask":                         # answered in place, in the same dialog as the floating button
        from src.ask_view import open_dialog
        open_dialog(cmd["question"])
    else:
        st.toast("没有找到。试试企业简称、6 位代码，或命令：" + "、".join(f"{k} {v[0]}" for k, v in FUNCS.items()),
                 icon=":material/search_off:")


def page_header(title: str, icon: str, question: str, grades: bool = False, about: str | None = None,
                step: int | None = None, fresh: bool = False, subtitle: str | None = None) -> None:
    """Title, one caption line (story step + the question the page answers), and everything explanatory
    folded into a single box. Data freshness is shown only where asked (the home page)."""
    command_bar()
    st.title(title, icon=icon)
    if subtitle:
        st.subheader(subtitle, divider=False)
    line = question
    if step:
        line = f"第 {step} 步 / 共 {len(STORY)} 步　·　{question}"
    if fresh:
        f = freshness()
        line += f"　·　数据截至 {f['snapshot']}（公告检查至 {f['announcements']}，价格至 {f['prices']}）"
    st.caption(line)
    if about or grades:
        with st.expander("说明：范围、方法与证据等级", icon=":material/info:"):
            if about:
                st.markdown(about)
            if grades:
                st.markdown(GRADES)


def next_step(text: str, label: str, page: str, key: str, state: dict | None = None, state_key: str | None = None) -> None:
    """A closing box that says where the story goes next; the button carries the current company along."""
    st.divider()
    with st.container(border=True):
        a, b = st.columns([3, 1], vertical_alignment="center")
        a.markdown(f"**下一步** · {text}")
        if b.button(label, key=key, type="primary", icon=":material/arrow_forward:", width="stretch"):
            if state_key:
                st.session_state[state_key] = state or {}
            st.switch_page(page)


def open_unified(code: str | None = None, snapshot: str | None = None) -> None:
    """Hand a company to the 风险传导 page (it preselects it once)."""
    st.session_state["_goto_unified"] = {"code": code, "snapshot": snapshot}


def verdict(level: str, text: str) -> None:
    """The one-sentence conclusion at the top of a result."""
    icon = {"error": ":material/error:", "warning": ":material/warning:", "success": ":material/check_circle:"}.get(level,
                                                                                                                   ":material/info:")
    getattr(st, level if level in ("error", "warning", "success") else "info")(text, icon=icon)


def open_profile(code: str, snapshot: str | None = None, chain: str | None = None) -> None:
    """Button callback target: remember the company, the page switch happens in goto_profile_button."""
    st.session_state["_goto_profile"] = {"code": code, "snapshot": snapshot, "chain": chain}


def profile_button(code: str, label: str = "企业档案", key: str | None = None, snapshot: str | None = None,
                   chain: str | None = None, **kwargs) -> None:
    if st.button(label, key=key or f"profile_{code}", icon=":material/badge:", **kwargs):
        open_profile(code, snapshot, chain)
        st.switch_page(PROFILE_PAGE)


def deposit_block(code: str, as_of: str) -> None:
    """集团财务公司存款（资金归集）for one company, with its source; scenario information, not scored."""
    import csv as _csv
    from src.finance_channel import exposure
    metrics = ROOT / "data" / "snapshots" / as_of / "quarterly_metrics.csv"
    equity = None
    if metrics.exists():
        with metrics.open(encoding="utf-8-sig", newline="") as f:
            row = next((r for r in _csv.DictReader(f) if r["security_code"] == code), None)
        equity = float(row["equity"]) if row and row.get("equity") else None
    e = exposure(code, as_of, equity)
    st.markdown("**资金归集：集团财务公司存款**（情景信息，不计入风险得分）")
    if not e:
        st.caption("评估日前没有收集到该企业在集团财务公司存款的披露。")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("存款余额", f"{e['deposit_yi']:.2f} 亿元", help=f"截至 {e['period']}")
    c2.metric("占净资产", f"{e['deposit_to_equity']:.1%}" if e["deposit_to_equity"] is not None else "—")
    c3.metric("占自身存款", f"{e['deposit_share']:.1%}" if e["deposit_share"] is not None else "未披露")
    c4.metric("从财务公司借款", f"{e['loan_yi']:.2f} 亿元" if e["loan_yi"] is not None else "未披露")
    st.caption(f"{e['finance_company']} · 截至 {e['period']} · 来源：{e['source_label']}《{e['source_title']}》（{e['source_date']}）"
               + ("" if e["verified"] == "Y" else " · 数字尚未人工对照原文核对"))
    st.markdown(f"> {e['evidence_text']}  \n[原文链接]({e['source_url']})")
