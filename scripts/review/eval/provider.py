"""promptfoo provider: one review of one case by one model, on the shared ledger.

Runs in promptfoo's workers; `run.py` sets the interpreter, `PYTHONPATH`, the ledger
and the cap. Errors and metadata are fixed kinds and numbers, never the diff, model
text or a key (the trust rule of `run_review.py`).
"""

import os
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from openai import LengthFinishReasonError, OpenAI
from pydantic import ValidationError

from scripts.review.criteria import CRITERIA, Review
from scripts.review.eval import budget
from scripts.review.eval.cases import Case, get_case, materialise
from scripts.review.eval.models import EvalModel, get_model
from scripts.review.run_review import (
    MAX_OUTPUT_TOKENS,
    REASONING_EFFORT,
    TIMEOUT_SECONDS,
    _build_input,
    truncate_diff,
)

FAKE_ENV = "REVIEW_EVAL_FAKE"  # set only by `run.py --fake`
LEDGER_ENV = "REVIEW_EVAL_LEDGER"
MAX_USD_ENV = "REVIEW_EVAL_MAX_USD"
KEY_ENV = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
# Count against the model; `budget`, `config` and `api:*` are infra errors.
MODEL_ERRORS = ("schema", "no_output", "incomplete")


def prepare(case: Case) -> tuple[list[Any], bool]:
    """The reviewer's messages for the case's diff, and whether the diff was cut."""
    full = materialise(case)
    diff, _ = truncate_diff(full)
    return _build_input(diff, len(diff) < len(full)), len(diff) < len(full)


def input_chars(messages: list[Any]) -> int:
    return sum(len(message["content"]) for message in messages)


@dataclass
class Outcome:
    review: Review | None = None
    error: str | None = None
    usage: budget.Usage | None = None
    reasoning: int = 0
    status: str | None = None
    served: str | None = None


def _n(obj: Any, name: str) -> int:
    return getattr(obj, name, None) or 0


def _call_openai(model: EvalModel, key: str, messages: list[Any]) -> Outcome:
    # As `run_review._call_model`, with the eval's model.
    response = OpenAI(
        api_key=key, timeout=TIMEOUT_SECONDS, max_retries=0
    ).responses.parse(
        model=model.api_id,
        input=messages,
        text_format=Review,
        reasoning={"effort": REASONING_EFFORT},
        max_output_tokens=MAX_OUTPUT_TOKENS,
        store=False,
    )
    out = Outcome(review=response.output_parsed, status=response.status)
    if (u := response.usage) is not None:
        cached = _n(u.input_tokens_details, "cached_tokens")
        out.usage = budget.Usage(u.input_tokens, cached, u.output_tokens)
        out.reasoning = _n(u.output_tokens_details, "reasoning_tokens")
    if out.review is None:  # a refusal, or cut off while reasoning
        out.error = "incomplete" if response.status == "incomplete" else "no_output"
    return out


def _chat(completion: Any) -> Outcome:
    choices = completion.choices
    out = Outcome(
        review=choices[0].message.parsed if choices else None,
        status=choices[0].finish_reason if choices else None,
        served=getattr(completion, "provider", None),
    )
    if (u := completion.usage) is not None:
        billed = getattr(u, "cost", None)  # USD, as OpenRouter billed it
        out.usage = budget.Usage(
            u.prompt_tokens,
            _n(u.prompt_tokens_details, "cached_tokens"),
            u.completion_tokens,
            None if billed is None else Decimal(str(billed)),
        )
        out.reasoning = _n(u.completion_tokens_details, "reasoning_tokens")
    return out


def _call_openrouter(model: EvalModel, key: str, messages: list[Any]) -> Outcome:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )
    roles = {"developer": "system"}
    try:
        out = _chat(
            client.chat.completions.parse(
                model=model.api_id,
                messages=[
                    {"role": roles.get(m["role"], m["role"]), "content": m["content"]}
                    for m in messages
                ],
                response_format=Review,
                max_tokens=MAX_OUTPUT_TOKENS,
                extra_body={
                    "reasoning": {"effort": REASONING_EFFORT},
                    "provider": model.provider_options(),
                },
            )
        )
    except LengthFinishReasonError as exc:
        out = _chat(exc.completion)
        out.review, out.error = None, "incomplete"
    if out.review is None and out.error is None:
        out.error = "no_output"
    return out


def _fake_review() -> dict[str, Any]:
    scores = {name: {"score": 10, "rationale": "Fake mode."} for name in CRITERIA}
    return Review(**scores, verdict="pass", summary="Fake mode.").model_dump()


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> Any:
    """promptfoo's entry point; `vars.case_id` names the case."""
    model = get_model(options["config"]["model"])
    messages, truncated = prepare(get_case(context["vars"]["case_id"]))
    meta: dict[str, Any] = {"model": model.label, "truncated": truncated}
    meta |= dict.fromkeys(("status", "served_provider", "completion_tokens"))
    meta |= dict.fromkeys(("reserved_usd", "cost_usd", "regular_usd", "latency_ms"), 0)
    meta["error_kind"] = None
    if os.environ.get(FAKE_ENV) == "1":
        return {"output": _fake_review(), "metadata": meta | {"status": "fake"}}

    def error(kind: str) -> dict[str, Any]:
        return {"error": kind, "metadata": meta | {"error_kind": kind}}

    key = os.environ.get(KEY_ENV[model.route], "").strip()
    max_usd = os.environ.get(MAX_USD_ENV, "").strip()
    if not key or not max_usd:
        return error("config")
    path = Path(os.environ.get(LEDGER_ENV) or budget.DEFAULT_LEDGER)
    ledger = budget.Ledger(path, Decimal(max_usd))
    reservation = ledger.reserve(budget.worst_case_usd(model, input_chars(messages)))
    if reservation is None:
        return error("budget")
    # Without usage (an exception, or none reported) the reservation is spent.
    actual = regular = reservation.amount
    start, out = time.monotonic(), Outcome()
    try:
        call = _call_openai if model.route == "openai" else _call_openrouter
        out = call(model, key, messages)
    except ValidationError:
        out = Outcome(error="schema")
    except Exception as exc:  # the type only: exception text can quote the model
        out = Outcome(error=f"api:{type(exc).__name__}")
    finally:
        if (u := out.usage) is not None:
            actual = budget.actual_cost_usd(model, u)
            regular = budget.regular_cost_usd(model, u)
        ledger.settle(reservation, actual)
    meta |= {
        "status": out.status,
        "served_provider": out.served,
        "completion_tokens": u and u.output_tokens,
        "reserved_usd": float(reservation.amount),
        "cost_usd": float(actual),
        "regular_usd": float(regular),
        "latency_ms": round((time.monotonic() - start) * 1000),
    }
    if out.error or out.review is None:
        return error(out.error or "no_output")
    result = {
        "output": out.review.model_dump(),
        "cost": float(actual),
        "metadata": meta,
    }
    result["latencyMs"] = meta["latency_ms"]
    if u is not None:
        result["tokenUsage"] = {
            "prompt": u.input_tokens,
            "cached": u.cached_input_tokens,
            "completion": u.output_tokens,
            "total": u.input_tokens + u.output_tokens,
            "numRequests": 1,
            "completionDetails": {"reasoning": out.reasoning},
        }
    return result
