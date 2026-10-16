"""Daily LLM budget rules.

One place for everything about the per-user daily limit: the cost of a turn (also
used for the cost of a post-conversation analysis), what was spent today (agent
turns, analyses and the `LLMCharge` ledger of paid calls that saved neither),
whether the budget is exhausted, whether the day's sum already reached the limit
(the hard ceiling), whether the next turn must be the last one and when talking is
allowed again. Functions take `now` as a parameter so
tests can use fixed dates (including daylight-saving changes).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Sum

from accounts.models import User

from .models import Conversation, LLMCharge, Message

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


def turn_cost(
    model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """Cost in USD of one LLM call (an agent turn or a mistake analysis).

    `input_tokens` includes the cached ones.
    """
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
    """Agent turns, mistake analyses and ledger entries since the last midnight."""
    start = day_start(now)
    turns = Message.objects.filter(
        conversation__in=Conversation.objects.for_user(user),
        created_at__gte=start,
    ).aggregate(total=Sum("cost_usd"))["total"]
    analyses = (
        Conversation.objects.for_user(user)
        .filter(analyzed_at__gte=start)
        .aggregate(total=Sum("analysis_cost_usd"))["total"]
    )
    charges = (
        LLMCharge.objects.for_user(user)
        .filter(charged_at__gte=start)
        .aggregate(total=Sum("cost_usd"))["total"]
    )
    return (turns or Decimal(0)) + (analyses or Decimal(0)) + (charges or Decimal(0))


def is_exhausted(user: User, now: datetime) -> bool:
    """Whether a new conversation may start (home page, starting, reset notice).

    Keeps room for one more turn, unlike `limit_reached`, which only says the day's
    sum already reached the budget. A conversation ended by the daily limit closes
    the day even when the spent sum is still just below the budget; otherwise the
    next conversation would say goodbye in its opening turn.
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


def limit_reached(user: User, now: datetime) -> bool:
    """The hard ceiling: today's sum already reached the budget.

    No new paid turn and no analysis retry starts once this is true. Unlike
    `is_exhausted`, it does not forecast the next call.
    """
    return spent_today(user, now) >= settings.DAILY_BUDGET_USD


def is_final_turn(user: User, conversation: Conversation, now: datetime) -> bool:
    """True when the budget would not cover one more turn like the last one."""
    estimate = next_turn_estimate(user, conversation)
    return spent_today(user, now) + estimate >= settings.DAILY_BUDGET_USD


def next_turn_estimate(user: User, conversation: Conversation) -> Decimal:
    """The expected cost of the conversation's next agent turn.

    The cost of its last agent turn, or `LLM_TURN_COST_ESTIMATE_USD` before the
    first one. Also what a turn that timed out is charged.
    """
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
    if last_agent_turn is None:
        return settings.LLM_TURN_COST_ESTIMATE_USD
    return last_agent_turn.cost_usd
