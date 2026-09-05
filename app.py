import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from src.pipeline import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
UPLOAD_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "uploads"


def record_rows(document) -> list[dict]:
    return [
        {
            "股东名称": record.shareholder_name,
            "质押数量": record.pledged_shares,
            "单位": record.pledged_shares_unit,
            "质押开始日": record.pledge_start_date,
            "质押到期日": record.pledge_end_date,
            "质权人": record.pledgee,
            "占其持股比例(%)": record.shareholder_holding_ratio,
            "占总股本比例(%)": record.total_share_capital_ratio,
            "资金用途": record.pledge_purpose,
            "来源页": record.source_page,
            "置信度": record.confidence,
        }
        for record in document.records
    ]


st.set_page_config(
    page_title="FinStruct Agent",
    page_icon="📄",
    layout="wide",
)

st.title("FinStruct Agent")
st.caption("A股股份质押公告结构化提取")

uploaded_file = st.file_uploader(
    "选择公告PDF",
    type=["pdf"],
    accept_multiple_files=False,
)

run_clicked = st.button(
    "运行提取",
    type="primary",
    disabled=uploaded_file is None,
    use_container_width=True,
)

if run_clicked and uploaded_file is not None:
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

    safe_name = Path(uploaded_file.name).name
    stored_path = (
        UPLOAD_DIRECTORY
        / f"{Path(safe_name).stem}_{uuid.uuid4().hex[:8]}.pdf"
    )
    stored_path.write_bytes(uploaded_file.getvalue())

    try:
        with st.spinner("正在解析公告并提取结构化数据..."):
            st.session_state["pipeline_result"] = run_pipeline(stored_path)
            st.session_state["uploaded_name"] = safe_name
    except Exception as error:
        st.error(f"处理失败：{error}")

result = st.session_state.get("pipeline_result")

if result:
    document = result["document"]
    evidence_report = result["evidence_report"]
    rows = record_rows(document)
    frame = pd.DataFrame(rows)

    if result["status"] == "success":
        st.success("处理完成，结构与证据检查均已通过。")
    else:
        st.warning("处理完成，但部分字段需要人工复核。")

    first, second, third, fourth = st.columns(4)
    first.metric("证券代码", document.security_code or "-")
    second.metric("证券简称", document.security_name or "-")
    third.metric("公告编号", document.announcement_number or "-")
    fourth.metric("质押记录", len(document.records))

    result_tab, evidence_tab, log_tab = st.tabs(
        ["结构化结果", "证据检查", "运行日志"]
    )

    with result_tab:
        if frame.empty:
            st.info("公告中未提取到质押记录。")
        else:
            st.dataframe(frame, use_container_width=True, hide_index=True)

        json_data = document.model_dump_json(indent=2)
        csv_data = frame.to_csv(index=False).encode("utf-8-sig")

        json_column, csv_column = st.columns(2)
        json_column.download_button(
            "下载JSON",
            data=json_data,
            file_name="pledge_prediction.json",
            mime="application/json",
            use_container_width=True,
        )
        csv_column.download_button(
            "下载CSV",
            data=csv_data,
            file_name="pledge_records.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with evidence_tab:
        if evidence_report["passed"]:
            st.success(
                f"证据检查通过："
                f"{evidence_report['passed_checks']}/"
                f"{evidence_report['checks_count']}"
            )
        else:
            st.error("发现证据不一致字段。")
            st.dataframe(
                evidence_report["issues"],
                use_container_width=True,
                hide_index=True,
            )

        for index, record in enumerate(document.records, start=1):
            with st.expander(f"记录 {index} · 第{record.source_page}页"):
                st.code(record.evidence_text or "无证据文本")

    with log_tab:
        st.dataframe(
            result["log"]["steps"],
            use_container_width=True,
            hide_index=True,
        )
        st.json(result["log"])