# AI review merge gate — Plan Brief

> Full plan: `context/changes/ci-ai-review-gate/plan.md`
> Research: `context/changes/ci-ai-review-gate/research.md`

## What & Why

The AI review only advises today: a failed review leaves the job green, so nothing stops a merge. This change makes job `review` the required check on `main`, so a serious finding really blocks. Warnings stay warnings, so the model's opinion alone cannot stop a PR.

## Starting Point

The script scores six criteria and fails on any low score or the model's own fail, but exits 0. The workflow skips forks (a skipped required check counts as passed) and has `labeled` and `workflow_dispatch` paths. `main` has no protection, and there are no open PRs.

## Desired End State

A blocker at or below 3, or a truncated diff, posts the comment and `ai-cr:failed`, then ends the job red and blocks the merge. Low warnings and the model's own fail appear as fixed notes and do not stop the PR. A real fail test proves it, and its evidence is in `plan.md`.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Criteria | `data_isolation`, `tests`, `no_secrets`, `openai_boundary`, `correctness`, `migrations` | Fits what can really break production | Research |
| Blockers | `data_isolation`, `no_secrets`, `correctness`, `migrations` | `tests` and `openai_boundary` are warnings only | Research |
| Verdict | Fail on a blocker `<= 3` or truncation; the model's verdict is never read | It cannot rescue a blocker or stop a PR alone | Research |
| Truncated diff | Still call the model, verdict fail, comment says so | Keeps a useful partial review | Orchestrator |
| One verdict | Computed once in `run`, passed to the comment | Comment and output cannot differ | Orchestrator |
| Truncation signal | Explicit `truncated` flag, not `dropped_paths` | An over-cap diff can have no dropped paths | Plan |
| Who decides red | The workflow's last step; the script keeps exit 0 | Comment and label are already posted | Research |
| Fork handling | Guard step fails red before checkout | Skipped would pass; it is not an anti-spoof control | Research |
| Required checks | Only `review`, app 15368, `strict` false, admins not enforced | As decided; `lint-and-test` is a proposal | Orchestrator |
| Order | Control, protection, fail test, evidence, then the user merges | The agent never merges | Orchestrator |
| Fail test base | From the gate branch, not a new `main` | Gate is not merged yet, and the merge commit carries the new workflow | Orchestrator |
| Red control | Stop and show the user, no fix push | Every push is a paid run | Plan |

## Scope

**In scope:**

- `scripts/review/criteria.py`, `scripts/review/run_review.py`, `.github/workflows/ai-review.yml` and their tests
- `context/foundation/test-plan.md`, `context/deployment/deploy-plan.md`
- Branch protection on `main`, one throwaway fail test PR

**Out of scope:**

- Merging anything; requiring `lint-and-test`
- Fork approval policy and deleting the `ai-cr:review` label (user steps)
- `CLAUDE.md`, `context/archive/`, `.claude/`, `ci.yml`
- New mutants (none cover `scripts/review/`) and the AI eval (does not depend on review criteria)

## Architecture / Approach

The script writes one verdict after the comment. The workflow posts the comment and label, leaves failure-cleanup alone because no step has failed, and its last step turns verdict fail into red. An operational failure sets no verdict and stays red, so it fails closed. A required check is only a name on a SHA, and a PR can edit its own workflow: the gate stops honest mistakes, and the owner reads PRs touching `.github/workflows/` or `scripts/review/` by hand.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Criteria, verdict and comment | New rule, one verdict, fixed notes, tests | Comment and verdict drifting apart |
| 2. Workflow | One trigger, red forks, stop step, guard tests | Stop step placed so labels get deleted |
| 3. Docs and review before the first push | Docs, `/10x-impl-review`, diff size check | Bug found only after a paid run |
| 4. Go live and fail test | Control, protection, fail test, evidence | Non-deterministic model on real runs |

**Prerequisites:** branch `ci-ai-review-gate`, `OPENAI_API_KEY` secret already set, repo stays public.
**Estimated effort:** about 2 sessions; 3 paid runs, each at most about 0.19 USD.

## Open Risks & Assumptions

- The model is not deterministic: the control may go red on a false positive, or the fail test may stay green. Control: stop and ask. Fail test: one re-run, then stop.
- `checks` without `contexts` is inferred to be accepted; the fallback for a 422 is in the plan.
- `BLOCKED` comes from a secondary source; `UNKNOWN` is retried, anything else stops the rollout.
- Fork behaviour is inferred, not tested with a real fork.
- Between protection and the user's merge, other PRs would run the old workflow. There are none open now.

## Success Criteria (Summary)

- `uv run pytest` and ruff are green, with tests covering the verdict rule and truncation.
- A real violation gets a comment, `ai-cr:failed`, a red job and `BLOCKED`; evidence is in `## Progress`.
- The gate PR ends green and ready for the user to merge.
