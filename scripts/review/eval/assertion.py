"""promptfoo assertion: the reviewer's own verdict rule on the model's review.

The model's `verdict` field is never read: `final_verdict` decides, as in CI. An
expected-fail case passes only when every expected blocker failed too.
"""

from typing import Any

from pydantic import ValidationError

from scripts.review.criteria import (
    Review,
    Verdict,
    failed_blockers,
    final_verdict,
    low_warnings,
)
from scripts.review.eval.cases import get_case


def judge(output: Any, truncated: bool) -> tuple[Verdict, list[str], list[str]]:
    """Verdict, failed blockers and low warnings; `ValidationError` if not a Review."""
    if isinstance(output, str):
        review = Review.model_validate_json(output)
    else:
        review = Review.model_validate(output)
    verdict = final_verdict(review, truncated=truncated)
    return verdict, failed_blockers(review), low_warnings(review)


def get_assert(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    metadata = (context.get("providerResponse") or {}).get("metadata") or {}
    case = get_case(context["vars"]["case_id"])
    try:
        verdict, failed, low = judge(output, bool(metadata["truncated"]))
    except (KeyError, ValidationError):
        return {"pass": False, "score": 0, "reason": "no valid review"}
    expected = context["vars"]["expected_verdict"]
    passed = verdict == expected and set(case.expected_blockers) <= set(failed)
    reason = (
        f"verdict {verdict}, expected {expected}; failed blockers: "
        f"{', '.join(failed) or 'none'}; low warnings: {', '.join(low) or 'none'}"
    )
    return {"pass": passed, "score": int(passed), "reason": reason}
