from src.llm_extractor import CAPACITY_PROMPT_PATH


def test_capacity_extractor_uses_v5_prompt():
    assert CAPACITY_PROMPT_PATH.name == "capacity_extraction_v5.txt"


def test_capacity_v5_prompt_contains_regression_rules():
    prompt = CAPACITY_PROMPT_PATH.read_text(encoding="utf-8")

    assert "整个计划只生成一个technical_upgrade框架事件" in prompt
    assert "events必须为空数组" in prompt
    assert "禁止自行补为当月第一天或最后一天" in prompt
    assert "不得生成capacity_changes" in prompt