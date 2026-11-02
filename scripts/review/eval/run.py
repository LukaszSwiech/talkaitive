"""The AI review model eval runner; local and manual, never in CI.

    uv run --env-file .env python -m scripts.review.eval.run --repeats 3 --max-usd 10

`--dry-run` stops before promptfoo; `--fake` runs it with a canned review (no
network, no spend); `--smoke` reviews one small case once; `--out DIR` (outside the
repo) is a trial. Exit: 0 complete, 1 runtime error, 2 configuration error or a
reservation refused mid-repeat (partial result, `complete: false`). Decision rule:
`pick_winner`.
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scripts.review.eval import provider
from scripts.review.eval.assertion import judge
from scripts.review.eval.budget import (
    DEFAULT_LEDGER,
    Ledger,
    LedgerError,
    worst_case_usd,
)
from scripts.review.eval.cases import CASES, REPO, Case, get_case
from scripts.review.eval.fingerprint import fingerprint
from scripts.review.eval.models import MODELS, PRICES_CHECKED, EvalModel, get_model
from scripts.review.run_review import LLM_MODEL, ConfigError

HERE = Path(__file__).resolve().parent
CONFIG, RESULTS_DIR = HERE / "promptfooconfig.yaml", HERE / "results"
VENV_PYTHON = REPO / ".venv" / "bin" / "python"
PROMPTFOO_VERSION = "0.125.1"
MAX_RESULT_CHARS = 20_000
SMOKE_CASE = "pass-settings-env"
# One repeat of a (case, model) in the result file; `regular_usd` null = `usd`.
REPEAT_FIELDS = (
    "verdict",
    "failed",
    "low",
    "error",
    "usd",
    "regular_usd",
    "ms",
    "served",
)
COUNTERS = (
    "runs hard_false_passes false_fails hard_pass_runs model_errors unmeasured_hard "
    "wrong_blocker warnings_detected warning_runs soft_detected soft_runs"
).split()


class EvalError(Exception):
    """A runtime failure with a fixed-format message."""


def check_node(version: str) -> str:
    if tuple(int(n) for n in re.findall(r"\d+", version)[:3]) < (22, 22, 0):
        raise ConfigError(f"promptfoo {PROMPTFOO_VERSION} needs Node >= 22.22.0")
    return version.strip()


def promptfoo_command(global_version: str | None) -> list[str]:
    if (global_version or "").strip() == PROMPTFOO_VERSION:
        return ["promptfoo"]
    return ["npx", "-y", f"promptfoo@{PROMPTFOO_VERSION}"]


def missing_keys(models: Sequence[EvalModel], env: Mapping[str, str]) -> list[str]:
    names = dict.fromkeys(provider.KEY_ENV[m.route] for m in models)
    return [name for name in names if not env.get(name, "").strip()]


def worst_case_per_repeat(
    models: Sequence[EvalModel], chars: Mapping[str, int]
) -> dict[str, Decimal]:
    return {
        m.label: sum((worst_case_usd(m, c) for c in chars.values()), Decimal(0))
        for m in models
    }


def _out(*args: str) -> str | None:
    try:
        done = subprocess.run(
            args, cwd=REPO, capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def row_record(row: Mapping[str, Any]) -> tuple[str, str, list[Any]]:
    """(case id, model label, repeat in `REPEAT_FIELDS` order) of a promptfoo row."""
    response = row.get("response") or {}
    meta = response.get("metadata") or {}
    error = meta.get("error_kind")
    # `failureReason` 2 is a provider error; 1, a failed assertion, is a measurement.
    if error is None and (response.get("error") or row.get("failureReason") == 2):
        error = "api:promptfoo"
    verdict = failed = low = None
    if error is None:
        try:
            verdict, failed, low = judge(
                response.get("output"), bool(meta["truncated"])
            )
        except (KeyError, ValidationError):
            error = "schema"
    usd = round(meta.get("cost_usd") or 0.0, 5)
    regular = round(meta.get("regular_usd") or 0.0, 5)
    record = [verdict, failed, low, error, usd, None if regular == usd else regular]
    record += [meta.get("latency_ms"), meta.get("served_provider")]
    return row["vars"]["case_id"], meta.get("model") or row["provider"]["label"], record


def _add(a: dict[str, Any], case: Case, r: dict[str, Any]) -> None:
    error, verdict = r["error"], r["verdict"]
    if error is not None and error not in provider.MODEL_ERRORS:
        a["infra_errors"][error] = a["infra_errors"].get(error, 0) + 1
        a["unmeasured_hard"] += case.tier == "hard"
        return
    a["runs"] += 1
    a["model_errors"] += error is not None
    a["usd"].append(r["usd"])
    a["regular"].append(r["usd"] if r["regular_usd"] is None else r["regular_usd"])
    if error is None:
        a["ms"].append(r["ms"])
    if case.tier == "soft":
        a["soft_runs"] += 1
        a["soft_detected"] += verdict == "fail"
    elif case.expected_verdict == "pass":
        # A model error blocks a good PR, as production exits 1.
        a["hard_pass_runs"] += 1
        a["false_fails"] += verdict != "pass"
        if case.expected_warnings:
            a["warning_runs"] += 1
            a["warnings_detected"] += set(case.expected_warnings) <= set(r["low"] or ())
    elif verdict == "pass":
        a["hard_false_passes"] += 1
    elif verdict == "fail" and not set(case.expected_blockers) <= set(r["failed"]):
        a["wrong_blocker"] += 1


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def aggregate(entries: Sequence[Mapping[str, Any]], repeats: int) -> dict[str, dict]:
    """The matrix per model, from the result file's entries alone.

    An entry is one case: `{"case": id, <model label>: [repeat, ...], ...}`.
    """
    acc: dict[str, dict[str, Any]] = {}
    for entry in entries:
        case = get_case(entry["case"])
        for label, records in entry.items():
            if label == "case":
                continue
            a = acc.setdefault(
                label,
                dict.fromkeys(COUNTERS, 0)
                | {
                    "infra_errors": {},
                    "usd": [],
                    "regular": [],
                    "ms": [],
                    "stable": [],
                },
            )
            for record in records:
                _add(a, case, dict(zip(REPEAT_FIELDS, record, strict=True)))
            a["stable"].append(len({record[0] or record[3] for record in records}) == 1)
    for a in acc.values():
        usd, regular, ms, stable = (
            a.pop(k) for k in ("usd", "regular", "ms", "stable")
        )
        a |= {
            "disqualified": a["hard_false_passes"] > 0,
            "false_fail_rate": _ratio(a["false_fails"], a["hard_pass_runs"]),
            "model_error_rate": _ratio(a["model_errors"], a["runs"]),
            "warning_rate": _ratio(a["warnings_detected"], a["warning_runs"]),
            "soft_rate": _ratio(a["soft_detected"], a["soft_runs"]),
            "mean_usd": round(statistics.fmean(usd), 6) if usd else None,
            "mean_regular_usd": round(statistics.fmean(regular), 6)
            if regular
            else None,
            "median_ms": round(statistics.median(ms)) if ms else None,
            "stability": _ratio(sum(stable), len(stable)) if repeats >= 2 else "n/a",
        }
    return acc


def pick_winner(matrix: Mapping[str, Mapping[str, Any]]) -> tuple[str | None, str]:
    """D8 then D9: a hard false pass, or a hard case left unmeasured by an infra
    error, disqualifies; the rest rank by false-fail rate, mean cost at regular
    prices, then median latency; a full tie goes to the model listed first."""
    eligible = [
        k for k, a in matrix.items() if not (a["disqualified"] or a["unmeasured_hard"])
    ]
    if not eligible:
        return None, "no model qualifies: keep gpt-5.4"
    keys = ("false_fail_rate", "mean_regular_usd", "median_ms")

    def rank(label: str) -> list[float]:
        return [
            float("inf") if matrix[label][k] is None else matrix[label][k] for k in keys
        ]

    return min(eligible, key=rank), f"ranked by {', '.join(keys)} among {eligible}"


def render_json(result: Mapping[str, Any]) -> str:
    """Compact JSON with one top-level key, list item or map item per line."""

    def dump(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"))

    parts = []
    for key, value in result.items():
        if isinstance(value, dict) and value:
            lines = [f"{dump(k)}:{dump(v)}" for k, v in value.items()]
            parts.append(f"{dump(key)}:{{\n" + ",\n".join(lines) + "\n}")
        elif isinstance(value, list | tuple) and value:
            parts.append(f"{dump(key)}:[\n" + ",\n".join(map(dump, value)) + "\n]")
        else:
            parts.append(f"{dump(key)}:{dump(value)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def render_markdown(result: Mapping[str, Any]) -> str:
    matrix = result["aggregate"]
    columns = list(next(iter(matrix.values()), {}))
    lines = [
        f"# AI review model eval {result['created_at']}\n",
        f"Commit `{result['git_sha']}`, repeats {result['repeats_completed']} of "
        f"{result['repeats_requested']} (skipped for budget: "
        f"{result['repeats_skipped_budget']}), complete: {result['complete']}, "
        f"fake: {result['fake']}. Winner: {result['winner']} "
        f"({result['winner_reason']}).\n",
        "| model | " + " | ".join(columns) + " |",
        "|---" * (len(columns) + 1) + "|",
    ]
    for label, a in matrix.items():
        lines.append(f"| {label} | " + " | ".join(str(v) for v in a.values()) + " |")
    lines += [f"\n- {link}" for link in result["share_links"] if link]
    return "\n".join(lines) + "\n"


def write_result(result: Mapping[str, Any], directory: Path, stem: str) -> Path:
    """`<stem>.json` and `.md`; never overwrites, refuses above `MAX_RESULT_CHARS`."""
    text = render_json(result)
    if len(text) > MAX_RESULT_CHARS:
        raise EvalError(
            f"the result has {len(text)} characters, over {MAX_RESULT_CHARS}"
        )
    path, markdown = directory / f"{stem}.json", directory / f"{stem}.md"
    if path.exists() or markdown.exists():
        raise EvalError(f"{path.name} exists; results are never overwritten")
    directory.mkdir(parents=True, exist_ok=True)
    for target, content in ((path, text), (markdown, render_markdown(result))):
        with target.open("x", encoding="utf-8") as file:
            file.write(content)
    return path


def _prices(model: EvalModel) -> dict[str, Any]:
    pairs = (("prices", model.prices), ("regular_prices", model.regular_prices))
    return {k: {n: str(v) for n, v in p.items()} for k, p in pairs if p}


def run(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="AI review model eval.")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-usd", type=Decimal, default=Decimal(10))
    parser.add_argument("--models", default="", help="labels, comma-separated")
    for flag in ("--smoke", "--dry-run", "--fake", "--share"):
        parser.add_argument(flag, action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args(argv)
    try:
        labels = [label for label in args.models.split(",") if label]
        models = [get_model(label) for label in labels] or list(MODELS)
    except KeyError as exc:
        raise ConfigError(f"unknown model {exc}") from None
    cases = [get_case(SMOKE_CASE)] if args.smoke else list(CASES)
    repeats, trial = 1 if args.smoke else args.repeats, args.out is not None
    if repeats < 1 or (args.share and (args.fake or args.dry_run)):
        raise ConfigError("--repeats must be >= 1, and --share needs a real run")
    if (args.fake or args.smoke) and not trial:
        raise ConfigError("--fake and --smoke are trials: pass --out")
    if trial and args.out.resolve().is_relative_to(REPO):
        raise ConfigError("--out must be outside the repo")
    if not (trial or args.dry_run) and _out("git", "status", "--porcelain") != "":
        raise ConfigError("the tree is dirty: commit first, or pass --out for a trial")
    node = check_node(_out("node", "--version") or "")
    command = promptfoo_command(_out("promptfoo", "--version"))
    missing = [] if args.fake else missing_keys(models, os.environ)
    if missing or not VENV_PYTHON.exists():
        raise ConfigError(f"missing or empty: {', '.join(missing) or VENV_PYTHON}")

    ledger = Ledger(args.ledger, args.max_usd)
    print(f"reviewer model: {LLM_MODEL}; fingerprint: {fingerprint()}; node {node}")
    chars = {c.id: provider.input_chars(provider.prepare(c)[0]) for c in cases}
    worst = worst_case_per_repeat(models, chars)
    for label, usd in worst.items():
        print(f"worst case per repeat, {label}: {usd:.4f} USD ({len(cases)} calls)")
    total, left = sum(worst.values(), Decimal(0)), ledger.remaining()
    fit = max(0, min(repeats, int(left // total)))
    print(f"worst case per repeat, all models: {total:.4f} USD")
    print(
        f"ledger: {left:.4f} USD left of the cap; repeats that fit: {fit} of {repeats}"
    )
    if args.dry_run:
        return 0
    if fit == 0 and not args.fake:
        raise ConfigError("not even one repeat fits the budget")

    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
    raw = (args.out / "raw" if trial else DEFAULT_LEDGER.parent / "runs") / run_id
    raw.mkdir(parents=True)
    share_env = {k: v for k, v in os.environ.items() if k != provider.FAKE_ENV}
    env = share_env | {
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "PROMPTFOO_DISABLE_SHARING": "true",
        "PROMPTFOO_PYTHON": str(VENV_PYTHON),
        "PYTHONPATH": str(REPO),
        provider.LEDGER_ENV: str(args.ledger.expanduser().resolve()),
        provider.MAX_USD_ENV: str(args.max_usd),
    }
    env |= {provider.FAKE_ENV: "1"} if args.fake else {}
    pattern = "|".join(re.escape(m.label) for m in models)
    flags = ["--no-cache", "--no-share", "-j", "4", "--no-table", "--no-progress-bar"]
    flags += ["--filter-providers", f"^({pattern})$"]
    flags += ["--filter-pattern", f"^{SMOKE_CASE}$"] if args.smoke else []

    def promptfoo(log: str, *more: str, environ: dict[str, str] = env) -> str:
        done = subprocess.run(
            [*command, *more], cwd=REPO, env=environ, capture_output=True, timeout=3600
        )
        (raw / f"{log}.log").write_bytes(done.stdout + done.stderr)
        # 100: some assertions failed, which is what an eval measures.
        if done.returncode not in (0, 100):
            raise EvalError(f"promptfoo exited {done.returncode}; log in {raw}")
        return done.stdout.decode(errors="replace")

    table: dict[tuple[str, str], list[list[Any]]] = {}
    eval_ids: list[str] = []
    completed = skipped = 0
    stopped = False
    for index in range(1, repeats + 1):
        if not args.fake and total > ledger.remaining():
            skipped = repeats - index + 1
            break
        out = raw / f"repeat-{index}.json"
        promptfoo(f"repeat-{index}", "eval", "-c", str(CONFIG), *flags, "-o", str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        eval_ids.append(data["evalId"])
        for row in data["results"]["results"]:
            case_id, label, record = row_record(row)
            table.setdefault((case_id, label), []).append(record)
            stopped |= record[3] == "budget"
        if stopped:
            break
        completed += 1
    complete = completed >= 1 and not stopped
    links = []
    for eval_id in eval_ids if args.share and complete else []:
        shared = promptfoo(f"share-{eval_id}", "share", eval_id, environ=share_env)
        links.append(next(iter(re.findall(r"https://\S+", shared)), None))
    entries = [
        {"case": c.id}
        | {m.label: table[c.id, m.label] for m in models if (c.id, m.label) in table}
        for c in cases
    ]
    matrix = aggregate(entries, completed)
    winner, reason = pick_winner(matrix)
    sha = (_out("git", "rev-parse", "--short", "HEAD") or "unknown").strip()
    result = {
        "created_at": run_id,
        "git_sha": sha,
        "fake": args.fake,
        "fingerprint": fingerprint(),
        "promptfoo_version": PROMPTFOO_VERSION,
        "node_version": node,
        "prices_checked": PRICES_CHECKED,
        "ledger_spent_usd": str(ledger.spent()),
        "repeats_requested": repeats,
        "repeats_completed": completed,
        "repeats_skipped_budget": skipped,
        "complete": complete,
        "share_links": links,
        "winner": winner,
        "winner_reason": reason,
        "models": [
            {"label": m.label, "api_id": m.api_id, "route": m.route} | _prices(m)
            for m in models
        ],
        "cases": [
            {"id": c.id, "tier": c.tier, "expected": c.expected_verdict}
            | {"blockers": c.expected_blockers, "warnings": c.expected_warnings}
            for c in cases
        ],
        "aggregate": matrix,
        "repeat_fields": REPEAT_FIELDS,
        "entries": entries,
    }
    # The copy outside the repo survives a refusal of the committed one.
    (raw / "result.json").write_text(render_json(result), encoding="utf-8")
    path = write_result(result, args.out or RESULTS_DIR, f"{run_id}-{sha}")
    print(f"result: {path} ({len(table)} case-model entries); complete: {complete}")
    print(f"winner: {winner}")
    return 0 if complete else 2


def main(argv: Sequence[str]) -> int:
    try:
        return run(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    except (ConfigError, EvalError, LedgerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, ConfigError) else 1
    except Exception as exc:  # the type only: exception text can quote the model
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
