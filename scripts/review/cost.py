"""The cost of one review, without Django.

`conversations.budget.turn_cost` cannot be imported here (it needs the Django app
registry), so the formula is mirrored; `tests/test_review_criteria.py` ties the two
together. The prices come from `talkaitive.settings.LLM_PRICES_USD_PER_MTOK`.
"""

from collections.abc import Mapping
from decimal import Decimal

Prices = Mapping[str, Decimal]

CHARS_PER_TOKEN_ESTIMATE = 3

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


def cost_usd(
    prices: Prices, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal:
    """Cost in USD of one call. `input_tokens` includes the cached ones."""
    cost = (
        (input_tokens - cached_input_tokens) * prices["input"]
        + cached_input_tokens * prices["cached_input"]
        + output_tokens * prices["output"]
    )
    return cost / _TOKENS_PER_PRICE_UNIT


def worst_case_usd(prices: Prices, input_chars: int, max_output_tokens: int) -> Decimal:
    """An estimate of the most a call can cost; no cached discount."""
    input_tokens = input_chars // CHARS_PER_TOKEN_ESTIMATE
    return cost_usd(prices, input_tokens, 0, max_output_tokens)


def cost_line(
    model: str,
    cost: Decimal,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> str:
    return (
        f"cost: {cost:.6f} USD (model={model} input={input_tokens} "
        f"cached={cached_input_tokens} output={output_tokens})"
    )


def unknown_cost_line(worst_case: Decimal) -> str:
    return f"cost: unknown (worst case about {worst_case:.2f} USD)"
