<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: AI review merge gate

- **Plan**: context/changes/ci-ai-review-gate/plan.md
- **Scope**: Full plan, completed phases only (phase 4 is the live rollout and has not started)
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-11-01
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence

Run on 2026-11-01 at `cdb3b6d`, without paid calls or GitHub writes.

- `uv run pytest`: 710 passed. The three review test files: 146 passed. `ruff check` and `ruff format --check`: clean.
- Diff the script will see: 47,696 characters, under the 100,000 limit of row 3.2.
- GitHub, read-only: repo public, `main` not protected yet (404, as expected before phase 4), no open PRs, branch not pushed, label `ai-cr:review` still present (a user step in phase 4).
- `conversations/views.py:31` is the line phase 4's fail test plans to change.
- 43 mutants in a throwaway copy: 34 killed, 9 survived (see F1, F2, F3; the ninth, `not full_diff` in place of `not full_diff.strip()`, only matters for a whitespace-only diff under the cap, which git does not produce). The verdict rule, the one-verdict wiring, truncation, sanitising, note order, step order, stop and guard conditions were all killed.

Attacks that found nothing:

- Blocker failure or truncation ending green: `final_verdict` never reads `review.verdict`; truncation comes from lengths, not from `dropped_paths`.
- Operational failures: API error, schema error, refusal, git error and a missing key all exit non-zero and write no verdict, so the job is red.
- Comment and output disagreeing: `run` computes one value and passes it to both.
- Labels on fail: `failure()` is false at the cleanup step, so the comment and `ai-cr:failed` stay. If `post` fails, the job is red anyway.
- Fork: the guard is first and goes red, a null `head.repo` also goes red, and later steps are skipped; cleanup is spared by its condition.
- Shell injection: no `${{ }}` in any `run` block; the verdict and PR number reach shell through env, and `post` validates the verdict with `case`.
- Sanitize bypass in notes: the notes hold only constants and names from `CRITERIA`. Hostile rationale and summary text rendered inert (mentions, character references, HTML, comments, images).

Accepted limits, not findings: a PR can edit its own workflow and script (threat model, `deploy-plan.md`), a prompt-injected diff can talk the model into high scores, and an admin can merge past red (decided).

## Findings

### F1 — The stop step is a denylist, so a run with no verdict ends green

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/ai-review.yml:150
- **Detail**: The decision says an operational failure keeps the job red. Today that rests only on the script exiting non-zero. If the review step ever exits 0 with no verdict, `post` and `stop` both skip and the job is green with no comment. No such path exists in today's script. A later edit can create one: the mutant `...run_review --comment-file "..."; exit 0` on the review step survived the whole suite, so an API failure would then pass the gate. The same happens if step id `review` is renamed in the workflow's conditions together with its test. The plan itself specified `== 'fail'` (plan.md:176), so this is a plan flaw, not drift.
- **Fix**: Change the stop condition to `steps.review.outputs.verdict != 'pass'`, keep the implicit `success()`, and update `test_the_stop_step_ends_the_job_red_only_on_a_fail_verdict` (tests/test_review_workflow.py:224) and plan.md:176.
  - Strength: Red becomes the default: only an explicit pass ends green. All today's cases keep their behaviour, because a failed guard, review or post still skips this step through `success()`.
  - Tradeoff: In that no-verdict case the cleanup step stays out, so an older `ai-cr:passed` label would remain next to a red job. Accepted, since the check is what blocks.
  - Confidence: HIGH — the condition is one expression, and the failing mutant shows the gap.
  - Blind spot: Not run on real Actions; the next control run exercises the pass path and the fail test the fail path.
- **Decision**: FIXED

### F2 — Workflow guards are weaker than the properties they pin

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: tests/test_review_workflow.py:227, :233, :241-247, :279-281
- **Detail**: These mutants survived all 146 tests:
  - `post` only on `verdict == 'pass'` (`:241` only checks the expression's substring), so on a fail there is no comment and no label.
  - `result`/`opposite` swapped in the `fail)` branch, so a failed PR gets `ai-cr:passed`.
  - `delete_label "$opposite"` removed, so a stale label stays.
  - `; exit 0` appended to the review step (`:233` only checks `startswith`).
  - `continue-on-error: true` on the job (`:281` checks steps only). Whether this turns the required check green was not tested on GitHub.
  - `exit 1` commented out in `stop` (`:227` is a substring check).
  - `paths-ignore` added to the trigger. This one fails safe (pending, blocks).

  Phase 4's fail test proves today's file once; these guards are what protect it afterwards.
- **Fix**: Tighten to exact checks: `post["if"] == "steps.review.outputs.verdict != ''"`; assert the `fail)` and `pass)` branch text and `delete_label "$opposite"`; `run == 'uv run --no-sync python -m scripts.review.run_review --comment-file "$RUNNER_TEMP/ai-review-comment.md"'`; `"continue-on-error" not in job()`; last non-blank line of `stop`'s and the guard's `run` equals `exit 1`; `set(triggers["pull_request"]) == {"branches", "types"}`.
- **Decision**: FIXED

### F3 — The decided floor of 3 is not pinned by any test

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: scripts/review/criteria.py:20
- **Detail**: `FAIL_FLOOR = 2` survived, because every boundary test is written relative to the constant. The decision (research.md:32) and `deploy-plan.md` both state 3. Lowering it weakens the gate with a green suite.
- **Fix**: Add `assert FAIL_FLOOR == 3` to tests/test_review_criteria.py.
- **Decision**: FIXED

### F4 — The gate section does not say which PRs pass with no model call, or that forks are always red

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: context/deployment/deploy-plan.md, "AI review merge gate", "What stops a merge"
- **Detail**: A PR changing only `uv.lock` has an empty reviewed diff, so it passes with no model call, and that lockfile reaches production on deploy. This matches the decision "an empty diff passes", and the comment's scope note names the exclusion, but plan.md:30 discusses only `context/` and the operating rules do not mention it. Separately, a fork PR is always red and can only go in by admin merge, which is also unstated.
- **Fix**: Add one bullet to the gate section: lockfile-only and `context/`-only PRs pass with no model call, so the owner reads lockfile PRs by hand; a fork PR is always red.
- **Decision**: FIXED

### F5 — Model summary can show a second, false verdict heading

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/review/run_review.py:234
- **Detail**: `sanitize` keeps line structure in the summary, so a prompt-injected summary rendered `## AI review: pass` and `**Blocked:** none` under a real `## AI review: fail`. The true heading stays first, and the label and check are correct, so this can only mislead a reader. Rationales are folded and cannot do this.
- **Fix**: Under the fixed notes, add a line such as `**Model summary (untrusted):**` before the summary, so the fixed block is clearly separate.
- **Decision**: FIXED

## Process notes

- `change.md` was not stamped `impl_reviewed`: this run was told to leave only the report changed. Stamp it when the findings are handled.
- Progress row 3.5 stays open until the findings are decided, as the plan requires before the first push.
- The one recorded deviation (plan.md:386, `not truncated and not full_diff.strip()`) is correct: it is the only reading that meets the plan's other two statements.
- `deploy-plan.md` states protection in the present tense while `main` is still unprotected. That becomes true at phase 4's step 2, before the user's merge, so no change is needed unless the rollout stops.
