"""Display of 问一句: the answer block (shared by the full page and the floating dialog) and the floating button.

The floating button is a normal Streamlit button inside a keyed container; CSS pins it to the lower right of every
page, and a small script (st.html with JavaScript enabled; our own code, no user input) makes it draggable and remembers where it was
left. If the script cannot run, the button still works where CSS put it."""
from __future__ import annotations

import zlib

import pandas as pd
import streamlit as st

from src.ask import EXAMPLES, ask, model_available
from src.network_view import NATURE_COLOR
from src.ui import open_profile, open_unified, public_mode, verdict

MAX_MODEL_CALLS = 20       # per session on the public site

FAB_CSS = """
<style>
.st-key-ask_fab {position: fixed !important; right: 28px; bottom: 28px; z-index: 90; width: auto !important;
                 touch-action: none; cursor: grab;}
.st-key-ask_fab.dragging {cursor: grabbing;}
.st-key-ask_fab button {width: 56px; height: 56px; min-height: 56px; border-radius: 50% !important; padding: 0;
                        box-shadow: 0 8px 24px rgba(198,63,69,.35); transition: transform .15s, box-shadow .15s;}
.st-key-ask_fab button:hover {transform: scale(1.06); box-shadow: 0 10px 28px rgba(198,63,69,.45);}
.st-key-ask_fab button [data-testid="stIconMaterial"] {font-size: 26px;}
.st-key-ask_fab_assets {position: absolute !important; height: 0 !important; overflow: hidden; margin: 0 !important;}
</style>
"""

FAB_JS = """
<script>
(function () {
  if (window.__chainproofFab) return;          // the script is re-inserted on every rerun; set up once
  window.__chainproofFab = true;
  const doc = document, KEY = "chainproof_fab_pos_v2", SIZE = 60, EDGE = 20;
  // the button may not go above the top bar and the search bar (it would cover the menus)
  function minTop() {
    let y = 70;
    const head = doc.querySelector('header[data-testid="stHeader"]');
    if (head) y = Math.max(y, head.getBoundingClientRect().bottom);
    const bar = doc.querySelector(".st-key-cmd_bar");
    if (bar) { const r = bar.getBoundingClientRect(); if (r.bottom > 0) y = Math.max(y, r.bottom); }
    return y + 12;
  }
  function clampY(y) { return Math.max(minTop(), Math.min(window.innerHeight - SIZE - EDGE, y)); }
  function sideX(x) { return (x + SIZE / 2 < window.innerWidth / 2) ? EDGE : window.innerWidth - SIZE - EDGE; }
  function put(el, x, y) { el.style.left = x + "px"; el.style.top = y + "px"; el.style.right = "auto"; el.style.bottom = "auto"; }
  function reset(el) {
    try { window.localStorage.removeItem(KEY); } catch (e) {}
    el.style.left = el.style.top = el.style.right = el.style.bottom = "";
  }
  function place(el) {
    try {
      const p = JSON.parse(window.localStorage.getItem(KEY) || "null");
      if (p) put(el, p.side === "left" ? EDGE : window.innerWidth - SIZE - EDGE, clampY(p.y));
    } catch (e) {}
  }
  function swallowNextClick(el) {
    el.addEventListener("click", function stop(ev) { ev.stopPropagation(); ev.preventDefault();
                                                     el.removeEventListener("click", stop, true); }, true);
  }
  function attach(el) {
    if (el.dataset.drag) return;
    el.dataset.drag = "1"; place(el);
    let sx, sy, ox, oy, moved = false, down = false, timer = null, wasReset = false;
    el.addEventListener("pointerdown", function (e) {
      down = true; moved = false; wasReset = false; sx = e.clientX; sy = e.clientY;
      const r = el.getBoundingClientRect(); ox = r.left; oy = r.top;
      timer = setTimeout(function () { if (down && !moved) { wasReset = true; reset(el); } }, 800);  // long press
    });
    doc.addEventListener("pointermove", function (e) {
      if (!down) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 6) return;
      moved = true; clearTimeout(timer); el.classList.add("dragging");
      put(el, Math.max(4, Math.min(window.innerWidth - SIZE - 4, ox + dx)), clampY(oy + dy));
    });
    doc.addEventListener("pointerup", function () {
      if (!down) return; down = false; clearTimeout(timer); el.classList.remove("dragging");
      if (moved) {                               // snap to the nearer side and remember it
        const r = el.getBoundingClientRect(), x = sideX(r.left), y = clampY(r.top);
        el.style.transition = "left .18s ease-out"; put(el, x, y);
        setTimeout(function () { el.style.transition = ""; }, 200);
        try { window.localStorage.setItem(KEY, JSON.stringify({side: x === EDGE ? "left" : "right", y: y})); } catch (e) {}
      }
      if (moved || wasReset) swallowNextClick(el);   // a drag or a reset must not also open the dialog
    });
    window.addEventListener("resize", function () { if (el.style.top) place(el); });
  }
  function scan() { const el = doc.querySelector(".st-key-ask_fab"); if (el) attach(el); }
  scan();
  new MutationObserver(scan).observe(doc.body, {childList: true, subtree: true});
})();
</script>
"""


HISTORY_MAX = 12


def remember(question: str, result: dict) -> None:
    """One question list for the dialog, the search bar and the full page (newest first, no repeats)."""
    history = [h for h in st.session_state.get("_ask_history", []) if h["q"] != question]
    st.session_state["_ask_history"] = [{"q": question, "label": result["label"]}] + history[:HISTORY_MAX - 1]


def company_name(code: str | None) -> str | None:
    from src.ask import name_index
    return next((n for _, c, n in name_index() if c == code), None) if code else None


def context_examples(page_title: str | None) -> tuple[str, list[str]]:
    """Example questions for the page the user is on: the open company first, otherwise the page's topic."""
    if page_title == "企业档案":
        name = company_name(st.session_state.get("pf_code"))
    elif page_title == "风险传导":
        name = company_name(st.session_state.get("u_company"))
    else:
        name = None
    if name:
        return f"关于{name}", [f"{name}现在风险怎么样？", f"{name}出现风险会波及哪些企业？",
                               f"哪些企业的风险会传到{name}？", f"{name}在核心钢厂里排第几？"]
    if page_title and page_title.startswith("市场冲击"):
        return "关于市场冲击", ["铁矿石涨 20% 谁受影响最大？", "出口关税提高 10% 对谁影响大？", "螺纹钢跌 10% 谁受影响最大？"]
    if page_title == "可信度":
        return "关于可信度", ["这个系统准不准？", "承压最弱的钢厂有哪些？"]
    return "试试这些问题", EXAMPLES


def run_question(question: str) -> dict:
    calls = st.session_state.get("_ask_model_calls", 0)
    use_model = model_available() and (not public_mode() or calls < MAX_MODEL_CALLS)
    result = ask(question, use_model=use_model)
    if any(s["kind"] == "model" for s in result["trace"]):
        st.session_state["_ask_model_calls"] = calls + 1
    remember(question, result)
    return result


def render_result(result: dict, key: str) -> None:
    head = f"**问题类型：{result['label']}**"
    for nature in filter(None, (n.strip() for n in result["nature"].split("/"))):
        head += f"　:{NATURE_COLOR.get(nature, 'gray')}-badge[{nature}]"
    st.markdown(head + f"　·　数据截至 {result['snapshot']}")
    verdict(*result["verdict"])
    for caption, rows in result["tables"]:
        if rows:
            st.markdown(f"**{caption}**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if result["note"]:
        st.caption(result["note"])
    if result.get("goto"):
        page, label, code = result["goto"]
        if st.button(label, icon=":material/arrow_forward:", key=f"{key}_goto"):
            if code and page.endswith("7_企业档案.py"):
                open_profile(code)
            elif code and page.endswith("8_风险传导总图.py"):
                open_unified(code)
            st.switch_page(page)
    with st.expander("智能体调用轨迹（每一步用了什么工具、得到什么）", icon=":material/route:"):
        trace = pd.DataFrame([{"步骤": s["step"], "工具": s["tool"], "类型": s["kind"], "结果": s["output"],
                               "理由": s["reason"], "耗时(ms)": s["ms"]} for s in result["trace"]])
        st.dataframe(trace, hide_index=True, use_container_width=True)
        route = result["route"]
        move = "无" if route["move"] is None else format(route["move"], "+.0%")
        companies = "、".join(route["companies"]) or "无"
        st.caption(f"路由方式：{route['by']}；识别到的企业：{companies}；产品：{route['product'] or '无'}；幅度：{move}")


def _pills(label: str, options: list[str], qkey: str, pkey: str) -> None:
    pkey = f"{pkey}_{zlib.crc32('|'.join(options).encode()):x}"   # new options (other page, longer history) -> new widget
    last = f"_{pkey}_last_pick"
    picked = st.pills(label, options, key=pkey)
    if picked and picked != st.session_state.get(last):
        st.session_state[qkey] = picked
        st.session_state[last] = picked


def ask_box(key: str, examples: tuple[str, list[str]] | None = None, history: bool = False) -> str:
    """Example pills (+ this session's earlier questions) + question box + answer.
    Used on the full page and in the dialog (different keys). Returns the question."""
    qkey = f"{key}_q"
    if qkey not in st.session_state:
        st.session_state[qkey] = ""
    label, options = examples or ("试试这些问题", EXAMPLES)
    _pills(label, options, qkey, f"{key}_example")
    asked = [h["q"] for h in st.session_state.get("_ask_history", [])]
    if history and asked:
        _pills(f"本次问过（{len(asked)}）", asked, qkey, f"{key}_history")
    question = st.text_input("你的问题", key=qkey, placeholder="例如：凌钢股份出现风险会波及哪些企业？")
    if question.strip():
        with st.spinner("正在选择工具并计算 …"):
            result = run_question(question)
        render_result(result, key)
    return question


@st.dialog("问一句", width="large")
def ask_dialog() -> None:
    st.caption("用一句话提问：系统选一个工具作答，并给出调用轨迹。答案只来自公告与财务数据，超出范围的问题会直接说明。")
    question = ask_box("fab", st.session_state.get("_fab_examples"))
    if st.button("全屏继续", icon=":material/open_in_full:", key="fab_full",
                 help="带着这个问题到「问一句（全屏）」，可连续提问并查看本次问过的问题"):
        st.session_state["ask_q"] = question
        st.switch_page("views/9_问一句.py")


def open_dialog(question: str = "", page_title: str | None = None) -> None:
    """Open the dialog on the current page; with a question it is answered right away (used by the search bar)."""
    st.session_state["_fab_examples"] = context_examples(page_title or st.session_state.get("_page_title"))
    st.session_state["fab_q"] = question
    ask_dialog()


def floating_button(page_title: str | None = None) -> None:
    """Call once per run (app.py) so it appears on every page; page_title lets the examples follow the page."""
    st.session_state["_page_title"] = page_title
    with st.container(key="ask_fab_assets"):           # style + drag script, taking no space on the page
        st.html(FAB_CSS)
        st.html(FAB_JS, unsafe_allow_javascript=True)
    with st.container(key="ask_fab"):
        if st.button("", icon=":material/forum:", type="primary", key="ask_fab_btn", help="问一句：就地提问（可拖动；长按复位到右下角）"):
            open_dialog(st.session_state.get("fab_q", ""), page_title)
