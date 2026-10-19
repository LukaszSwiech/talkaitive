"""AI eval on the real model: run the golden set, or compare two runs.

Calls `conversations.llm` directly (no database, no app budget) on the golden set
in `golden.py`, scores every answer with `scoring.py` and writes one JSON result.
Local and manual only, never in CI: run it before and after a change of the turn
prompt, the analysis prompt, the memory block text, `LLM_MODEL` or a reasoning
effort.

Usage:

    uv run --env-file .env python scripts/eval/run_eval.py run \
        [--suite analysis,turn,memory,latency] [--repeats 3] [--max-usd 5] \
        [--out PATH]
    uv run python scripts/eval/run_eval.py compare A.json B.json

Series (`--suite`, default all four):

- analysis: each short chat of `ANALYSIS_CASES` through `llm.analyze_mistakes`;
  recall, category accuracy, extras, typo_free, notes_questions; hard rules A1-A5.
- turn: each `TURN_CASES` history through `llm.generate_turn`; recast,
  lecture_free, one_question; T1.
- memory: an opening turn of each `MEMORY_CASES` scene with its notes as the memory
  block; no_repeat; T1.
- latency: one long analysis (`LATENCY_CASE`) once per run, only timed and priced,
  against the analysis timeout and Railway's proxy limit.

Repetitions are the outer loop (`--repeats`, K), the series run one after another
inside it, calls are sequential. No seed and no temperature: production sets
neither.

Cost: counted like the app (`cost.CostMeter`), including failed calls. Before the
run the script prints the number of calls per series, the estimate (calls times the
settings' per-call estimates, an upper bound) and the cap. Before every call it
checks that the spend plus that call's estimate stays within `--max-usd`; when it
would not, the partial result is written with `"complete": false`.

The result goes to `scripts/eval/results/<YYYY-MM-DD>-<model>-<commit>[-dirty].json`
(or `--out`); `-dirty` marks a run on modified tracked files. The key is never
printed or written.

Exit codes (`run`): 0 complete run, no hard-rule violation and no failed call;
1 complete run with violations or failed calls (listed with the case id); 2 a
configuration error, no real `OPENAI_API_KEY` (empty or the test settings' value),
or the cost cap reached (partial result written).

Exit codes (`compare`): 0 the comparison was printed; 2 a file is missing or not a
result of this script.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.eval.cost import CostMeter

REPO = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO / "scripts" / "eval" / "results"

SUITES = ("analysis", "turn", "memory", "latency")
# The value `talkaitive.settings_test` sets; it must never reach the model.
TEST_KEY = "test-key"
LANGUAGE = "de"
# Railway's proxy drops a request after 5 minutes without data
# (context/foundation/infrastructure.md); reported next to the long analysis.
RAILWAY_PROXY_LIMIT_S = 300
DATA_LICENCE = (
    "Learner messages: MERLIN Written Learner Corpus for Czech, German, Italian 1.1 "
    "(Wisniewski et al., Eurac Research), http://hdl.handle.net/20.500.12124/6, "
    "CC BY-SA 4.0; adapted in scripts/eval/golden.py (CC BY-SA 4.0)."
)


class ConfigError(Exception):
    """The script cannot run or cannot read its input."""


def result_filename(day: date, model: str, commit: str, dirty: bool) -> str:
    """`<YYYY-MM-DD>-<model>-<commit>[-dirty].json`."""
    suffix = "-dirty" if dirty else ""
    return f"{day.isoformat()}-{model}-{commit}{suffix}.json"


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def git_state() -> tuple[str, bool]:
    """(short commit, dirty): dirty when tracked files differ from the commit.

    Untracked files (e.g. earlier result files) do not count. Without git the
    commit is "nogit" and the run counts as dirty.
    """
    commit = _git("rev-parse", "--short", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    if commit is None or status is None:
        return "nogit", True
    return commit, status != ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _setup_django() -> None:
    """Settings of the app (a test run keeps its own), then `django.setup()`."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "talkaitive.settings")
    import django

    django.setup()


@dataclass
class _Run:
    """The state of one `run`, filled while the calls go."""

    meter: "CostMeter"
    calls: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    # Successful scores per series and case, for `scoring.aggregate`.
    scores: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    errors: list[tuple[str, str, int, str]] = field(default_factory=list)
    latency: dict[str, Any] | None = None
    complete: bool = True


def _parse_run_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_eval.py run")
    parser.add_argument("--suite", default=",".join(SUITES))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-usd", default="5")
    parser.add_argument("--out", type=Path)
    return parser.parse_args(argv)


def _suites(text: str) -> list[str]:
    names = [name.strip() for name in text.split(",") if name.strip()]
    unknown = [name for name in names if name not in SUITES]
    if unknown or not names:
        raise ConfigError(
            f"unknown or empty --suite {text!r}; choose from {', '.join(SUITES)}"
        )
    # Always in the documented order, each once.
    return [name for name in SUITES if name in names]


def _analysis_output(result: Any) -> dict[str, Any]:
    return {
        "mistakes": [mistake.model_dump() for mistake in result.mistakes],
        "learner_facts": list(result.learner_facts),
        "scene_notes": list(result.scene_notes),
        "model": result.model,
        "input_tokens": result.input_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "output_tokens": result.output_tokens,
    }


def _turn_output(result: Any) -> dict[str, Any]:
    return {
        "reply": result.reply,
        "end_conversation": result.end_conversation,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "output_tokens": result.output_tokens,
    }


def _call(
    state: _Run, kind: str, function: Callable[..., Any], **kwargs: Any
) -> tuple[Any | None, float, Decimal, str | None]:
    """One timed and priced model call: (result or None, seconds, cost, error)."""
    from conversations.llm import LLMError

    started = time.monotonic()
    try:
        result = function(**kwargs)
    except LLMError as exc:
        seconds = time.monotonic() - started
        return None, seconds, state.meter.charge_error(exc, kind), str(exc)
    seconds = time.monotonic() - started
    return result, seconds, state.meter.charge_result(result), None


def _run_series(state: _Run, suite: str, repetition: int) -> bool:
    """One repetition of one series; False when the cap stopped it."""
    from conversations import llm
    from conversations.memory import Memory
    from conversations.topics import get_topic

    from . import golden, scoring

    cases: Sequence[Any]
    if suite == "analysis":
        cases, kind = golden.ANALYSIS_CASES, "analysis"
    elif suite == "turn":
        cases, kind = golden.TURN_CASES, "turn"
    else:
        cases, kind = golden.MEMORY_CASES, "turn"

    for case in cases:
        if not state.meter.can_start(kind):
            return False
        if suite == "analysis":
            result, seconds, cost, error = _call(
                state,
                kind,
                llm.analyze_mistakes,
                language=LANGUAGE,
                history=list(case.history),
            )
        else:
            if suite == "turn":
                history, memory = list(case.history), ""
            else:
                history = []
                memory = llm.format_memory(
                    Memory(scene_notes=[list(notes) for notes in case.scene_notes])
                )
            result, seconds, cost, error = _call(
                state,
                kind,
                llm.generate_turn,
                topic=get_topic(case.topic_key),
                language=LANGUAGE,
                history=history,
                final_turn=False,
                memory=memory,
            )

        record: dict[str, Any] = {
            "repetition": repetition,
            "seconds": round(seconds, 3),
            "cost_usd": str(cost),
            "error": error,
        }
        state.seconds[suite] = state.seconds.get(suite, 0.0) + seconds
        if result is not None:
            if suite == "analysis":
                score = scoring.score_analysis(case, result)
                record["output"] = _analysis_output(result)
                record["extras"] = [item.model_dump() for item in score.extras]
                record["neutral"] = [item.model_dump() for item in score.neutral]
            elif suite == "turn":
                score = scoring.score_turn(case, result)
                record["output"] = _turn_output(result)
                record["markers"] = list(score.markers)
            else:
                score = scoring.score_memory(case, result)
                record["output"] = _turn_output(result)
            record["metrics"] = score.metrics
            record["violations"] = [
                {"kind": finding.kind, "detail": finding.detail}
                for finding in score.findings
            ]
            state.scores.setdefault(suite, {}).setdefault(case.id, []).append(score)
        else:
            state.errors.append((suite, case.id, repetition, error or ""))
            state.scores.setdefault(suite, {}).setdefault(case.id, [])
        state.calls.setdefault(suite, {}).setdefault(case.id, []).append(record)
        status = f"error: {error}" if error else "ok"
        print(
            f"[{repetition}] {suite:<8} {case.id:<22} {seconds:6.1f} s "
            f"{cost:.4f} USD {status}",
            flush=True,
        )
    return True


def _run_latency(state: _Run) -> bool:
    """The long analysis, once; False when the cap stopped it."""
    from django.conf import settings

    from conversations import llm

    from . import golden

    if not state.meter.can_start("analysis"):
        return False
    history = list(golden.LATENCY_CASE)
    result, seconds, cost, error = _call(
        state, "analysis", llm.analyze_mistakes, language=LANGUAGE, history=history
    )
    state.seconds["latency"] = seconds
    state.latency = {
        "messages": len(history),
        "seconds": round(seconds, 3),
        "cost_usd": str(cost),
        "error": error,
        "mistakes": None if result is None else len(result.mistakes),
        "analysis_timeout_s": settings.LLM_ANALYSIS_TIMEOUT_SECONDS,
        "railway_proxy_limit_s": RAILWAY_PROXY_LIMIT_S,
        "output": None if result is None else _analysis_output(result),
    }
    if error is not None:
        state.errors.append(("latency", "latency", 1, error))
    status = f"error: {error}" if error else "ok"
    print(
        f"[-] latency  {'latency':<22} {seconds:6.1f} s {cost:.4f} USD {status}",
        flush=True,
    )
    return True


def _prompt_hashes() -> dict[str, str]:
    from conversations import llm
    from conversations.memory import Memory, PastMistake

    # A fixed sample with every section, so a change of the block's text shows.
    sample = Memory(
        learner_facts=["The learner has a dog called Waldi."],
        scene_notes=[["The partner asked where the learner works."]],
        mistakes=[
            PastMistake(
                wrong="habe ... gegangen",
                correct="bin ... gegangen",
                explanation="Gehen forms the perfect tense with sein.",
                conversations=2,
            )
        ],
    )
    return {
        "turn_instructions": _sha256(llm._INSTRUCTIONS),
        "analysis_instructions": _sha256(llm._ANALYSIS_INSTRUCTIONS),
        "memory_block": _sha256(llm.format_memory(sample)),
    }


def _summary_json(summary: Any) -> dict[str, Any]:
    return {
        "cases": summary.cases,
        "run": summary.run,
        "violations": [
            {
                "kind": v.kind,
                "case": v.case_id,
                "repetition": v.repetition,
                "detail": v.detail,
            }
            for v in summary.violations
        ],
    }


def _format_value(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _print_report(result: Mapping[str, Any]) -> None:
    print()
    print(f"{'series':<9} | {'metric':<18} | value")
    print("-" * 42)
    for suite, summary in result["aggregate"].items():
        for metric, value in summary["run"].items():
            print(f"{suite:<9} | {metric:<18} | {_format_value(value)}")
    violations = [
        (suite, v) for suite, s in result["aggregate"].items() for v in s["violations"]
    ]
    print()
    print(f"Violations: {len(violations)}")
    for suite, v in violations:
        print(f"  {v['kind']} {suite}/{v['case']} #{v['repetition']}: {v['detail']}")
    print(f"Failed calls: {len(result['errors'])}")
    for error in result["errors"]:
        print(
            f"  {error['series']}/{error['case']} #{error['repetition']}: "
            f"{error['error']}"
        )
    print()
    for suite, seconds in result["seconds"].items():
        print(f"Time {suite}: {seconds:.1f} s")
    latency = result["latency"]
    if latency is not None:
        print(
            f"Long analysis ({latency['messages']} messages): "
            f"{latency['seconds']:.1f} s, {latency['cost_usd']} USD, "
            f"{latency['mistakes']} mistakes, error: {latency['error']}; "
            f"analysis timeout {latency['analysis_timeout_s']} s, "
            f"Railway proxy limit {latency['railway_proxy_limit_s']} s"
        )
    print(
        f"Spent {result['spent_usd']} USD of {result['max_usd']} USD; "
        f"complete: {str(result['complete']).lower()}"
    )


def run(argv: Sequence[str]) -> int:
    args = _parse_run_args(argv)
    suites = _suites(args.suite)
    if args.repeats < 1:
        raise ConfigError("--repeats must be at least 1")
    try:
        cap = Decimal(args.max_usd)
    except InvalidOperation:
        raise ConfigError(f"--max-usd {args.max_usd!r} is not a number") from None
    if cap <= 0:
        raise ConfigError("--max-usd must be above 0")

    _setup_django()
    from django.conf import settings

    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == TEST_KEY:
        raise ConfigError(
            "no real OPENAI_API_KEY (empty or the test value); run with "
            "`uv run --env-file .env python scripts/eval/run_eval.py run`"
        )

    from . import golden, scoring
    from .cost import CallKind, CostMeter, estimate

    calls = {
        "analysis": len(golden.ANALYSIS_CASES) * args.repeats,
        "turn": len(golden.TURN_CASES) * args.repeats,
        "memory": len(golden.MEMORY_CASES) * args.repeats,
        "latency": 1,
    }
    kinds: dict[str, CallKind] = {
        "analysis": "analysis",
        "turn": "turn",
        "memory": "turn",
        "latency": "analysis",
    }
    estimated = sum(
        (calls[suite] * estimate(kinds[suite]) for suite in suites), Decimal(0)
    )
    print("Calls: " + ", ".join(f"{suite} {calls[suite]}" for suite in suites))
    print(
        f"Estimate: {estimated} USD (per-call estimates from the settings: turn "
        f"{estimate('turn')}, analysis {estimate('analysis')}); cap {cap} USD"
    )

    commit, dirty = git_state()
    today = date.today()
    out = args.out or RESULTS_DIR / result_filename(
        today, settings.LLM_MODEL, commit, dirty
    )
    state = _Run(meter=CostMeter(cap))
    for repetition in range(1, args.repeats + 1):
        for suite in suites:
            if suite == "latency":
                continue
            if not _run_series(state, suite, repetition):
                state.complete = False
                break
        if not state.complete:
            break
    if state.complete and "latency" in suites:
        state.complete = _run_latency(state)

    aggregate = {
        suite: _summary_json(scoring.aggregate(state.scores[suite]))
        for suite in suites
        if suite in state.scores
    }
    result: dict[str, Any] = {
        "date": today.isoformat(),
        "commit": commit,
        "dirty": dirty,
        "model": settings.LLM_MODEL,
        "reasoning_effort": {
            "turn": settings.LLM_REASONING_EFFORT,
            "analysis": settings.LLM_ANALYSIS_REASONING_EFFORT,
        },
        "prompt_sha256": _prompt_hashes(),
        "suites": suites,
        "repeats": args.repeats,
        "max_usd": str(cap),
        "spent_usd": str(state.meter.spent),
        "complete": state.complete,
        "data_licence": DATA_LICENCE,
        "seconds": {suite: round(s, 3) for suite, s in state.seconds.items()},
        "calls": state.calls,
        "aggregate": aggregate,
        "latency": state.latency,
        "errors": [
            {"series": suite, "case": case_id, "repetition": rep, "error": error}
            for suite, case_id, rep, error in state.errors
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(result)
    print(f"Result: {out}")

    if not state.complete:
        print("error: the cost cap stopped the run; the result is partial")
        return 2
    has_violations = any(s["violations"] for s in aggregate.values())
    return 1 if has_violations or state.errors else 0


def _load_result(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    required = ("model", "prompt_sha256", "aggregate")
    if not isinstance(data, dict) or any(key not in data for key in required):
        raise ConfigError(f"{path} is not a result of run_eval.py run")
    return data


def compare_files(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_eval.py compare")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    a, b = _load_result(args.a), _load_result(args.b)

    _setup_django()
    from . import scoring

    if a["model"] == b["model"] and a["prompt_sha256"] == b["prompt_sha256"]:
        print(
            "warning: same model and same prompt hashes in A and B; the "
            "difference is the model's run-to-run noise"
        )
    print(f"A: {args.a} ({a['model']}, {a.get('commit')})")
    print(f"B: {args.b} ({b['model']}, {b.get('commit')})")
    print()
    print(
        f"{'series':<9} | {'metric':<18} | {'n':>3} | {'A':>6} | {'B':>6} | "
        f"{'delta':>7} | {'95% interval':<18} | verdict"
    )
    print("-" * 96)
    changed_lines: list[str] = []
    for suite in [s for s in SUITES if s in a["aggregate"] and s in b["aggregate"]]:
        comparison = scoring.compare(
            a["aggregate"][suite]["cases"], b["aggregate"][suite]["cases"]
        )
        if comparison.only_in_a or comparison.only_in_b:
            print(
                f"warning: {suite}: the case sets differ; only in A: "
                f"{', '.join(comparison.only_in_a) or '-'}; only in B: "
                f"{', '.join(comparison.only_in_b) or '-'}"
            )
        for m in comparison.metrics:
            delta = "-" if m.mean_delta is None else f"{m.mean_delta:+.3f}"
            interval = (
                "-"
                if m.low is None or m.high is None
                else f"[{m.low:+.3f}, {m.high:+.3f}]"
            )
            print(
                f"{suite:<9} | {m.metric:<18} | {m.n:>3} | "
                f"{_format_value(m.mean_a):>6} | {_format_value(m.mean_b):>6} | "
                f"{delta:>7} | {interval:<18} | {m.verdict}"
            )
            for case_id, case_delta in m.changed:
                changed_lines.append(
                    f"  {suite}/{m.metric} {case_id}: {case_delta:+.3f}"
                )
    only = [s for s in SUITES if (s in a["aggregate"]) != (s in b["aggregate"])]
    if only:
        print(f"warning: series in only one run: {', '.join(only)}")
    print()
    print("Changed cases (B - A):")
    for line in changed_lines or ["  none"]:
        print(line)
    return 0


def main(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in ("run", "compare"):
        print("usage: run_eval.py {run,compare} ...", file=sys.stderr)
        return 2
    try:
        if argv[0] == "run":
            return run(argv[1:])
        return compare_files(argv[1:])
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        # argparse: 0 after --help, 2 on a usage error.
        return exc.code if isinstance(exc.code, int) else 2


if __name__ == "__main__":
    # Run as a file, the script's own directory is first on sys.path; the repo
    # root is needed for `talkaitive`, `conversations` and `scripts.eval`.
    sys.path.insert(0, str(REPO))
    from scripts.eval.run_eval import main as _main

    sys.exit(_main(sys.argv[1:]))
