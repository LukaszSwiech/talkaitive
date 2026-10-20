"""Cost meter with a hard cap for the AI eval.

The eval calls `conversations.llm` directly, so the app's daily budget (which sums
`Message`, `Conversation` and `LLMCharge` rows) never sees it. The meter counts the
spend the same way the app does: a result by its token usage (`budget.turn_cost`),
an `LLMError` by its `usage` when known, by the estimate from the settings when the
call was most likely billed without usage, otherwise 0 (the provider refused at
once). A call starts only when the spend plus its estimate stays within the cap.
"""

from decimal import Decimal
from typing import Literal

from django.conf import settings

from conversations.budget import turn_cost
from conversations.llm import AnalysisResult, LLMError, TurnResult

CallKind = Literal["turn", "analysis"]


def estimate(kind: CallKind) -> Decimal:
    """The expected cost of one call of `kind`, from the settings."""
    if kind == "turn":
        return settings.LLM_TURN_COST_ESTIMATE_USD
    return settings.LLM_ANALYSIS_COST_ESTIMATE_USD


class CostMeter:
    def __init__(self, cap_usd: Decimal) -> None:
        self.cap_usd = cap_usd
        self.spent = Decimal(0)

    def charge_result(self, result: TurnResult | AnalysisResult) -> Decimal:
        """Adds and returns the cost of a successful call."""
        cost = turn_cost(
            result.model,
            result.input_tokens,
            result.cached_input_tokens,
            result.output_tokens,
        )
        self.spent += cost
        return cost

    def charge_error(self, error: LLMError, kind: CallKind) -> Decimal:
        """Adds and returns the cost of a failed call of `kind`."""
        if error.usage is not None:
            usage = error.usage
            cost = turn_cost(
                usage.model,
                usage.input_tokens,
                usage.cached_input_tokens,
                usage.output_tokens,
            )
        elif error.billed_without_usage:
            cost = estimate(kind)
        else:
            cost = Decimal(0)
        self.spent += cost
        return cost

    def can_start(self, kind: CallKind) -> bool:
        """Whether one more call of `kind` stays within the cap at its estimate."""
        return self.spent + estimate(kind) <= self.cap_usd
