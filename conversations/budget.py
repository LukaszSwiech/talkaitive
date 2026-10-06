"""Daily LLM budget rules.

One place for everything about the per-user daily limit: the cost of a turn, what
was spent today, whether the budget is exhausted, whether the next turn must be the
last one and when talking is allowed again. Functions take `now` as a parameter so
tests can use fixed dates (including daylight-saving changes).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Sum

from accounts.models import User

from .models import Conversation, Message

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


def turn_cost(
    model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """Cost in USD of one agent turn; `input_tokens` includes the cached ones."""
    try:
        prices = settings.LLM_PRICES_USD_PER_MTOK[model]
    except KeyError:
        raise ImproperlyConfigured(
            f"Model {model!r} has no entry in LLM_PRICES_USD_PER_MTOK."
        ) from None
    cost = (
        (input_tokens - cached_input_tokens) * prices["input"]
        + cached_input_tokens * prices["cached_input"]
        + output_tokens * prices["output"]
    )
    return cost / _TOKENS_PER_PRICE_UNIT


def _midnight(now: datetime, days_ahead: int) -> datetime:
    zone = ZoneInfo(settings.BUDGET_TIME_ZONE)
    local_date = now.astimezone(zone).date() + timedelta(days=days_ahead)
    return datetime.combine(local_date, time.min, tzinfo=zone)


def day_start(now: datetime) -> datetime:
    """The last midnight in `BUDGET_TIME_ZONE` (aware)."""
    return _midnight(now, 0)


def next_reset(now: datetime) -> datetime:
    """The next midnight in `BUDGET_TIME_ZONE` (aware): when the budget resets."""
    return _midnight(now, 1)


def spent_today(user: User, now: datetime) -> Decimal:
    total = Message.objects.filter(
        conversation__in=Conversation.objects.for_user(user),
        created_at__gte=day_start(now),
    ).aggregate(total=Sum("cost_usd"))["total"]
    return total or Decimal(0)


def is_exhausted(user: User, now: datetime) -> bool:
    """The only "budget exhausted" predicate (home page, starting, reset notice).

    A conversation ended by the daily limit closes the day even when the spent sum
    is still just below the budget; otherwise the next conversation would say
    goodbye in its opening turn.
    """
    ended_by_limit = (
        Conversation.objects.for_user(user)
        .filter(
            end_reason=Conversation.EndReason.DAILY_LIMIT,
            ended_at__gte=day_start(now),
        )
        .exists()
    )
    if ended_by_limit:
        return True
    return (
        spent_today(user, now) + settings.LLM_TURN_COST_ESTIMATE_USD
        >= settings.DAILY_BUDGET_USD
    )


def is_final_turn(user: User, conversation: Conversation, now: datetime) -> bool:
    """True when the budget would not cover one more turn like the last one."""
    last_agent_turn = (
        Message.objects.filter(
            conversation__in=Conversation.objects.for_user(user).filter(
                pk=conversation.pk
            ),
            role=Message.Role.ASSISTANT,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    estimate = (
        last_agent_turn.cost_usd
        if last_agent_turn is not None
        else settings.LLM_TURN_COST_ESTIMATE_USD
    )
    return spent_today(user, now) + estimate >= settings.DAILY_BUDGET_USD
