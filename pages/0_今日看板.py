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
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.ui import page_header, profile_button, verdict  # noqa: E402

page_header("链证 · 钢铁产业链风险传导预警", ":material/dashboard:", "今天有什么风险？先看哪家企业？这个系统凭什么可信？",
            grades=True,
            about="链证把上市公司公告变成可核查的风险链条：**公告事实**（关联交易、担保、产能、质押）→ "
                  "**企业承压**（财报、市场、事件三层评分）→ **风险传导**（沿公告披露的关系传给谁）。"
                  "页面上的每个结论都能点回公告原文和页码。")


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
shocks = [m for m in moves if m["shock"]]

# ---------------------------------------------------------------- conclusion first
parts = [f"{len(weak)} 家企业承压为弱" + (f"（新进入 {len(new_weak)} 家）" if new_weak else ""),
         f"{len(key_now)} 条关键风险路径" + (f"（新增 {len(new_paths)} 条）" if new_paths else ""),
         f"{len(shocks)} 个产品价格冲击" if shocks else "产品价格无明显冲击"]
verdict("error" if new_weak or new_paths else "warning" if weak or key_now else "success",
        f"**今日结论**（{live[-1].name if live else '—'}）：" + "；".join(parts) + "。")

m1, m2, m3, m4 = st.columns(4)
m1.metric("承压为弱的企业", len(weak),
          delta=(len(weak) - sum(1 for r in before.values() if r["tier"] == "weak")) if before else None, delta_color="inverse")
m2.metric("关键风险路径", len(key_now), delta=len(new_paths) if key_before else None, delta_color="inverse",
          help="delta = 与上一期相比新增的路径数")
m3.metric(f"产品价格冲击（{WINDOW} 日 ±{THRESHOLD:.0%}）", len(shocks))
reports = sorted((ROOT / "data" / "live").glob("report_*.md"))
m4.metric("最新日报", reports[-1].stem[7:] if reports else "—")

# ---------------------------------------------------------------- what to look at
left, right = st.columns(2, gap="large")
with left:
    st.subheader("先看这些企业", divider="gray")
    if not weak:
        st.caption("今天没有承压为弱的企业。")
    for r in weak:
        a, b = st.columns([5, 1.3], vertical_alignment="center")
        tag = " · **新进入**" if r in new_weak else ""
        a.markdown(f"🔴 **{r['security_name']}** {r['total_score']} 分{tag}  \n"
                   f"<small>{(r['reasons'] or '')[:70]}…</small>", unsafe_allow_html=True)
        with b:
            profile_button(r["security_code"], "档案", key=f"home_{r['security_code']}", width="stretch")
    st.page_link("pages/2_承压评分.py", label="全部 24 家核心钢厂的评分", icon=":material/monitoring:")
with right:
    st.subheader("得分最高的传导路径", divider="gray")
    if not key_now:
        st.caption("没有需要关注的传导路径。")
    for r in key_now[:4]:
        tag = " · **新增**" if r in new_paths else ""
        st.markdown(f"- {r['path']}{tag}  \n  <small>得分 {r['score']}</small>", unsafe_allow_html=True)
    st.page_link("pages/4_风险路径图.py", label="打开关联与担保传导图", icon=":material/account_tree:")
    st.subheader("产品价格", divider="gray")
    st.caption(f"近 {WINDOW} 个交易日；加粗为冲击（涨跌 ≥ {THRESHOLD:.0%}）  \n" + "；".join(
        f"{'**' if m['shock'] else ''}{m['product']} {m['ret']:+.1%}{'**' if m['shock'] else ''}" for m in moves) or "无价格数据")
    st.page_link("pages/5_上下游情景.py", label="模拟一次价格或停产冲击会波及谁", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- trust
st.subheader("凭什么可信", divider="gray")
summary = ROOT / "experiments" / "final_test" / "summary.json"
final = json.loads(summary.read_text(encoding="utf-8"))["aggregate"]["related_party"] if summary.exists() else None
t1, t2, t3, t4 = st.columns(4)
t1.metric("公告抽取 · 最终盲测 F1", f"{final['f1']['mean']:.1%}" if final else "—",
          help="关联交易 7 份 × 3 次，记录级 F1；冻结系统、Gold 在运行前锁定（AI 预标注、人工抽查 53/178）。修复单位缺陷后（非盲）为 92.15%")
t2.metric("财务数据 · 年报抽查", "30 / 30", help="6 家企业 × 5 个科目，与年报原文逐位一致")
t3.metric("风险传导 · 预注册回测", "3 个案例", help="安泰（标准 1、3 通过，2 部分通过）、凌钢（2、3 通过，1 部分通过）、方大（全部通过，无误报）")
t4.metric("上下游产品层 · 预注册检验", "2 次未显著", help="利润检验未通过；股价检验方向一致但 p = 0.28。因此只作情景提示")
st.page_link("pages/6_验证与证据.py", label="全部验证结果（包括没通过的）", icon=":material/verified:")
st.caption("股份质押保留为辅助风险信号，不作为主宣传指标；其独立盲测事件 F1 为 73.85%。")

# ---------------------------------------------------------------- start here
st.subheader("从这里开始", divider="gray")
g1, g2, g3, g4 = st.columns(4)
g1.page_link("pages/7_企业档案.py", label="查一家企业的全部风险", icon=":material/badge:")
g2.page_link("pages/3_一键分析.py", label="分析一份新公告", icon=":material/bolt:")
g3.page_link("pages/1_公告结构化.py", label="看公告被抽取成了什么", icon=":material/description:")
g4.page_link("pages/5_上下游情景.py", label="模拟一次冲击", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- maintenance (folded)
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
