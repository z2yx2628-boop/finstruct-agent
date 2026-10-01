"""Display of 问一句: the answer block (shared by the full page and the floating dialog) and the floating button.

The floating button is a normal Streamlit button inside a keyed container; CSS pins it to the lower right of every
page, and a small script (st.html with JavaScript enabled; our own code, no user input) makes it draggable and remembers where it was
left. If the script cannot run, the button still works where CSS put it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ask import EXAMPLES, ask, model_available
from src.network_view import NATURE_COLOR
from src.ui import open_profile, open_unified, public_mode, verdict

MAX_MODEL_CALLS = 20       # per session on the public site

FAB_CSS = """
<style>
.st-key-ask_fab {position: fixed !important; right: 28px; bottom: 28px; z-index: 999990; width: auto !important;
                 touch-action: none; cursor: grab;}
.st-key-ask_fab.dragging {cursor: grabbing;}
.st-key-ask_fab button {width: 60px; height: 60px; min-height: 60px; border-radius: 50% !important; padding: 0;
                        box-shadow: 0 6px 18px rgba(0,0,0,.25); font-size: 26px; line-height: 1;}
.st-key-ask_fab button p {font-size: 26px;}
.st-key-ask_fab_assets {position: absolute !important; height: 0 !important; overflow: hidden; margin: 0 !important;}
</style>
"""

FAB_JS = """
<script>
(function () {
  if (window.__chainproofFab) return;          // the script is re-inserted on every rerun; set up once
  window.__chainproofFab = true;
  const doc = document, KEY = "chainproof_fab_pos";
  function place(el) {
    try {
      const p = JSON.parse(window.localStorage.getItem(KEY) || "null");
      if (p) { el.style.left = Math.min(p.x, window.innerWidth - 70) + "px";
               el.style.top = Math.min(p.y, window.innerHeight - 70) + "px";
               el.style.right = "auto"; el.style.bottom = "auto"; }
    } catch (e) {}
  }
  function attach(el) {
    if (el.dataset.drag) return;
    el.dataset.drag = "1"; place(el);
    let sx, sy, ox, oy, moved = false, down = false;
    el.addEventListener("pointerdown", function (e) {
      down = true; moved = false; sx = e.clientX; sy = e.clientY;
      const r = el.getBoundingClientRect(); ox = r.left; oy = r.top;
    });
    doc.addEventListener("pointermove", function (e) {
      if (!down) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 6) return;
      moved = true; el.classList.add("dragging");
      const x = Math.max(4, Math.min(window.innerWidth - 66, ox + dx));
      const y = Math.max(4, Math.min(window.innerHeight - 66, oy + dy));
      el.style.left = x + "px"; el.style.top = y + "px"; el.style.right = "auto"; el.style.bottom = "auto";
    });
    doc.addEventListener("pointerup", function () {
      if (!down) return; down = false; el.classList.remove("dragging");
      if (moved) {
        try { const r = el.getBoundingClientRect();
              window.localStorage.setItem(KEY, JSON.stringify({x: r.left, y: r.top})); } catch (e) {}
        // a drag must not also count as a click
        el.addEventListener("click", function stop(ev) { ev.stopPropagation(); ev.preventDefault();
                                                         el.removeEventListener("click", stop, true); }, true);
      }
    });
  }
  function scan() { const el = doc.querySelector(".st-key-ask_fab"); if (el) attach(el); }
  scan();
  new MutationObserver(scan).observe(doc.body, {childList: true, subtree: true});
})();
</script>
"""


def run_question(question: str) -> dict:
    calls = st.session_state.get("_ask_model_calls", 0)
    use_model = model_available() and (not public_mode() or calls < MAX_MODEL_CALLS)
    result = ask(question, use_model=use_model)
    if any(s["kind"] == "model" for s in result["trace"]):
        st.session_state["_ask_model_calls"] = calls + 1
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


def ask_box(key: str) -> None:
    """Example pills + question box + answer. Used on the page and in the dialog (different keys)."""
    qkey, pkey, last = f"{key}_q", f"{key}_example", f"_{key}_last_pick"
    if qkey not in st.session_state:
        st.session_state[qkey] = ""
    picked = st.pills("试试这些问题", EXAMPLES, key=pkey)
    if picked and picked != st.session_state.get(last):
        st.session_state[qkey] = picked
        st.session_state[last] = picked
    question = st.text_input("你的问题", key=qkey, placeholder="例如：凌钢股份出事会传给谁？")
    if question.strip():
        with st.spinner("正在选择工具并计算 …"):
            result = run_question(question)
        render_result(result, key)


@st.dialog("问一句", width="large")
def ask_dialog() -> None:
    st.caption("用一句话提问：系统选一个工具作答，并给出调用轨迹。答案只来自公告与财务数据，超出范围的问题会直接说明。")
    ask_box("fab")


def floating_button() -> None:
    """Call once per run (app.py) so it appears on every page."""
    with st.container(key="ask_fab_assets"):           # style + drag script, taking no space on the page
        st.html(FAB_CSS)
        st.html(FAB_JS, unsafe_allow_javascript=True)
    with st.container(key="ask_fab"):
        if st.button("💬", key="ask_fab_btn", help="问一句：用一句话提问（可拖动）"):
            ask_dialog()
