"""Stand-ins for the two model calls, patched into `conversations.services`.

Nothing that uses them touches the network. Each call takes the next queued
outcome: a result, an exception to raise, or a function called with the same kwargs
(for a scenario that changes the database while the "model" is working). With an
empty queue the fake returns `default()`.
"""

from collections.abc import Callable
from typing import Any

from conversations.llm import AnalysisResult, TurnResult

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
