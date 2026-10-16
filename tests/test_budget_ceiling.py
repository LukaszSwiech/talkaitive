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

Two clocks: `Message.created_at` is the real clock (auto_now_add), so tests that go
through turns use `now = timezone.now()`, taken after seeding. A test with fixed
UTC moments (midnight, a daylight-saving day) controls only the ledger and the
analysis, which are dated by the `now` passed in.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import PracticeLanguage, User
from conversations import services
from conversations.budget import spent_today
from conversations.llm import AnalysisResult, LLMError, TurnResult
from conversations.models import Conversation, LLMCharge, Message
from conversations.services import ConversationError
from tests.fake_provider import FakeProvider
from tests.fakes import FakeAnalyzeMistakes, FakeGenerateTurn, add_charge

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


def spent_earlier_today(user: User, cost: str) -> None:
    """An earlier conversation, ended today by the user, whose agent turn cost `cost`."""
    conversation = make_conversation(
        user,
        status=Conversation.Status.ENDED,
        end_reason=Conversation.EndReason.USER,
        ended_at=timezone.now(),
    )
    add_turn(conversation, Message.Role.ASSISTANT, cost)


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


# --- the hard ceiling: once the day's sum reaches the limit, no new paid call ------
#
# The day may go over the limit only by calls that started below it (at most one
# turn in flight) and by first analysis attempts. After the ceiling, no request
# reaches the provider; every refusal says why.


def test_one_expensive_call_crosses_the_limit_and_the_next_message_is_refused(
    anna: User, client: Client, fake_provider: FakeProvider
) -> None:
    """Guards M31 (no ceiling in send_message) and M33 (refused, but not ended)."""
    spent_earlier_today(anna, "0.85")
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.05")
    # Spent 0.85 + 0.05 = 0.90; 0.90 + the last turn's 0.05 < 1.00, so not final.
    # 20 000 output tokens: 20000 * 15.00 = 300 000 per 1M = 0.30.
    fake_provider.reply("Gern!", usage=(0, 0, 20000))
    client.force_login(anna)
    send_url = reverse("conversation_send", kwargs={"pk": conversation.pk})

    client.post(send_url, {"text": "Zwei Brötchen, bitte."})

    conversation.refresh_from_db()
    # 0.90 + 0.30 = 1.20: one call went over the limit, the conversation goes on.
    assert spent_today(anna, timezone.now()) == Decimal("1.20")
    assert conversation.status == Conversation.Status.ACTIVE

    page = client.post(send_url, {"text": "Noch ein Brot."}, follow=True)

    conversation.refresh_from_db()
    assert conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
    assert not conversation.messages.filter(text="Noch ein Brot.").exists()
    assert len(fake_provider.requests) == 1
    assert "used today&#x27;s conversation limit" in page.content.decode()
    assert "You can talk again after" in page.content.decode()


def test_turn_retries_stop_once_the_limit_is_reached(
    anna: User, fake_provider: FakeProvider
) -> None:
    """Guards M32 (no ceiling in run_agent_turn) and mutmut
    `x_run_agent_turn__mutmut_23` (ended by the daily limit, but without `ended_at`).
    """
    spent_earlier_today(anna, "0.94")
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    # Spent 0.94 + 0.02 = 0.96. Every attempt times out twice (the SDK retries once)
    # and is charged the last agent turn's 0.02.
    fake_provider.hang(times=4)

    with pytest.raises(LLMError):
        services.send_message(conversation, "Zwei Brötchen, bitte.", timezone.now())
    # 0.96 + 0.02 = 0.98, below the limit: "Try again" (now the farewell turn) runs.
    with pytest.raises(LLMError):
        services.run_agent_turn(conversation, timezone.now())
    # 0.98 + 0.02 = 1.00: the ceiling.
    refused_at = timezone.now()
    with pytest.raises(ConversationError):
        services.run_agent_turn(conversation, refused_at)

    conversation.refresh_from_db()
    assert spent_today(anna, timezone.now()) == Decimal("1.00")
    assert conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
    # The refusal ends the conversation at that moment.
    assert conversation.ended_at == refused_at
    assert len(fake_provider.requests) == 4


def test_message_just_below_the_limit_still_gets_the_farewell_turn(
    anna: User, fake_provider: FakeProvider
) -> None:
    spent_earlier_today(anna, "0.979999")
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    # Spent 0.979999 + 0.02 = 0.999999 < 1.00: the call starts, as the farewell turn
    # (0.999999 + the last turn's 0.02 >= 1.00).
    fake_provider.reply("Tschüss!")

    services.send_message(conversation, "Zwei Brötchen, bitte.", timezone.now())

    conversation.refresh_from_db()
    assert conversation.messages.filter(text="Tschüss!").exists()
    assert conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
    assert len(fake_provider.requests) == 1


def test_message_at_exactly_the_limit_is_refused_without_a_call(
    anna: User, fake_provider: FakeProvider
) -> None:
    spent_earlier_today(anna, "0.98")
    conversation = make_conversation(anna)
    add_turn(conversation, Message.Role.ASSISTANT, "0.02")
    # Spent 0.98 + 0.02 = 1.00, the budget itself.

    with pytest.raises(ConversationError):
        services.send_message(conversation, "Zwei Brötchen, bitte.", timezone.now())

    conversation.refresh_from_db()
    assert not conversation.messages.filter(text="Zwei Brötchen, bitte.").exists()
    assert conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
    assert len(fake_provider.requests) == 0


def test_start_at_the_limit_is_still_refused_without_a_call(
    anna: User, fake_provider: FakeProvider
) -> None:
    spent_earlier_today(anna, "1.00")

    with pytest.raises(ConversationError):
        services.start_conversation(anna, "bakery", timezone.now())

    assert len(fake_provider.requests) == 0


def test_analysis_retry_waits_for_the_reset_across_the_autumn_midnight(
    anna: User, fake_provider: FakeProvider
) -> None:
    """The first attempt runs whatever is left (S-02); a retry waits for the reset.

    Guards M34 (no ceiling on the analysis retry). 25 October 2026 is 25 hours long
    in Berlin: the day starts at 24 October 22:00 UTC (CEST) and the next midnight
    is 25 October 23:00 UTC (CET).
    """
    conversation = ended_conversation(anna)
    add_charge(conversation, "1.00", datetime(2026, 10, 25, 10, 0, tzinfo=UTC))
    fake_provider.hang()

    # 12:00 CET, the limit already reached: the first attempt still runs.
    with pytest.raises(LLMError):
        services.analyze_conversation(
            conversation, datetime(2026, 10, 25, 11, 0, tzinfo=UTC)
        )
    assert len(fake_provider.requests) == 1

    # 23:59 CET, still the same day: the retry is refused without a request.
    with pytest.raises(ConversationError):
        services.analyze_conversation(
            conversation, datetime(2026, 10, 25, 22, 59, tzinfo=UTC)
        )
    assert len(fake_provider.requests) == 1

    # 00:00 CET on 26 October: a new day, the retry runs and saves the list.
    fake_provider.analysis()
    services.analyze_conversation(
        conversation, datetime(2026, 10, 25, 23, 0, tzinfo=UTC)
    )

    assert conversation.analyzed_at is not None
    assert len(fake_provider.requests) == 2


def failed_analysis(user: User) -> Conversation:
    """An ended conversation whose analysis failed a moment ago."""
    conversation = ended_conversation(user)
    Conversation.objects.filter(pk=conversation.pk).update(
        analysis_failed_at=timezone.now()
    )
    return conversation


def test_failed_analysis_at_the_limit_shows_the_reset_time_instead_of_try_again(
    anna: User, client: Client
) -> None:
    conversation = failed_analysis(anna)
    add_charge(conversation, "1.00", timezone.now())
    client.force_login(anna)

    page = client.get(reverse("conversation_detail", kwargs={"pk": conversation.pk}))

    content = page.content.decode()
    assert "We could not prepare your list of mistakes." in content
    # The reset notice names the budget time zone; the wording is not a requirement.
    assert "(Europe/Berlin)" in content
    analyze_url = reverse("conversation_analyze", kwargs={"pk": conversation.pk})
    assert analyze_url not in content


def test_failed_analysis_below_the_limit_offers_try_again(
    anna: User, client: Client
) -> None:
    conversation = failed_analysis(anna)
    add_charge(conversation, "0.99", timezone.now())
    client.force_login(anna)

    page = client.get(reverse("conversation_detail", kwargs={"pk": conversation.pk}))

    content = page.content.decode()
    assert reverse("conversation_analyze", kwargs={"pk": conversation.pk}) in content
    assert "(Europe/Berlin)" not in content
