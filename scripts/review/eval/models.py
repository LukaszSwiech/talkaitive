"""The models the review eval compares, described once.

Local and manual only: the CI reviewer itself still uses `LLM_MODEL` from the
settings. Prices are USD per 1M tokens, standard tier, checked on `PRICES_CHECKED`
(sources: `context/archive/2026-11-02-ai-review-model-eval/research.md` §3). Reasoning tokens
are billed as output on every route.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from scripts.review.cost import Prices

Route = Literal["openai", "openrouter"]

PRICES_CHECKED = "2026-11-02"

# Only what the user asked for: no provider that may store or train on the diff,
# zero retention, and only endpoints that list every parameter we send.
_OPENROUTER_POLICY: Mapping[str, Any] = {
    "data_collection": "deny",
    "require_parameters": True,
    "zdr": True,
}

# OpenRouter reports the serving provider by display name; `only` takes slugs. A
# name missing here counts as off policy in the result's matrix.
OPENROUTER_SLUGS: Mapping[str, str] = {
    "Google": "google-vertex",
    "Google AI Studio": "google-ai-studio",
    "Azure": "azure",
    "Anthropic": "anthropic",
    "Amazon Bedrock": "amazon-bedrock",
}


@dataclass(frozen=True)
class EvalModel:
    label: str
    route: Route
    api_id: str
    # List prices: `input`, `cached_input`, `output`. For a model with an intro
    # price, the intro set.
    prices: Prices
    # The highest price a call can be billed at (regional endpoint, regular price,
    # cache write); the budget reserves with these.
    worst_input: Decimal
    worst_output: Decimal
    # Uncached input may be billed at the cache-write price instead of `input`.
    cache_write_input: Decimal | None = None
    # The price after the intro ends (the day after `intro_until`).
    regular_prices: Prices | None = None
    intro_until: date | None = None
    # OpenRouter endpoints that advertise `structured_outputs`.
    openrouter_only: tuple[str, ...] = ()

    def provider_options(self) -> dict[str, Any]:
        """OpenRouter's `provider` object for this model; empty for OpenAI."""
        if self.route != "openrouter":
            return {}
        return {**_OPENROUTER_POLICY, "only": list(self.openrouter_only)}


MODELS: tuple[EvalModel, ...] = (
    # Baseline: the reviewer's model today; must equal the settings' prices.
    EvalModel(
        label="gpt-5.4",
        route="openai",
        api_id="gpt-5.4",
        prices={
            "input": Decimal("2.50"),
            "cached_input": Decimal("0.25"),
            "output": Decimal("15.00"),
        },
        worst_input=Decimal("2.50"),
        worst_output=Decimal("15.00"),
    ),
    # No dated snapshot: it can change under the same name.
    EvalModel(
        label="gpt-6.1-terra",
        route="openai",
        api_id="gpt-6.1-terra",
        prices={
            "input": Decimal("1.00"),
            "cached_input": Decimal("0.05"),
            "output": Decimal("5.00"),
        },
        worst_input=Decimal("1.25"),
        worst_output=Decimal("5.00"),
        cache_write_input=Decimal("1.25"),
    ),
    # Regional endpoints cost 10% more (2.20 / 11.00).
    EvalModel(
        label="claude-sonnet-5.5",
        route="openrouter",
        api_id="anthropic/claude-sonnet-5.5",
        prices={
            "input": Decimal("2.00"),
            "cached_input": Decimal("0.10"),
            "output": Decimal("10.00"),
        },
        worst_input=Decimal("2.20"),
        worst_output=Decimal("11.00"),
        openrouter_only=("google-vertex", "azure"),
    ),
    # Intro price until 2026-12-31; Vertex non-global endpoints cost 10% more
    # (regular 1.65 / 8.25).
    EvalModel(
        label="gemini-3.8-flash",
        route="openrouter",
        api_id="google/gemini-3.8-flash",
        prices={
            "input": Decimal("0.75"),
            "cached_input": Decimal("0.075"),
            "output": Decimal("3.75"),
        },
        worst_input=Decimal("1.65"),
        worst_output=Decimal("8.25"),
        regular_prices={
            "input": Decimal("1.50"),
            "cached_input": Decimal("0.15"),
            "output": Decimal("7.50"),
        },
        intro_until=date(2026, 12, 31),
        openrouter_only=("google-vertex",),
    ),
)


def get_model(label: str) -> EvalModel:
    """The model with `label`; `KeyError` for an unknown one."""
    for model in MODELS:
        if model.label == label:
            return model
    raise KeyError(label)
