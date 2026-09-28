"""今日看板：今天有什么风险、数据有多新、这个系统有多可信（首页）。"""
import csv
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fragility_view import snapshot_meta  # noqa: E402
from src.price_shock import THRESHOLD, WINDOW, price_moves  # noqa: E402
from src.ui import page_header  # noqa: E402

page_header("钢铁产业链风险传导预警", ":material/dashboard:", "今天有什么风险？这个系统凭什么可信？", grades=True)
st.caption("公告事实 → 企业承压 → 风险传导 · 每一步可追溯到公告原文")


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


snaps = sorted(p for p in (ROOT / "data" / "snapshots").glob("2026-*") if (p / "fragility.csv").exists())
live = [p for p in snaps if snapshot_meta(p).get("version") == "v1"]
now = read(live[-1] / "fragility.csv") if live else []
before = {r["security_code"]: r for r in read(live[-2] / "fragility.csv")} if len(live) > 1 else {}

# ---------------------------------------------------------------- today
st.subheader("今日风险", divider="gray")
weak = [r for r in now if r["tier"] == "weak"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("承压为弱的企业", len(weak),
          delta=(len(weak) - sum(1 for r in before.values() if r["tier"] == "weak")) if before else None, delta_color="inverse")
paths = sorted(ROOT.joinpath("data", "chain", "live").glob("key_paths_*.csv"))
key_now = read(paths[-1]) if paths else []
key_before = {r["path"] for r in read(paths[-2])} if len(paths) > 1 else set()
m2.metric("关键风险路径", sum(1 for r in key_now if float(r["score"]) > 0),
          delta=sum(1 for r in key_now if r["path"] not in key_before and float(r["score"]) > 0) if key_before else None,
          delta_color="inverse", help="delta = 与上一期相比新增的路径数")
moves = price_moves(live[-1].name if live else "9999-12-31")
shocks = [m for m in moves if m["shock"]]
m3.metric(f"产品价格冲击（{WINDOW} 日 ±{THRESHOLD:.0%}）", len(shocks))
reports = sorted((ROOT / "data" / "live").glob("report_*.md"))
m4.metric("最新日报", reports[-1].stem[7:] if reports else "—")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**承压为弱的企业**")
    if weak:
        for r in sorted(weak, key=lambda r: -float(r["total_score"] or 0)):
            change = "（新进入）" if before and before.get(r["security_code"], {}).get("tier") != "weak" else ""
            st.markdown(f"- 🔴 **{r['security_name']}** {r['total_score']} 分{change}：{r['reasons'][:60]}…")
    else:
        st.caption("无。")
    st.page_link("pages/2_承压评分.py", label="查看全部企业的评分与来源", icon=":material/monitoring:")
with c2:
    st.markdown("**得分最高的关键风险路径**（公告披露的关系，A/B 级）")
    for r in [r for r in key_now if float(r["score"]) > 0][:3]:
        new = "（新增）" if key_before and r["path"] not in key_before else ""
        st.markdown(f"- {r['path']}{new} · 得分 {r['score']}")
    st.page_link("pages/4_风险路径图.py", label="打开关联与担保传导图", icon=":material/account_tree:")
    st.markdown("**产品价格**（近 20 个交易日）")
    st.caption("；".join(f"{'**' if m['shock'] else ''}{m['product']} {m['ret']:+.1%}{'**' if m['shock'] else ''}" for m in moves)
               or "无价格数据")
    st.page_link("pages/5_上下游情景.py", label="用上下游情景看一次冲击会波及谁", icon=":material/swap_horiz:")

# ---------------------------------------------------------------- trust
st.subheader("凭什么可信", divider="gray")
summary = ROOT / "experiments" / "final_test" / "summary.json"
final = json.loads(summary.read_text(encoding="utf-8"))["aggregate"]["related_party"] if summary.exists() else None
t1, t2, t3, t4 = st.columns(4)
t1.metric("公告抽取·最终盲测", f"{final['f1']['mean']:.1%}" if final else "—",
          help="关联交易 7 份 × 3 次，记录级 F1；冻结系统、Gold 在运行前锁定（AI 预标注、人工抽查 53/178）。修复单位缺陷后（非盲）为 92.15%")
t2.metric("财务数据·年报抽查", "30 / 30", help="6 家企业 × 5 个科目，与年报原文逐位一致")
t3.metric("风险传导·预注册回测", "3 个案例", help="安泰（标准 1、3 通过，2 部分通过）、凌钢（2、3 通过，1 部分通过）、方大（全部通过，无误报）")
t4.metric("上下游产品层·预注册检验", "2 次未显著", help="利润检验未通过；股价检验方向一致但 p = 0.28。因此只作情景提示")
st.page_link("pages/6_验证与证据.py", label="查看全部验证结果（包括没通过的）", icon=":material/verified:")

st.subheader("从这里开始", divider="gray")
g1, g2, g3 = st.columns(3)
g1.page_link("pages/3_一键分析.py", label="上传一份新公告，生成风险预警", icon=":material/upload_file:")
g2.page_link("pages/1_公告结构化.py", label="看公告被抽取成了什么", icon=":material/description:")
g3.page_link("pages/5_上下游情景.py", label="模拟一次价格或停产冲击", icon=":material/swap_horiz:")
