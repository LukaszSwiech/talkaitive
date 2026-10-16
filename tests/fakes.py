"""Stand-ins for the two model calls, patched into `conversations.services`.

Nothing that uses them touches the network. Each call takes the next queued
outcome: a result, an exception to raise, or a function called with the same kwargs
(for a scenario that changes the database while the "model" is working). With an
empty queue the fake returns `default()`.

Also `add_charge`, the one way tests seed the cost ledger (`LLMCharge`).
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from conversations.llm import AnalysisResult, TurnResult
from conversations.models import Conversation, LLMCharge

TurnOutcome = TurnResult | Exception | Callable[..., TurnResult]
AnalysisOutcome = AnalysisResult | Exception | Callable[..., AnalysisResult]


class FakeGenerateTurn:
    """Stands in for `llm.generate_turn`."""

    def __init__(self, default: Callable[[], TurnResult]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[TurnOutcome] = []
        self._default = default

    def __call__(self, **kwargs: Any) -> TurnResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else self._default()
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, TurnResult):
            return outcome
        return outcome(**kwargs)


class FakeAnalyzeMistakes:
    """Stands in for `llm.analyze_mistakes`."""

    def __init__(self, default: Callable[[], AnalysisResult]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[AnalysisOutcome] = []
        self._default = default

    def __call__(self, **kwargs: Any) -> AnalysisResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else self._default()
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, AnalysisResult):
            return outcome
        return outcome(**kwargs)


def add_charge(conversation: Conversation, cost: str, at: datetime) -> LLMCharge:
    """A ledger entry: a paid call that left no message and no analysis result.

    Dated by `at`, like the service's `now`, not by the real clock.
    """
    return LLMCharge.objects.create(
        user=conversation.user,
        conversation=conversation,
        kind=LLMCharge.Kind.TURN,
        reason=LLMCharge.Reason.ESTIMATE,
        cost_usd=Decimal(cost),
        charged_at=at,
    )
