import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from src.document_parser import PARSERS
from src.pipeline import run_pipeline
from src.tasks import get_task, task_names


PROJECT_ROOT = Path(__file__).resolve().parent
UPLOAD_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "uploads"
APP_SCHEMA_VERSION = 2

EVENT_LABELS = {
    "pledge": "新增质押",
    "release": "解除质押",
    "extension": "质押展期",
}

SHARE_UNIT_MULTIPLIERS = {
    "股": 1,
    "万股": 10_000,
}


def boolean_label(value: bool | None) -> str | None:
    if value is None:
        return None
    return "是" if value else "否"


def event_rows(document) -> list[dict]:
    return [
        {
            "事件类型": EVENT_LABELS[event.event_type],
            "股东名称": event.shareholder_name,
            "涉及数量": event.shares,
            "单位": event.shares_unit,
            "质押开始日": event.pledge_start_date,
            "质押到期日": event.pledge_end_date,
            "到期条件": event.pledge_end_condition,
            "解除日期": event.release_date,
            "原到期日": event.original_end_date,
            "展期后到期日": event.extended_end_date,
            "质权人": event.pledgee,
            "占其持股比例(%)": event.shareholder_holding_ratio,
            "占总股本比例(%)": event.total_share_capital_ratio,
            "是否限售股": boolean_label(event.is_restricted_share),
            "是否补充质押": boolean_label(event.is_supplementary_pledge),
            "资金用途": event.purpose,
            "来源页": event.source_page,
            "置信度": event.confidence,
        }
        for event in document.events
    ]


def share_change_summary(document) -> dict:
    totals = {"pledge": 0.0, "release": 0.0}
    unsupported_units = 0

    for event in document.events:
        if event.event_type not in totals:
            continue
        multiplier = SHARE_UNIT_MULTIPLIERS.get(event.shares_unit)
        if multiplier is None:
            unsupported_units += 1
            continue
        totals[event.event_type] += event.shares * multiplier

    return {
        "pledged_shares": totals["pledge"],
        "released_shares": totals["release"],
        "net_change": totals["pledge"] - totals["release"],
        "unsupported_units": unsupported_units,
    }


def format_shares(value: float) -> str:
    return f"{value:,.0f}"


st.set_page_config(
    page_title="FinStruct Agent",
    page_icon="📄",
    layout="wide",
)

if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.pop("pipeline_result", None)
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

st.title("FinStruct Agent")
st.caption("钢铁产业链公告结构化提取：股份质押、产能事件；支持文字PDF、扫描PDF、图片和网页")

task_name = st.selectbox(
    "公告类型",
    options=list(task_names()),
    format_func=lambda name: get_task(name).label,
)

uploaded_file = st.file_uploader(
    "选择公告文件（文字PDF、扫描PDF或图片）",
    type=[suffix.lstrip(".") for suffix in sorted(PARSERS)],
    accept_multiple_files=False,
)

page_url = st.text_input(
    "或输入网页地址（新闻、互动平台问答、政府公告等）",
    placeholder="https://",
).strip()

run_clicked = st.button(
    "运行提取",
    type="primary",
    disabled=uploaded_file is None and not page_url,
    width="stretch",
)

if run_clicked and uploaded_file is None and page_url:
    try:
        from scripts.fetch_webpage import fetch

        with st.spinner("正在抓取网页并提取结构化数据..."):
            stored_path = fetch(
                page_url,
                PROJECT_ROOT / "data" / "raw" / "web",
                f"web_{uuid.uuid4().hex[:8]}",
            )
            st.session_state["pipeline_result"] = run_pipeline(
                stored_path, task=task_name,
            )
            st.session_state["uploaded_name"] = page_url
    except Exception as error:
        st.error(f"处理失败：{error}")

if run_clicked and uploaded_file is not None:
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

    safe_name = Path(uploaded_file.name).name
    stored_path = (
        UPLOAD_DIRECTORY
        / f"{Path(safe_name).stem}_{uuid.uuid4().hex[:8]}"
        f"{Path(safe_name).suffix.lower()}"
    )
    stored_path.write_bytes(uploaded_file.getvalue())

    try:
        with st.spinner("正在解析公告并提取结构化数据..."):
            st.session_state["pipeline_result"] = run_pipeline(
                stored_path, task=task_name,
            )
            st.session_state["uploaded_name"] = safe_name
    except Exception as error:
        st.error(f"处理失败：{error}")

CAPACITY_EVENT_LABELS = {
    "capacity_construction": "产能建设",
    "capacity_replacement": "产能置换",
    "technical_upgrade": "技术改造",
    "commissioning": "投产",
    "delay": "延期",
    "suspension": "暂停",
    "termination": "终止",
    "maintenance": "检修/临时停产",
    "guarantee_provided": "提供担保",
    "guarantee_limit": "担保额度",
    "guarantee_released": "担保解除",
    "guarantee_overdue": "逾期担保",
}


def show_ocr_notice(log: dict) -> None:
    parsing = next(
        (step for step in log["steps"] if step["name"] == "document_parsing"),
        {},
    )
    if parsing.get("ocr_pages"):
        st.info(
            f"第 {parsing['ocr_pages']} 页通过 OCR 识别"
            f"（{parsing.get('ocr_engine') or 'OCR'}）。"
        )
    if parsing.get("ocr_low_confidence_pages"):
        st.warning(
            f"第 {parsing['ocr_low_confidence_pages']} 页 OCR 置信度较低，"
            "请对照原文核对数字。"
        )


def show_generic_result(result: dict) -> None:
    """Result view for every non-pledge task."""
    document = result["document"]
    evidence_report = result["evidence_report"]
    if result["status"] == "success":
        st.success("处理完成，证据检查通过。")
    else:
        st.warning("处理完成，但存在需要人工复核的字段。")
    show_ocr_notice(result["log"])

    first, second, third, fourth = st.columns(4)
    first.metric("证券代码", document.security_code or "-")
    second.metric("证券简称", document.security_name or "-")
    third.metric("公告编号", document.announcement_number or "-")
    fourth.metric("事件记录", len(document.events))

    events = [event.model_dump() for event in document.events]
    event_frame = pd.DataFrame([
        {
            "事件类型": CAPACITY_EVENT_LABELS.get(item.get("event_type"), item.get("event_type")),
            **{
                key: value for key, value in item.items()
                if key not in {"capacity_changes", "environmental_metrics", "event_type"}
            },
        }
        for item in events
    ])
    capacity_frame = pd.DataFrame([
        {"事件序号": index, **record}
        for index, item in enumerate(events, start=1)
        for record in item.get("capacity_changes", [])
    ])

    result_tab, evidence_tab, log_tab = st.tabs(
        ["结构化结果", "证据检查", "运行日志"]
    )
    with result_tab:
        if event_frame.empty:
            st.info("公告中未提取到相关事件。")
        else:
            st.dataframe(event_frame, width="stretch", hide_index=True)
        if not capacity_frame.empty:
            st.subheader("产能变化")
            st.dataframe(capacity_frame, width="stretch", hide_index=True)
        st.download_button(
            "下载JSON",
            data=document.model_dump_json(indent=2),
            file_name=f"{result['log']['task']}_prediction.json",
            mime="application/json",
            width="stretch",
        )
    with evidence_tab:
        if evidence_report.get("passed"):
            st.success("证据检查通过。")
        else:
            st.error("发现需要复核的证据问题。")
            st.dataframe(
                evidence_report.get("issues", []),
                width="stretch",
                hide_index=True,
            )
        for index, event in enumerate(document.events, start=1):
            with st.expander(
                f"事件 {index} · "
                f"{CAPACITY_EVENT_LABELS.get(event.event_type, event.event_type)}"
                f" · 第{event.source_page}页"
            ):
                st.code(event.evidence_text or "无证据文本")
    with log_tab:
        st.json(result["log"])


result = st.session_state.get("pipeline_result")

if result and result["log"].get("task", "pledge") != "pledge":
    show_generic_result(result)
elif result:
    show_ocr_notice(result["log"])
    document = result["document"]
    evidence_report = result["evidence_report"]
    rows = event_rows(document)
    frame = pd.DataFrame(rows)
    event_counts = evidence_report["event_counts"]
    share_summary = share_change_summary(document)

    if result["status"] == "success":
        st.success("处理完成，字段证据与事件类型覆盖检查均已通过。")
    else:
        st.warning("处理完成，但存在字段或事件类型需要人工复核。")

    first, second, third, fourth = st.columns(4)
    first.metric("证券代码", document.security_code or "-")
    second.metric("证券简称", document.security_name or "-")
    third.metric("公告编号", document.announcement_number or "-")
    fourth.metric("事件记录", len(document.events))

    pledged, released, net_change, extensions = st.columns(4)
    pledged.metric(
        "新增质押（股）",
        format_shares(share_summary["pledged_shares"]),
    )
    released.metric(
        "解除质押（股）",
        format_shares(share_summary["released_shares"]),
    )
    net_change.metric(
        "净变化（股）",
        format_shares(share_summary["net_change"]),
    )
    extensions.metric("展期事件", event_counts["extension"])

    if share_summary["unsupported_units"]:
        st.caption("存在无法换算为股的单位，汇总数未包含对应事件。")

    result_tab, evidence_tab, log_tab = st.tabs(
        ["结构化结果", "证据检查", "运行日志"]
    )

    with result_tab:
        if frame.empty:
            st.info("公告中未提取到股份质押相关事件。")
        else:
            st.dataframe(frame, width="stretch", hide_index=True)

        json_data = document.model_dump_json(indent=2)
        csv_data = frame.to_csv(index=False).encode("utf-8-sig")

        json_column, csv_column = st.columns(2)
        json_column.download_button(
            "下载JSON",
            data=json_data,
            file_name="pledge_prediction.json",
            mime="application/json",
            width="stretch",
        )
        csv_column.download_button(
            "下载CSV",
            data=csv_data,
            file_name="pledge_events.csv",
            mime="text/csv",
            width="stretch",
        )

    with evidence_tab:
        expected_labels = [
            EVENT_LABELS[item]
            for item in evidence_report["expected_event_types"]
        ]
        extracted_labels = [
            EVENT_LABELS[item]
            for item in evidence_report["extracted_event_types"]
        ]
        st.caption(
            f"原文识别到的事件类型："
            f"{', '.join(expected_labels) or '未识别'}；"
            f"输出事件类型：{', '.join(extracted_labels) or '无'}"
        )

        if evidence_report["passed"]:
            st.success(
                f"证据与事件类型检查通过："
                f"{evidence_report['passed_checks']}/"
                f"{evidence_report['checks_count']}"
            )
        else:
            st.error("发现证据不一致、必填字段缺失或事件类型遗漏。")
            st.dataframe(
                evidence_report["issues"],
                width="stretch",
                hide_index=True,
            )

        for index, event in enumerate(document.events, start=1):
            event_label = EVENT_LABELS[event.event_type]
            with st.expander(
                f"事件 {index} · {event_label} · 第{event.source_page}页"
            ):
                st.code(event.evidence_text or "无证据文本")

    with log_tab:
        st.dataframe(
            result["log"]["steps"],
            width="stretch",
            hide_index=True,
        )
        st.json(result["log"])
