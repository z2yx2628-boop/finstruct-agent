"""分析新公告 page helpers: ten steps, every demo case explained, recent runs and their failures."""
import json

from src.analyze import ROOT
from src.analyze_ui import CASES, PIPELINE, last_daily_failure, pipeline_html, recent_runs


def test_ten_steps_and_every_demo_case_has_a_plain_explanation():
    assert len(PIPELINE) == 10 and pipeline_html().count("font-weight:600") == 10
    ids = {c["id"] for c in json.loads((ROOT / "data" / "demo" / "manifest.json").read_text(encoding="utf-8"))}
    assert ids <= set(CASES)


def test_failures_are_reported_with_their_cause():
    runs = [{"抽取": "失败", "error": "Error code: 400 - Model not exist."}, {"抽取": "成功", "error": ""}]
    note = last_daily_failure(runs)
    assert "2 份" in note and "1 份抽取失败" in note and "模型名称不可用" in note
    assert last_daily_failure([{"抽取": "成功", "error": ""}]) is None


def test_recent_runs_are_newest_first():
    rows = recent_runs()
    assert rows == sorted(rows, key=lambda r: r["日期"], reverse=True)


def test_page_url_points_to_announcement_page():
    from src.analyze_ui import page_url
    raw = "http://file.finance.sina.com.cn/211.154.219.97:9494/MRGG/CNSESH_STOCK/2026/2026-11/2026-11-18/12711094.PDF"
    assert page_url(raw, "600022") == ("https://vip.stock.finance.sina.com.cn/corp/view/"
                                       "vCB_AllBulletinDetail.php?stockid=600022&id=12711094")
    assert page_url("https://example.com/a.html", "600022") == "https://example.com/a.html"
