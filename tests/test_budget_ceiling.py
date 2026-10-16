"""The daily budget counts every paid model call (test-plan risk #4).

Each test goes from a service call to the day's sum and checks how much it grew,
which ledger entries (`LLMCharge`) were left and how many requests reached the
provider. Expected amounts are written out by hand, with the arithmetic in a
comment, from the prices pinned below (gpt-5.4 per 1M tokens: input 2.50, cached
input 0.25, output 15.00), never computed with the code's `turn_cost`.

Sources: PRD Access Control "Koszty modeli" (a $1 daily limit per user covering the
model calls of the day) and the decisions of
context/changes/testing-budget-ceiling/plan.md (a call that most likely cost money
counts: its real usage when known, otherwise an estimate of 0.03 for a turn without
an earlier agent turn, the last agent turn's cost after one, and 0.07 for an
analysis; a call the provider refused at once counts nothing).

Two clocks: `Message.created_at` is the real clock (auto_now_add), so these tests
use `now = timezone.now()`, taken after seeding.
"""

from decimal import Decimal
from typing import Any

import pytest
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import PracticeLanguage, User
from conversations import services
from conversations.budget import spent_today
from conversations.llm import AnalysisResult, LLMError, TurnResult
from conversations.models import Conversation, LLMCharge, Message
from tests.fake_provider import FakeProvider
from tests.fakes import FakeAnalyzeMistakes, FakeGenerateTurn

# 1000 input tokens of which 400 cached, 200 output tokens:
# 600 * 2.50 + 400 * 0.25 + 200 * 15.00 = 4600 per 1M = 0.0046 USD.
RESULT_TOKENS = {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 200}


@pytest.fixture(autouse=True)
def pinned_budget(settings) -> None:
    settings.LLM_MODEL = "gpt-5.4"
    settings.LLM_PRICES_USD_PER_MTOK = {
        "gpt-5.4": {
            "input": Decimal("2.50"),
            "cached_input": Decimal("0.25"),
            "output": Decimal("15.00"),
        }
    }
    settings.DAILY_BUDGET_USD = Decimal("1.00")
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_ANALYSIS_COST_ESTIMATE_USD = Decimal("0.07")


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


def make_conversation(user: User, **fields: Any) -> Conversation:
    return Conversation.objects.create(
        user=user,
        topic="bakery",
        topic_title="Bakery",
        topic_scenario="You are a baker.",
        language=PracticeLanguage.GERMAN,
        **fields,
    )


def add_turn(conversation: Conversation, role: str, cost: str = "0") -> None:
    Message.objects.create(
        conversation=conversation, role=role, text="Hallo", cost_usd=Decimal(cost)
    )


def ended_conversation(user: User) -> Conversation:
    """An ended conversation with one learner message, ready for the analysis."""
    conversation = make_conversation(
        user,
        status=Conversation.Status.ENDED,
        end_reason=Conversation.EndReason.USER,
        ended_at=timezone.now(),
    )
    add_turn(conversation, Message.Role.ASSISTANT)
    add_turn(conversation, Message.Role.USER)
    return conversation


def charges(user: User) -> list[tuple[str, str, Decimal]]:
    return [
        (charge.kind, charge.reason, charge.cost_usd)
        for charge in LLMCharge.objects.for_user(user).order_by("id")
    ]


# --- agent turns ---------------------------------------------------------------


def test_turn_that_times_out_before_any_agent_turn_costs_the_fixed_estimate(
    anna: User, fake_provider: FakeProvider
) -> None:
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.USER)
    fake_provider.hang(times=2)
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(LLMError):
        services.run_agent_turn(conversation, now)

    # No earlier agent turn: the fixed turn estimate, 0.03.
    assert spent_today(anna, now) - before == Decimal("0.03")
    assert charges(anna) == [("turn", "estimate", Decimal("0.03"))]
    assert len(fake_provider.requests) == 2


def test_turn_that_times_out_costs_the_last_agent_turn(
    anna: User, fake_provider: FakeProvider
) -> None:
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    fake_provider.hang(times=2)
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(LLMError):
        services.send_message(conversation, "Zwei Brötchen, bitte.", now)

    # The conversation's last agent turn cost 0.02.
    assert spent_today(anna, now) - before == Decimal("0.02")
    assert charges(anna) == [("turn", "estimate", Decimal("0.02"))]
    assert len(fake_provider.requests) == 2


def test_blank_reply_is_paid_at_its_real_usage(
    anna: User, fake_provider: FakeProvider
) -> None:
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    fake_provider.reply("")
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(LLMError):
        services.send_message(conversation, "Zwei Brötchen, bitte.", now)

    # The fake's default usage: 1200 input of which 1000 cached, 40 output:
    # 200 * 2.50 + 1000 * 0.25 + 40 * 15.00 = 1350 per 1M = 0.00135.
    assert spent_today(anna, now) - before == Decimal("0.00135")
    assert charges(anna) == [("turn", "no_usable_answer", Decimal("0.00135"))]
    assert len(fake_provider.requests) == 1


def test_turn_refused_by_the_provider_costs_nothing(
    anna: User, fake_provider: FakeProvider
) -> None:
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    fake_provider.fail(503).fail(503)
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(LLMError):
        services.send_message(conversation, "Zwei Brötchen, bitte.", now)

    assert spent_today(anna, now) == before
    assert charges(anna) == []
    assert len(fake_provider.requests) == 2


def test_late_turn_is_dropped_but_its_cost_counts(
    anna: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards M30 (a late turn without a ledger entry)."""
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    now = timezone.now()

    def user_ends_meanwhile(**kwargs: Any) -> TurnResult:
        services.end_conversation(conversation, Conversation.EndReason.USER, now)
        return TurnResult(
            reply="Gerne!", end_conversation=False, model="gpt-5.4", **RESULT_TOKENS
        )

    fake = FakeGenerateTurn(default=lambda: pytest.fail("one call expected"))
    fake.outcomes.append(user_ends_meanwhile)
    monkeypatch.setattr(services, "generate_turn", fake)
    before = spent_today(anna, now)

    services.send_message(conversation, "Zwei Brötchen, bitte.", now)

    assert not conversation.messages.filter(text="Gerne!").exists()
    # RESULT_TOKENS: 0.0046.
    assert spent_today(anna, now) - before == Decimal("0.0046")
    assert charges(anna) == [("turn", "late_result", Decimal("0.0046"))]


# --- mistake analysis ----------------------------------------------------------


def test_analysis_that_times_out_costs_the_analysis_estimate(
    anna: User, fake_provider: FakeProvider
) -> None:
    conversation = ended_conversation(anna)
    fake_provider.hang()
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(LLMError):
        services.analyze_conversation(conversation, now)

    # The analysis estimate, 0.07.
    assert spent_today(anna, now) - before == Decimal("0.07")
    assert charges(anna) == [("analysis", "estimate", Decimal("0.07"))]
    assert len(fake_provider.requests) == 1


def test_late_analysis_is_dropped_but_its_cost_counts(
    anna: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = ended_conversation(anna)
    now = timezone.now()

    def parallel_request_finishes_first(**kwargs: Any) -> AnalysisResult:
        Conversation.objects.filter(pk=conversation.pk).update(analyzed_at=now)
        return AnalysisResult(
            mistakes=[],
            learner_facts=["The learner likes bread."],
            scene_notes=[],
            model="gpt-5.4",
            **RESULT_TOKENS,
        )

    fake = FakeAnalyzeMistakes(default=lambda: pytest.fail("one call expected"))
    fake.outcomes.append(parallel_request_finishes_first)
    monkeypatch.setattr(services, "analyze_mistakes", fake)
    before = spent_today(anna, now)

    services.analyze_conversation(conversation, now)

    assert conversation.learner_facts == []
    # RESULT_TOKENS: 0.0046.
    assert spent_today(anna, now) - before == Decimal("0.0046")
    assert charges(anna) == [("analysis", "late_result", Decimal("0.0046"))]


def test_analysis_whose_save_fails_still_counts_its_cost(
    anna: User, fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = ended_conversation(anna)
    fake_provider.analysis(usage=(2000, 0, 100))

    def broken_save(*args: Any, **kwargs: Any) -> None:
        raise DatabaseError("disk full")

    monkeypatch.setattr(services, "_save_mistakes", broken_save)
    now = timezone.now()
    before = spent_today(anna, now)

    with pytest.raises(DatabaseError):
        services.analyze_conversation(conversation, now)

    # 2000 input (none cached), 100 output: 2000 * 2.50 + 100 * 15.00 = 6500 per 1M.
    assert spent_today(anna, now) - before == Decimal("0.0065")
    assert charges(anna) == [("analysis", "save_failed", Decimal("0.0065"))]
    assert len(fake_provider.requests) == 1
