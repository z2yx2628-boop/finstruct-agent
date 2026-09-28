"""Shared page header: the question the page answers, how fresh the data is, and the evidence-grade legend."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
GRADES = ("**证据等级** A 披露确认：公告或年报写明双方（和金额），或股权关系已核对 · "
          "B 部分确认：公司自己披露的产品暴露、未逐一核对的集团归属 · C 行业推断：只作情景，不计入风险得分")


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


def page_header(title: str, icon: str, question: str, grades: bool = False) -> None:
    st.title(title, icon=icon)
    f = freshness()
    st.caption(f"**本页回答：{question}**  \n数据截至：承压快照 {f['snapshot']} · 公告检查至 {f['announcements']} · "
               f"产品价格至 {f['prices']}")
    if grades:
        st.caption(GRADES)
