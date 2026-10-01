"""问一句: the rule router on a fixed question set, the answers, and the page."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.ask import ask, find_move, rule_route

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

# (question, expected intent, expected company or None). Development set: written together with the router.
# An honest accuracy figure needs NEW questions written by someone else (see docs or the plan).
CASES = [
    ("安阳钢铁现在风险怎么样？", "company", "安阳钢铁"), ("宝钢股份的承压评分是多少", "company", "宝钢股份"),
    ("介绍一下八一钢铁", "company", "八一钢铁"), ("600231 怎么样", "company", "凌钢股份"), ("鞍钢情况如何", "company", "鞍钢股份"),
    ("安泰集团的风险", "company", "安泰集团"), ("八一钢铁出事会传给谁？", "spread", "八一钢铁"),
    ("如果凌钢股份出问题会影响哪些公司", "spread", "凌钢股份"), ("本钢板材暴雷会连累谁", "spread", "本钢板材"),
    ("方大特钢的风险会波及哪些企业", "spread", "方大特钢"), ("哪些企业的风险会传到鞍钢股份？", "exposure", "鞍钢股份"),
    ("安泰集团的风险来自哪里", "exposure", "安泰集团"), ("宝钢会受谁的影响", "exposure", "宝钢股份"),
    ("今天最该关注什么？", "today", None), ("现在有哪些风险预警", "today", None), ("最近有什么风险", "today", None),
    ("承压最弱的钢厂有哪些？", "ranking", None), ("风险最大的五家钢企", "ranking", None), ("钢厂抗风险能力排名", "ranking", None),
    ("铁矿石涨 20% 谁受影响最大？", "price", None), ("焦炭价格下跌10%对谁影响大", "price", None), ("螺纹钢跌价两成会怎样", "price", None),
    ("废钢涨价影响谁", "price", None), ("出口关税提高 10% 对谁影响大？", "export", None), ("反倾销对哪些钢厂冲击最大", "export", None),
    ("出口退税下调怎么办", "export", None), ("这个系统准不准？", "trust", None), ("你们的结论经过验证了吗", "trust", None),
    ("帮我分析这份公告", "document", None), ("明天股价会涨吗", "unsupported", None), ("推荐一只股票", "unsupported", None),
    ("北京天气怎么样", "unsupported", None),
]


@pytest.mark.parametrize("question,intent,company", CASES)
def test_rule_router(question, intent, company):
    r = rule_route(question)
    assert r["intent"] == intent
    if company:
        assert r["companies"] and r["companies"][0][1] == company


def test_moves():
    assert find_move("铁矿石涨 20%") == 0.2
    assert find_move("焦炭价格下跌10%") == -0.1
    assert find_move("下调 3 个百分点") == -0.03
    assert find_move("没有数字") is None


@pytest.mark.parametrize("question", ["安阳钢铁现在风险怎么样？", "八一钢铁出事会传给谁？", "哪些企业的风险会传到鞍钢股份？",
                                      "今天最该关注什么？", "承压最弱的钢厂有哪些？", "铁矿石涨 20% 谁受影响最大？",
                                      "出口关税提高 10% 对谁影响大？", "这个系统准不准？", "明天股价会涨吗"])
def test_answers_are_structured_and_traced(question):
    r = ask(question, use_model=False)
    assert r["verdict"][1]
    assert [s["step"][0] for s in r["trace"]] == ["①", "②", "③", "④", "⑤"] or r["intent"] in ("unsupported", "document")
    assert all(isinstance(rows, list) for _, rows in r["tables"])


def test_unsupported_never_calls_a_tool():
    r = ask("推荐一只股票", use_model=False)
    assert r["intent"] == "unsupported"
    assert not any(s["step"].startswith("④") for s in r["trace"])


def test_page_answers_an_example():
    app = AppTest.from_file(APP_PATH, default_timeout=60).run()
    app.switch_page("pages/9_问一句.py").run()
    assert not app.exception
    app.text_input(key="ask_q").set_value("承压最弱的钢厂有哪些？").run()
    assert not app.exception
    assert any("问题类型" in m.value for m in app.markdown)
