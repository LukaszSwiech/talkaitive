<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Lista błędów po zakończeniu rozmowy (S-02)

- **Plan**: context/changes/post-conversation-error-list/plan.md
- **Scope**: Phase 3 of 4
- **Reviewed phases**: 3
- **Date**: 2026-10-07
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS (2 observations) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Evidence: commit b4632ed touches only the planned files (`conversations/services.py`, `tests/test_analysis.py`, plan Progress). Every contract item of Phase 3 (refusal messages, `AnalysisNotNeeded` subclass, lock → call outside transaction → locked save, own-marker clearing, zero-learner shortcut, failure marking, merge/sort rules, `analysis_in_progress` timeout) is implemented and covered by a test. Learner numbering in `_merge_mistakes` matches `llm._build_transcript` (same `role != "assistant"` rule). `uv run pytest`: 151 passed; `ruff check` and `ruff format --check`: clean (run on the working tree, which also contains uncommitted Phase 4 work).

## Findings

### F1 — Failure update is not guarded against a newer in-flight analysis

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:285-288
- **Detail**: After a failed model call the service clears its own marker and then, in a separate statement, sets `analysis_failed_at` whenever `analyzed_at IS NULL`. If the marker had already expired and a second request set its own marker, the first request's failure still stamps `analysis_failed_at` while the second analysis runs. Today this is harmless: the template checks "in progress" before "failed", and a successful save clears `analysis_failed_at`. No test covers the failure path racing a parallel request (neither "parallel succeeded first" nor "parallel still running").
- **Fix**: Add `analysis_started_at__isnull=True` to the failure `update()` filter and a test where a parallel request finished first (failure must leave `analysis_failed_at` as `None`).
- **Decision**: FIXED — filter guarded in `conversations/services.py`; tests `test_failure_does_not_mark_a_conversation_a_newer_request_is_analysing` and `..._a_parallel_request_analysed` added (153 passed, ruff clean).

### F2 — `analyzed_at` is the request start time, not the finish time

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:297
- **Detail**: `analyzed_at = now`, where `now` is taken before the up-to-90 s model call (as the plan's contract says). `spent_today` attributes analysis cost by `analyzed_at`, so an analysis started just before midnight Europe/Berlin and saved after it counts towards the previous day. The effect is at most one analysis cost per user per day boundary — negligible for the MVP, but the field name suggests a finish time, which S-03 might rely on.
- **Fix**: Leave as is and note in the plan that `analyzed_at` means "analysis requested at" (or pass `timezone.now()` for the save if S-03 needs a true finish time).
- **Decision**: SKIPPED
