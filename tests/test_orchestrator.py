"""The dispatch agent runs the same traced plan for every demo case, offline, and its decisions are rules."""
from src.analyze import demo_cases
from src.orchestrator import full_markdown, run


def test_demo_case_gives_a_full_trace_and_a_graph_decision():
    case = demo_cases()[0]
    card = run(case=case)
    steps = [s["step"][:1] for s in card["trace"]]
    assert steps[0] == "①" and steps[-1] == "⑩"
    assert card["extraction_status"] == "offline_replay" and "离线回放" in card["offline_note"]
    assert isinstance(card["graph_decision"]["auto"], bool)
    assert "调度轨迹" in full_markdown(card)


def test_every_demo_case_runs_offline_without_a_model():
    for case in demo_cases():
        card = run(case=case)
        assert card["trace"] and card["task"] == case["task"]
