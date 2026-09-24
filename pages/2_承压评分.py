"""方向二：承压评分页面（财报层 + 市场层 + 事件层），带一键更新。"""
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "snapshots"
TIER_COLOR = {"weak": "🔴", "medium": "🟡", "strong": "🟢"}

st.set_page_config(page_title="承压评分 · FinStruct Agent", layout="wide")
st.title("承压评分：这家企业扛不扛得住冲击？")
st.caption("财报层（最新法定披露期，同行排名）+ 市场层（60日超额收益、回撤、波动）+ 事件层（财报后的高风险公告）。"
           "每个等级都附原因；红线（资不抵债、负债率≥85%）和财报后事件只会使等级变差。")

col1, col2 = st.columns([1, 3])
with col1:
    as_of = st.date_input("评估日期", value=date.today())
    offline = st.checkbox("只用已缓存数据（历史回测用）", value=as_of < date.today())
    if st.button("更新数据并重新评分", type="primary"):
        cmd = [sys.executable, str(ROOT / "scripts" / "update_all.py"), "--as-of", as_of.isoformat()]
        if offline:
            cmd.append("--offline")
        with st.spinner("正在更新（联网时约3–5分钟）…"):
            run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        st.code((run.stdout or "")[-2000:] + (run.stderr or "")[-1500:])

snapshots = sorted((d for d in SNAP.glob("*") if (d / "fragility.csv").exists()), reverse=True)
if not snapshots:
    st.info("还没有评分快照。点击左侧按钮生成第一份。")
    st.stop()
with col2:
    chosen = st.selectbox("查看快照", [d.name for d in snapshots])
folder = SNAP / chosen
with (folder / "fragility.csv").open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

counts = {k: sum(1 for r in rows if r["tier"] == k) for k in ("weak", "medium", "strong")}
m1, m2, m3 = st.columns(3)
m1.metric("🔴 弱", counts["weak"])
m2.metric("🟡 中", counts["medium"])
m3.metric("🟢 强", counts["strong"])

table = [{
    "等级": f"{TIER_COLOR.get(r['tier'], '')} {r['tier_label']}", "企业": r["security_name"], "代码": r["security_code"],
    "总分(越高越弱)": r["total_score"], "杠杆": r["score_leverage"], "短期偿债": r["score_liquidity"],
    "造血": r["score_cash"], "盈利": r["score_profit"], "市场": r["score_market"],
    "财报后事件": r["events_after_report"], "原因": r["reasons"],
} for r in rows]
st.dataframe(table, use_container_width=True, hide_index=True)

if (folder / "changes.md").exists():
    with st.expander("本次变化与弱档说明", expanded=True):
        st.markdown((folder / "changes.md").read_text(encoding="utf-8"))
