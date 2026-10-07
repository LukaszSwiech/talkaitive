from types import SimpleNamespace
from typing import Any

import openai
import pydantic
import pytest

from conversations import llm
from conversations.llm import (
    AgentTurn,
    AnalysisResult,
    FoundMistake,
    LLMError,
    MistakeReport,
    TurnResult,
    analyze_mistakes,
    generate_turn,
)
from conversations.topics import get_topic

TOPIC = get_topic("bakery")
assert TOPIC is not None


class FakeResponses:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_response(
    parsed: pydantic.BaseModel | None = None,
    usage: object | None = "default",
) -> SimpleNamespace:
    if parsed is None:
        parsed = AgentTurn(reply="Guten Tag!", end_conversation=False)
    if usage == "default":
        usage = SimpleNamespace(
            input_tokens=1200,
            input_tokens_details=SimpleNamespace(cached_tokens=1000),
            output_tokens=40,
        )
    return SimpleNamespace(output_parsed=parsed, usage=usage)


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the SDK client class; nothing in these tests touches the network."""
    state = SimpleNamespace(client_kwargs={}, responses=FakeResponses(make_response()))

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            state.client_kwargs = kwargs
            self.responses = state.responses

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    return state


def call(**overrides: Any) -> TurnResult:
    kwargs: dict[str, Any] = {
        "topic": TOPIC,
        "language": "de",
        "history": [("assistant", "Guten Tag!"), ("user", "Ich möchte Brötchen.")],
        "final_turn": False,
    }
    kwargs.update(overrides)
    return generate_turn(**kwargs)


def test_client_gets_settings_from_django_settings(
    fake_openai: SimpleNamespace, settings
) -> None:
    settings.OPENAI_API_KEY = "sk-test"
    settings.OPENAI_BASE_URL = "https://eu.example.test/v1"
    settings.LLM_TIMEOUT_SECONDS = 12
    settings.LLM_MAX_RETRIES = 3

    call()

    assert fake_openai.client_kwargs == {
        "api_key": "sk-test",
        "base_url": "https://eu.example.test/v1",
        "timeout": 12,
        "max_retries": 3,
    }


def test_call_passes_model_effort_store_and_text_format(
    fake_openai: SimpleNamespace, settings
) -> None:
    settings.LLM_MODEL = "gpt-5.4"
    settings.LLM_REASONING_EFFORT = "none"

    call()

    (kwargs,) = fake_openai.responses.calls
    assert kwargs["model"] == "gpt-5.4"
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["store"] is False
    assert kwargs["text_format"] is AgentTurn


def test_instructions_contain_language_and_scenario(
    fake_openai: SimpleNamespace,
) -> None:
    call(language="en")
    call(language="de")

    english, german = (c["instructions"] for c in fake_openai.responses.calls)
    assert "Practice language: English" in english
    assert "Practice language: German" not in english
    assert "Practice language: German" in german
    assert "Practice language: English" not in german
    assert TOPIC.scenario in english
    assert TOPIC.scenario in german


def test_instructions_start_with_the_same_stable_prefix(
    fake_openai: SimpleNamespace,
) -> None:
    call(language="en")
    call(language="de")

    english, german = (c["instructions"] for c in fake_openai.responses.calls)
    marker = "Practice language:"
    assert english.split(marker)[0] == german.split(marker)[0]
    assert "B1-B2" in english
    assert "at most the 1-2 most important" in english.replace("\\\n", "")


def test_history_is_passed_in_order_as_input_messages(
    fake_openai: SimpleNamespace,
) -> None:
    call()

    (kwargs,) = fake_openai.responses.calls
    assert kwargs["input"] == [
        {"role": "assistant", "content": "Guten Tag!"},
        {"role": "user", "content": "Ich möchte Brötchen."},
    ]


def test_empty_history_sends_an_opening_message(
    fake_openai: SimpleNamespace,
) -> None:
    call(history=[])

    (kwargs,) = fake_openai.responses.calls
    assert len(kwargs["input"]) == 1
    assert kwargs["input"][0]["role"] == "user"
    assert "speak first" in kwargs["input"][0]["content"]


def test_final_turn_appends_a_goodbye_instruction_at_the_end(
    fake_openai: SimpleNamespace,
) -> None:
    call(final_turn=True)
    call(final_turn=False)

    with_final, without_final = (c["input"] for c in fake_openai.responses.calls)
    assert with_final[:-1] == without_final
    assert "last reply" in with_final[-1]["content"]
    assert "daily conversation limit" in with_final[-1]["content"]


def test_final_turn_with_empty_history_keeps_the_opening_message_first(
    fake_openai: SimpleNamespace,
) -> None:
    call(history=[], final_turn=True)

    (kwargs,) = fake_openai.responses.calls
    assert "speak first" in kwargs["input"][0]["content"]
    assert "last reply" in kwargs["input"][-1]["content"]


def test_usage_and_reply_are_mapped_to_turn_result(
    fake_openai: SimpleNamespace, settings
) -> None:
    settings.LLM_MODEL = "gpt-5.4"
    fake_openai.responses.outcome = make_response(
        AgentTurn(reply="Tschüss!", end_conversation=True)
    )

    result = call()

    assert result == TurnResult(
        reply="Tschüss!",
        end_conversation=True,
        model="gpt-5.4",
        input_tokens=1200,
        cached_input_tokens=1000,
        output_tokens=40,
    )


def _status_error(cls: type[openai.APIStatusError], status: int) -> Exception:
    response = SimpleNamespace(status_code=status, headers={}, request=None)
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=SimpleNamespace()),
        openai.APIConnectionError(request=SimpleNamespace()),
        _status_error(openai.RateLimitError, 429),
        _status_error(openai.InternalServerError, 500),
    ],
    ids=["timeout", "connection", "rate-limit", "status"],
)
def test_sdk_errors_become_llm_error(
    fake_openai: SimpleNamespace, error: Exception
) -> None:
    fake_openai.responses.outcome = error

    with pytest.raises(LLMError):
        call()


def test_empty_parsed_output_raises_llm_error(fake_openai: SimpleNamespace) -> None:
    fake_openai.responses.outcome = SimpleNamespace(output_parsed=None, usage=None)

    with pytest.raises(LLMError):
        call()


def test_missing_usage_raises_llm_error(fake_openai: SimpleNamespace) -> None:
    fake_openai.responses.outcome = make_response(usage=None)

    with pytest.raises(LLMError):
        call()


def test_missing_api_key_raises_llm_error_not_at_import(
    fake_openai: SimpleNamespace, settings
) -> None:
    settings.OPENAI_API_KEY = None

    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        call()
    assert fake_openai.responses.calls == []


def test_error_log_does_not_contain_conversation_text(
    fake_openai: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    fake_openai.responses.outcome = openai.APIConnectionError(request=SimpleNamespace())

    with pytest.raises(LLMError), caplog.at_level("ERROR", logger="conversations.llm"):
        call()

    assert "APIConnectionError" in caplog.text
    assert "Brötchen" not in caplog.text


def test_malformed_structured_output_becomes_llm_error(
    fake_openai: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    # The SDK parses the output with pydantic; a truncated answer fails like this.
    with pytest.raises(pydantic.ValidationError) as truncated:
        AgentTurn.model_validate_json('{"reply": "Gerne, zwei Brötchen')
    fake_openai.responses.outcome = truncated.value

    with pytest.raises(LLMError), caplog.at_level("ERROR", logger="conversations.llm"):
        call()

    assert "AgentTurn" in caplog.text
    assert "Brötchen" not in caplog.text


# --- analyze_mistakes ---------------------------------------------------------

ANALYSIS_HISTORY = [
    ("assistant", "Was hast du am Wochenende gemacht?"),
    ("user", "Ich habe ins Kino gegangen."),
    ("assistant", "Ach, du bist ins Kino gegangen! Welcher Film?"),
    ("user", "Ein Film über Hunde, er war sehr lustig."),
]

MISTAKE = FoundMistake(
    message_number=1,
    category="grammar",
    wrong="habe ... gegangen",
    correct="bin ... gegangen",
    sentence="Ich habe ins Kino gegangen.",
    explanation="Verbs of motion form the perfect with 'sein'.",
)


def analyze(**overrides: Any) -> AnalysisResult:
    kwargs: dict[str, Any] = {"language": "de", "history": ANALYSIS_HISTORY}
    kwargs.update(overrides)
    return analyze_mistakes(**kwargs)


@pytest.fixture
def fake_analysis(fake_openai: SimpleNamespace) -> SimpleNamespace:
    fake_openai.responses.outcome = make_response(MistakeReport(mistakes=[MISTAKE]))
    return fake_openai


def test_analysis_client_uses_analysis_timeout_and_retries(
    fake_analysis: SimpleNamespace, settings
) -> None:
    settings.OPENAI_API_KEY = "sk-test"
    settings.OPENAI_BASE_URL = "https://eu.example.test/v1"
    settings.LLM_TIMEOUT_SECONDS = 12
    settings.LLM_MAX_RETRIES = 3
    settings.LLM_ANALYSIS_TIMEOUT_SECONDS = 90
    settings.LLM_ANALYSIS_MAX_RETRIES = 0

    analyze()

    assert fake_analysis.client_kwargs == {
        "api_key": "sk-test",
        "base_url": "https://eu.example.test/v1",
        "timeout": 90,
        "max_retries": 0,
    }


def test_analysis_call_passes_model_effort_store_and_text_format(
    fake_analysis: SimpleNamespace, settings
) -> None:
    settings.LLM_MODEL = "gpt-5.4"
    settings.LLM_REASONING_EFFORT = "none"
    settings.LLM_ANALYSIS_REASONING_EFFORT = "high"

    analyze()

    (kwargs,) = fake_analysis.responses.calls
    assert kwargs["model"] == "gpt-5.4"
    assert kwargs["reasoning"] == {"effort": "high"}
    assert kwargs["store"] is False
    assert kwargs["text_format"] is MistakeReport


def test_transcript_numbers_only_learner_messages(
    fake_analysis: SimpleNamespace,
) -> None:
    analyze()

    (kwargs,) = fake_analysis.responses.calls
    transcript = kwargs["input"]
    assert isinstance(transcript, str)
    assert "[1] Learner: Ich habe ins Kino gegangen." in transcript
    assert "[2] Learner: Ein Film über Hunde, er war sehr lustig." in transcript
    assert "[3]" not in transcript
    assert "Partner: Was hast du am Wochenende gemacht?" in transcript
    assert "Partner: Ach, du bist ins Kino gegangen! Welcher Film?" in transcript
    # Partner messages carry no number.
    assert "] Partner:" not in transcript
    # Order is kept.
    assert transcript.index("Wochenende") < transcript.index("[1] Learner")
    assert transcript.index("[1] Learner") < transcript.index("Welcher Film")
    assert transcript.index("Welcher Film") < transcript.index("[2] Learner")


def test_analysis_instructions_share_a_stable_prefix_across_languages(
    fake_analysis: SimpleNamespace,
) -> None:
    analyze(language="en")
    analyze(language="de")

    english, german = (c["instructions"] for c in fake_analysis.responses.calls)
    marker = "Practice language:"
    assert english.split(marker)[0] == german.split(marker)[0]
    assert "Practice language: English" in english
    assert "Practice language: German" in german
    assert "word_order" in english


def test_analysis_maps_mistakes_and_usage_to_result(
    fake_analysis: SimpleNamespace, settings
) -> None:
    settings.LLM_MODEL = "gpt-5.4"

    result = analyze()

    assert result == AnalysisResult(
        mistakes=[MISTAKE],
        model="gpt-5.4",
        input_tokens=1200,
        cached_input_tokens=1000,
        output_tokens=40,
    )


def test_analysis_with_no_mistakes_returns_an_empty_list(
    fake_openai: SimpleNamespace,
) -> None:
    fake_openai.responses.outcome = make_response(MistakeReport(mistakes=[]))

    assert analyze().mistakes == []


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=SimpleNamespace()),
        openai.APIConnectionError(request=SimpleNamespace()),
        _status_error(openai.RateLimitError, 429),
        _status_error(openai.InternalServerError, 500),
    ],
    ids=["timeout", "connection", "rate-limit", "status"],
)
def test_analysis_sdk_errors_become_llm_error(
    fake_openai: SimpleNamespace,
    error: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_openai.responses.outcome = error

    with pytest.raises(LLMError), caplog.at_level("ERROR", logger="conversations.llm"):
        analyze()

    assert type(error).__name__ in caplog.text
    assert "Kino" not in caplog.text


def test_analysis_malformed_output_becomes_llm_error(
    fake_openai: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(pydantic.ValidationError) as truncated:
        MistakeReport.model_validate_json(
            '{"mistakes": [{"sentence": "Ich habe ins Kino'
        )
    fake_openai.responses.outcome = truncated.value

    with pytest.raises(LLMError), caplog.at_level("ERROR", logger="conversations.llm"):
        analyze()

    assert "MistakeReport" in caplog.text
    assert "Kino" not in caplog.text


def test_analysis_empty_parsed_output_raises_llm_error(
    fake_openai: SimpleNamespace,
) -> None:
    fake_openai.responses.outcome = SimpleNamespace(output_parsed=None, usage=None)

    with pytest.raises(LLMError):
        analyze()


def test_analysis_missing_usage_raises_llm_error(fake_openai: SimpleNamespace) -> None:
    fake_openai.responses.outcome = make_response(
        MistakeReport(mistakes=[MISTAKE]), usage=None
    )

    with pytest.raises(LLMError):
        analyze()
