"""What the AI review scores, and how the final verdict is decided.

The six TalkAItive criteria are named fields, so the schema itself forces the model
to score all six. A criterion the diff does not touch scores 10; otherwise the floor
below would fail every backend PR on the UI criterion.
"""

from typing import Literal

from pydantic import BaseModel, Field

# `Literal` rather than `Field(ge=1, le=10)`: `enum` is what `conversations/llm.py`
# already sends to the server, while `minimum`/`maximum` would need a real call to
# prove the server accepts them.
Score = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
Verdict = Literal["pass", "fail"]

# A score at or below this fails the review, whatever the model's verdict says.
FAIL_FLOOR = 3

_UNTOUCHED = "Also 10 when the diff does not touch this area."


class CriterionScore(BaseModel):
    score: Score
    rationale: str


class Review(BaseModel):
    """The model's answer: one score per criterion, a verdict and a summary."""

    data_isolation: CriterionScore = Field(
        description=(
            "Per-user data isolation: queries for per-user data go through "
            "Model.objects.for_user(request.user), and per-user models stay out of "
            "the admin. 1: a query or an admin registration exposes one user's data "
            f"to another user. 10: every such query is scoped. {_UNTOUCHED}"
        )
    )
    type_hints: CriterionScore = Field(
        description=(
            "New models, views and services are type-hinted. 1: new code has no type "
            f"hints. 10: all new code is fully type-hinted. {_UNTOUCHED}"
        )
    )
    tests: CriterionScore = Field(
        description=(
            "Changed behaviour has tests. 1: behaviour changes with no test at all. "
            f"10: every changed behaviour is covered by a test. {_UNTOUCHED}"
        )
    )
    no_secrets: CriterionScore = Field(
        description=(
            "No keys, tokens or passwords in code. 1: a real-looking secret is "
            "committed. 10: no secret values, configuration comes from env vars. "
            f"{_UNTOUCHED}"
        )
    )
    openai_boundary: CriterionScore = Field(
        description=(
            "Application code calls OpenAI only through conversations/llm.py. "
            "scripts/review/ and tests/ are exempt, so OpenAI use there is fine. "
            "1: application code outside conversations/llm.py imports or calls "
            f"OpenAI directly. 10: the boundary holds. {_UNTOUCHED}"
        )
    )
    ui_contract: CriterionScore = Field(
        description=(
            "The UI tokens and components contract: no colours, <style> or style= in "
            "templates; variants only through data-variant; colour values only in "
            "tokens.css. 1: a template hard-codes colours or styles. 10: the contract "
            f"is followed everywhere. {_UNTOUCHED}"
        )
    )
    verdict: Verdict
    summary: str = Field(description="A short review summary in Markdown.")


CRITERIA = (
    "data_isolation",
    "type_hints",
    "tests",
    "no_secrets",
    "openai_boundary",
    "ui_contract",
)


def criterion_scores(review: Review) -> dict[str, CriterionScore]:
    """Every criterion's score, by name, in `CRITERIA` order."""
    return {name: getattr(review, name) for name in CRITERIA}


def floor_failed(review: Review) -> bool:
    """Whether any criterion is at or below `FAIL_FLOOR`."""
    return any(c.score <= FAIL_FLOOR for c in criterion_scores(review).values())


def final_verdict(review: Review) -> Verdict:
    """`fail` if the model said so or any criterion is at or below `FAIL_FLOOR`.

    This can lower a verdict and never raises one, which makes a prompt-injected
    "pass" harder to obtain.
    """
    if review.verdict == "fail" or floor_failed(review):
        return "fail"
    return "pass"
