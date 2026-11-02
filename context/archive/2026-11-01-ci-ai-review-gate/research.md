---
date: 2026-11-01T22:20:03+0100
researcher: Claude (10x-research subagent)
git_commit: f3a97898b4de541586622d1992a63013116a7fa2
branch: ci-ai-review-gate
repository: LukaszSwiech/talkaitive
topic: "Turn the advisory AI review into a real merge gate: risks of a required check `review` on main"
tags: [research, ci, github-actions, branch-protection, ai-review, railway]
status: complete
last_updated: 2026-11-01
last_updated_by: Claude (10x-research subagent)
---

# Research: Turn the advisory AI review into a real merge gate

**Date**: 2026-11-01T22:20:03+0100
**Researcher**: Claude (10x-research subagent)
**Git Commit**: f3a97898b4de541586622d1992a63013116a7fa2
**Branch**: ci-ai-review-gate
**Repository**: LukaszSwiech/talkaitive (public)

Evidence labels: **[confirmed-doc]** stated by the cited doc, **[confirmed-data]** seen in this repo's API data on 2026-11-01, **[inferred]** reasoned from those, **[secondary]** a non-GitHub source. All GitHub calls were read-only. Nothing was changed on GitHub.

## Decisions (source of truth, decided with the user 2026-11-01)

Recorded verbatim:

> Six criteria: data_isolation, tests, no_secrets, openai_boundary, correctness (new: logic errors, missed cases, regressions), migrations (new: main auto-deploys and migrate runs pre-deploy, so risky migrations count). Removed: ui_contract, type_hints.
>
> Blockers: data_isolation, no_secrets, correctness, migrations. Warnings only: tests, openai_boundary.
>
> Verdict rule: fail when a blocker scores <= FAIL_FLOOR (3), or the diff was truncated. A low warning criterion, or the model's own fail alone, is a warning and does not stop the PR. The model's verdict can never turn a blocker failure into a pass. An empty diff passes. An operational failure (API, key, bad output) keeps the job red, so it fails closed.
>
> Real stop: on verdict fail the job must end red AFTER the comment and ai-cr:failed label are posted; the failure-cleanup step deletes result labels on failure(), and must not remove them in this case.
>
> Repo is public for now, which is what makes branch protection available on the free plan; going private disables it.

Goal of the change: job `review` becomes a required check on `main`, admins not enforced.

## Research Question

Verify four risks against current GitHub and Railway docs and this repo's data (skipped/fork/spoofed checks; replaced conclusions, dispatch and retry; Railway "Wait for CI"; effect of protection on open PRs and the order of steps), map all the code that must change, and confirm or refute the candidate design.

## Summary

| Risk | Verdict |
| --- | --- |
| 1a. Skipped job passes a required check | **Real, confirmed.** Today's job-level `if` would let fork PRs pass. Must go. |
| 1b. A PR edits the workflow, or adds a job `review`, and goes green | **Real and not closable by branch protection or `app_id`.** All Actions jobs share app 15368. A fork step that fails red can be deleted by that same fork. The real limits: the only collaborator is the admin owner, so a fork author cannot merge, and fork runs can require approval. The gate stops honest mistakes, not a hostile editor. |
| 1c. Fork approval | Stricter setting exists: `all_external_contributors`, settable by REST on the repo. Current value: `first_time_contributors`. |
| 2a. Unrelated `labeled` event opens the gate | **Plausible, undocumented, not observed here. Removing `labeled` closes it.** Surprise: REST `filter=latest` returns one run per check suite, so failed runs stay listed next to a later success on one SHA. |
| 2b. `workflow_dispatch` puts `review` on the wrong commit | **Attachment confirmed.** Per docs it does not satisfy a required check on a ruleset (branch protection is inferred the same), but it can skip a Railway deploy. Remove. |
| 2c. Retry after removing `labeled`/dispatch | Re-run job (UI or `gh run rerun`) keeps the same `GITHUB_SHA`. Not yet seen in this repo: no run in the last 100 has `run_attempt > 1`. Verify during implementation. |
| 3. Railway "Wait for CI" | **Safe in the normal flow.** PR merges from the button make a new SHA with no `review` suite. Only a local fast-forward push of a red SHA, or a red dispatch on main, could skip a deploy. The first needs admin bypass; the second goes away with the trigger. |
| 4. Effect on open PRs, order | **No open PRs, no protection, no rulesets now.** Exact call below. Order confirmed. A cancelled run does not satisfy the check. |

**Candidate design: confirmed, with one correction.** The fork step is good for clarity and cost but is not a security control; pair it with the stricter approval policy and a stated threat model. Details in [Recommended design](#recommended-design).

## Detailed Findings

### 1. Skipped jobs, forks and spoofing

**Skipped jobs pass.** [confirmed-doc] A job skipped by a conditional "will report its status as "Success"" and successful statuses are `success`, `skipped`, `neutral` ([troubleshooting required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks), [job conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)). The job `if` at `.github/workflows/ai-review.yml:30-34` skips fork PRs, so they would pass. By contrast, a workflow skipped by a branch or path filter, or a commit message, stays "Pending" and blocks (same doc). So `[skip ci]` fails safe, and the job must have no job-level `if`.

**A PR controls its own workflow.** [confirmed-doc] `pull_request` "runs the workflow file from the merge commit" of the PR, and for a fork that commit is controlled by someone without write access; those runs get a read-only token and no secrets ([securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)). [inferred] So any PR, fork or same-repo, can replace the job with `exit 0`, or change `scripts/review/`, which the workflow runs from the merge commit (`ai-review.yml:83-98`). A same-repo PR also holds the model key while doing so; forks do not.

**A second job named `review`.** [confirmed-doc] GitHub warns that the same job name in several workflows gives "ambiguous status check results" ([about protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)). Which result wins is not documented. [inferred] A guard test can stop this by mistake, not by intent, because the PR can edit the test too.

**`app_id` does not help against this.** [confirmed-data] All check runs in this repo come from `github-actions`, app id 15368 (`review` and `lint-and-test` on `65073228`). [inferred] A spoofed job from a PR-edited workflow is the same app. [secondary] A public workflow comment measured the same point ([ranex example](https://github.com/anthonykewl20/ranex/blob/f46c4e5ade1216f7a4bc299fc3446bae116c1acd/.github/workflows/architecture-contracts.yml)). Pinning still has a small use: it rejects a commit status or check of that name from another source. [confirmed-doc] Omitting `app_id` "automatically" selects the app that recently provided the check, and `-1` allows any ([PUT protection](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection)). Recommendation: pass 15368 explicitly, and do not claim it stops spoofing.

**A ruleset `workflows` rule?** The secondary source above mentions one that pins a workflow by SHA. It is not on GitHub's [available rules page](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) (grep of that page for "require workflows" and "workflows to pass" found nothing). Treat as not available for this repo unless the plan proves otherwise.

**What limits the harm.**
- [confirmed-data] The only collaborator is `LukaszSwiech` (admin), so a fork author cannot press merge. A green spoofed check misleads the owner; it does not merge anything.
- [confirmed-doc] Fork runs get no secrets, so a fork that keeps the real script exits 2 on the missing key (`scripts/review/run_review.py:261-263`), red.
- Stricter approval, next.

**Approval settings.** [confirmed-data] `GET .../actions/permissions/fork-pr-contributor-approval` returns `first_time_contributors`. [confirmed-doc] The enum is `first_time_contributors_new_to_github`, `first_time_contributors`, `all_external_contributors`, with GET and PUT at repo level ([Actions permissions REST](https://docs.github.com/en/rest/actions/permissions)). GitHub warns that with the first two settings, someone with any merged commit or PR no longer needs approval, and says these policies target compute use ([Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)). Approvers should be "especially alert" to `.github/workflows/` changes ([approving runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks)). Setting call, for the user to approve:

```sh
gh api --method PUT repos/LukaszSwiech/talkaitive/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors
```

**An unapproved fork run.** [secondary + inferred] Required checks stay "Expected — Waiting for status to be reported" and block, because the job never started; reported in the field for workflows awaiting approval ([explainer](https://lesstep.com/github-pull-requests/errors/required-check-expected/), [issue example](https://github.com/PicPeak/picpeak/issues/719)). [confirmed-doc] After 30 days such a run expires and is marked failed. Not tested here: this needs a real fork PR. Fail-safe either way.

**Other paths found that also block (fail safe).** [secondary] `pull_request` workflows do not run while a PR has a merge conflict. [inferred] A PR opened against another branch and retargeted to `main` gets no run, since `edited` is not in `types`; it blocks until a push or a reopen. Dependabot would behave like a fork (no secrets, red), but [confirmed-data] no `.github/dependabot.yml` exists and no Dependabot PRs were found.

### 2. Conclusions on one commit, dispatch and retry

**Real data, PR 28** (all `review` runs are `pull_request` events):

| Commit | `review` runs (`filter=all`) | Same with `filter=latest` |
| --- | --- | --- |
| `65073228` | failure 21:06:52, failure 21:11:32, success 21:13:59, each in its own suite | **the same 3 runs** |
| `9338faa8`, `0b894d69`, `cb533822` (head) | one success each | same |
| `f3a97898` (merge commit on main) | none; only `lint-and-test` success | same |

- [confirmed-data] **No skipped `review` run exists** in this data: none among the 6 runs of `ai-review.yml`, and no skipped run in the last 100 of the repo. The requested skipped-run evidence does not exist here.
- [confirmed-data] Each new event creates a new check suite on the same SHA, and `filter=latest` kept all three runs. The docs say only that `latest` "returns the most recent check runs" ([check runs REST](https://docs.github.com/en/rest/checks/runs)). So in REST, a later run does not visibly replace an earlier one from another suite.
- **Unresolved:** docs do not state how protection chooses between suites on one SHA. The repo was unprotected during PR 28, so its data cannot settle this. [secondary] A [runner discussion](https://github.com/actions/runner/discussions/3202) reports a required check stuck on a cancelled earlier run after `opened` + `labeled`; the opposite direction (later skipped opens the gate) is the risk to avoid. With `skipped` in the success set, treat it as possible.
- Removing `labeled` makes the question moot for labels. It remains only for close-and-reopen on one SHA, which is a deliberate owner action. If a stale result sticks, a new commit gives a new SHA, since "checks from earlier commits" do not count.

**Labels from `GITHUB_TOKEN`.** [confirmed-doc] They do not create runs: `labeled` is among the types that "do not create workflow runs" ([GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token)). [confirmed-data] Consistent: the workflow's own labels on PR 28 produced no extra runs.

**`workflow_dispatch`.**
- [confirmed-data] It attaches a check run with the job's name to the dispatched ref's head SHA: `e306597e` holds two `lint-and-test` runs in two suites, one `workflow_dispatch`, one `pull_request` (PR 21).
- [confirmed-doc] Runs from `workflow_dispatch` "do not satisfy a required status check in a branch ruleset" and do not appear in the PR's checks. The doc names rulesets; [inferred] branch protection likely matches. Verify if the trigger were kept.
- [inferred] Wrong-commit case: today a dispatch from branch A with `pr_number` of PR B checks out B's merge (`ai-review.yml:87`) but reports on A's head. A red dispatch on `main` also adds a failed suite there, which matters for Railway (section 3).
- Remove it from this workflow. `ci.yml:9` keeps its own dispatch; that is out of scope, under another job name.

**Retry path after removal.** [confirmed-doc] Re-runs use "the same `GITHUB_SHA`" and `GITHUB_REF` as the original event, up to 30 days after the run and 50 times; commands are `gh run rerun RUN_ID` and `gh run rerun RUN_ID --failed` ([re-running](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)). [inferred] It reports under the same SHA and name. [confirmed-data] No run in the last 100 has `run_attempt > 1`, so this repo has no example. Other paths: push a commit, or close and reopen.

**Surprise: re-roll.** [inferred] A red blocker verdict can be re-run for a new model answer at no code change, and may turn green. The operational retry and the re-roll are the same button. Accepted as part of "owner's gate"; say so in the docs.

### 3. Railway "Wait for CI"

[confirmed-doc] From [Railway docs](https://docs.railway.com/guides/github-autodeploys): a deployment waits until "every GitHub Actions check suite on the commit has finished"; Railway reads each workflow run's conclusion; a failed one skips the deployment immediately; skipped or neutral never blocks; a cancelled one blocks only if no other workflow on that commit succeeded; other apps' checks are ignored; two hours unfinished means skipped.

[confirmed-data] `ci.yml:5-6` is the only `push` trigger, and merge commit `f3a97898` has only the `lint-and-test` suite. The queued `railway-app` and `claude` suites are other apps.

| Path to `main` | New SHA? | Red `review` on it? | Deploy |
| --- | --- | --- | --- |
| Merge button | Yes, as with PR 28 | No | Normal |
| Squash, or Rebase and merge | Yes: GitHub "creates new commit SHAs" ([merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github)) | No | Normal |
| Admin merge past a red check, by button | Yes | No | Normal, and a blocked review deploys. By design of admins-not-enforced |
| Local fast-forward push of the PR head | **No** | Possible: all suites on that SHA count, including old failed ones like `65073228` ([inferred] from the Railway rule) | **Could skip** |
| Red dispatch on main before the deploy starts | No | Yes | **Could skip**; gone with the trigger |

**Conclusion:** gate does not affect normal deploys. Keep no `push` trigger. Rule for the docs: merge through GitHub, not by a local fast-forward. If a deploy is skipped, Railway's "Deploy Latest Commit" exists. `context/deployment/deploy-plan.md:151` already warns about workflows on `push`.

### 4. Protection: effect, exact call, order

[confirmed-data] Open PRs: **none**. `GET .../branches/main/protection` returns 404 "Branch not protected". Rulesets: empty. Visibility: public. Last `review` success: 2026-11-01 20:11:31Z.

**Exact call** (a user-approved write, not run here):

```sh
gh api --method PUT repos/LukaszSwiech/talkaitive/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": false,
    "checks": [{ "context": "review", "app_id": 15368 }]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
```

[confirmed-doc] [PUT protection](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection): `required_status_checks`, `enforce_admins`, `required_pull_request_reviews`, `restrictions` are required and nullable. `contexts` carries a "Closing down notice" pointing to `checks`, yet is still listed as required. [inferred] `checks` alone should be accepted. If the call returns 422, add `"contexts": ["review"]`. `enforce_admins` is documented "boolean or null"; `false` follows the decision.

Side effects: [confirmed-doc] each rule by default disables force pushes and deletion of `main`, except that the restrictions do not apply to admins here; [confirmed-doc] checks must have "completed successfully" within seven days to be required, which the data above meets until about 2026-11-08 (a new control run refreshes it); [inferred] `strict: false` means a green review may be against an older `main`; and direct pushes by non-admins are refused.

**Order, confirmed:**

1. Open the change's PR. Its `pull_request` run already uses the new workflow from its merge commit, so it is the control: a real `review` success on the new rules.
2. Set protection and the approval policy, after the control is green. Reversed, the first red run would block with nothing proved. [inferred] `mergeStateStatus` before protection cannot show `BLOCKED` for a failed non-required check.
3. Merge the change PR through the gate.
4. Fail test: from the new `main`, a throwaway PR with a deliberate blocker (for example a query without `for_user`; never a real secret, since the repo is public). Expect: comment, `ai-cr:failed` present, job red, `gh pr view <n> --json mergeStateStatus` = `BLOCKED` ([secondary] for that value; the GraphQL enum page was not retrievable). May read `UNKNOWN` at first; retry. Close without merging. Doing this after step 3 keeps the diff small and the cost low.

**Cancelled runs.** [confirmed-doc] `cancelled` is a distinct conclusion, not in the success set (`success`, `skipped`, `neutral`) ([status checks](https://docs.github.com/en/pull-requests/reference/status-checks)). [secondary] It blocks until a new run. [confirmed-doc] Old-SHA results do not count, so `cancel-in-progress` on a new push is harmless. Same-SHA races are covered in section 2; without `labeled` they need a manual close and reopen.

## Candidate design: verdict

| Part | Verdict |
| --- | --- |
| No job-level `if` | **Confirmed**, required |
| First step fails red for a fork, before checkout | **Confirmed as UX and safety, refuted as an anti-spoof control.** Keep the id `guard`, so the cleanup condition `steps.guard.outcome != 'failure'` still spares a read-only token a 403 |
| Drop `labeled`, `workflow_dispatch`, `ai-cr:review` | **Confirmed.** Also removes the odd concurrency branch, retry-cleanup step and Ensure-labels line |
| Retry through re-run | **Confirmed by docs**; first real re-run should be observed |
| Last step `exit 1` on verdict fail, after failure-cleanup | **Confirmed.** `failure()` is false at cleanup since no step failed, so labels stay. If `post` fails, cleanup runs, this step is skipped by the implicit `success()`, and the job is red anyway |

### Recommended design

```yaml
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]
concurrency:
  group: ai-review-pr-${{ github.event.pull_request.number }}
  cancel-in-progress: true
# job `review`: no job-level if; PR_NUMBER only from the event
# steps: guard (if head.repo.full_name != github.repository: error + exit 1)
#        -> ensure-labels (two labels) -> checkout -> uv -> review -> post
#        -> failure-cleanup (unchanged condition)
#        -> stop: if steps.review.outputs.verdict == 'fail', error + exit 1
```

`run_review.py` keeps exit 0 for a reviewed fail (`:11`), so the workflow stays the one place deciding red. Also: set `all_external_contributors`; add a guard test that no other workflow defines a job named `review`; write the threat model plainly: **the gate stops honest mistakes and agents working normally; when a PR touches `.github/workflows/` or `scripts/review/`, the owner reads those files by hand.**

A stronger option, not recommended now: a base-branch `pull_request_target` guard job, required too, with no checkout. It could not be edited by a PR. It adds a riskier trigger and a second required check for a one-person repo, and how its check attaches to the head SHA was not verified.

## Code References

### `scripts/review/criteria.py`
- `:3-6` docstring: "six TalkAItive criteria", UI example, floor wording
- `:32-74` fields: remove `type_hints` (`:40-45`), `ui_contract` (`:67-74`); add `correctness`, `migrations`. Keep "1", "10" and "does not touch" in each description (test `:66-72`)
- `:79-86` `CRITERIA`; add a `BLOCKERS` set or similar
- `:94-96` `floor_failed`: any criterion, becomes blockers only. Add a helper for low warnings
- `:99-107` `final_verdict`: `review.verdict == "fail"` must no longer fail; needs a truncation input. Only callers: `run_review.py:40,179,306`

### `scripts/review/run_review.py`
- `:59` `_ADVISORY_NOTE`, used `:185,:204`: remove or replace
- `:1-22` docstring: add that a fail verdict ends red through the workflow; exit codes unchanged
- `:74-75` prompt, and `:76-79` `_TRUNCATED_INSTRUCTION`: still valid, but a truncated PR now fails regardless; say so in the comment
- `:150-160` `_scope_note` "Truncated" text: state that this fails the review
- `:170-196` `render_comment`: takes `dropped_paths`, not `truncated`; `:186-190` note assumes model pass → floor fail. Now three cases need text: blocker override, truncation fail, model fail or low warning that stays pass
- `:267` `truncated` computed; `:303-307` passes only `final_verdict(review)`: must pass truncation. `render_comment` calls `final_verdict` again at `:179`; use one value so comment and verdict cannot differ
- `:273-276` empty diff passes: unchanged, matches the decision

### `.github/workflows/ai-review.yml`
- `:3-4` header "Advisory: never a required check": rewrite
- `:8` drop `labeled`; `:9-14` drop dispatch; `:20-25` simplify concurrency
- `:29-34` remove job `if`; `:38` event-only PR number
- `:41-53` guard: new condition and check; `:55-56,:78` drop `ai-cr:review`
- `:87` checkout ref: drop the expression (default is the merge commit); comment `:80-82` still applies
- `:142-162` failure-cleanup: keep; `:164-184` retry-cleanup: remove
- append final stop step after `:162`

### `tests/test_review_criteria.py`
- `:37-44` `SIX_CRITERIA`: new names; `:71` comment
- `:96-97` model fail stays fail → inverted: stays pass
- `:100-102` every criterion fails at floor → only blockers; add warnings stay pass, and a blocker fail with model pass; add truncation
- `:105-106` uses `tests`: pick a blocker

### `tests/test_review_script.py`
Uses of `tests=` as a failing criterion must move to a blocker: `:261` (`:260-265`), `:317` (`:311-331`), `:337`, `:633` (`:630-639`), `:837`.
- `:249-253`, `:327`, `:341` assert the advisory note → new wording
- `:268-272` model fail "AI review: fail" → now pass with a warning
- `:292-298`, `:796-826` truncation comment tests: add verdict fail and `verdict=fail` output; `:533-547` prompt test stands
- `:636-639` exit 0 with fail stands: red comes from the workflow

### `tests/test_review_workflow.py`
- `:98-111` triggers: only `pull_request`, no `labeled`, no dispatch
- `:144-149` checkout ref assertions
- `:159-167` job `if`: replace with "no `if`" (safety property, keep as a guard)
- `:170-175`, `:178-182` concurrency, PR number
- `:185-190` guard asserted for dispatch → for forks; still first and before checkout
- `:193-204` order: drop `retry-cleanup`, add stop last
- `:226-232`, `:235-239`, `:245` retry-cleanup references
- New: stop step comes after failure-cleanup and reads the verdict through `if`; no other workflow has job `review`
- `:1-14` and `:159` wording

### Repo mentions outside `context/archive` (grep, excluding `.claude`, `.agents`)
- `advisory`: the above, plus `context/changes/ci-ai-review-gate/change.md:3,12` (its own title)
- `ui_contract`, `type_hints`: only criteria files and their tests
- `ai-cr:*`, `pr_number`: only workflow and workflow tests
- `context/foundation/test-plan.md:99`: "jest tylko doradczy i nie blokuje merge'a" → update
- `context/deployment/deploy-plan.md:12` "branch protection on a private repo needs..." and `:151` "(private)": stale, the repo is public; add the gate and protection
- `CLAUDE.md`: no match on these terms, but see below

**Runtime settings outside the repo (user-approved):** protection, approval policy, optional removal of the existing label `ai-cr:review`.

## CLAUDE.md wording proposals (not edited in this change)

- At `CLAUDE.md:46` (Production on Railway), after the CI sentence: "Merging to `main` also requires the check `review` (`.github/workflows/ai-review.yml`; admins not enforced). It has no `push` trigger on purpose: Railway waits on all workflows on a commit. Merge through GitHub, not a local fast-forward: a red `review` on the same SHA skips the deploy."
- A new line: "Repo must stay public for branch protection on the free plan; going private disables it."
- A new line: "AI review retry: `gh run rerun <id>`. When a PR touches `.github/workflows/` or `scripts/review/`, read them by hand: a PR can edit its own gate."
- `CLAUDE.md:43` needs no change for this topic.

## Architecture Insights

- A required check is a name on a SHA; the workflow behind it is PR-editable. The gate's strength is who can merge, not the check.
- The design keeps one decision point: the script writes the verdict, the workflow turns it into red. That keeps the comment and label on a failure.
- Fail-closed comes from the existing order (`verdict` set only after the comment, `run_review.py:246-253`).

## Historical Context (from prior changes)

- `context/archive/2026-10-31-ci-ai-code-review/plan.md:39,41`: no required check, no `pull_request_target`, no fork reviews. The second stands; the first is what this change reverses.
- `plan.md:71-72,244-245`: guard, labeled and concurrency reasoning, all removable with the triggers.
- `plan.md:320` expected a red run before the key was set, and `:438` records the label retry. [inferred] These explain the two failures on `65073228`.
- `research.md:148` (same folder): `GITHUB_TOKEN` label finding; still correct. `research.md:298` and `deploy-plan.md:12`: branch protection gave 403 while private (2026-10-14); superseded as the repo is now public.

## Related Research

- `context/archive/2026-10-31-ci-ai-code-review/research.md`
- `context/archive/2026-10-14-testing-suite-trust-and-ci/research.md`

## Open Questions

For `/10x-plan` or the user; none blocks planning:

1. **Should `lint-and-test` be required too?** Only `review` was decided. Today a red CI PR could merge, and Railway would then skip its deploy. Adding it costs one array entry. Recommended; user's call.
2. **On truncation, call the model or not?** The verdict is already fail. Calling gives a useful partial review at a cost; skipping is cheaper. Recommendation: keep the call, smallest change, and comment stays useful.
3. **How should a warning look in the comment?** Decisions say "is a warning" but not the format. Suggest a fixed note before model text, per `render_comment`'s rule at `run_review.py:176-177`.
4. **Verify at implementation (cannot be tested read-only):** re-run replaces red on the same SHA; `checks` without `contexts` is accepted; `BLOCKED` on the fail test. Fork approval behaviour needs a real fork; if none is available, leave it marked inferred.
