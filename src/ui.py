"""Shared page furniture: a short header (title + the question the page answers + data freshness),
one folded "说明" box for scope, method and the evidence-grade legend, a conclusion banner, and
navigation into the company profile."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PAGE = "pages/7_企业档案.py"
GRADES = ("**证据等级**  \n"
          "- **A 披露确认**：公告或年报写明双方（和金额），或股权关系已核对来源；计入风险得分。\n"
          "- **B 部分确认**：公司自己披露的产品暴露、未逐一核对的集团归属；只证明一半。\n"
          "- **C 行业推断**：按行业推断的潜在关系，只作情景提示，不计入风险得分。")
TIER_BADGE = {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强"}


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
