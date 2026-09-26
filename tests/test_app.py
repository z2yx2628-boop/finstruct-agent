from pathlib import Path

from streamlit.testing.v1 import AppTest

from schemas.pledge import PledgeDocument, PledgeEvent
from src.evidence_validator import validate_evidence


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def make_result() -> dict:
    pledge_evidence = """昝圣达
1,000
4.17%
0.77%
否
否
2026-6-11
2029-6-1
招商银行股份有限公司南通分行
融资担保"""
    release_evidence = """昝圣达
200
0.83%
0.15%
2025-1-1
2026-1-1
招商银行股份有限公司南通分行"""
    pages = [{
        "page": 1,
        "text": f"""证券代码：600770
证券简称：综艺股份
公告编号：临2026-026
江苏综艺股份有限公司
本次股份质押基本情况
本次质押股数（万股）
{pledge_evidence}
本次股份解除质押基本情况
本次解除质押股数（万股）
{release_evidence}""",
    }]
    document = PledgeDocument(
        security_code="600770",
        security_name="综艺股份",
        announcement_number="临2026-026",
        company_name="江苏综艺股份有限公司",
        events=[
            PledgeEvent(
                event_type="pledge",
                shareholder_name="昝圣达",
                shares=1000,
                shares_unit="万股",
                shareholder_holding_ratio=4.17,
                total_share_capital_ratio=0.77,
                is_restricted_share=False,
                is_supplementary_pledge=False,
                pledge_start_date="2026-06-11",
                pledge_end_date="2029-06-01",
                pledgee="招商银行股份有限公司南通分行",
                purpose="融资担保",
                source_page=1,
                evidence_text=pledge_evidence,
                confidence=1.0,
            ),
            PledgeEvent(
                event_type="release",
                shareholder_name="昝圣达",
                shares=200,
                shares_unit="万股",
                shareholder_holding_ratio=0.83,
                total_share_capital_ratio=0.15,
                pledge_start_date="2025-01-01",
                release_date="2026-01-01",
                pledgee="招商银行股份有限公司南通分行",
                source_page=1,
                evidence_text=release_evidence,
                confidence=1.0,
            ),
        ],
    )
    return {
        "status": "success",
        "document": document,
        "evidence_report": validate_evidence(document, pages),
        "log": {"steps": [], "status": "success"},
    }


def test_app_loads_without_a_result():
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "FinStruct Agent"
    assert app.button[0].disabled is True


def test_app_displays_event_summary():
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.switch_page("pages/1_公告结构化.py")
    app.session_state["app_schema_version"] = 2
    app.session_state["pipeline_result"] = make_result()

    app.run()

    metrics = {item.label: item.value for item in app.metric}
    assert not app.exception
    assert metrics["事件记录"] == "2"
    assert metrics["新增质押（股）"] == "10,000,000"
    assert metrics["解除质押（股）"] == "2,000,000"
    assert metrics["净变化（股）"] == "8,000,000"
