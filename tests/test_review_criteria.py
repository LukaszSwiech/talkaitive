"""The pure part of the AI review: criteria, schema, verdict floor and cost."""

import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pydantic
import pytest
from django.conf import settings
from openai.lib._pydantic import to_strict_json_schema

from conversations.budget import turn_cost
from scripts.review.cost import (
    cost_line,
    cost_usd,
    unknown_cost_line,
    worst_case_usd,
)
from scripts.review.criteria import (
    CRITERIA,
    FAIL_FLOOR,
    CriterionScore,
    Review,
    final_verdict,
)

REPO = Path(__file__).resolve().parents[1]
PRICES = {
    "input": Decimal("2.50"),
    "cached_input": Decimal("0.25"),
    "output": Decimal("15.00"),
}
SIX_CRITERIA = {
    "data_isolation",
    "type_hints",
    "tests",
    "no_secrets",
    "openai_boundary",
    "ui_contract",
}


def make_review(verdict: str = "pass", **scores: int) -> Review:
    """A review with every criterion at 9, except the `scores` given."""
    fields: dict[str, Any] = {
        name: {"score": scores.get(name, 9), "rationale": "why"} for name in CRITERIA
    }
    return Review(**fields, verdict=verdict, summary="Looks fine.")


# --- criteria and schema ------------------------------------------------------------


def test_strict_schema_requires_all_six_criteria_and_the_verdict() -> None:
    schema = to_strict_json_schema(Review)

    assert set(CRITERIA) == SIX_CRITERIA
    assert set(schema["required"]) == SIX_CRITERIA | {"verdict", "summary"}


@pytest.mark.parametrize("name", sorted(SIX_CRITERIA))
def test_each_criterion_description_says_what_1_and_10_mean(name: str) -> None:
    description = to_strict_json_schema(Review)["properties"][name]["description"]

    assert re.search(r"\b1\b", description)
    assert re.search(r"\b10\b", description)
    # Otherwise the floor would fail every backend PR on the UI criterion.
    assert "does not touch" in description


@pytest.mark.parametrize("score", [0, 11])
def test_score_outside_1_to_10_is_rejected(score: int) -> None:
    with pytest.raises(pydantic.ValidationError):
        CriterionScore(score=score, rationale="why")


def test_openai_boundary_description_names_both_exemptions() -> None:
    description = Review.model_fields["openai_boundary"].description

    assert description is not None
    assert "scripts/review/" in description
    assert "tests/" in description


# --- verdict floor ------------------------------------------------------------------


def test_model_pass_with_scores_above_the_floor_stays_pass() -> None:
    assert final_verdict(make_review("pass")) == "pass"


def test_model_fail_with_high_scores_stays_fail() -> None:
    assert final_verdict(make_review("fail")) == "fail"


@pytest.mark.parametrize("name", sorted(SIX_CRITERIA))
def test_any_score_at_the_floor_turns_a_pass_into_fail(name: str) -> None:
    assert final_verdict(make_review("pass", **{name: FAIL_FLOOR})) == "fail"


def test_score_just_above_the_floor_stays_pass() -> None:
    assert final_verdict(make_review("pass", tests=FAIL_FLOOR + 1)) == "pass"


# --- cost ---------------------------------------------------------------------------


def test_cost_usd_matches_hand_computed_value() -> None:
    # (200 * 2.50 + 1000 * 0.25 + 40 * 15.00) / 1,000,000
    assert cost_usd(PRICES, 1200, 1000, 40) == Decimal("0.00135")


def test_cost_usd_equals_the_apps_turn_cost() -> None:
    """Drift guard: the script cannot import `turn_cost`, so it mirrors the formula."""
    model = "gpt-5.4"

    assert cost_usd(
        settings.LLM_PRICES_USD_PER_MTOK[model], 1234, 567, 89
    ) == turn_cost(model, 1234, 567, 89)


def test_worst_case_usd_at_the_diff_and_output_caps() -> None:
    # (20,000 * 2.50 + 6,000 * 15.00) / 1,000,000, no cached discount
    assert worst_case_usd(PRICES, 60_000, 6_000) == Decimal("0.14")


def test_cost_line_format() -> None:
    assert (
        cost_line("gpt-5.4", Decimal("0.00135"), 1200, 1000, 40)
        == "cost: 0.001350 USD (model=gpt-5.4 input=1200 cached=1000 output=40)"
    )


def test_unknown_cost_line_format() -> None:
    assert (
        unknown_cost_line(Decimal("0.14"))
        == "cost: unknown (worst case about 0.14 USD)"
    )


# --- standalone -----------------------------------------------------------------------


def test_modules_import_in_a_clean_interpreter_without_django_setup() -> None:
    code = (
        "import sys\n"
        "import scripts.review.cost, scripts.review.criteria\n"
        "from django.apps import apps\n"
        "assert not apps.ready\n"
        "assert 'talkaitive.settings' not in sys.modules\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
