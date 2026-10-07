from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import DatabaseError

from accounts.models import PracticeLanguage, User
from conversations import services
from conversations.budget import is_exhausted, spent_today
from conversations.llm import AnalysisResult, FoundMistake, LLMError
from conversations.models import Conversation, Message, Mistake

# Wednesday 10 June 2026, 12:00 Berlin time (CEST, UTC+2).
NOON = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)

Outcome = AnalysisResult | Exception | Callable[..., AnalysisResult]


def found(
    number: int,
    wrong: str,
    correct: str,
    category: str = "grammar",
    sentence: str | None = None,
    explanation: str = "Explanation.",
) -> FoundMistake:
    return FoundMistake(
        message_number=number,
        category=category,  # type: ignore[arg-type]
        wrong=wrong,
        correct=correct,
        sentence=sentence if sentence is not None else f"Sentence {number}.",
        explanation=explanation,
    )


def make_result(*mistakes: FoundMistake) -> AnalysisResult:
    # With the test prices: 600 * 2.00 + 400 * 0.50 + 200 * 10.00 = 3400 / 1M.
    return AnalysisResult(
        mistakes=list(mistakes),
        model="test-model",
        input_tokens=1000,
        cached_input_tokens=400,
        output_tokens=200,
    )


ANALYSIS_COST = Decimal("0.0034")


class FakeAnalyzeMistakes:
    """Stands in for `llm.analyze_mistakes`; nothing here touches the network.

    Each call takes the next queued outcome (a result, an exception to raise, or a
    function called with the same kwargs); with an empty queue it returns no
    mistakes.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[Outcome] = []

    def __call__(self, **kwargs: Any) -> AnalysisResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else make_result()
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, AnalysisResult):
            return outcome
        return outcome(**kwargs)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeAnalyzeMistakes:
    fake = FakeAnalyzeMistakes()
    monkeypatch.setattr(services, "analyze_mistakes", fake)
    return fake


@pytest.fixture(autouse=True)
def pinned_settings(settings) -> None:
    settings.DAILY_BUDGET_USD = Decimal("1.00")
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_ANALYSIS_TIMEOUT_SECONDS = 90
    settings.LLM_ANALYSIS_MAX_RETRIES = 0
    settings.LLM_PRICES_USD_PER_MTOK = {
        "test-model": {
            "input": Decimal("2.00"),
            "cached_input": Decimal("0.50"),
            "output": Decimal("10.00"),
        }
    }


# 90 s x 1 attempt + 30 s.
ANALYSIS_TIMEOUT = timedelta(seconds=120)


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


def make_conversation(
    user: User,
    learner_texts: tuple[str, ...] = ("Ich habe gegangen.",),
    reason: Conversation.EndReason | None = Conversation.EndReason.USER,
) -> Conversation:
    """A conversation with an agent turn before each learner message."""
    conversation = Conversation.objects.create(
        user=user,
        topic="bakery",
        topic_title="Bakery",
        topic_scenario="You are a baker.",
        language=PracticeLanguage.GERMAN,
    )
    for text in learner_texts:
        Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, text="Und dann?"
        )
        Message.objects.create(
            conversation=conversation, role=Message.Role.USER, text=text
        )
    if reason is not None:
        services.end_conversation(conversation, reason, NOON)
    return conversation


def saved(conversation: Conversation) -> list[tuple[int, str, str, int]]:
    return [
        (m.position, m.wrong, m.correct, m.occurrences)
        for m in Mistake.objects.for_user(conversation.user).filter(
            conversation=conversation
        )
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("reason", list(Conversation.EndReason))
def test_analysis_runs_after_every_end_reason_even_with_exhausted_budget(
    anna: User, fake_llm: FakeAnalyzeMistakes, settings, reason: str
) -> None:
    settings.DAILY_BUDGET_USD = Decimal("0.01")
    conversation = make_conversation(anna, reason=Conversation.EndReason(reason))
    assert is_exhausted(anna, NOON)
    fake_llm.outcomes.append(make_result(found(1, "habe gegangen", "bin gegangen")))

    services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analyzed_at == NOON
    assert conversation.analysis_started_at is None
    assert saved(conversation) == [(1, "habe gegangen", "bin gegangen", 1)]
    [call] = fake_llm.calls
    assert call["language"] == "de"
    assert call["history"] == [
        ("assistant", "Und dann?"),
        ("user", "Ich habe gegangen."),
    ]


@pytest.mark.django_db
def test_active_conversation_is_refused_without_model_call(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna, reason=None)

    with pytest.raises(services.ConversationError, match="has not ended yet"):
        services.analyze_conversation(conversation, NOON)

    assert fake_llm.calls == []
    conversation.refresh_from_db()
    assert conversation.analysis_started_at is None


@pytest.mark.django_db
def test_second_analysis_is_refused_and_the_model_is_called_once(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    services.analyze_conversation(conversation, NOON)

    with pytest.raises(services.AnalysisNotNeeded, match="already ready"):
        services.analyze_conversation(conversation, NOON + timedelta(minutes=1))

    assert len(fake_llm.calls) == 1


@pytest.mark.django_db
def test_analysis_in_progress_is_refused(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    started = NOON - ANALYSIS_TIMEOUT + timedelta(seconds=1)
    Conversation.objects.filter(pk=conversation.pk).update(analysis_started_at=started)
    conversation.refresh_from_db()
    assert services.analysis_in_progress(conversation, NOON)

    with pytest.raises(services.AnalysisNotNeeded, match="still being prepared"):
        services.analyze_conversation(conversation, NOON)

    assert fake_llm.calls == []
    conversation.refresh_from_db()
    assert conversation.analysis_started_at == started
    assert conversation.analyzed_at is None


@pytest.mark.django_db
def test_expired_marker_lets_the_analysis_run(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    Conversation.objects.filter(pk=conversation.pk).update(
        analysis_started_at=NOON - ANALYSIS_TIMEOUT
    )
    conversation.refresh_from_db()
    assert not services.analysis_in_progress(conversation, NOON)

    services.analyze_conversation(conversation, NOON)

    assert len(fake_llm.calls) == 1
    conversation.refresh_from_db()
    assert conversation.analyzed_at == NOON
    assert conversation.analysis_started_at is None


@pytest.mark.django_db
def test_late_result_for_analysed_conversation_is_dropped_unpaid(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    earlier = NOON - timedelta(seconds=5)

    def parallel_request_finishes_first(**kwargs: Any) -> AnalysisResult:
        Conversation.objects.filter(pk=conversation.pk).update(
            analyzed_at=earlier, analysis_cost_usd=Decimal("0.001")
        )
        return make_result(found(1, "habe gegangen", "bin gegangen"))

    fake_llm.outcomes.append(parallel_request_finishes_first)

    services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analyzed_at == earlier
    assert conversation.analysis_cost_usd == Decimal("0.001")
    assert conversation.analysis_started_at is None
    assert saved(conversation) == []


@pytest.mark.django_db
def test_conversation_without_learner_messages_is_analysed_without_model_call(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna, learner_texts=())
    Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, text="Guten Tag!"
    )

    services.analyze_conversation(conversation, NOON)

    assert fake_llm.calls == []
    conversation.refresh_from_db()
    assert conversation.analyzed_at == NOON
    assert conversation.analysis_cost_usd == 0
    assert conversation.analysis_started_at is None
    assert saved(conversation) == []


@pytest.mark.django_db
def test_llm_error_marks_failure_and_retry_succeeds(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    fake_llm.outcomes.append(LLMError("down"))

    with pytest.raises(LLMError):
        services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analysis_failed_at == NOON
    assert conversation.analysis_started_at is None
    assert conversation.analyzed_at is None
    assert saved(conversation) == []

    later = NOON + timedelta(seconds=10)
    fake_llm.outcomes.append(make_result(found(1, "habe gegangen", "bin gegangen")))
    services.analyze_conversation(conversation, later)

    conversation.refresh_from_db()
    assert conversation.analysis_failed_at is None
    assert conversation.analyzed_at == later
    assert saved(conversation) == [(1, "habe gegangen", "bin gegangen", 1)]


@pytest.mark.django_db
def test_failure_does_not_mark_a_conversation_a_newer_request_is_analysing(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    newer = NOON + ANALYSIS_TIMEOUT

    def newer_request_takes_over(**kwargs: Any) -> AnalysisResult:
        Conversation.objects.filter(pk=conversation.pk).update(
            analysis_started_at=newer
        )
        raise LLMError("down")

    fake_llm.outcomes.append(newer_request_takes_over)

    with pytest.raises(LLMError):
        services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analysis_failed_at is None
    assert conversation.analysis_started_at == newer


@pytest.mark.django_db
def test_failure_does_not_mark_a_conversation_a_parallel_request_analysed(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    earlier = NOON - timedelta(seconds=5)

    def parallel_request_finishes_first(**kwargs: Any) -> AnalysisResult:
        Conversation.objects.filter(pk=conversation.pk).update(analyzed_at=earlier)
        raise LLMError("down")

    fake_llm.outcomes.append(parallel_request_finishes_first)

    with pytest.raises(LLMError):
        services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analysis_failed_at is None
    assert conversation.analyzed_at == earlier


@pytest.mark.django_db
def test_save_error_after_model_call_marks_failure(
    anna: User, fake_llm: FakeAnalyzeMistakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = make_conversation(anna)
    fake_llm.outcomes.append(make_result(found(1, "habe gegangen", "bin gegangen")))

    def broken_save(*args: Any) -> None:
        raise DatabaseError("disk full")

    monkeypatch.setattr(services, "_save_mistakes", broken_save)

    with pytest.raises(DatabaseError):
        services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analysis_failed_at == NOON
    assert conversation.analysis_started_at is None
    assert conversation.analyzed_at is None
    assert conversation.analysis_cost_usd == 0
    assert saved(conversation) == []


@pytest.mark.django_db
def test_identical_pairs_merge_at_the_first_occurrence(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna, learner_texts=("a", "b", "c", "d", "e"))
    fake_llm.outcomes.append(
        make_result(
            found(4, "habe gegangen", "bin gegangen", sentence="Fourth."),
            found(1, "habe gegangen", "bin gegangen", sentence="First."),
            found(2, "habe gefahren", "bin gefahren"),
            # Only whitespace differs: the same mistake.
            found(3, "  habe   gefahren ", "bin\tgefahren"),
            # Only letter case differs: a different mistake.
            found(5, "Habe gefahren", "Bin gefahren"),
        )
    )

    services.analyze_conversation(conversation, NOON)

    assert saved(conversation) == [
        (1, "habe gegangen", "bin gegangen", 2),
        (2, "habe gefahren", "bin gefahren", 2),
        (3, "Habe gefahren", "Bin gefahren", 1),
    ]
    first = Mistake.objects.for_user(anna).get(position=1)
    assert first.sentence == "First."


@pytest.mark.django_db
def test_order_is_chronological_with_out_of_range_numbers_last(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna, learner_texts=("a", "b", "c"))
    fake_llm.outcomes.append(
        make_result(
            found(3, "drei", "Drei"),
            found(7, "sieben", "Sieben"),
            found(1, "eins", "Eins"),
            found(0, "null", "Null"),
            found(2, "zwei", "Zwei"),
            found(1, "   ", "leer"),
            found(2, "gleich", "gleich "),
            found(3, "ohne", ""),
        )
    )

    services.analyze_conversation(conversation, NOON)

    assert saved(conversation) == [
        (1, "eins", "Eins", 1),
        (2, "zwei", "Zwei", 1),
        (3, "drei", "Drei", 1),
        (4, "sieben", "Sieben", 1),
        (5, "null", "Null", 1),
    ]


@pytest.mark.django_db
def test_analysis_cost_is_saved_and_counted_in_spent_today(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)

    services.analyze_conversation(conversation, NOON)

    conversation.refresh_from_db()
    assert conversation.analysis_cost_usd == ANALYSIS_COST
    assert spent_today(anna, NOON) == ANALYSIS_COST


@pytest.mark.django_db
def test_saved_mistakes_belong_to_the_conversation_owner(
    anna: User, fake_llm: FakeAnalyzeMistakes
) -> None:
    conversation = make_conversation(anna)
    fake_llm.outcomes.append(
        make_result(found(1, "habe gegangen", "bin gegangen", category="vocabulary"))
    )

    services.analyze_conversation(conversation, NOON)

    mistake = Mistake.objects.get()
    assert mistake.user == anna
    assert mistake.conversation == conversation
    assert mistake.category == Mistake.Category.VOCABULARY
    assert mistake.explanation == "Explanation."
