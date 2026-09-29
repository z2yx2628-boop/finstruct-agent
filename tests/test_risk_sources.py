"""Stage 1 (risk sources) is listed on its own before propagation, and every source says what it is:
an event that happened, an exposure, or a model warning."""
from scripts.collect_credit_events import classify
from src.entity_resolver import ROOT
from src.network_view import NATURE_COLOR, SOURCE_KIND, risk_sources, seed_nature


def test_every_seed_is_listed_with_a_nature_and_readable_reason():
    snaps = sorted(p for p in (ROOT / "data" / "snapshots").glob("2026-*") if (p / "fragility.csv").exists())
    sources = risk_sources(ROOT / "data" / "chain" / "live", snaps[-1])
    assert sources
    for s in sources:
        assert s["kind"] in SOURCE_KIND and s["nature"] in NATURE_COLOR
        assert not any(code in s["reason"] for code in ("share_pledge", "credit_exposure", "guarantee_limit", "outputs/", "http"))
    assert all(s["nature"] == "模型预警" for s in sources if s["kind"] == "weak")


def test_seed_nature_separates_facts_exposures_and_model_warnings():
    assert seed_nature("承压评分为弱：资产负债率87.4%") == "模型预警"
    assert seed_nature("未评分的非子公司被担保方（财务不公开）：获担保 10 亿元") == "风险敞口"
    assert seed_nature("2026-03-30 credit_event：被实施风险警示：关于股票被实施退市风险警示暨停牌的公告") == "已发生事件"
    assert seed_nature("2024-03-13 credit_exposure：guarantee_provided → X") == "风险敞口"
    assert seed_nature(" share_pledge：股东质押") == "风险敞口"


def test_live_titles_use_the_preregistered_patterns():
    assert classify("关于股票被实施退市风险警示暨停牌的公告") == "st"
    assert classify("关于部分银行账户资金被冻结暨诉讼进展公告") == "freeze"
    assert classify("关于为全资子公司提供担保的公告") is None
