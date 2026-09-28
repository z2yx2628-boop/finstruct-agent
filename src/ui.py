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
PROFILE_PAGE = "pages/7_企业档案.py"
GRADES = ("**证据等级**  \n"
          "- **A 披露确认**：公告或年报写明双方（和金额），或股权关系已核对来源；计入风险得分。\n"
          "- **B 部分确认**：公司自己披露的产品暴露、未逐一核对的集团归属；只证明一半。\n"
          "- **C 行业推断**：按行业推断的潜在关系，只作情景提示，不计入风险得分。")
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


def page_header(title: str, icon: str, question: str, grades: bool = False, about: str | None = None) -> None:
    """Title, one caption line, and (optionally) everything explanatory folded into a single box."""
    st.title(title, icon=icon)
    f = freshness()
    st.caption(f"{question}　·　数据截至 {f['snapshot']}（公告检查至 {f['announcements']}，价格至 {f['prices']}）")
    if about or grades:
        with st.expander("说明：范围、方法与证据等级", icon=":material/info:"):
            if about:
                st.markdown(about)
            if grades:
                st.markdown(GRADES)


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
