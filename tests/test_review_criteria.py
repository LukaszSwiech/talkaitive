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
    BLOCKERS,
    CRITERIA,
    FAIL_FLOOR,
    WARNINGS,
    CriterionScore,
    Review,
    failed_blockers,
    final_verdict,
    low_warnings,
)

REPO = Path(__file__).resolve().parents[1]
PRICES = {
    "input": Decimal("2.50"),
    "cached_input": Decimal("0.25"),
    "output": Decimal("15.00"),
}
SIX_CRITERIA = {
    "data_isolation",
    "no_secrets",
    "correctness",
    "migrations",
    "tests",
    "openai_boundary",
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
    # Otherwise the floor would fail every PR that has no migration in it.
    assert "does not touch" in description


def test_blockers_and_warnings_split_the_criteria_without_overlap() -> None:
    assert not set(BLOCKERS) & set(WARNINGS)
    assert set(BLOCKERS) | set(WARNINGS) == set(CRITERIA)
    assert set(BLOCKERS) == {
        "data_isolation",
        "no_secrets",
        "correctness",
        "migrations",
    }
    assert set(WARNINGS) == {"tests", "openai_boundary"}


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
    assert final_verdict(make_review("pass"), truncated=False) == "pass"


def test_model_fail_alone_does_not_fail_the_review() -> None:
    assert final_verdict(make_review("fail"), truncated=False) == "pass"


@pytest.mark.parametrize("name", BLOCKERS)
def test_a_blocker_at_the_floor_fails(name: str) -> None:
    review = make_review("pass", **{name: FAIL_FLOOR})

    assert final_verdict(review, truncated=False) == "fail"
    assert failed_blockers(review) == [name]


@pytest.mark.parametrize("name", BLOCKERS)
def test_a_blocker_just_above_the_floor_passes(name: str) -> None:
    review = make_review("pass", **{name: FAIL_FLOOR + 1})

    assert final_verdict(review, truncated=False) == "pass"
    assert failed_blockers(review) == []


@pytest.mark.parametrize("name", WARNINGS)
def test_a_warning_at_the_lowest_score_passes(name: str) -> None:
    review = make_review("pass", **{name: 1})

    assert final_verdict(review, truncated=False) == "pass"
    assert low_warnings(review) == [name]


@pytest.mark.parametrize("name", WARNINGS)
def test_low_warnings_uses_the_floor_as_its_threshold(name: str) -> None:
    assert low_warnings(make_review(**{name: FAIL_FLOOR})) == [name]
    assert low_warnings(make_review(**{name: FAIL_FLOOR + 1})) == []


def test_a_low_warning_is_not_a_failed_blocker_and_the_reverse() -> None:
    assert failed_blockers(make_review(tests=1)) == []
    assert low_warnings(make_review(correctness=1)) == []


def test_names_come_back_in_criteria_order() -> None:
    review = make_review(migrations=1, data_isolation=1, openai_boundary=1, tests=1)

    assert failed_blockers(review) == ["data_isolation", "migrations"]
    assert low_warnings(review) == ["tests", "openai_boundary"]


def test_model_pass_cannot_rescue_a_failed_blocker() -> None:
    assert final_verdict(make_review("pass", no_secrets=1), truncated=False) == "fail"


def test_truncation_fails_with_every_score_at_10_and_a_model_pass() -> None:
    perfect = make_review("pass", **{name: 10 for name in CRITERIA})

    assert final_verdict(perfect, truncated=True) == "fail"
    assert final_verdict(perfect, truncated=False) == "pass"


def test_truncated_has_to_be_named_so_a_caller_cannot_forget_it() -> None:
    with pytest.raises(TypeError):
        final_verdict(make_review())  # type: ignore[call-arg]


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
