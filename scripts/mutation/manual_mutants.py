"""Hand-written mutants that mutmut cannot generate.

Removed `.for_user()` calls and query filters, deletion cleanup and signal wiring,
cascade rules, guard registries (a new route or model), module constants, prompt
labels, and the budget's cost paths (error branches in `llm.py`, which mutmut does
not mutate, ledger terms and writes, and the hard ceiling's checks), and the AI
eval's scorer and cost meter (`scripts/eval/`, outside mutmut's `only_mutate`).
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
            "        raise _no_usable_answer(response)\n"
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
    Mutant(
        id="M16",
        area="izolacja: pamięć, select_memory bez for_user (rozmowy)",
        path="conversations/memory.py",
        original="Conversation.objects.for_user(user)",
        mutated="Conversation.objects.all()",
    ),
    Mutant(
        id="M17",
        area="izolacja: pamięć, _mistakes bez for_user (błędy)",
        path="conversations/memory.py",
        original=(
            "Mistake.objects.for_user(user).filter(conversation_id__in=conversation_ids)"
        ),
        mutated="Mistake.objects.filter(conversation_id__in=conversation_ids)",
        expected="accepted",
    ),
    Mutant(
        id="M18",
        area="izolacja: nowa trasa z id bez decyzji w ID_ROUTES (strażnik tras)",
        path="conversations/urls.py",
        original="urlpatterns = [\n",
        mutated=(
            "urlpatterns = [\n"
            '    path("conversations/<int:pk>/copy/", views.conversation_detail, '
            'name="conversation_copy"),\n'
        ),
    ),
    Mutant(
        id="M19",
        area="usuwanie: sprzątanie bez pętli po sesjach użytkownika",
        path="accounts/services.py",
        original=(
            "    for session in Session.objects.iterator():\n"
            '        if session.get_decoded().get("_auth_user_id") == user_id:\n'
            "            session.delete()\n"
        ),
        mutated="",
    ),
    Mutant(
        id="M20",
        area="usuwanie: sprzątanie bez kasowania LogEntry o użytkowniku",
        path="accounts/services.py",
        original=(
            "    LogEntry.objects.filter(\n"
            "        content_type=ContentType.objects.get_for_model(User),\n"
            "        object_id=user_id,\n"
            "    ).delete()\n"
        ),
        mutated="",
    ),
    Mutant(
        id="M21",
        area="usuwanie: LogEntry o użytkowniku bez filtra object_id=",
        path="accounts/services.py",
        original="        object_id=user_id,\n",
        mutated="",
    ),
    Mutant(
        id="M22",
        area="usuwanie: Message.conversation PROTECT zamiast CASCADE",
        path="conversations/models.py",
        original='Conversation, on_delete=models.CASCADE, related_name="messages"',
        mutated='Conversation, on_delete=models.PROTECT, related_name="messages"',
    ),
    # No migration on purpose: only the model registry guard (metadata, no table)
    # must kill it.
    Mutant(
        id="M23",
        area="usuwanie: nowy model z e-mailem bez decyzji w MODEL_DECISIONS",
        path="conversations/models.py",
        original=(
            "    def __str__(self) -> str:\n"
            '        return f"{self.category}: {self.wrong} -> {self.correct}"\n'
        ),
        mutated=(
            "    def __str__(self) -> str:\n"
            '        return f"{self.category}: {self.wrong} -> {self.correct}"\n'
            "\n\n"
            "class NewsletterSignup(models.Model):\n"
            "    email = models.EmailField()\n"
        ),
    ),
    Mutant(
        id="M24",
        area="usuwanie: odbiornik pre_delete niepodłączony w AccountsConfig.ready",
        path="accounts/apps.py",
        original=(
            "        pre_delete.connect(\n"
            "            remove_sessions_and_log_entries_about_user,\n"
            "            sender=User,\n"
            '            dispatch_uid="accounts.remove_sessions_and_log_entries_about_user",\n'
            "        )\n"
        ),
        mutated="        pass\n",
    ),
    # M25 and M26 differ in the comment and log line of each branch.
    Mutant(
        id="M25",
        area="budżet: generate_turn bez gałęzi APITimeoutError (timeout za 0)",
        path="conversations/llm.py",
        original=(
            "    except APITimeoutError as exc:\n"
            "        # Before `APIError`, its base class. The provider may have generated (and\n"
            "        # billed) the answer that never arrived.\n"
            '        logger.error("LLM call failed: %s (status None)", type(exc).__name__)\n'
            '        raise LLMError("The model call failed.", billed_without_usage=True) from exc\n'
        ),
        mutated="",
    ),
    Mutant(
        id="M26",
        area="budżet: analyze_mistakes bez gałęzi APITimeoutError (timeout za 0)",
        path="conversations/llm.py",
        original=(
            "    except APITimeoutError as exc:\n"
            "        # Before `APIError`, its base class; the analysis may have been billed.\n"
            '        logger.error("LLM analysis call failed: %s (status None)", type(exc).__name__)\n'
            '        raise LLMError("The model call failed.", billed_without_usage=True) from exc\n'
        ),
        mutated="",
    ),
    Mutant(
        id="M27",
        area="budżet: generate_turn, pusty reply jako LLMError bez usage",
        path="conversations/llm.py",
        original=(
            '        logger.error("LLM returned a blank agent reply.")\n'
            "        raise _no_usable_answer(response)\n"
        ),
        mutated=(
            '        logger.error("LLM returned a blank agent reply.")\n'
            '        raise LLMError("The model returned no usable answer.")\n'
        ),
    ),
    Mutant(
        id="M28",
        area="budżet: spent_today bez składnika księgi",
        path="conversations/budget.py",
        original=" + (charges or Decimal(0))",
        mutated="",
    ),
    Mutant(
        id="M29",
        area="budżet + izolacja: spent_today, księga bez for_user",
        path="conversations/budget.py",
        original="LLMCharge.objects.for_user(user)",
        mutated="LLMCharge.objects",
    ),
    Mutant(
        id="M30",
        area="budżet: _generate_and_save, spóźniona tura bez wpisu w księdze",
        path="conversations/services.py",
        original=(
            "            # A late turn: dropped, but paid for.\n"
            "            _charge(\n"
            "                locked,\n"
            "                LLMCharge.Kind.TURN,\n"
            "                LLMCharge.Reason.LATE_RESULT,\n"
            "                _result_cost(result),\n"
            "                now,\n"
            "            )\n"
        ),
        mutated="            pass\n",
    ),
    Mutant(
        id="M31",
        area="budżet: send_message bez sprawdzenia dachu",
        path="conversations/services.py",
        original=(
            'raise ConversationError("Please wait for the agent\'s reply.")\n'
            "        at_ceiling = limit_reached(locked.user, now)\n"
        ),
        mutated=(
            'raise ConversationError("Please wait for the agent\'s reply.")\n'
            "        at_ceiling = False\n"
        ),
    ),
    Mutant(
        id="M32",
        area="budżet: run_agent_turn bez sprawdzenia dachu",
        path="conversations/services.py",
        original=(
            'raise ConversationError("The agent is still replying. Please wait.")\n'
            "        at_ceiling = limit_reached(locked.user, now)\n"
        ),
        mutated=(
            'raise ConversationError("The agent is still replying. Please wait.")\n'
            "        at_ceiling = False\n"
        ),
    ),
    Mutant(
        id="M33",
        area="budżet: send_message odmawia na dachu, ale nie kończy rozmowy",
        path="conversations/services.py",
        original=(
            'raise ConversationError("Please wait for the agent\'s reply.")\n'
            "        at_ceiling = limit_reached(locked.user, now)\n"
            "        if at_ceiling:\n"
            "            end_conversation(locked, Conversation.EndReason.DAILY_LIMIT, now)\n"
        ),
        mutated=(
            'raise ConversationError("Please wait for the agent\'s reply.")\n'
            "        at_ceiling = limit_reached(locked.user, now)\n"
            "        if at_ceiling:\n"
            "            pass\n"
        ),
    ),
    Mutant(
        id="M34",
        area="budżet: analyze_conversation bez dachu na ponowienie",
        path="conversations/services.py",
        original="if analysis_failed(locked, now) and limit_reached(locked.user, now):",
        mutated="if False:",
    ),
    Mutant(
        id="M35",
        area="eval: dopasowanie do wzorca bez sprawdzania numeru wiadomości",
        path="scripts/eval/scoring.py",
        original="        gold.message == item.message_number\n",
        mutated="        True\n",
    ),
    Mutant(
        id="M36",
        area="eval: wyłączone A3 (literówka liczona jako zwykła pozycja)",
        path="scripts/eval/scoring.py",
        original="if any(contains_phrase(item.wrong, typo.token) for typo in typos):",
        mutated="if False:",
    ),
    Mutant(
        id="M37",
        area="eval: wyłączone A2 (zmienione sentence)",
        path="scripts/eval/scoring.py",
        original="if _fragment(item.sentence) not in normalize(message):",
        mutated="if False:",
    ),
    Mutant(
        id="M38",
        area='eval: compare z werdyktem "różnica" bez względu na SE',
        path="scripts/eval/scoring.py",
        original=(
            "difference = low is not None and high is not None and (low > 0 or high < 0)"
        ),
        mutated="difference = mean_delta != 0",
    ),
    Mutant(
        id="M39",
        area="eval: licznik kosztu bez szacunku dla billed_without_usage",
        path="scripts/eval/cost.py",
        original="        elif error.billed_without_usage:\n",
        mutated="        elif False:\n",
    ),
    Mutant(
        id="M40",
        area="eval: can_start bez szacunku następnego wywołania",
        path="scripts/eval/cost.py",
        original="return self.spent + estimate(kind) <= self.cap_usd",
        mutated="return self.spent <= self.cap_usd",
    ),
    Mutant(
        id="M41",
        area="eval: dopasowanie nie jeden-do-jednego (wzorzec dopasowany wielokrotnie)",
        path="scripts/eval/scoring.py",
        original="if gold_index not in taken and _matches(gold, item):",
        mutated="if _matches(gold, item):",
    ),
    Mutant(
        id="M42",
        area="eval: wyłączone A1 dla słów spoza wiadomości ucznia",
        path="scripts/eval/scoring.py",
        original="if not _words(item.wrong) <= _words(message):",
        mutated="if False:",
    ),
    Mutant(
        id="M43",
        area="eval: znaczniki wykładu bez granicy słowa",
        path="scripts/eval/scoring.py",
        original='pattern = rf"(?<!\\w){re.escape(needle)}(?!\\w)"',
        mutated="pattern = re.escape(needle)",
    ),
    Mutant(
        id="M44",
        area="eval: klucz wzorca dopasowany jako podnapis (bez granicy słowa)",
        path="scripts/eval/scoring.py",
        original="and contains_phrase(item.wrong, gold.wrong_key)",
        mutated="and normalize(gold.wrong_key) in normalize(item.wrong)",
    ),
    Mutant(
        id="M45",
        area="eval: token neutralny dopasowany jako podnapis (bez granicy słowa)",
        path="scripts/eval/scoring.py",
        original="contains_phrase(item.wrong, token.token) for token in neutrals",
        mutated="normalize(token.token) in normalize(item.wrong) for token in neutrals",
    ),
    Mutant(
        id="M46",
        area="eval: przedrostek znacznika wykładu tylko jako całe słowo (bez złożeń)",
        path="scripts/eval/scoring.py",
        original='rf"(?<!\\w){re.escape(normalize(prefix))}"',
        mutated='rf"(?<!\\w){re.escape(normalize(prefix))}(?!\\w)"',
    ),
    Mutant(
        id="M47",
        area="eval: końcówka znacznika wykładu bez prawej granicy słowa",
        path="scripts/eval/scoring.py",
        original='rf"{re.escape(normalize(suffix))}(?!\\w)"',
        mutated="re.escape(normalize(suffix))",
    ),
    Mutant(
        id="M48",
        area="eval: końcówka znacznika wykładu tylko jako całe słowo (bez złożeń)",
        path="scripts/eval/scoring.py",
        original='rf"{re.escape(normalize(suffix))}(?!\\w)"',
        mutated='rf"(?<!\\w){re.escape(normalize(suffix))}(?!\\w)"',
    ),
    Mutant(
        id="M49",
        area="eval: A2 liczy kropkę dodaną przez model na końcu sentence",
        path="scripts/eval/scoring.py",
        original='return normalize(sentence).rstrip(".!?")',
        mutated="return normalize(sentence)",
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
