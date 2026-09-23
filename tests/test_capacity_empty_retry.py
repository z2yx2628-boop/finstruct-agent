from schemas.capacity import CapacityDocument, CapacityEvent
from src.capacity_empty_retry import capacity_empty_retry_reason
from types import SimpleNamespace

import src.llm_extractor as llm_extractor

def test_empty_project_agreement_triggers_retry():
    document = CapacityDocument(events=[])
    pages = [{
        "page": 1,
        "text": (
            "公司签署《印尼金祥新能源科技有限责任公司"
            "年产390万吨焦炭项目合资协议》；"
            "同日签署《保证协议》。"
        ),
    }]

    reason = capacity_empty_retry_reason(document, pages)

    assert reason == "binding_project_agreement_with_capacity"


def test_pure_guarantee_notice_does_not_trigger_retry():
    document = CapacityDocument(events=[])
    pages = [{
        "page": 1,
        "text": (
            "公司签署《保证协议》，融资资金拟用于"
            "年产390万吨焦炭项目。"
        ),
    }]

    reason = capacity_empty_retry_reason(document, pages)

    assert reason is None


def test_nonempty_document_does_not_trigger_retry():
    document = CapacityDocument(events=[CapacityEvent(
        event_type="capacity_construction",
        source_page=1,
        evidence_text="签署项目建设协议",
        confidence=1.0,
    )])
    pages = [{
        "page": 1,
        "text": "签署《年产390万吨焦炭项目合资协议》",
    }]

    reason = capacity_empty_retry_reason(document, pages)

    assert reason is None
def make_fake_client(responses: list[str]):
    calls = []
    response_iterator = iter(responses)

    def create(**kwargs):
        calls.append(kwargs)
        content = next(response_iterator)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content)
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        )
    )
    return client, calls


def configure_fake_model(monkeypatch, responses: list[str]):
    client, calls = make_fake_client(responses)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://example.test/v1",
    )
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr(
        llm_extractor,
        "OpenAI",
        lambda **kwargs: client,
    )

    return calls


def test_empty_strong_candidate_calls_model_twice(monkeypatch):
    pages = [{
        "page": 1,
        "text": (
            "公司签署《印尼金祥新能源科技有限责任公司"
            "年产390万吨焦炭项目合资协议》；"
            "同日签署《保证协议》。"
        ),
    }]

    first_response = CapacityDocument(
        events=[]
    ).model_dump_json()

    second_response = CapacityDocument(
        security_code="600282",
        security_name="南钢股份",
        events=[
            CapacityEvent(
                event_type="capacity_construction",
                project_name=(
                    "印尼金祥新能源科技有限责任公司"
                    "年产390万吨焦炭项目"
                ),
                project_status="planned",
                source_page=1,
                evidence_text=(
                    "公司签署年产390万吨焦炭项目合资协议"
                ),
                confidence=0.95,
            )
        ],
    ).model_dump_json()

    calls = configure_fake_model(
        monkeypatch,
        [first_response, second_response],
    )

    document, raw_content, changes = (
        llm_extractor.extract_capacity(pages)
    )

    assert len(calls) == 2
    assert len(document.events) == 1
    assert raw_content == second_response
    assert any(
        change.get("action") == "empty_event_retry"
        and change.get("accepted") is True
        for change in changes
    )


def test_empty_guarantee_notice_calls_model_once(monkeypatch):
    pages = [{
        "page": 1,
        "text": (
            "公司签署《保证协议》，融资资金拟用于"
            "年产390万吨焦炭项目。"
        ),
    }]

    empty_response = CapacityDocument(
        events=[]
    ).model_dump_json()

    calls = configure_fake_model(
        monkeypatch,
        [empty_response],
    )

    document, raw_content, changes = (
        llm_extractor.extract_capacity(pages)
    )

    assert len(calls) == 1
    assert document.events == []
    assert raw_content == empty_response
    assert not any(
        change.get("action") in {
            "empty_event_retry",
            "empty_event_retry_failed",
        }
        for change in changes
    )