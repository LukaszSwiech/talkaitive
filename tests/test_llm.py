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
    format_memory,
    generate_turn,
)
from conversations.memory import Memory, PastMistake
from conversations.topics import get_topic
from tests.fake_provider import FakeProvider, UnscriptedRequest

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
        "memory": "",
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


FULL_MEMORY = Memory(
    learner_facts=["The learner has a dog called Bello.", "The learner is a nurse."],
    scene_notes=[
        ["They talked about rye bread.", "The baker asked about the weekend."],
        ["The baker said she bakes at 4 a.m."],
    ],
    mistakes=[
        PastMistake("habe gegangen", "bin gegangen", "Gehen takes sein.", 3),
        PastMistake("der Brot", "das Brot", "Brot is neuter.", 1),
    ],
)


def test_memory_block_comes_after_the_scene(fake_openai: SimpleNamespace) -> None:
    memory = format_memory(FULL_MEMORY)

    call(memory=memory)

    (kwargs,) = fake_openai.responses.calls
    instructions = kwargs["instructions"]
    assert instructions.endswith(f"Scene: {TOPIC.scenario}\n\n{memory}")
    assert instructions.index("Practice language:") < instructions.index("Scene:")


def test_empty_memory_leaves_instructions_unchanged(
    fake_openai: SimpleNamespace,
) -> None:
    call(memory="")
    call(memory=format_memory(Memory()))

    without, with_empty = (c["instructions"] for c in fake_openai.responses.calls)
    assert without == with_empty
    assert without.endswith(f"Scene: {TOPIC.scenario}")


def test_memory_keeps_the_stable_instructions_prefix(
    fake_openai: SimpleNamespace,
) -> None:
    call(memory="")
    call(memory=format_memory(FULL_MEMORY))

    without, with_memory = (c["instructions"] for c in fake_openai.responses.calls)
    assert without.startswith(llm._INSTRUCTIONS)
    assert with_memory.startswith(without)


def test_format_memory_of_empty_memory_is_empty() -> None:
    assert format_memory(Memory()) == ""


def test_format_memory_lists_every_section_in_order() -> None:
    text = format_memory(FULL_MEMORY)

    assert text.index("Bello") < text.index("nurse")
    assert text.index("nurse") < text.index("rye bread")
    assert text.index("rye bread") < text.index("4 a.m.")
    assert text.index("4 a.m.") < text.index("habe gegangen")
    assert "- habe gegangen → bin gegangen: Gehen takes sein." in text
    assert text.index("habe gegangen") < text.index("der Brot")
    assert "trust the newer one" in text
    assert "do not ask again questions that were already asked" in text
    assert "at most one" in text
    assert "Never say that this is an exercise" in text


@pytest.mark.parametrize(
    ("memory", "present", "absent"),
    [
        (
            Memory(learner_facts=["The learner has a dog."]),
            "about the learner",
            ["this same scene", "got wrong before"],
        ),
        (
            Memory(scene_notes=[["They talked about bread."]]),
            "this same scene",
            ["about the learner", "got wrong before"],
        ),
        (
            Memory(mistakes=[PastMistake("a", "b", "Why.", 1)]),
            "got wrong before",
            ["about the learner", "this same scene"],
        ),
    ],
    ids=["facts-only", "scene-only", "mistakes-only"],
)
def test_format_memory_skips_empty_sections(
    memory: Memory, present: str, absent: list[str]
) -> None:
    text = format_memory(memory)

    assert present in text
    for heading in absent:
        assert heading not in text


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

FACTS = ["The learner likes films about dogs."]
NOTES = ["They talked about the weekend.", "The partner asked which film it was."]


def analyze(**overrides: Any) -> AnalysisResult:
    kwargs: dict[str, Any] = {"language": "de", "history": ANALYSIS_HISTORY}
    kwargs.update(overrides)
    return analyze_mistakes(**kwargs)


@pytest.fixture
def fake_analysis(fake_openai: SimpleNamespace) -> SimpleNamespace:
    fake_openai.responses.outcome = make_response(
        MistakeReport(mistakes=[MISTAKE], learner_facts=FACTS, scene_notes=NOTES)
    )
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
    assert "learner_facts" in english
    assert "scene_notes" in english
    # The notes section is fixed text, before the language.
    assert english.index("scene_notes") < english.index(marker)


def test_analysis_maps_mistakes_and_usage_to_result(
    fake_analysis: SimpleNamespace, settings
) -> None:
    settings.LLM_MODEL = "gpt-5.4"

    result = analyze()

    assert result == AnalysisResult(
        mistakes=[MISTAKE],
        learner_facts=FACTS,
        scene_notes=NOTES,
        model="gpt-5.4",
        input_tokens=1200,
        cached_input_tokens=1000,
        output_tokens=40,
    )


def test_analysis_with_no_mistakes_returns_an_empty_list(
    fake_openai: SimpleNamespace,
) -> None:
    fake_openai.responses.outcome = make_response(
        MistakeReport(mistakes=[], learner_facts=[], scene_notes=[])
    )

    result = analyze()

    assert result.mistakes == []
    assert result.learner_facts == []
    assert result.scene_notes == []


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
        MistakeReport(mistakes=[MISTAKE], learner_facts=FACTS, scene_notes=NOTES),
        usage=None,
    )

    with pytest.raises(LLMError):
        analyze()


# --- SDK boundary on the HTTP transport -----------------------------------------
#
# These tests run the real SDK client on a scripted provider (`fake_provider`), so
# its retry loop, `Retry-After` handling and timeouts behave as in production. They
# pin the SDK behaviour that the "agent is typing" marker and the error page rely
# on. Expected numbers come from the SDK and our settings, never from our code:
#
# - 30 s: `LLM_TIMEOUT_SECONDS` in `talkaitive/settings.py` (a turn's read limit);
#   one retry (`LLM_MAX_RETRIES = 1`) means at most 2 requests per turn.
# - 150 s: `LLM_ANALYSIS_TIMEOUT_SECONDS`; no retries (`LLM_ANALYSIS_MAX_RETRIES = 0`).
# - 120 s: `MAX_RETRY_AFTER_DELAY = 2 * 60` in `openai/_constants.py`, the longest
#   `Retry-After` the SDK honours; above it the SDK does not retry at all.
# - 0.5 s: `INITIAL_RETRY_DELAY` in `openai/_constants.py`, the SDK's first backoff
#   without a `Retry-After` (reduced by up to 25% jitter).


def test_turn_that_hangs_twice_fails_after_two_requests_each_cut_at_30_s(
    fake_provider: FakeProvider,
) -> None:
    fake_provider.hang(times=2)

    with pytest.raises(LLMError) as failure:
        call()

    assert isinstance(failure.value.__cause__, openai.APITimeoutError)
    assert fake_provider.read_timeouts == [30, 30]
    # One short backoff between the two attempts, not a server-directed wait.
    (sleep,) = fake_provider.sleeps
    assert 0 < sleep <= 0.5


def test_turn_retries_after_503_with_retry_after_and_returns_the_reply(
    fake_provider: FakeProvider,
) -> None:
    fake_provider.fail(503, retry_after=56).reply("Guten Morgen!")

    result = call()

    assert result.reply == "Guten Morgen!"
    assert len(fake_provider.requests) == 2
    assert fake_provider.sleeps == [56]


def test_turn_honours_retry_after_of_exactly_120_s(
    fake_provider: FakeProvider,
) -> None:
    fake_provider.fail(429, retry_after=120).reply("Hallo!")

    result = call()

    assert result.reply == "Hallo!"
    assert len(fake_provider.requests) == 2
    assert fake_provider.sleeps == [120]


def test_turn_does_not_retry_when_retry_after_exceeds_120_s(
    fake_provider: FakeProvider,
) -> None:
    """Above the SDK's 120 s cap the first error is final: no wait, no retry.

    The marker's length is built on this cap; if a future SDK changes it, this
    test fails.
    """
    fake_provider.fail(429, retry_after=121)

    with pytest.raises(LLMError) as failure:
        call()

    assert isinstance(failure.value.__cause__, openai.RateLimitError)
    assert len(fake_provider.requests) == 1
    assert fake_provider.sleeps == []


def test_analysis_that_hangs_fails_after_one_request_cut_at_150_s(
    fake_provider: FakeProvider,
) -> None:
    fake_provider.hang()

    with pytest.raises(LLMError) as failure:
        analyze()

    assert isinstance(failure.value.__cause__, openai.APITimeoutError)
    assert fake_provider.read_timeouts == [150]
    assert fake_provider.sleeps == []


def test_analysis_on_the_fake_provider_returns_the_report(
    fake_provider: FakeProvider,
) -> None:
    fake_provider.analysis(mistakes=[MISTAKE], learner_facts=FACTS, scene_notes=NOTES)

    result = analyze()

    assert result.mistakes == [MISTAKE]
    assert result.learner_facts == FACTS
    assert result.scene_notes == NOTES
    assert (result.input_tokens, result.cached_input_tokens) == (1200, 1000)
    assert result.output_tokens == 40


def test_fake_provider_fails_loudly_on_an_unscripted_request(
    fake_provider: FakeProvider,
) -> None:
    # Nothing queued: the request must not get a silent answer or a retry.
    with pytest.raises(UnscriptedRequest):
        call()

    assert len(fake_provider.unscripted) == 1
    assert fake_provider.sleeps == []
    fake_provider.unscripted.clear()  # Seen on purpose; keep the teardown check quiet.


# --- empty agent reply ----------------------------------------------------------
#
# Oracle: test-plan.md §2 risk #1 guidance ("empty result -> message and Try
# again") and decision P2 of testing-waiting-path-recovery (plan, 2026-10-15): a
# reply that is empty or only whitespace is an unusable answer like any other.


@pytest.mark.parametrize(
    ("reply", "usable"),
    [("", False), (" ", False), ("\n\t ", False), (" Hallo ", True)],
    ids=["empty", "space", "whitespace-mix", "text-with-spaces"],
)
def test_blank_reply_is_an_llm_error_but_padded_text_is_kept(
    fake_provider: FakeProvider, reply: str, usable: bool
) -> None:
    fake_provider.reply(reply)

    if usable:
        # Text around whitespace is a real answer, returned as it came (untrimmed).
        assert call().reply == reply
    else:
        with pytest.raises(LLMError):
            call()
    # A 200 answer is never retried by the SDK, blank or not.
    assert len(fake_provider.requests) == 1
