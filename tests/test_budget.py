from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured

from accounts.models import PracticeLanguage, User
from conversations.budget import (
    day_start,
    is_exhausted,
    is_final_turn,
    limit_reached,
    next_reset,
    next_turn_estimate,
    spent_today,
    turn_cost,
)
from conversations.models import Conversation, Message
from tests.fakes import add_charge

# Wednesday 10 June 2026, 12:00 Berlin time (CEST, UTC+2).
NOON = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)
# Midnight of that day in Berlin is 9 June 22:00 UTC.
MIDNIGHT = datetime(2026, 6, 9, 22, 0, tzinfo=UTC)
YESTERDAY = datetime(2026, 6, 9, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pinned_budget(settings) -> None:
    settings.DAILY_BUDGET_USD = Decimal("1.00")
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_ANALYSIS_COST_ESTIMATE_USD = Decimal("0.07")


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


@pytest.fixture
def lukasz(db) -> User:
    return User.objects.create_user("lukasz@example.de", "pass-12345-xyz")


def make_conversation(user: User, **fields: object) -> Conversation:
    return Conversation.objects.create(
        user=user,
        topic="bakery",
        topic_title="Bakery",
        topic_scenario="You are a baker.",
        language=PracticeLanguage.GERMAN,
        **fields,
    )


def add_message(
    conversation: Conversation,
    cost: str,
    at: datetime,
    role: str = Message.Role.ASSISTANT,
) -> Message:
    message = Message.objects.create(
        conversation=conversation, role=role, text="Hallo", cost_usd=Decimal(cost)
    )
    # created_at is auto_now_add, so it can only be moved with an update.
    Message.objects.filter(pk=message.pk).update(created_at=at)
    return message


def add_analysis(conversation: Conversation, cost: str, at: datetime) -> None:
    Conversation.objects.filter(pk=conversation.pk).update(
        analyzed_at=at, analysis_cost_usd=Decimal(cost)
    )


def end_by_daily_limit(conversation: Conversation, at: datetime) -> None:
    Conversation.objects.filter(pk=conversation.pk).update(
        status=Conversation.Status.ENDED,
        end_reason=Conversation.EndReason.DAILY_LIMIT,
        ended_at=at,
    )


def test_turn_cost_counts_cached_tokens_at_the_cached_price(settings) -> None:
    settings.LLM_PRICES_USD_PER_MTOK = {
        "test-model": {
            "input": Decimal("2.00"),
            "cached_input": Decimal("0.50"),
            "output": Decimal("10.00"),
        }
    }

    cost = turn_cost("test-model", 1000, 400, 200)

    # 600 * 2.00 + 400 * 0.50 + 200 * 10.00 = 3400 per 1M tokens.
    assert cost == Decimal("0.0034")


def test_turn_cost_for_unpriced_model_raises() -> None:
    with pytest.raises(ImproperlyConfigured):
        turn_cost("model-without-prices", 10, 0, 10)


def test_day_start_and_next_reset_around_midnight_in_summer() -> None:
    before_midnight = datetime(2026, 6, 10, 21, 59, tzinfo=UTC)  # 23:59 CEST
    after_midnight = datetime(2026, 6, 10, 22, 1, tzinfo=UTC)  # 00:01 CEST next day

    assert day_start(before_midnight) == datetime(2026, 6, 9, 22, 0, tzinfo=UTC)
    assert next_reset(before_midnight) == datetime(2026, 6, 10, 22, 0, tzinfo=UTC)
    assert day_start(after_midnight) == datetime(2026, 6, 10, 22, 0, tzinfo=UTC)
    assert next_reset(after_midnight) == datetime(2026, 6, 11, 22, 0, tzinfo=UTC)


def test_day_start_and_next_reset_around_midnight_in_winter() -> None:
    before_midnight = datetime(2026, 1, 15, 22, 59, tzinfo=UTC)  # 23:59 CET
    after_midnight = datetime(2026, 1, 15, 23, 1, tzinfo=UTC)  # 00:01 CET next day

    assert day_start(before_midnight) == datetime(2026, 1, 14, 23, 0, tzinfo=UTC)
    assert next_reset(before_midnight) == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
    assert day_start(after_midnight) == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
    assert next_reset(after_midnight) == datetime(2026, 1, 16, 23, 0, tzinfo=UTC)


def test_day_is_23_hours_long_when_clocks_go_forward() -> None:
    # 29 March 2026: Berlin switches from CET (UTC+1) to CEST (UTC+2) at 02:00.
    now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)

    start = day_start(now)
    reset = next_reset(now)

    assert start == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    assert reset == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)
    # Same-zone aware datetimes subtract by wall clock, so compare in UTC.
    assert (reset.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == 23 * 3600


def test_day_is_25_hours_long_when_clocks_go_back() -> None:
    # 25 October 2026: Berlin switches from CEST (UTC+2) back to CET (UTC+1).
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)

    assert day_start(now) == datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    assert next_reset(now) == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)
    length = next_reset(now).astimezone(UTC) - day_start(now).astimezone(UTC)
    assert length.total_seconds() == 25 * 3600


def test_spent_today_sums_only_todays_messages(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.100000", NOON)
    add_message(conversation, "0.250000", NOON, role=Message.Role.USER)
    add_message(conversation, "0.400000", YESTERDAY)

    assert spent_today(anna, NOON) == Decimal("0.35")


def test_spent_today_counts_from_midnight_inclusive(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.200000", MIDNIGHT)

    assert spent_today(anna, NOON) == Decimal("0.2")


def test_spent_today_ignores_other_users(anna: User, lukasz: User) -> None:
    add_message(make_conversation(anna), "0.100000", NOON)
    add_message(make_conversation(lukasz), "0.900000", NOON)

    assert spent_today(anna, NOON) == Decimal("0.1")


def test_spent_today_adds_todays_analyses_to_turns(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.100000", NOON)
    add_analysis(conversation, "0.050000", NOON)

    assert spent_today(anna, NOON) == Decimal("0.15")


def test_spent_today_ignores_analysis_from_before_midnight(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.100000", NOON)
    add_analysis(conversation, "0.400000", MIDNIGHT - timedelta(seconds=1))

    assert spent_today(anna, NOON) == Decimal("0.1")


def test_spent_today_counts_analysis_at_midnight(anna: User) -> None:
    add_analysis(make_conversation(anna), "0.200000", MIDNIGHT)

    assert spent_today(anna, NOON) == Decimal("0.2")


def test_spent_today_ignores_other_users_analyses(anna: User, lukasz: User) -> None:
    add_analysis(make_conversation(lukasz), "0.900000", NOON)

    assert spent_today(anna, NOON) == Decimal(0)


def test_is_exhausted_true_when_only_the_analysis_crosses_the_threshold(
    anna: User,
) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.900000", NOON)
    assert not is_exhausted(anna, NOON)

    add_analysis(conversation, "0.070000", NOON)

    # 0.90 + 0.07 + 0.03 estimate reaches the 1.00 budget.
    assert is_exhausted(anna, NOON)


def test_spent_today_is_zero_without_messages(anna: User) -> None:
    assert spent_today(anna, NOON) == Decimal(0)


def test_is_exhausted_false_with_budget_left(anna: User) -> None:
    add_message(make_conversation(anna), "0.500000", NOON)

    assert not is_exhausted(anna, NOON)


def test_is_exhausted_true_when_budget_does_not_cover_one_more_turn(
    anna: User,
) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.970000", NOON)

    # 0.97 + 0.03 estimate reaches the 1.00 budget.
    assert is_exhausted(anna, NOON)


def test_is_exhausted_false_just_below_the_estimate_threshold(anna: User) -> None:
    add_message(make_conversation(anna), "0.969999", NOON)

    assert not is_exhausted(anna, NOON)


def test_is_exhausted_true_after_daily_limit_end_even_with_money_left(
    anna: User,
) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.500000", NOON)
    end_by_daily_limit(conversation, NOON)

    assert spent_today(anna, NOON) < Decimal("1.00")
    assert is_exhausted(anna, NOON)


def test_is_exhausted_false_after_midnight_reset(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.990000", NOON)
    end_by_daily_limit(conversation, NOON)
    # 11 June 2026 00:00 CEST (UTC+2), the midnight after NOON.
    after_reset = datetime(2026, 6, 10, 22, 0, tzinfo=UTC)

    assert not is_exhausted(anna, after_reset)


def test_daily_limit_end_exactly_at_midnight_closes_that_day(anna: User) -> None:
    """Ended by the limit at 00:00:00 Berlin: that day is closed, the next is not.

    Source: PRD Access Control "Koszty modeli" (reset at midnight Europe/Berlin);
    a day is
    [midnight, next midnight), as in the "midnight inclusive" tests. Guards M5.
    """
    # 10 June 2026 00:00:00 CEST (UTC+2) is 9 June 22:00:00 UTC.
    end_by_daily_limit(make_conversation(anna), datetime(2026, 6, 9, 22, 0, tzinfo=UTC))
    later_that_day = datetime(2026, 6, 10, 10, 0, tzinfo=UTC)  # 12:00 CEST
    next_midnight = datetime(2026, 6, 10, 22, 0, tzinfo=UTC)  # 11 June 00:00 CEST

    assert is_exhausted(anna, later_that_day)
    assert not is_exhausted(anna, next_midnight)


def test_is_exhausted_ignores_other_users_daily_limit_end(
    anna: User, lukasz: User
) -> None:
    conversation = make_conversation(lukasz)
    add_message(conversation, "0.990000", NOON)
    end_by_daily_limit(conversation, NOON)

    assert not is_exhausted(anna, NOON)


def test_is_exhausted_ignores_other_end_reasons(anna: User) -> None:
    conversation = make_conversation(anna)
    Conversation.objects.filter(pk=conversation.pk).update(
        status=Conversation.Status.ENDED,
        end_reason=Conversation.EndReason.USER,
        ended_at=NOON,
    )

    assert not is_exhausted(anna, NOON)


def test_is_final_turn_without_agent_turn_uses_the_estimate(anna: User) -> None:
    conversation = make_conversation(anna)
    assert not is_final_turn(anna, conversation, NOON)

    add_message(conversation, "0.970000", NOON, role=Message.Role.USER)
    assert is_final_turn(anna, conversation, NOON)


def test_is_final_turn_uses_the_cost_of_the_last_agent_turn(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.010000", NOON.replace(hour=7))
    add_message(conversation, "0.500000", NOON.replace(hour=8))
    add_message(conversation, "0.200000", NOON.replace(hour=9))

    # Spent 0.71; the LAST agent turn cost 0.20 -> 0.91 < 1.00. Using the most
    # expensive turn (0.50) instead would give 1.21 and wrongly say "final".
    assert not is_final_turn(anna, conversation, NOON)

    add_message(conversation, "0.090000", NOON.replace(hour=9, minute=30))
    # Spent 0.80; the last agent turn cost 0.09 -> 0.89 < 1.00.
    assert not is_final_turn(anna, conversation, NOON)

    add_message(conversation, "0.150000", NOON.replace(hour=9, minute=45))
    # Spent 0.95; the last agent turn cost 0.15 -> 1.10 >= 1.00.
    assert is_final_turn(anna, conversation, NOON)


def test_is_final_turn_false_with_plenty_of_budget(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.040000", NOON)

    assert not is_final_turn(anna, conversation, NOON)


def test_is_final_turn_ignores_other_users_spending(anna: User, lukasz: User) -> None:
    conversation = make_conversation(anna)
    add_message(make_conversation(lukasz), "0.990000", NOON)

    assert not is_final_turn(anna, conversation, NOON)


def test_is_final_turn_ignores_other_users_newer_agent_turn(
    anna: User, lukasz: User
) -> None:
    """Anna's final-turn answer is the same with and without Lukasz's turns.

    Source: PRD Access Control "Koszty modeli" (the $1 limit is per user) and
    Prywatność. Guards M4.
    """
    conversation = make_conversation(anna)
    add_message(conversation, "0.100000", NOON.replace(hour=8))
    # Anna spent $0.10 of $1.00: one more turn like hers cannot be her last.
    without_lukasz = is_final_turn(anna, conversation, NOON)
    assert not without_lukasz

    # Newer and expensive enough that counting it for Anna would cross $1.00.
    add_message(make_conversation(lukasz), "0.950000", NOON.replace(hour=9))

    assert is_final_turn(anna, conversation, NOON) == without_lukasz


# --- the ledger (LLMCharge): paid calls that left no message and no analysis -------
#
# Source: PRD Access Control "Koszty modeli" (the $1 limit covers every model call of
# the day, per user, reset at midnight Europe/Berlin) and the decision of
# context/changes/testing-budget-ceiling/plan.md (failed and late calls count).


def test_spent_today_counts_todays_ledger_entry(anna: User) -> None:
    add_charge(make_conversation(anna), "0.030000", NOON)

    assert spent_today(anna, NOON) == Decimal("0.03")


def test_spent_today_ignores_ledger_entry_from_before_midnight(anna: User) -> None:
    add_charge(make_conversation(anna), "0.400000", MIDNIGHT - timedelta(seconds=1))

    assert spent_today(anna, NOON) == Decimal(0)


def test_spent_today_counts_ledger_entry_at_midnight(anna: User) -> None:
    add_charge(make_conversation(anna), "0.200000", MIDNIGHT)

    assert spent_today(anna, NOON) == Decimal("0.2")


def test_spent_today_ignores_other_users_ledger_entries(
    anna: User, lukasz: User
) -> None:
    """Guards M29 (the ledger read without `for_user`)."""
    add_charge(make_conversation(lukasz), "0.900000", NOON)

    assert spent_today(anna, NOON) == Decimal(0)


def test_spent_today_adds_turns_analyses_and_ledger(anna: User) -> None:
    """Guards M28 (the ledger left out of the day's sum)."""
    conversation = make_conversation(anna)
    add_message(conversation, "0.100000", NOON)
    add_analysis(conversation, "0.050000", NOON)
    add_charge(conversation, "0.030000", NOON)

    # 0.10 turn + 0.05 analysis + 0.03 ledger entry.
    assert spent_today(anna, NOON) == Decimal("0.18")


def test_spent_today_on_the_day_clocks_go_forward(anna: User) -> None:
    # 29 March 2026: midnight is still CET (UTC+1), so the day starts at
    # 28 March 23:00 UTC; 12:00 CEST (UTC+2) that day is 10:00 UTC.
    conversation = make_conversation(anna)
    add_charge(conversation, "0.400000", datetime(2026, 3, 28, 22, 59, 59, tzinfo=UTC))
    add_charge(conversation, "0.200000", datetime(2026, 3, 28, 23, 0, tzinfo=UTC))

    assert spent_today(anna, datetime(2026, 3, 29, 10, 0, tzinfo=UTC)) == Decimal("0.2")


def test_spent_today_on_the_day_clocks_go_back(anna: User) -> None:
    # 25 October 2026: midnight is still CEST (UTC+2), so the day starts at
    # 24 October 22:00 UTC; 12:00 CET (UTC+1) that day is 11:00 UTC.
    conversation = make_conversation(anna)
    add_charge(conversation, "0.400000", datetime(2026, 10, 24, 21, 59, 59, tzinfo=UTC))
    add_charge(conversation, "0.200000", datetime(2026, 10, 24, 22, 0, tzinfo=UTC))

    assert spent_today(anna, datetime(2026, 10, 25, 11, 0, tzinfo=UTC)) == Decimal(
        "0.2"
    )


def test_next_turn_estimate_without_agent_turn_is_the_fixed_estimate(
    anna: User,
) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0", NOON, role=Message.Role.USER)

    # LLM_TURN_COST_ESTIMATE_USD pinned to 0.03 above.
    assert next_turn_estimate(anna, conversation) == Decimal("0.03")


def test_next_turn_estimate_is_the_cost_of_the_last_agent_turn(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.500000", NOON.replace(hour=8))
    add_message(conversation, "0.020000", NOON.replace(hour=9))

    assert next_turn_estimate(anna, conversation) == Decimal("0.02")


# --- the hard ceiling: once the day's sum reaches the limit -------------------------


def test_limit_reached_false_just_below_the_budget(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.900000", NOON)
    add_charge(conversation, "0.099999", NOON)

    # 0.90 + 0.099999 = 0.999999 < 1.00: no forecast, only what was spent.
    assert not limit_reached(anna, NOON)


def test_limit_reached_true_at_exactly_the_budget(anna: User) -> None:
    conversation = make_conversation(anna)
    add_message(conversation, "0.900000", NOON)
    add_charge(conversation, "0.100000", NOON)

    # 0.90 + 0.10 = 1.00, the budget itself.
    assert limit_reached(anna, NOON)
