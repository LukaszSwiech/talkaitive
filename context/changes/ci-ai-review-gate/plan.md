# AI review merge gate Implementation Plan

## Overview

Turn the advisory AI review into a real merge gate. Job `review` in `.github/workflows/ai-review.yml` becomes the only required check on `main`, with admins not enforced. A blocker criterion at or below the floor, or a truncated diff, ends the job red after the comment and the `ai-cr:failed` label are posted. Criteria change to the six decided in `research.md`.

## Current State Analysis

- The script scores `data_isolation`, `type_hints`, `tests`, `no_secrets`, `openai_boundary`, `ui_contract`; any criterion at or below `FAIL_FLOOR`, or the model's own fail, gives verdict fail (`scripts/review/criteria.py:79-107`).
- A reviewed fail exits 0 (`scripts/review/run_review.py:11`), so the job stays green. The comment calls itself advisory (`:59`, `:185`, `:204`).
- The workflow has a job-level `if` that would let fork PRs pass a required check as skipped, plus `labeled` and `workflow_dispatch` paths (`ai-review.yml:6-14`, `:30-34`).
- `main` has no protection and no rulesets, there are no open PRs, and the repo is public (`research.md`, section 4).

## Desired End State

- Six criteria: blockers `data_isolation`, `no_secrets`, `correctness`, `migrations`; warnings `tests`, `openai_boundary`.
- Verdict fail only when a blocker is `<= FAIL_FLOOR` or the diff was truncated. An empty diff passes. An operational failure keeps the job red and sets no verdict.
- One verdict value per run: computed once in `run`, passed to both the comment and `$GITHUB_OUTPUT`.
- The workflow runs only on `pull_request` (`opened`, `synchronize`, `reopened`), has no job-level `if`, goes red for forks before checkout, and its last step ends red on verdict fail, leaving the comment and label in place.
- Branch protection on `main` requires `review` (app 15368, `strict: false`, `enforce_admins: false`).
- Verify: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` are green, and the fail test evidence is in `## Progress`.

### Key Discoveries:

- `truncate_diff` can return an empty `dropped_paths` for an over-cap diff with no `diff --git` header before the cut (`run_review.py:119-129`). So truncation must reach the verdict and the comment as the explicit `truncated` flag from `run` (`:267`), never derived from `dropped_paths`.
- `render_comment` computes its own verdict (`:179`) while `run` computes another (`:306`). This change removes the first.
- The guard no longer calls `gh`, so it must lose `GH_TOKEN`: `test_the_github_token_is_only_in_steps_that_call_gh` requires exactly that (`tests/test_review_workflow.py:135-141`).
- The required check's name is the job's name. A `name:` key on the job, or renaming the job id, would silently leave the required check waiting forever, so a test pins both.
- `[skip ci]` on a push leaves the required check pending and blocks (`research.md`, section 1), so it cannot save the paid evidence run.
- `context` is excluded from the reviewed diff (`run_review.py:53`), so a PR touching only `context/` gets a free pass with no model call. The later `/10x-archive` PR is one.
- Mutants: `scripts/mutation/manual_mutants.py` and `accepted_survivors.md` have no mutant on `scripts/review/` (grep for `review`, `criteria`, `final_verdict`, `FAIL_FLOOR` finds nothing), and mutmut's `only_mutate` does not include it. No mutant update is needed.
- Eval: nothing in `scripts/eval/` references `scripts.review` or the review criteria (grep finds nothing). The eval is unaffected and need not be re-run.
- Other callers: `final_verdict` and `floor_failed` are used only in `scripts/review/` and `tests/test_review_criteria.py`.

## What We're NOT Doing

- Requiring `lint-and-test`: a proposal for the final report, not done here.
- Setting the fork approval policy or deleting the `ai-cr:review` label on GitHub: user steps (see "User steps in the final report").
- Merging anything: the agent never merges. The user merges the gate PR.
- Editing `CLAUDE.md` (proposals stay in `research.md`, section "CLAUDE.md wording proposals"), `context/archive/`, `.claude/`, or `ci.yml`.
- A base-branch `pull_request_target` guard: rejected in `research.md` as a riskier trigger for a one-person repo.
- Calling the gate a security control. It stops honest mistakes, not a hostile editor of the workflow.
- Testing fork behaviour with a real fork: stays marked inferred in `research.md`.
- New mutants or re-running the AI eval (see Key Discoveries).

## Implementation Approach

Change the Python first (criteria, verdict, comment), then the workflow, then the docs, all verified locally. `/10x-impl-review` runs before the first push, because every later push to the gate PR is a paid run. Only then go live, in the order the user's "agent never merges" rule forces: control run, then protection, then the fail test, all before the user merges.

Decisions recorded for this non-interactive plan (orchestrator overrides `research.md` where they differ):

- Truncated diff: the model is still called, the verdict is fail, and the comment says so.
- Fail test runs from the gate branch, not a new `main`, so its merge commit carries the new workflow and rules.
- Conservative choices made while planning: a red control run stops the rollout and goes to the user instead of being fixed by a push; the fail test gets at most one re-run; `final_verdict`'s `truncated` is a required keyword argument so a caller cannot forget it.

## Branches and PRs

One branch `ci-ai-review-gate` and one PR for everything; the fail test uses a throwaway branch and PR that are closed unmerged and deleted.

## Critical Implementation Details

**State sequencing.** The stop step must come after failure-cleanup and rely on the implicit `success()`: no `always()`. On verdict fail no earlier step failed, so `failure()` is false at cleanup and the labels stay. If `post` fails, cleanup runs, the stop step is skipped, and the job is red anyway. For a fork, the failed guard skips everything, and cleanup's `steps.guard.outcome != 'failure'` spares the read-only token a 403.

**Paid pushes.** The gate PR gets exactly two pushes: the first (control) and the evidence commit (second control, accepted). Anything else needs a go-ahead from the user. Commit all phases before the first push.

## Phase 1: Criteria, verdict and comment

### Overview

The new rule and the new comment in the script, with their tests. These go together because the signature changes break callers and tests at once.

### Changes Required:

#### 1. Criteria and verdict

**File**: `scripts/review/criteria.py`

**Intent**: Replace `type_hints` and `ui_contract` with `correctness` and `migrations`, separate blockers from warnings, and make the verdict follow the decided rule. Update the module docstring (its UI example goes) and the `FAIL_FLOOR` comment, which now applies to blockers.

**Contract**:

- `correctness` description covers logic errors, missed cases and regressions. 1 = a clear bug that breaks behaviour; 10 = none found.
- `migrations` description: `main` auto-deploys and migrate runs pre-deploy, so it covers data loss, irreversible or locking operations, non-null without default, and a model change with no migration. 1 = would break or lose production data; 10 = safe.
- Both keep the `1`, `10` and `_UNTOUCHED` wording that `test_each_criterion_description_says_what_1_and_10_mean` checks. `tests` and `openai_boundary` keep their descriptions.
- `CRITERIA` holds the six names; `BLOCKERS = ("data_isolation", "no_secrets", "correctness", "migrations")`, `WARNINGS = ("tests", "openai_boundary")`.
- `floor_failed` is replaced by `failed_blockers(review) -> list[str]` and `low_warnings(review) -> list[str]`, both in `CRITERIA` order. Both use the same threshold, `score <= FAIL_FLOOR`.
- `final_verdict(review: Review, *, truncated: bool) -> Verdict`: `fail` if `truncated` or `failed_blockers(review)` is non-empty, otherwise `pass`. `review.verdict` is never read, so it cannot rescue a blocker failure or stop a PR alone.

#### 2. Script and comment

**File**: `scripts/review/run_review.py`

**Intent**: Compute the verdict once in `run`, pass it to the comment, and replace the advisory note with fixed notes that say why the verdict is what it is. Keep exit 0 for a reviewed fail: the workflow decides red.

**Contract**:

- `run` sets `verdict = final_verdict(review, truncated=truncated)` once and passes the same value to `render_comment` and `_write_result`. The comment heading and `$GITHUB_OUTPUT` cannot differ.
- `render_comment(review, dropped_paths, *, verdict, truncated)` never calls `final_verdict`.
- `_ADVISORY_NOTE` is removed, including from `render_nothing_to_review`.
- Fixed notes, in this order, before the scope note and all model text, built from constants only:

| Condition | Note says |
| --- | --- |
| `failed_blockers` non-empty | `**Blocked:**` names each failed blocker and the floor. If the model said pass, adds that the model said pass but cannot override a blocker |
| `truncated` | `**Blocked:**` the diff was cut at its size cap, part of it was not reviewed, so this fails whatever the scores; split the PR |
| `low_warnings` non-empty | `**Warning:**` names each low warning criterion; this does not stop the merge. Shown whatever the verdict |
| `review.verdict == "fail"` and `verdict == "pass"` | `**Warning:**` the model's own verdict was fail, no blocker is at or below the floor, so this does not stop the merge; read the summary |

- The module docstring says a reviewed fail ends red through the workflow; the exit codes stay. `_scope_note` and `_TRUNCATED_INSTRUCTION` stay as they are.
- The empty-diff branch tests `full_diff.strip()`, not the cut text, so only a diff that is blank in full passes. A truncated diff can never take this branch.

#### 3. Tests

**Files**: `tests/test_review_criteria.py`, `tests/test_review_script.py`

**Intent**: Pin the verdict rule at its boundaries and the note for every case, and move tests that used `tests` as the failing criterion onto a blocker.

**Contract**:

- `test_review_criteria.py`:
  - Update `SIX_CRITERIA` and the comment at `:71`. `BLOCKERS` and `WARNINGS` are disjoint and together equal `CRITERIA`.
  - Each blocker at `FAIL_FLOOR` fails; each blocker at `FAIL_FLOOR + 1` passes.
  - Each warning at 1 passes. Model fail with high scores passes (`:96-97` inverted).
  - `low_warnings` includes a warning at `FAIL_FLOOR` and excludes one at `FAIL_FLOOR + 1`.
  - Model pass with a failed blocker fails. Truncated with every score at 10 and a model pass fails.
- `test_review_script.py`:
  - A small helper computes the verdict the way `run` does, for the many `render_comment` calls.
  - Failing `tests=` moves to `data_isolation=` at `:261`, `:317`, `:337`, `:633`, `:837`.
  - Advisory assertions at `:249-253`, `:327`, `:341` become assertions on the new notes, and "advisory" appears in no comment, including the nothing-to-review one.
  - `:268-272` becomes a model fail that renders `AI review: pass` plus the warning note.
  - New: each note table row is present when its condition holds and absent otherwise, naming the right criteria.
  - New: the notes come before an unclosed code fence and survive the size cap.
  - New: `render_comment` renders the verdict it is given.
  - New: the warning note appears for a warning at `FAIL_FLOOR` and not at `FAIL_FLOOR + 1`.
  - New, through `main`: `read_diff` faked to return `" " * (MAX_DIFF_CHARS + 1)` gives `verdict=fail`.
  - New, through `main`: truncated diff (the existing merge repo at `:804` fits) has `verdict=fail`, the heading and output agree, the note is present, the model is called, exit 0.
  - New, through `main`: a low warning with `verdict=pass`, exit 0.
  - New, through `main`: an over-cap diff with no `diff --git` header before the cut still fails (`truncated` true, `dropped_paths` empty). Build it with `read_diff` faked, if the merge repo cannot produce it.
  - Unchanged: exit 0 on fail at `:636-639`, and the empty diff pass.

### Success Criteria:

#### Automated Verification:

- Criteria tests pass: `uv run pytest tests/test_review_criteria.py`
- Script tests pass: `uv run pytest tests/test_review_script.py`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check .` and `uv run ruff format --check .`
- Phase commit exists: `feat(ci-ai-review-gate): six criteria, blockers and one verdict for the comment and the output`, also holding this folder's `change.md`, `research.md`, `public-exposure-report.md`, `plan.md`, `plan-brief.md` and `reviews/plan-review.md`

---

## Phase 2: Workflow

### Overview

The workflow becomes a real check: one trigger, nothing skipped, forks red, a reviewed fail red.

### Changes Required:

#### 1. Workflow

**File**: `.github/workflows/ai-review.yml`

**Intent**: Apply the recommended design from `research.md`. Rewrite the header comment: this is a required check, there is still no `push` trigger because Railway waits for all workflows on a commit, and a PR can edit this file, so the owner reads such PRs by hand.

**Contract**:

- `on.pull_request`: `branches: [main]`, `types: [opened, synchronize, reopened]`. `workflow_dispatch` is gone.
- `concurrency.group`: `ai-review-pr-${{ github.event.pull_request.number }}`, `cancel-in-progress: true`.
- Job `review`: no `if`, no `name`; `PR_NUMBER` only from the event.
- First step keeps `id: guard`, with `if: github.event.pull_request.head.repo.full_name != github.repository`. It runs before checkout, prints a fixed `::error::` and does `exit 1`, with no `gh` and no `GH_TOKEN`.
- `ensure-labels` loses the `ai-cr:review` line and its comment about retries.
- Checkout has no `ref`; the rest of `with` and the comment on depth stay.
- `retry-cleanup` is removed. `post` and `failure-cleanup` are unchanged.
- New last step, `id: stop`, `name: Stop on a failed review`, `if: steps.review.outputs.verdict != 'pass'`, `run` prints a fixed `::error::` and does `exit 1`, with no expressions in `run`, no `env`, no `always()`.

#### 2. Workflow tests

**File**: `tests/test_review_workflow.py`

**Intent**: Replace guards for the removed paths with guards for the new safety properties. The header at `:1-14` stops describing the labels as a retry path.

**Contract**:

- Triggers: only `pull_request`, with exactly the three types (`:98-111`).
- No `if` on the job, replacing `:159-167`. The job key is exactly `review` and has no `name`.
- Checkout has no `ref` (`:144-149`). Concurrency and `PR_NUMBER` are event-only (`:170-182`).
- Guard is first, before checkout, reads the fork condition, has no `GH_TOKEN`, and its `run` contains `exit 1` (`:185-190`).
- Safe order ends with `failure-cleanup`, then `stop`, and `stop` is the last step (`:193-204`).
- `stop`: `name` is `Stop on a failed review`, `if` is exactly the verdict condition, with no `always()` or `failure()`, and `run` has `exit 1`.
- `failure-cleanup`'s `if` equals exactly `failure() && steps.guard.outcome != 'failure'`, and it is the only step with `failure()` or `always()` in its `if`. `retry-cleanup` and `ai-cr:review` appear nowhere in the file (`:226-245`).
- New: no other workflow in `.github/workflows/` (`*.yml`, `*.yaml`) has a job with id or `name` `review`.

### Success Criteria:

#### Automated Verification:

- Workflow tests pass: `uv run pytest tests/test_review_workflow.py`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check .` and `uv run ruff format --check .`
- Phase commit exists: `feat(ci-ai-review-gate): make the review job a real check that ends red on a fail`

---

## Phase 3: Docs and review before the first push

### Overview

Say what is true now, then review the whole change while it is still free to fix.

### Changes Required:

#### 1. Test plan

**File**: `context/foundation/test-plan.md`

**Intent**: Line 99 calls the review advisory. Replace with the gate (in Polish, like the file): wymagany check `review` na `main`, blokują cztery kryteria albo ucięty diff.

**Contract**: The "AI code review" row of the stack table; the rest of the row (limits, cost) stays.

#### 2. Deploy plan

**File**: `context/deployment/deploy-plan.md`

**Intent**: Fix stale facts and record the gate's operating rules in one place.

**Contract**:

- `:12`: keep the dated history and add that the 403 applied while private; the repo is public now and has branch protection through this change.
- `:151`: `(private)` becomes `(public)`, and the row names the required check.
- New short section on the gate, stating:
  - the required check is `review` (app 15368, `strict: false`, admins not enforced);
  - the repo must stay public, because going private disables protection on the free plan;
  - merge through GitHub, not a local fast-forward, because a red `review` on the same SHA can skip the Railway deploy;
  - retry with `gh run rerun <id>`, same SHA; this is also a re-roll of the model's answer, accepted as the owner's call, and useless for truncation, which needs a split PR;
  - a PR retargeted to `main` gets no run until a push or a reopen;
  - threat model: the gate stops honest mistakes and agents working normally, and the owner reads by hand any PR touching `.github/workflows/` or `scripts/review/`;
  - rollback: `gh api --method DELETE repos/LukaszSwiech/talkaitive/branches/main/protection`.

#### 3. Pre-push checks

**Intent**: The gate PR's own diff must not trip the truncation rule, and review findings must be fixed before any paid run.

**Contract**: Run `/10x-impl-review`, fix findings on the branch. Measure the diff the script will see: `git diff --no-ext-diff --no-color main...HEAD -- . ':(exclude)uv.lock' ':(exclude)package-lock.json' ':(exclude)context' | wc -m` must be under 100000, leaving a margin below `MAX_DIFF_CHARS`.

### Success Criteria:

#### Automated Verification:

- No stale wording remains: `grep -n "doradczy" context/foundation/test-plan.md` and `grep -n "(private)" context/deployment/deploy-plan.md` find nothing
- Reviewed diff is under 100000 characters
- Full quality gates are green: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
- Phase commit exists: `docs(ci-ai-review-gate): describe the gate, its limits and how to retry`

#### Manual Verification:

- `/10x-impl-review` is done and its findings are fixed before the first push

---

## Phase 4: Go live and fail test

### Overview

Real runs in the only safe order. Commands that change GitHub are named here; none merges anything.

### Changes Required:

#### 1. Control

**Intent**: Prove a real green `review` on the new rules before anything can block. It also records the check that protection needs within seven days.

**Contract**:

- `git push -u origin ci-ai-review-gate`, then `gh pr create --base main` with an English title and description, the description ending with the repo's attribution line.
- `gh pr checks <n> --watch`: `review` must be green, with one `ai-cr:passed` label and one comment.
- **If it is red, stop and show the user the comment.** Do not push a fix or re-run without a go-ahead.

#### 2. Protection

**Intent**: Turn the check on, after the control is green.

**Contract**: The exact call from `research.md`, section 4 (`checks: [{context: "review", app_id: 15368}]`, `strict: false`, `enforce_admins: false`, `required_pull_request_reviews: null`, `restrictions: null`). On a 422, add `"contexts": ["review"]`. Verify with `gh api repos/LukaszSwiech/talkaitive/branches/main/protection`.

#### 3. Fail test

**Intent**: Prove the gate stops a real violation: comment, label, red job, blocked merge.

**Contract**:

- `git switch -c ci-ai-review-gate-fail-test ci-ai-review-gate`.
- The violation: in `conversations/views.py:31`, `_get_conversation` uses `Conversation.objects.all()` instead of `for_user(request.user)`. No real secret, since the repo is public.
- One commit, `test(ci-ai-review-gate): deliberate data_isolation violation, never merge`, pushed. A PR to `main` titled "DO NOT MERGE: ...".
- Its diff against `main` also holds the whole gate change, as expected. A red `lint-and-test` there is expected too, and is not part of the evidence.
- Evidence: `gh pr view <n> --json comments,labels,mergeStateStatus` and `gh run view <id> --json jobs`:
  - comment posted, its `**Blocked:**` note names `data_isolation`, and that criterion's bullet scores at or below 3 (every comment lists all criteria, so the name alone proves nothing);
  - `ai-cr:failed` set;
  - job `review` red, and the failed step in the run data is `Stop on a failed review` (step id `stop`);
  - `mergeStateStatus` = `BLOCKED` (retry while `UNKNOWN`).
- If the model does not fail it: at most one `gh run rerun <id>`, noted in the evidence. Another blocker failing as well is fine. If it is still green, or `data_isolation` is missing from the note, or the status is not `BLOCKED`, stop and report.
- Clean up: `git switch ci-ai-review-gate`, then `gh pr close <n> --delete-branch`, which removes both the remote and the local branch; check that the branch is gone. The agent never merges this PR.

#### 4. Evidence

**Intent**: Record the proof where the change is tracked. This is the single accepted extra paid run.

**Contract**:

- Tick rows 4.1 to 4.7 and 4.9 in `## Progress` with one-line evidence on each row: PR number, run id, the tested SHA, and the observed values. Row 4.8 is the result of this commit's own run, so it stays open here.
- Add the protection date and fail test PR number to the gate section of `deploy-plan.md`.
- One commit, `chore(ci-ai-review-gate): record the gate's control and fail test evidence`, then one push. No `[skip ci]`, because it would leave the required check pending.
- `gh pr checks <n> --watch`: `review` green again, and `mergeStateStatus` is `CLEAN` (retry while `UNKNOWN`). A red run here is treated like a red control: stop and show the user.
- Row 4.8 is checked after this push and reported in the final report with its run id and SHA. It is ticked at `/10x-archive` on the change branch; there is no third paid push.

### User steps in the final report

Not granted to the agent:

- Merge the gate PR through GitHub's button.
- `gh api --method PUT repos/LukaszSwiech/talkaitive/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors`
- `gh label delete "ai-cr:review" --repo LukaszSwiech/talkaitive --yes`
- Decide on the proposal to require `lint-and-test` too (one more entry in `checks`).
- Decide on the `CLAUDE.md` wording proposals in `research.md`.

### Success Criteria:

#### Automated Verification:

- Control run on the gate PR is green with `ai-cr:passed` and a comment
- Branch protection requires only `review`, app 15368, `strict` false, admins not enforced
- Fail test comment is posted and names `data_isolation`
- Fail test PR has the `ai-cr:failed` label
- Fail test job `review` is red, failed at step `stop`
- Fail test `mergeStateStatus` is `BLOCKED`
- Fail test PR is closed unmerged and its branch is deleted
- Evidence commit's control run is green and the gate PR is `CLEAN`
- Final quality gates are green: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`

#### Manual Verification:

- The user merged the gate PR through GitHub, and the Railway deploy of the merge commit succeeded
- The user set the fork approval policy and deleted the `ai-cr:review` label

**Implementation Note**: The agent stops after the automated rows and reports, including row 4.8's run id and SHA. Rows 4.8, 4.10 and 4.11 stay open and are ticked on the `/10x-archive` branch, whose `context/`-only PR makes no model call.

---

## Testing Strategy

### Unit Tests:

- Verdict boundaries: each blocker at 3 and 4, each warning at 1, model fail alone, model pass with a failed blocker, truncation with perfect scores.
- Comment: each note present and absent, right names, order before model text, survives the cap, no "advisory".

### Integration Tests:

- Through `main` with a fake client: truncation, low warning, and a blocker failure give matching heading and `verdict=`, exit 0. Operational failures stay as they are: non-zero, no verdict.
- Workflow shape parsed as data: triggers, no job `if`, step order, stop condition, one job `review` across all workflows.

### Manual Testing Steps:

1. Real control run on the gate PR (Phase 4).
2. Real fail test, closed unmerged (Phase 4).
3. Not tested: `gh run rerun` turning red into green on one SHA, unless the fail test needs its one re-run. Fork behaviour stays inferred.

## Performance Considerations

Three paid runs are planned: control, fail test, evidence control. Each is at most about 0.19 USD by the script's worst case (120,000 characters, 6,000 output tokens); a past run cost about 0.05 USD.

## Migration Notes

No data changes. Rollback: `gh api --method DELETE repos/LukaszSwiech/talkaitive/branches/main/protection` removes protection at once; revert the merge for the code. Between setting protection and the user's merge, a PR from another branch would still run the old workflow from its own merge commit. There are no other open PRs, so merge soon after the evidence run.

## References

- Research and decisions: `context/changes/ci-ai-review-gate/research.md`
- Public exposure scan: `context/changes/ci-ai-review-gate/public-exposure-report.md`
- Prior change: `context/archive/2026-10-31-ci-ai-code-review/plan.md`
- Code: `scripts/review/criteria.py:79-107`, `scripts/review/run_review.py:170-208`, `scripts/review/run_review.py:303-307`, `.github/workflows/ai-review.yml:6-34`

## Implementation Notes

Deviations from the phase text, recorded during `/10x-implement`:

- Phase 1, empty-diff branch: the plan says the branch tests `full_diff.strip()`, and also that a truncated diff can never take it and that `" " * (MAX_DIFF_CHARS + 1)` gives `verdict=fail`. `full_diff.strip()` alone would pass that whitespace diff, so the condition is `not truncated and not full_diff.strip()`, which meets the other two statements. The stricter reading won.
- Phase 2, stop step (impl-review F1): the condition changed from `== 'fail'` to `!= 'pass'`, so only an explicit pass ends green; the Phase 2 contract above is updated to match. In a run that exits 0 with no verdict, an older `ai-cr:passed` label can remain next to the red job (accepted).
- Phase 1, comment (impl-review F5): a fixed `**Model summary (untrusted):**` line now comes before the model's summary.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Criteria, verdict and comment

#### Automated

- [x] 1.1 Criteria tests pass: `uv run pytest tests/test_review_criteria.py` — ee63b37
- [x] 1.2 Script tests pass: `uv run pytest tests/test_review_script.py` — ee63b37
- [x] 1.3 Full suite passes: `uv run pytest` — ee63b37
- [x] 1.4 Lint and format are clean: `uv run ruff check .` and `uv run ruff format --check .` — ee63b37
- [x] 1.5 Phase commit exists: `feat(ci-ai-review-gate): six criteria, blockers and one verdict for the comment and the output`, also holding this folder's `change.md`, `research.md`, `public-exposure-report.md`, `plan.md`, `plan-brief.md` and `reviews/plan-review.md` — ee63b37

### Phase 2: Workflow

#### Automated

- [x] 2.1 Workflow tests pass: `uv run pytest tests/test_review_workflow.py` — cef42e1
- [x] 2.2 Full suite passes: `uv run pytest` — cef42e1
- [x] 2.3 Lint and format are clean: `uv run ruff check .` and `uv run ruff format --check .` — cef42e1
- [x] 2.4 Phase commit exists: `feat(ci-ai-review-gate): make the review job a real check that ends red on a fail` — cef42e1

### Phase 3: Docs and review before the first push

#### Automated

- [x] 3.1 No stale wording remains: `grep -n "doradczy" context/foundation/test-plan.md` and `grep -n "(private)" context/deployment/deploy-plan.md` find nothing — 7e495b5
- [x] 3.2 Reviewed diff is under 100000 characters — 7e495b5
- [x] 3.3 Full quality gates are green: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` — 7e495b5
- [x] 3.4 Phase commit exists: `docs(ci-ai-review-gate): describe the gate, its limits and how to retry` — 7e495b5

#### Manual

- [x] 3.5 `/10x-impl-review` is done and its findings are fixed before the first push

### Phase 4: Go live and fail test

#### Automated

- [x] 4.1 Control run on the gate PR is green with `ai-cr:passed` and a comment — PR 29, run 41391187741, SHA 43aebf0: `review` success, `mergeStateStatus` CLEAN, label `ai-cr:passed`, comment "AI review: pass" (correctness 6/10)
- [x] 4.2 Branch protection requires only `review`, app 15368, `strict` false, admins not enforced — read back after the PUT: checks `[{review, 15368}]`, strict false, admins false; `checks` without `contexts` was accepted
- [x] 4.3 Fail test comment is posted and names `data_isolation` — PR 30, SHA 74d7411: "**Blocked:** data_isolation, correctness scored at or below the floor of 3" (data_isolation 1/10, correctness 1/10); `tests` 2/10 appears as a separate warning
- [x] 4.4 Fail test PR has the `ai-cr:failed` label — PR 30 labels: `["ai-cr:failed"]`, still there after the red job
- [x] 4.5 Fail test job `review` is red, failed at step `stop` — run 41393876424: job failure; post success, failure-cleanup skipped, "Stop on a failed review" failure
- [x] 4.6 Fail test `mergeStateStatus` is `BLOCKED` — read on PR 30 before closing: BLOCKED, mergeable MERGEABLE, only required check `review` (`lint-and-test` also failed there, but is not required)
- [x] 4.7 Fail test PR is closed unmerged and its branch is deleted — PR 30: state CLOSED, mergedAt null; `git ls-remote` for `ci-ai-review-gate-failtest` is empty
- [ ] 4.8 Evidence commit's control run is green and the gate PR is `CLEAN`
- [x] 4.9 Final quality gates are green: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` — 712 passed, ruff clean, on 43aebf0

#### Manual

- [ ] 4.10 The user merged the gate PR through GitHub, and the Railway deploy of the merge commit succeeded
- [ ] 4.11 The user set the fork approval policy and deleted the `ai-cr:review` label
