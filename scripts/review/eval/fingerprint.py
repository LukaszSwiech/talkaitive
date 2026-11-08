"""One hash of everything that decides a review's verdict, except the model.

A result file carries it, and `tests/test_review_eval.py` compares it with the
current code, so a change of the prompt, the schema, a call constant or the verdict
rule without a new eval run turns CI red. The prompt is hashed as its template: the
delimiter in the sent prompt is random per run. The schema is the one the OpenAI SDK
sends, so an `openai` or `pydantic` upgrade can change the hash too.
"""

import hashlib
import json
from typing import Any

from openai.lib._pydantic import to_strict_json_schema

from scripts.review import criteria, run_review


def fingerprint_inputs() -> dict[str, Any]:
    """The hashed values, read from the reviewer's modules at call time."""
    return {
        "instructions": run_review._INSTRUCTIONS,
        "truncated_instruction": run_review._TRUNCATED_INSTRUCTION,
        "schema": to_strict_json_schema(criteria.Review),
        "max_output_tokens": run_review.MAX_OUTPUT_TOKENS,
        "reasoning_effort": run_review.REASONING_EFFORT,
        "max_diff_chars": run_review.MAX_DIFF_CHARS,
        "excluded_paths": list(run_review.EXCLUDED_PATHS),
        "fail_floor": criteria.FAIL_FLOOR,
        "blockers": list(criteria.BLOCKERS),
    }


def fingerprint() -> str:
    """Hex sha256 of the inputs as canonical JSON."""
    canonical = json.dumps(
        fingerprint_inputs(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
