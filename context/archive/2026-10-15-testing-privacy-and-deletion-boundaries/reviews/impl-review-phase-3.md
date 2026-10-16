<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Rollout Phase 3 — granice prywatności i usuwania konta

- **Plan**: context/changes/testing-privacy-and-deletion-boundaries/plan.md
- **Scope**: Phase 3 of 4
- **Reviewed phases**: 3
- **Date**: 2026-10-16
- **Verdict**: APPROVED
- **Findings**: 0 critical, 2 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

Verification run during review (on commit `375e2e4`): `uv run pytest` → 258 passed; `uv run ruff check . && uv run ruff format --check .` → clean; `uv run python scripts/mutation/manual_mutants.py M19 M20 M21 M24` → 4 mutants, 4 match, 0 mismatch. Criterion 3.1 (red before the fix) cannot be re-run after the fix; it was verified during implementation (both parametrized cases failed on Anna's leftover session), and the deliberate-break check (LogEntry cleanup removed) showed the log-entry assertion also fails. Manual 3.5 was confirmed by the user in chat. Plan drift check: all three "Changes Required" items MATCH; existing deletion tests are byte-identical to `df76370`; `[tool.mutmut]` unchanged; no admin permission changes, migrations or E2E tests.

## Findings

### F1 — Owner deleting their own account in /admin/ relies on default session settings

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/services.py:43-45; accounts/admin.py:8
- **Detail**: When the owner deletes their own account in `/admin/` (the path `delete_account`'s refusal message points to, `accounts/services.py:59-63`), the `pre_delete` receiver deletes the session row of the request doing the deletion. With today's settings (`SESSION_SAVE_EVERY_REQUEST` unset → `False`; `MESSAGE_STORAGE` unset → `FallbackStorage`, which keeps the admin message in a cookie) the session is never saved and both admin paths return 302 (probe test in the reviewer's scratchpad). With `MESSAGE_STORAGE=SessionStorage` or `SESSION_SAVE_EVERY_REQUEST=True`, or unread cookie messages over ~2 KB spilling into the session, `SessionMiddleware` saves the deleted row → `UpdateError` → `SessionInterrupted` → 400 (`django/contrib/sessions/middleware.py:48`, `:61-62`; `backends/db.py:134-136`). The user is still deleted (transaction committed); only the response breaks. Before `375e2e4` this path always returned 302. The account page avoids it by calling `logout()` after the delete (`accounts/views.py:32-36`).
- **Fix A ⭐ Recommended**: Add a test that the owner deleting their own account in `/admin/` (delete page and bulk action) gets a 302 and is logged out, plus a one-line comment at the receiver.
  - Strength: A change to either setting turns a test red the same day; no application code changes; fits the phase's approach of guards that compare with reality.
  - Tradeoff: ~20 lines of test; makes the risk visible rather than removing it.
  - Confidence: HIGH — the probe showed 302 today and 400 under both settings.
  - Blind spot: The rare >2 KB cookie-message spill stays unguarded.
- **Fix B**: Log the owner out in `UserAdmin` after they delete their own account (override `response_delete` and the bulk action path), like the account page does.
  - Strength: Removes the failure mode regardless of settings.
  - Tradeoff: New admin code in two places plus tests; widens the phase's scope ("ścieżka zostaje, tylko sprząta jak strona").
  - Confidence: MED — `logout()` after a deleted session needs care with message order (flush drops session-stored messages).
  - Blind spot: Not prototyped; the bulk action has no hook as clean as `response_delete`.
- **Decision**: SKIPPED

### F2 — Mutation docs not updated for M19–M21 and M24

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: scripts/mutation/accepted_survivors.md:5; scripts/mutation/manual_mutants.py:3
- **Detail**: The register header still lists the script's ids as `C1`, `C2`, `M1`–`M18`, `M22`, `M23`. Phases 1 and 2 updated this line in the same commit as their mutants; phase 3 did not (the phase 3 plan does not name the file). The module docstring of `manual_mutants.py` ("Removed `.for_user()` calls and query filters, module constants and prompt labels") no longer describes the kinds of mutants in the list: a new route (M18), a cascade rule (M22), a new model (M23), removed cleanup statements (M19, M20), an unconnected receiver (M24).
- **Fix**: Change the header to `C1`, `C2`, `M1`–`M24` and widen the docstring sentence (e.g. "…query filters, deletion cleanup and signal wiring, cascade rules, guard registries, module constants and prompt labels.").
- **Decision**: FIXED — register header now `C1`, `C2`, `M1`–`M24`; `manual_mutants.py` docstring lists deletion cleanup and signal wiring, cascade rules and guard registries.

### F3 — "Every way of deleting a user" means every ORM deletion

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/services.py:9-13; accounts/apps.py:14-15
- **Detail**: `pre_delete` is sent by `Model.delete()` / `QuerySet.delete()` only. Raw SQL (e.g. a database console on Railway), `QuerySet._raw_delete`, and a data migration deleting through a historical model (`apps.get_model(...)`) skip the receiver. None of these exist in the repo today (no `RunPython`, `RunSQL`, `_raw_delete`, `get_model(`). "this page" in a services-module docstring means the account page.
- **Fix**: Reword to "every ORM deletion of a user (`Model.delete` / `QuerySet.delete`): the account page, …" and say "the account page" instead of "this page".
- **Decision**: FIXED — `accounts/services.py` docstring now says "every ORM deletion of a user (`Model.delete()` / `QuerySet.delete()`)", names raw SQL and historical-model migrations as gaps, and says "the account page"; `accounts/apps.py` comment says "Every ORM deletion". Re-verified: ruff clean, `uv run pytest` 258 passed, `manual_mutants.py M19 M20 M21 M24` 4/4 match.
