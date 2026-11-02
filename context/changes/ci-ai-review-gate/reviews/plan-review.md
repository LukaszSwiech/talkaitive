<!-- PLAN-REVIEW-REPORT -->
# Plan Review: AI review merge gate

- **Plan**: context/changes/ci-ai-review-gate/plan.md
- **Mode**: Deep (done inline, no sub-agents, as instructed by the orchestrator; findings left for the orchestrator to triage)
- **Date**: 2026-11-01
- **Verdict**: REVISE
- **Findings**: 0 critical, 5 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

9/9 paths opened (`ai-review.yml`, `criteria.py`, `run_review.py`, three test files, `test-plan.md`, `deploy-plan.md`, `conversations/views.py`), and the cited symbols and test lines match. Brief and plan agree. Progress and phase criteria match (5, 4, 5 and 11 rows for phases 1 to 4). `docs/reference/contract-surfaces.md` does not exist, so that check was skipped. `context/foundation/lessons.md` has no rule on CI or review gates.

## Checked and sound

- **Blocker cannot end green:** `final_verdict` no longer reads `review.verdict`; `Score` is a `Literal`, so an out-of-range score is an operational failure (red). `stop` keeps its implicit `success()`.
- **Labels and comment stay:** on verdict fail no step failed, so `failure()` is false at cleanup. The order test plus "stop is last" catch a swap.
- **Post failure stays red:** the shell runs with `-e`, `test_only_a_404_is_tolerated` forbids `|| true` and `continue-on-error`, and `stop` being skipped does not turn the job green.
- **After a failed guard:** only `failure-cleanup` could run, and its condition stops it. No other step has `always()` or `failure()` once `retry-cleanup` is gone.
- **Required context name:** a job with id `review` and no `name` reports `review`; the plan pins both, plus no second job of that name.
- **Order:** control, protection, fail test, evidence, user merge. Safe, and the seven-day rule is met by the control.
- **Other tests:** every existing test that breaks is in the plan. The `render_comment` callers go through the helper; `:1-14` and `:245` are covered.
- **Diff cap on the test PR:** sound. `context` is excluded, so the evidence commit adds nothing. The fail test adds one line to a diff that must measure under 100000, a 20000 margin. All review scripts, tests and the workflow together are 65513 characters today, so the gate diff is well under. `main...HEAD` equals the merge diff while `main` does not move.
- **Mutants and eval:** no other caller of the review symbols outside `scripts/review/` and its tests.

## Findings

### F1 — A truncated diff can still end green through the empty-diff branch

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 1, change 2 ("the empty-diff branch stay as they are"); `scripts/review/run_review.py:273`
- **Detail**: `run` tests `diff.strip()` on the cut text, not the full diff. An over-cap diff whose first 120,000 characters are whitespace takes the nothing-to-review branch: verdict pass, no model call, `truncated` ignored. Real `git diff` output starts with `diff --git`, so this is unreachable today. But it is the one path that breaks "truncated always fails", and the plan already tests the same class of unreachable input (no header before the cut).
- **Fix**: In Phase 1 change 2, replace "the empty-diff branch stays" with: the branch tests `full_diff.strip()`, and only a diff that is blank in full passes. Add a test through `main`: `read_diff` faked to return `" " * (MAX_DIFF_CHARS + 1)` gives `verdict=fail`.
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md

### F2 — The "names data_isolation" evidence is always true

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 4, change 3, Evidence; criterion and Progress row 4.3
- **Detail**: `render_comment` prints a bullet for every criterion on every run (`run_review.py:180-184`), so each comment contains `data_isolation`. The row passes even if `correctness` alone failed, and "a different blocker failed" could not be detected this way.
- **Fix**: Change the Evidence bullet to require that the `**Blocked:**` note names `data_isolation` and that its bullet scores at or below 3. Another blocker failing as well is fine; `data_isolation` missing means stop and report. Keep the Progress title unless the plan's owner rewords it in both places, since titles must match.
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md

### F3 — Row 4.8 cannot be recorded in the commit it describes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4, change 4; "Paid pushes"; Implementation Note; Progress 4.8
- **Detail**: Change 4 ticks the Phase 4 rows in the evidence commit, but 4.8 is the result of that commit's own run. Ticking it on the branch takes a third push, which is a paid run and breaks "exactly two pushes", and that run would need its own evidence.
- **Fix**: In change 4, say that 4.1 to 4.7 and 4.9 are ticked in the evidence commit. 4.8 is checked after the push, reported to the user with run id and SHA, and ticked with 4.10 and 4.11 on the `/10x-archive` branch. Extend the Implementation Note the same way.
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md; row 4.8 goes in the final report with run id and SHA and is ticked at `/10x-archive` on the change branch, with no third paid push

### F4 — `stop` has no step name, so the run data cannot show it

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2, change 1 and 2; Phase 4 Evidence; Progress 4.5
- **Detail**: The contract gives the step `id: stop` only. `gh run view --json jobs` lists a step's `name` and conclusion, not its id, and an unnamed step shows as `Run <command>`. "Red with `stop` as the failed step" then has to be read from a generated string.
- **Fix**: Add `name: Stop on a failed review` to the contract and pin it in the workflow test. In Evidence, read "the failed step is `Stop on a failed review`".
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md

### F5 — Two regressions in the safety conditions would pass the planned tests

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2, change 2
- **Detail**: (a) `test_cleanups_touch_no_label_after_a_failed_guard` only uses `in`, so `failure() && steps.guard.outcome != 'failure' || steps.review.outputs.verdict == 'fail'` passes it and deletes the labels on every fail. (b) The guard test checks the condition, not that the guard stops: without `exit 1` a fork goes on to checkout and installs its code, while every planned test stays green.
- **Fix**: Add to the workflow test contract: `failure-cleanup`'s `if` equals exactly `failure() && steps.guard.outcome != 'failure'`; the guard's `run` contains `exit 1`; only `failure-cleanup` has `failure()` or `always()` in any step's `if`.
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md

### F6 — `low_warnings` has no stated threshold

- **Severity**: 🔵 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1, change 1 and 3
- **Detail**: The contract defines `low_warnings(review)` without saying what "low" means. The name suggests the floor, but only `failed_blockers` is tied to it. The tests only pin a warning at 1 for the verdict.
- **Fix**: State `score <= FAIL_FLOOR` in the contract, and test a warning at `FAIL_FLOOR` (note present) and at `FAIL_FLOOR + 1` (note absent).
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md

### F7 — Two small command and commit slips

- **Severity**: 🔵 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4, change 3 (clean up); Phase 1 criterion and Progress 1.5
- **Detail**: `gh pr close --delete-branch` also deletes the local branch (`gh pr close --help`: "Delete the local and remote branch after close"), so the later `git branch -D` fails. Separately, 1.5 lists the folder's files but not `reviews/plan-review.md`, which is untracked and not ignored.
- **Fix**: Drop `git branch -D ci-ai-review-gate-fail-test`, or make the check "the branch is gone". Add `reviews/plan-review.md` to the Phase 1 commit, in both the criterion and row 1.5, keeping them identical.
- **Decision**: ACCEPTED by the orchestrator, applied to plan.md
