"""Hand-written mutants that mutmut cannot generate.

Removed `.for_user()` calls and query filters, module constants and prompt labels.
For each mutant the repo is copied to a temporary directory, exactly one fragment is
replaced there and the test suite runs with the project's `.venv` interpreter. The
working tree is never written, so interrupting the script is harmless.

Usage: `uv run python scripts/mutation/manual_mutants.py [ID ...]` (no IDs = all).

Exit codes: 0 every result matches its expectation, 1 at least one mismatch,
2 a configuration error (unknown ID, fragment not found exactly once, mutated
file does not compile, missing interpreter, red baseline, pytest neither passing
nor failing, pytest over the time limit).

A mutant whose survival is accepted on purpose has `expected="accepted"` and a row
in `scripts/mutation/accepted_survivors.md`.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO / ".venv" / "bin" / "python"
ACCEPTED_REGISTER = "scripts/mutation/accepted_survivors.md"

# Not needed by the tests, or heavy, or private (.env files, databases, keys).
COPY_EXCLUDES = (
    ".venv",
    ".git",
    ".claude",
    ".agents",
    ".github",
    ".vscode",
    ".DS_Store",
    ".env*",
    "*.sqlite3",
    "*.pem",
    "*.key",
    "context",
    "mutants",
    "node_modules",
    "staticfiles",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
)
PYTEST_ARGS = ("-m", "pytest", "-q", "-x", "-p", "no:cacheprovider")
# The full suite takes ~2 s; a mutant that loops forever must not hang the run.
PYTEST_TIMEOUT_S = 300

Expectation = Literal["killed", "accepted"]
Result = Literal["KILLED", "SURVIVED"]


@dataclass(frozen=True)
class Mutant:
    id: str
    area: str
    path: str
    original: str
    mutated: str
    expected: Expectation = "killed"


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        id="C1",
        area="izolacja: _get_conversation bez for_user (kontrola)",
        path="conversations/views.py",
        original="get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)",
        mutated="get_object_or_404(Conversation.objects.all(), pk=pk)",
    ),
    Mutant(
        id="C2",
        area="budżet: is_exhausted >= na > (kontrola)",
        path="conversations/budget.py",
        original="        >= settings.DAILY_BUDGET_USD\n",
        mutated="        > settings.DAILY_BUDGET_USD\n",
    ),
    # M1 and M2 share the text; only the indentation tells them apart.
    Mutant(
        id="M1",
        area="izolacja: strona główna, aktywna rozmowa bez for_user",
        path="conversations/views.py",
        original="\n    active = (\n        Conversation.objects.for_user(request.user)\n",
        mutated="\n    active = (\n        Conversation.objects\n",
    ),
    Mutant(
        id="M2",
        area="izolacja: start rozmowy (LLMError), aktywna rozmowa bez for_user",
        path="conversations/views.py",
        original="\n        active = (\n            Conversation.objects.for_user(request.user)\n",
        mutated="\n        active = (\n            Conversation.objects\n",
    ),
    Mutant(
        id="M3",
        area="izolacja: strona rozmowy, błędy bez filtra conversation=",
        path="conversations/views.py",
        original=".filter(\n                conversation=conversation\n            ),",
        mutated=".filter(),",
    ),
    Mutant(
        id="M4",
        area="budżet + izolacja: is_final_turn bez conversation__in=",
        path="conversations/budget.py",
        original=(
            "            conversation__in=Conversation.objects.for_user(user).filter(\n"
            "                pk=conversation.pk\n"
            "            ),\n"
        ),
        mutated="",
    ),
    Mutant(
        id="M5",
        area="budżet: is_exhausted ended_at__gte na __gt",
        path="conversations/budget.py",
        original="ended_at__gte=day_start(now)",
        mutated="ended_at__gt=day_start(now)",
    ),
    Mutant(
        id="M6",
        area="stan analizy: _mark_analysis_failed bez pk=",
        path="conversations/services.py",
        original=(
            "pk=conversation.pk, analyzed_at__isnull=True, "
            "analysis_started_at__isnull=True"
        ),
        mutated="analyzed_at__isnull=True, analysis_started_at__isnull=True",
    ),
    Mutant(
        id="M7",
        area="stan analizy: znacznik w toku nigdy nie ustawiany",
        path="conversations/services.py",
        original="locked.analysis_started_at = now\n",
        mutated="locked.analysis_started_at = None\n",
    ),
    Mutant(
        id="M8",
        area="stan tury agenta: agent_turn_in_progress < na <=",
        path="conversations/services.py",
        original="now - started < _agent_turn_timeout()",
        mutated="now - started <= _agent_turn_timeout()",
        expected="accepted",
    ),
    Mutant(
        id="M9",
        area="stan tury agenta: timeout tury + 30 na + 3000 s",
        path="conversations/services.py",
        original="LLM_TIMEOUT_SECONDS * attempts + 30)",
        mutated="LLM_TIMEOUT_SECONDS * attempts + 3000)",
    ),
    Mutant(
        id="M10",
        area="pamięć: MISTAKE_WINDOW_CONVERSATIONS 20 na 19",
        path="conversations/memory.py",
        original="MISTAKE_WINDOW_CONVERSATIONS = 20",
        mutated="MISTAKE_WINDOW_CONVERSATIONS = 19",
    ),
    Mutant(
        id="M11",
        area="pamięć: select_memory bez filtra status=ENDED",
        path="conversations/memory.py",
        original="            status=Conversation.Status.ENDED,\n",
        mutated="",
        expected="accepted",
    ),
    Mutant(
        id="M12",
        area='pamięć: sortowanie bez "-ended_at"',
        path="conversations/memory.py",
        original='.order_by("-ended_at", "-id")',
        mutated='.order_by("-id")',
    ),
    Mutant(
        id="M13",
        area="pamięć -> prompt: etykieta (the most recent) na 2. rozmowie",
        path="conversations/llm.py",
        original='label = " (the most recent)" if number == 1 else ""',
        mutated='label = " (the most recent)" if number == 2 else ""',
    ),
    Mutant(
        id="M14",
        area="pusta odpowiedź: generate_turn bez sprawdzenia pustej odpowiedzi",
        path="conversations/llm.py",
        original=(
            '    if parsed.reply.strip() == "":\n'
            "        # A blank reply is no answer either. "
            "Log only the fact, never the text.\n"
            '        logger.error("LLM returned a blank agent reply.")\n'
            '        raise LLMError("The model returned no usable answer.")\n'
        ),
        mutated="",
    ),
    Mutant(
        id="M15",
        area="pusta odpowiedź: sprawdzenie bez .strip() (przepuszcza same spacje)",
        path="conversations/llm.py",
        original='if parsed.reply.strip() == "":',
        mutated='if parsed.reply == "":',
    ),
)


class ConfigError(Exception):
    """The script cannot give a trustworthy result."""


def select(ids: list[str]) -> list[Mutant]:
    if not ids:
        return list(MUTANTS)
    by_id = {mutant.id: mutant for mutant in MUTANTS}
    unknown = [mutant_id for mutant_id in ids if mutant_id not in by_id]
    if unknown:
        raise ConfigError(
            f"unknown mutant id(s): {', '.join(unknown)}; known: {', '.join(by_id)}"
        )
    return [by_id[mutant_id] for mutant_id in dict.fromkeys(ids)]


def validate(mutants: list[Mutant]) -> None:
    """Every fragment occurs exactly once and the mutated file compiles (read only)."""
    problems = []
    for mutant in mutants:
        source = REPO / mutant.path
        if not source.is_file():
            problems.append(f"{mutant.id}: file {mutant.path} does not exist")
            continue
        text = source.read_text(encoding="utf-8")
        count = text.count(mutant.original)
        if count != 1:
            problems.append(
                f"{mutant.id}: fragment found {count} times in {mutant.path} "
                f"(expected exactly 1): {mutant.original!r}"
            )
            continue
        # A mutant that does not compile fails the tests for the wrong reason
        # (views.py only loads on the first request) and would look KILLED.
        try:
            compile(
                text.replace(mutant.original, mutant.mutated, 1), mutant.path, "exec"
            )
        except SyntaxError as exc:
            problems.append(
                f"{mutant.id}: mutated {mutant.path} does not compile: "
                f"{exc.msg} (line {exc.lineno})"
            )
    if problems:
        raise ConfigError("invalid mutant list:\n  " + "\n  ".join(problems))


def run_pytest(copy: Path, label: str) -> int:
    try:
        completed = subprocess.run(
            [str(VENV_PYTHON), *PYTEST_ARGS],
            cwd=copy,
            # One copy serves every mutant: a .pyc is trusted by source mtime (whole
            # seconds) and size, so a same-size mutant restored within the same
            # second would keep running. Write no bytecode at all.
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=PYTEST_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise ConfigError(
            f"{label}: pytest did not finish within {PYTEST_TIMEOUT_S} s"
        ) from None
    return completed.returncode


def run_mutant(copy: Path, mutant: Mutant) -> Result:
    target = copy / mutant.path
    original_text = target.read_text(encoding="utf-8")
    target.write_text(
        original_text.replace(mutant.original, mutant.mutated, 1), encoding="utf-8"
    )
    try:
        code = run_pytest(copy, mutant.id)
    finally:
        target.write_text(original_text, encoding="utf-8")
    # pytest: 0 all passed, 1 some test failed; anything else (collection error,
    # usage error, no tests) is not a killed mutant.
    if code == 0:
        return "SURVIVED"
    if code == 1:
        return "KILLED"
    raise ConfigError(
        f"{mutant.id}: pytest exited with {code} (neither pass nor test failure)"
    )


def matches(result: Result, expected: Expectation) -> bool:
    return (result == "KILLED") == (expected == "killed")


def main(argv: list[str]) -> int:
    try:
        mutants = select(argv)
        validate(mutants)
        if not VENV_PYTHON.is_file():
            raise ConfigError(f"project interpreter not found: {VENV_PYTHON}")
        with tempfile.TemporaryDirectory(prefix="manual-mutants-") as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(*COPY_EXCLUDES))
            baseline = run_pytest(copy, "baseline")
            if baseline != 0:
                raise ConfigError(f"baseline pytest on the copy exited with {baseline}")
            rows = []
            for mutant in mutants:
                started = time.monotonic()
                result = run_mutant(copy, mutant)
                elapsed = time.monotonic() - started
                rows.append((mutant, result))
                print(f"{mutant.id}: {result} ({elapsed:.1f} s)", flush=True)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"{'id':<4} | {'result':<8} | {'expected':<8} | match | area")
    print("-" * 80)
    mismatches = 0
    for mutant, result in rows:
        ok = matches(result, mutant.expected)
        mismatches += not ok
        expected = mutant.expected
        if expected == "accepted":
            expected += f" (see {ACCEPTED_REGISTER})"
        print(
            f"{mutant.id:<4} | {result:<8} | {expected:<8} | "
            f"{'yes' if ok else 'NO':<5} | {mutant.area}"
        )
    print()
    print(f"{len(rows)} mutants, {len(rows) - mismatches} match, {mismatches} mismatch")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
