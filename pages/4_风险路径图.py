"""风险路径图：全产业链的关键传导路径，节点按承压等级着色，边附公告证据。"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.network_view import (SCOPE_LABEL, edge_index, path_scope, step_scope, DECISION_LABEL, GRADE_HELP, GRADE_LABEL, RULE_LABEL, evidence_grade, path_grade, SEVERITY_LABEL, TIER_LABEL, edge_windows,  # noqa: E402
                              evidence_ref, filter_paths, focus_entries, key_paths, name_of, page_png,
                              overview_chart, overview_layout, path_rows, route, score_parts, source_file,
                              snapshot_equity, stop_reason, to_dot)
from src.sources import readable, titles  # noqa: E402

CHAIN_LABEL = {"data/chain/live": "实时图谱（每日更新）", "data/chain/analysis_v1": "真实图谱（84份公告，2024–2026）",
               "data/chain/backtest_antai": "回测图谱（安泰，评估日 2025-01-31）",
               "data/chain/backtest_linggang": "回测图谱（凌钢，评估日 2024-04-30）", "data/chain/gold_demo": "演示图谱（仅开发用）",
               "data/chain/backtest_antai_fix1": "回测图谱·修复后（安泰，2025-01-31）",
               "data/chain/backtest_linggang_fix1": "回测图谱·修复后（凌钢，2024-04-30）",
               "data/chain/analysis_v1_fix1": "真实图谱·修复后（方大回测用 2025-02-28）"}

import pandas as pd  # noqa: E402

from src.ui import page_header, profile_button  # noqa: E402
page_header("信用通道明细", ":material/account_tree:", "风险会沿公告披露的关联交易、担保和集团关系传给谁？", grades=True,
            about="**范围：公告披露的关系网络（A 级）**，包括**集团内**（子公司、控股股东、同一控制下企业）和"
                  "**跨集团关联方**（联营/合营企业、其他关联方，例如关联方焦化厂、贸易商向钢厂供焦炭和铁矿石）。"
                  "没有股权或人事关系的普通客户和供应商，公告不披露名字，只能在“供需情景通道”里按产品暴露（B 级）或行业（C 级）推断，"
                  "那部分不计入得分；这里的“显示 C 级情景路径”默认关闭。  \n"
                  "**怎么用：** 总图上点企业 = 只看经过它的路径；点连线上的金额 = 打开那条路径；也可以在清单里点一行。"
                  "下方依次是路径详情（怎么传、为什么停、得分怎么来）和每一步的公告原文。  \n"
                  "**得分** = 起点严重度 × 金额系数 × 途经上市公司承压（弱 1、中 0.5、强 0）。")

chains = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "data" / "chain").glob("*") if (p / "edges.csv").exists())
snaps = sorted((p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists()), reverse=True)
DEMOS = [("今日实时", "data/chain/live", None), ("安泰回测", "data/chain/backtest_antai_fix1", "2025-01-31"),
         ("凌钢回测", "data/chain/backtest_linggang_fix1", "2024-04-30"), ("方大回测", "data/chain/analysis_v1_fix1", "2025-02-28")]


def reset_focus() -> None:
    st.session_state["company_pick"] = None
    st.session_state["_focus_rank"] = None
    for k in ("_seen_company", "_seen_link"):
        st.session_state[k] = st.session_state.get(k.replace("_seen", "_now"))


def use_demo(chain_name: str, snap_name: str | None) -> None:
    st.session_state["chain_pick"] = chain_name
    st.session_state["snap_pick"] = snap_name or snaps[0]
    reset_focus()


chains = [c for c in chains if c != "data/chain/gold_demo"]            # test answers: development only
goto = st.session_state.pop("_goto_network", None)                   # arriving from 企业档案
if goto and goto["chain"] in chains and goto["snapshot"] in snaps:
    use_demo(goto["chain"], goto["snapshot"])
    st.session_state["company_pick"] = goto["company"]
default = next((c for c in ("data/chain/live", "data/chain/analysis_v1") if c in chains), chains[0])
if st.session_state.get("chain_pick") not in chains:
    st.session_state["chain_pick"] = default
if st.session_state.get("snap_pick") not in snaps:
    st.session_state["snap_pick"] = snaps[0]

demo_cols = st.columns([1] + [1.2] * len(DEMOS) + [2.5], vertical_alignment="center")
demo_cols[0].caption("演示场景")
for col, (label, chain_name, snap_name) in zip(demo_cols[1:], DEMOS):
    if chain_name in chains and (snap_name is None or snap_name in snaps):
        col.button(label, on_click=use_demo, args=(chain_name, snap_name), width="stretch")
with demo_cols[-1].popover("选择图谱与评估日", icon=":material/tune:"):
    chain = st.selectbox("产业链图谱", chains, key="chain_pick", format_func=lambda c: CHAIN_LABEL.get(c, c))
    snap = st.selectbox("评估日（承压快照）", snaps, key="snap_pick")
st.caption(f"当前：{CHAIN_LABEL.get(chain, chain)} · 评估日 {snap}")
if "backtest_antai" in chain and snap > "2025-02-05":
    st.warning("安泰回测图谱应配合事件发生前的评估日 2025-01-31，否则会用到当时还不存在的信息。")
if "backtest_linggang" in chain and snap not in ("2024-04-30", "2025-04-30"):
    st.warning("凌钢回测图谱的预注册评估日为 2024-04-30（附加检查 2025-04-30）。")
if "analysis" in chain and snap < "2025-02-01":
    st.info("真实图谱的公告多发布于 2025–2026 年；评估日较早时，大部分关系会按日期被过滤掉。")


@st.cache_data(show_spinner="正在推导传导路径…")
def load(chain: str, snap: str):
    ranked, fragility, names = key_paths(ROOT / chain, ROOT / "data" / "snapshots" / snap)
    return ranked, fragility, names, edge_windows(ROOT / chain), edge_index(ROOT / chain)


ranked, fragility, names, windows, eindex = load(chain, snap)
if not ranked:
    st.info("该评估日下没有需要关注的传导路径。")
    st.stop()
companies = sorted({e["seed"] for e in ranked} | {s.dst for e in ranked for s in e["steps"]}, key=lambda n: name_of(n, names))


def picked_from(state_key: str, name: str, field: str):
    """Current click selection of the overview chart (None when nothing is selected)."""
    sel = (st.session_state.get(state_key) or {}).get("selection", {}).get(name) or []
    return sel[0].get(field) if sel else None


# A click on the overview chart is applied once (when it changes), so widgets can still be changed by hand.
chart_key = f"overview_{chain}_{snap}"
st.session_state["_now_company"] = picked_from(chart_key, "company", "node")
st.session_state["_now_link"] = picked_from(chart_key, "link", "edge")
if st.session_state["_now_company"] != st.session_state.get("_seen_company"):
    st.session_state["_seen_company"] = st.session_state["_now_company"]
    if st.session_state["_now_company"] in companies:
        st.session_state["company_pick"] = st.session_state["_now_company"]
        st.session_state["_focus_rank"] = None
link_rank = None
if st.session_state["_now_link"] != st.session_state.get("_seen_link"):
    st.session_state["_seen_link"] = st.session_state["_now_link"]
    link_rank = st.session_state["_now_link"]
if st.session_state.get("company_pick") not in [None] + companies:
    st.session_state["company_pick"] = None

# ---------------------------------------------------------------- filters
f3, f_more, f_profile = st.columns([2.5, 1.2, 1.2], vertical_alignment="bottom")
company = f3.selectbox("只看经过某企业", [None] + companies, key="company_pick",
                       format_func=lambda n: "全部企业" if n is None else name_of(n, names))
with f_more.popover("更多筛选", icon=":material/filter_list:"):
    rule_pick = st.multiselect("传导规则", list(RULE_LABEL), default=list(RULE_LABEL), format_func=RULE_LABEL.get)
    min_amount = st.number_input("最小金额（亿元）", min_value=0.0, value=0.0, step=1.0)
    hide_low = st.toggle("隐藏金额为0的同集团路径", value=True,
                         help="只由“同属一个集团”构成、没有披露金额的路径信息量低；仅隐藏显示，不改变排名。")
    show_c = st.toggle("显示 C 级情景路径", value=False, help=GRADE_HELP["C"])
    scope_pick = st.radio("关系范围", ["全部", "in_group", "cross_group"], horizontal=True,
                          format_func=lambda k: k if k == "全部" else "只看" + SCOPE_LABEL[k],
                          help="跨集团 = 路径中至少一步是联营/合营企业或其他关联方之间的披露交易")
if company and company in fragility:
    with f_profile:
        profile_button(company, f"{name_of(company, names)} 档案", key="net_profile", snapshot=snap, chain=chain,
                       width="stretch")
items = filter_paths(ranked, set(rule_pick), min_amount, company, hide_low, show_scenarios=show_c)
if scope_pick != "全部":
    items = [(i, e) for i, e in items if path_scope(e, eindex) == scope_pick]
if not items:
    if company:
        from src.network_view import EDGE_CN, coverage
        cov = coverage(ROOT / chain, ROOT / "data" / "snapshots" / snap, company)
        who = name_of(company, names)
        why = []
        if not cov["active"] and cov["expired"]:
            why.append(f"它在图谱中的 {len(cov['expired'])} 条披露关系都已过期（最近一份相关公告 {cov['latest']}；"
                       "关联交易预计只在预计年度内有效，担保按合同期限有效），评估日之后还没有抽取到它的新公告。")
        elif not cov["active"]:
            why.append("图谱里还没有它披露的关联交易、担保或资金往来（只知道它属于哪个集团）。")
        if cov["tier"] == "strong":
            why.append("它的抗冲击能力为“强”：风险传到它这里会被吸收，这类路径得分为 0，默认不列出。")
        if cov["active"]:
            why.append(f"它有 {len(cov['active'])} 条仍有效的披露关系，但这些关系附近没有风险源，或金额低于对方净资产的 1%，风险不会沿它们传导。")
        st.info(f"**没有经过{who}的关键传导路径。**  \n" + "  \n".join(f"- {w}" for w in why), icon=":material/info:")
        if cov["active"]:
            st.dataframe(pd.DataFrame([{"关系": EDGE_CN.get(e["edge_type"], e["edge_type"]), "从": e["src_name"], "到": e["dst_name"],
                                        "金额(亿元)": round(float(e["amount_wan"]) / 1e4, 2) if e.get("amount_wan") else None,
                                        "公告日": e.get("announcement_date", ""), "有效至": e.get("valid_to", "")}
                                       for e in cov["active"][:30]]), hide_index=True, width="stretch")
            st.caption("以上是它评估日仍有效的披露关系（最多 30 条）：有关系不等于有风险，只有起点出事时才会沿这些关系传导。")
    else:
        st.info("没有符合筛选条件的路径。")
    st.button("清除选择", on_click=reset_focus)
    st.stop()
ranks = [i for i, _ in items]

# which path is open: an edge click on the chart, else a row click in the list, else the top one
table_key = f"paths_{chain}_{snap}_{'-'.join(sorted(rule_pick))}_{min_amount}_{company}_{hide_low}_{show_c}_{scope_pick}"
rows = (st.session_state.get(table_key) or {}).get("selection", {}).get("rows") or []
row_now = ranks[rows[0]] if rows and rows[0] < len(ranks) else None
if row_now is not None and row_now != st.session_state.get("_seen_row"):
    st.session_state["_focus_rank"] = row_now
st.session_state["_seen_row"] = row_now
if link_rank:
    a, b, rule = link_rank.split("|")
    hit = [i for i, e in items if any((s.src, s.dst, s.rule) == (a, b, rule) for s in e["steps"])]
    if hit:
        st.session_state["_focus_rank"] = hit[0]
focus = st.session_state.get("_focus_rank")
index = focus if focus in ranks else ranks[0]
entry = ranked[index]

# ---------------------------------------------------------------- overview graph
st.subheader("全局风险图", divider="gray")
g1, g2, g3 = st.columns([2, 1, 3])
max_show = g1.slider("总图显示前 N 条", 5, 40, 15, help="按原始排名取前 N 条（在筛选结果内）")
shown = items[:max_show]
if index not in [i for i, _ in shown]:
    shown = shown + [(index, entry)]
g2.write("")
g2.button("清除选择", on_click=reset_focus, width="stretch")
notes = ["从左到右 = 传导方向；粗黑圈 = 风险起点；圆越大，经过的路径越多；线越粗，金额越大；虚线 = 同集团或行业近似（无金额）。"
         "点企业筛选，点金额标签打开该路径，双击空白处取消。"]
if company:
    into = sum(1 for _, e in items if any(s.dst == company for s in e["steps"]))
    notes.insert(0, f"**{name_of(company, names)}**：风险传入 {into} 条，由它传出或经过 {len(items) - into} 条。")
g3.caption("  \n".join(notes))
highlight = index if st.session_state.get("_focus_rank") in ranks else None     # nothing picked yet: show all
nodes_df, edges_df = overview_layout(shown, fragility, names, chosen=highlight)
columns_n = int(max(n["x"] for n in nodes_df)) + 1
rows_n = max(sum(1 for n in nodes_df if n["x"] == x) for x in range(columns_n))
st.vega_lite_chart(overview_chart(nodes_df, edges_df, width=min(1150, max(640, 240 * columns_n)), height=max(300, 95 * rows_n)),
                   on_select="rerun", key=chart_key, width="content")

# ---------------------------------------------------------------- ① list
with st.expander("集团财务公司通道：若财务公司出现兑付问题，哪些上市公司的钱被困住（情景，不计分）", icon=":material/account_balance:"):
    from src.finance_channel import by_finance_company
    _eq = {}
    _qm = ROOT / "data" / "snapshots" / snap / "quarterly_metrics.csv"
    if _qm.exists():
        _eq = {r["security_code"]: float(r["equity"]) for r in pd.read_csv(_qm, dtype=str).fillna("").to_dict("records") if r.get("equity")}
    _groups = by_finance_company(snap, fragility, _eq)
    if not _groups:
        st.caption("评估日前没有收集到财务公司存款披露。")
    for g in _groups:
        st.markdown(f"**{g['finance_company']}**：{len(g['members'])} 家上市公司存款合计 {g['total_yi']:.2f} 亿元")
        st.dataframe(pd.DataFrame([{"企业": m["name"], "承压": {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强"}.get(m["tier"], "未评分"),
                                    "存款(亿元)": round(m["deposit_yi"], 2),
                                    "占净资产": f"{m['deposit_to_equity']:.1%}" if m["deposit_to_equity"] is not None else "—",
                                    "截至": m["period"], "来源": m["source_label"]} for m in g["members"]]),
                     hide_index=True, width="stretch")
    st.caption("来源：各公司的财务公司风险评估报告等披露（A 级，data/reference/finance_company_deposits.csv），按发布日期使用；"
               "部分数字尚未人工对照原文核对。这条通道目前不计入路径得分：钢铁业内还没有可用于回测的财务公司兑付事件。")

st.subheader("关键路径清单", divider="gray")
st.caption(f"共 {len(ranked)} 条关键路径，符合筛选的 {len(items)} 条；“排名”为全部路径中的原始名次。点击一行查看详情。")
st.dataframe(pd.DataFrame(path_rows(items, names, eindex, snapshot_equity(ROOT / "data" / "snapshots" / snap))), hide_index=True, width="stretch",
             on_select="rerun", selection_mode="single-row", key=table_key,
             column_config={"金额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                            "得分": st.column_config.NumberColumn(format="%.2f")})

# ---------------------------------------------------------------- ② 传导过程
st.subheader(f"路径详情 · 第 {index + 1} 名：{route(entry, names)}", divider="gray")
COLOR = {"weak": "#c0392b", "medium": "#b9770e", "strong": "#1e8449", "unknown": "#7f8c8d"}


def chip(node: str, tier: str, seed: bool = False) -> str:
    border = "3px" if seed else "1.5px"
    return (f'<span style="display:inline-block;padding:6px 10px;border-radius:8px;border:{border} solid {COLOR.get(tier, "#7f8c8d")};'
            f'margin:4px 0">{name_of(node, names)}<br><small style="color:{COLOR.get(tier, "#7f8c8d")}">'
            f'{"风险起点 · " if seed else ""}承压{TIER_LABEL.get(tier, "未评分")}</small></span>')


seed_tier = fragility.get(entry["seed"], {}).get("tier") or "unknown"
html = [chip(entry["seed"], seed_tier, seed=True)]
for s in entry["steps"]:
    amount = f" {s.amount_wan / 1e4:.2f}亿" if s.amount_wan else ""
    html.append(f'<span style="display:inline-block;margin:0 8px;text-align:center;font-size:0.85em">'
                f'{RULE_LABEL[s.rule]}{amount} · <b>{evidence_grade(s)}级</b><br>──▶<br>'
                f'<small>{DECISION_LABEL.get(s.decision, s.decision)}</small></span>')
    html.append(chip(s.dst, s.dst_tier))
st.markdown('<div style="line-height:1.4">' + "".join(html) + "</div>", unsafe_allow_html=True)
if entry.get("scenario"):
    st.warning(f"情景路径：含 C 级（行业推断）关系，不是实际交易，得分不计入排名（参考值 {entry.get('scenario_score', 0):.2f}）。")
st.caption(f"起点原因：{entry['reason']}  \n证据等级：{GRADE_LABEL[path_grade(entry)]}（取最弱一步）。"
           "A = 公告披露确认；B = 部分确认；C = 行业推断。")
st.caption(stop_reason(entry, names) + (f"；另有 {entry['alternatives']} 条经不同集团子公司的同类路线" if entry.get("alternatives") else ""))

parts = score_parts(entry)
m1, m2, m3, m4 = st.columns(4)
m1.metric("起点严重度", f"{SEVERITY_LABEL.get(parts['severity'], parts['severity'])}（×{parts['severity_weight']}）")
m2.metric("金额系数", f"×{parts['amount_factor']}", help=f"1 + log10(1 + {parts['amount_yi']:.2f} 亿元)")
m3.metric("途经上市公司承压", f"×{parts['reach']:g}",
          help="；".join(f"{name_of(n, names)} {TIER_LABEL.get(t, t)} {w:g}" for n, t, w in parts["reached"]) or "无")
m4.metric("得分", f"{entry['score']:.2f}", help="起点严重度 × 金额系数 × 途经上市公司承压（弱1、中0.5、强0）")

with st.expander("局部关系图（这条路径及与它相连的其他路径）", expanded=False):
    st.graphviz_chart(to_dot(focus_entries(ranked, index), fragility, names, highlight=0), width="stretch")

# ---------------------------------------------------------------- ③ 证据
st.subheader("每一步的公告依据", divider="gray")
for k, s in enumerate(entry["steps"], 1):
    ref = evidence_ref(s.evidence)
    head = (f"第 {k} 步 · {RULE_LABEL[s.rule]}：{name_of(s.src, names)} → {name_of(s.dst, names)}"
            f" · {SCOPE_LABEL[step_scope(s, eindex)]} · 证据 {GRADE_LABEL[evidence_grade(s)]}")
    with st.expander(head, expanded=(k == 1)):
        if s.rule == "R3":
            st.markdown(f"**依据：** {readable(s.evidence)}")
            st.caption("同集团关系来自企业名称对照表（按评估日生效），不是单份公告披露的交易。")
            continue
        if s.rule == "R4":
            st.markdown(f"**依据：** {readable(s.evidence)}")
            st.caption("行业近似关系：上下游细分行业的依赖度，不是具体企业之间的交易，只用于提示。")
            continue
        st.markdown(f"**公告：** {titles().get(ref['stem'] or '', ref['stem'] or '（未知来源）')}")
        # risk runs against the edge direction for guarantees (guaranteed party -> guarantor): try both
        info = windows.get((s.src, s.dst, ref["stem"] or "")) or windows.get((s.dst, s.src, ref["stem"] or ""), {})
        meta = [f"第 {ref['page']} 页" if ref["page"] else None,
                f"公告日 {info['announcement_date']}" if info.get("announcement_date") else None,
                f"关系有效期 {info.get('valid_from') or '?'} 至 {info.get('valid_to') or '未注明'}" if info else None,
                f"金额 {s.amount_wan / 1e4:.2f} 亿元" if s.amount_wan else None,
                f"依据类型 {s.basis}"]
        st.caption(" · ".join(x for x in meta if x))
        if ref["quote"]:
            st.markdown("> " + ref["quote"][:400].replace("\n", " "))
        src = source_file(ref["stem"])
        if src is None:
            st.caption("原文文件不在本机（仅保留提取结果）。")
            continue
        b1, b2 = st.columns([1, 1])
        show = b1.toggle(f"查看原文第 {ref['page'] or 1} 页", key=f"pg_{index}_{k}") if src.suffix.lower() == ".pdf" else False
        b2.download_button("下载原文", src.read_bytes(), file_name=src.name, key=f"dl_{index}_{k}")
        if show:
            png = page_png(src, ref["page"] or 1)
            if png:
                st.image(png, caption=f"{src.name} 第 {ref['page'] or 1} 页")
            else:
                st.caption("该页无法渲染。")
