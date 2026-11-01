"""What the AI review scores, and how the final verdict is decided.

The six TalkAItive criteria are named fields, so the schema itself forces the model
to score all six. A criterion the diff does not touch scores 10; otherwise the floor
below would fail every PR that has, say, no migration in it.
"""

from typing import Literal

from pydantic import BaseModel, Field

# `Literal` rather than `Field(ge=1, le=10)`: `enum` is what `conversations/llm.py`
# already sends to the server, while `minimum`/`maximum` would need a real call to
# prove the server accepts them.
Score = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
Verdict = Literal["pass", "fail"]

# A blocker at or below this fails the review, whatever the model's verdict says. A
# warning criterion at or below this only gets a note in the comment.
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
    no_secrets: CriterionScore = Field(
        description=(
            "No keys, tokens or passwords in code. 1: a real-looking secret is "
            "committed. 10: no secret values, configuration comes from env vars. "
            f"{_UNTOUCHED}"
        )
    )
    correctness: CriterionScore = Field(
        description=(
            "Logic errors, missed cases and regressions in the changed code. 1: a "
            f"clear bug that breaks behaviour. 10: none found. {_UNTOUCHED}"
        )
    )
    migrations: CriterionScore = Field(
        description=(
            "Database migrations are safe: main auto-deploys and migrate runs "
            "pre-deploy, so this covers data loss, irreversible or locking "
            "operations, a non-null column without a default, and a model change "
            "with no migration. 1: would break or lose production data. 10: safe. "
            f"{_UNTOUCHED}"
        )
    )
    tests: CriterionScore = Field(
        description=(
            "Changed behaviour has tests. 1: behaviour changes with no test at all. "
            f"10: every changed behaviour is covered by a test. {_UNTOUCHED}"
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
    verdict: Verdict
    summary: str = Field(description="A short review summary in Markdown.")


CRITERIA = (
    "data_isolation",
    "no_secrets",
    "correctness",
    "migrations",
    "tests",
    "openai_boundary",
)
BLOCKERS = ("data_isolation", "no_secrets", "correctness", "migrations")
WARNINGS = ("tests", "openai_boundary")


def criterion_scores(review: Review) -> dict[str, CriterionScore]:
    """Every criterion's score, by name, in `CRITERIA` order."""
    return {name: getattr(review, name) for name in CRITERIA}


def _at_or_below_floor(review: Review, names: tuple[str, ...]) -> list[str]:
    return [
        name
        for name, criterion in criterion_scores(review).items()
        if name in names and criterion.score <= FAIL_FLOOR
    ]


def failed_blockers(review: Review) -> list[str]:
    """The blockers at or below `FAIL_FLOOR`, in `CRITERIA` order."""
    return _at_or_below_floor(review, BLOCKERS)


def low_warnings(review: Review) -> list[str]:
    """The warning criteria at or below `FAIL_FLOOR`, in `CRITERIA` order."""
    return _at_or_below_floor(review, WARNINGS)


def final_verdict(review: Review, *, truncated: bool) -> Verdict:
    """`fail` if the diff was cut or any blocker is at or below `FAIL_FLOOR`.

    `review.verdict` is never read: a prompt-injected "pass" cannot rescue a failed
    blocker, and the model's own "fail" cannot stop a PR alone.
    """
    if truncated or failed_blockers(review):
        return "fail"
    return "pass"
