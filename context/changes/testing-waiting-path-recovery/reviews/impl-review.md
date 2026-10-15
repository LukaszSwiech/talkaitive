<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Waiting-path recovery (test-plan Phase 2, ryzyko #1)

- **Plan**: context/changes/testing-waiting-path-recovery/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4, 5
- **Date**: 2026-10-15
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

Verification run during review: `uv run pytest` → 252 passed; `uv run ruff check . && uv run ruff format --check .` → clean; `grep -n "TBD — see §3 Phase 2" context/foundation/test-plan.md` → no match; `uv run python scripts/mutation/manual_mutants.py` → 17/17 match, exit 0, working tree clean afterwards. `mutmut run` / `mutmut results` NOT re-run (permission denied for removing `mutants/`).

## Findings

### F1 — mutmut criteria (3.3, 4.3) not re-verified in this review

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: plan.md Progress 3.3, 4.3; scripts/mutation/accepted_survivors.md
- **Detail**: Progress marks "mutmut bez niewyjaśnionych przeżyć" as done for `_agent_turn_timeout`, `_analysis_timeout`, `_clear_turn_marker`, `analysis_failed`. The review could not run a fresh `mutmut run` (deleting the stale `mutants/` was denied), so the new rows `_analysis_timeout__mutmut_5` / `_mutmut_9` and the removal of the six Phase-2 rows rest on the implementer's run only. The other automated checks were re-run and pass.
- **Fix**: Run `rm -rf mutants && uv run mutmut run && uv run mutmut results` once and confirm no unexplained survivors in those four functions.
- **Decision**: FIXED (verified) — user ran `uv run mutmut run && uv run mutmut results` (without deleting `mutants/`; last test change was phase 4, already mutmut-run at 4.3): 683 mutants, 637 killed, 46 survived; all 46 have a row in `accepted_survivors.md`. `_agent_turn_timeout` and `analysis_failed`: no survivors; `_clear_turn_marker`: only accepted `_3`; `_analysis_timeout`: accepted `_5`, `_9`.

### F2 — Boundary tests deviate from the plan's wording

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: tests/test_conversation_views.py:564-572; tests/test_waiting_path.py:219-238
- **Detail**: Plan Phase 3 asks for "210 s − 1 µs → w toku; dokładnie 210 s → nie w toku" and lists `tests/test_analysis.py` for the analysis boundary. The turn test checks 210 s + 1 µs instead (comment: exact 210 s would kill the accepted equivalent mutant M8 and turn `manual_mutants.py` red), while the analysis test does check exactly 180 s. The analysis boundary lives in `tests/test_waiting_path.py` because `test_analysis.py` overrides the timeout (explained in the docstring). Both deviations are justified in code comments but not in the plan, and the two marker tests now use different boundary conventions.
- **Fix**: Add a short addendum to plan.md Phase 3 (or to test-plan §6.3) explaining the +1 µs choice and the file location, so the cookbook reader sees why turn and analysis differ.
- **Decision**: FIXED — added a "Brzeg znacznika „w toku”" bullet to `context/foundation/test-plan.md` §6.3.

### F3 — Marker formula treats the httpx timeout as a whole-attempt limit

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:69-75; tests/test_waiting_path.py:300-325
- **Detail**: `_agent_turn_timeout` and the Railway 300 s invariant assume one attempt lasts at most `LLM_TIMEOUT_SECONDS`. In httpx the 30 s applies per phase (connect, write, read), and the read timeout is the gap between chunks, not total time. For a non-streaming Responses call the body arrives at once, so in practice read ≈ total; but a slow connect plus a slow read could in theory outlive the marker or approach 300 s.
- **Fix**: Add one line to the `_agent_turn_timeout` comment stating the assumption (non-streaming call, read timeout ≈ whole response).
  - Strength: Makes the assumption visible to whoever later switches to streaming or raises timeouts.
  - Tradeoff: Documentation only; the theoretical edge stays.
  - Confidence: MED — behaviour of httpx timeouts is documented; real-world impact not measured.
  - Blind spot: Actual connect latency to OpenAI in production not measured (Phase 5 eval).
- **Decision**: FIXED — assumption comment added to `_agent_turn_timeout` in `conversations/services.py`.

### F4 — `httpx2` imported in tests but not declared as a dependency

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/fake_provider.py:16; pyproject.toml
- **Detail**: `tests/fake_provider.py` imports `httpx2` directly, but `pyproject.toml` does not list it; it arrives only transitively through `openai>=3.24.0`. If the SDK ever changes its HTTP library, the test helper breaks with an import error instead of a clear dependency conflict.
- **Fix**: `uv add --dev httpx2` (or a comment in fake_provider.py stating it is used on purpose as the SDK's own transport).
- **Decision**: FIXED — `uv add --dev httpx2` (`httpx2>=2.13.1` in the dev group, `uv.lock` updated).

### F5 — Parametrized blank-reply test branches on `if usable:`

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/test_llm.py (`test_blank_reply_is_an_llm_error_but_padded_text_is_kept`)
- **Detail**: One parametrized test covers two different outcomes (blank → `LLMError`, padded → returned untrimmed) with an `if` inside the test body, so each case asserts a different path.
- **Fix**: Split into two tests: a parametrized "blank reply is an LLMError" and a single "padded reply is kept untrimmed".
- **Decision**: FIXED — split into `test_blank_reply_is_an_llm_error` and `test_text_with_surrounding_spaces_is_kept_untrimmed`; `tests/test_llm.py` 50 passed, M14/M15 still killed.

### F6 — Unused `FakeProvider.client_kwargs` field

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/fake_provider.py:47, 107
- **Detail**: `client_kwargs` is recorded when the client is built but no test asserts on it.
- **Fix**: Remove it, or use it in one test to pin that `_get_client` passes `timeout` / `max_retries` from settings.
- **Decision**: FIXED — field removed from `tests/fake_provider.py`; full suite 252 passed, ruff clean.
