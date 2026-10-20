<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Rollout Phase 5 — warstwa evalu AI

- **Plan**: context/changes/testing-ai-eval-layer/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-19
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 1 warning, 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

Success criteria (2026-10-19, HEAD `2cdab63`): eval + memory tests 148 passed; `uv run pytest` 437 passed; `pytest --collect-only` collects 0 items from `scripts/`; ruff check + format clean; `manual_mutants.py` 51/51 match (exit 0); mutmut (run today on the same code, only docs changed since) 841 mutants, 55 survivors, all registered. No production code changed (`git diff 2978faf..HEAD -- conversations accounts talkaitive` empty). All manual Progress items are checked and backed by artifacts (baseline JSON, change.md results, test-plan notes).

## Findings

### F1 — A non-LLMError exception loses the paid partial run

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/run_eval.py:191-204, :503
- **Detail**: `_call` catches only `LLMError` (:200). Ctrl-C during the ~12-minute run, a bug in `scoring.score_*`, or an `OSError` on an unwritable `--out` aborts `run()` before the result is written at :503. The spend of the calls already made is never printed or saved.
- **Fix**: Wrap the call loops in `try/finally` that writes the result with `"complete": false` and prints the spend, then re-raises.
- **Decision**: FIXED — `try/except BaseException` around the loops, partial result written, exception re-raised; test `test_interrupted_run_keeps_the_partial_result_and_reraises` (red when the handler catches only `KeyboardInterrupt`)

### F2 — A rerun silently overwrites an existing results file, including the baseline

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/run_eval.py:503
- **Detail**: `out.write_text` overwrites without checking. The default name `<date>-<model>-<commit>[-dirty].json` repeats for a second run on the same day and commit, so a rerun from `56e6109` today would replace the committed baseline (only git restores it); `--out` probes outside the repo cannot be restored.
- **Fix**: Refuse an existing target with exit 2 (open with mode `"x"`) unless a `--force` flag is given.
- **Decision**: FIXED — existing target without `--force` → `ConfigError` (exit 2) before any call; docstring updated; test `test_existing_result_file_is_not_overwritten_without_force` (red with the guard disabled)

### F3 — Docstring calls the per-call estimate an upper bound; the cap can be exceeded by one call

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/run_eval.py:33, scripts/eval/cost.py:63-64
- **Detail**: `can_start` checks `spent + estimate <= cap`, but 0.07 / 0.03 USD are measured averages (`talkaitive/settings.py`), not maxima, so one call costing more than its estimate can pass `--max-usd`. Observed maxima (analysis 0.031, long analysis 0.057) make the risk small.
- **Fix**: Reword the docstring (and test-plan §6.5 "górny szacunek") to "the cap can be exceeded by at most one call's overrun of its estimate".
- **Decision**: FIXED — `run_eval.py` docstring (estimates are measured averages, not maxima; one call can pass the cap by its overrun) and test-plan §6.5 reworded; no code change

### F4 — `Any` where concrete types exist in run_eval.py

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: scripts/eval/run_eval.py:168, :180, :191-192, :351
- **Detail**: `_analysis_output`, `_turn_output`, `_call` and `_summary_json` take `Any` instead of `AnalysisResult` / `TurnResult` / `scoring.Summary`; CLAUDE.md asks for type hints ahead of mypy + django-stubs.
- **Fix**: Import those types under the existing `TYPE_CHECKING` block (keeps the lazy imports Django needs) and use them.
- **Decision**: FIXED — `AnalysisResult`, `TurnResult`, `Summary` imported under `TYPE_CHECKING` and used as string annotations in the four signatures; no behaviour change

### F5 — `Typo` docstring still says punctuation, the module docstring excludes it

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: scripts/eval/golden.py:71
- **Detail**: The plan (Faza 2 §2) classified punctuation as `Typo`; the implementation deliberately drops punctuation-only differences (golden.py:30-32, no word to anchor) and test-plan §6.5 follows that. The `Typo` class docstring still says "Spelling, capitalisation or punctuation".
- **Fix**: Change the docstring to "Spelling, capitalisation or compound spelling the analysis must not report."
- **Decision**: FIXED — `Typo` docstring now matches the module docstring

### F6 — Test-plan §6.5 says pytest, CI and mutmut do not run `scripts/eval/`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: context/foundation/test-plan.md:206
- **Detail**: True for `run_eval.py run` on the real model, but `scoring.py`, `cost.py`, `golden.py` and `run_eval.py` (with fakes) run under `uv run pytest` / CI via `tests/test_eval_*.py`, and mutmut copies `scripts` (`also_copy`) without mutating it.
- **Fix**: Reword: no test file lives in `scripts/eval/` and the real-model run never starts from pytest/CI; the module code is covered by `tests/test_eval_*.py` and copied (not mutated) by mutmut.
- **Decision**: FIXED — §6.5 "Location" reworded (real-model run never from pytest/CI; module code tested in CI; mutmut copies, does not mutate)
