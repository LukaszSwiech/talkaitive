# AI code review agent in GitHub Actions — Plan Brief

> Full plan: `context/changes/ci-ai-code-review/plan.md`
> Research: `context/changes/ci-ai-code-review/research.md`

## What & Why

On every same-repo PR to `main`, a Python script reviews the diff with OpenAI in one structured call, and a workflow posts one comment and sets `ai-cr:passed` or `ai-cr:failed`. The purpose is 10xChampion evidence: a pipeline view, job logs with a cost line, and an LLM review comment on a PR. The check is advisory and never blocks a merge.

## Starting Point

`ci.yml` already lints and tests any new files and needs no edit. `talkaitive.settings` can supply the model and prices without booting Django. No `ai-cr:*` label exists, and the secret `OPENAI_API_KEY` was not set when research ran.

## Desired End State

The PR for this change shows one AI review comment and exactly one result label, its run is green, and the log shows a cost line and no diff or model text. Adding `ai-cr:review` re-runs the review.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Call path | Script imports `openai` directly, no `django.setup()` | The brief wants a standalone script; the criterion exempts `scripts/review/` and `tests/` | Research / Orchestrator |
| Prices and model | `from talkaitive.settings import ...`, pure `cost_usd`, drift test against `turn_cost` | `conversations.budget` cannot be imported without Django | Research / Orchestrator |
| Diff | `git diff --no-ext-diff HEAD^1 HEAD` with `fetch-depth: 2`, excluding `uv.lock`, `package-lock.json`, `context/`; 60k cap with a visible note | Otherwise `context/` uses the budget ahead of application code | Research / Orchestrator |
| Score type | `Literal[1..10]` | `enum` is the existing pattern, and only a paid call could prove `minimum`/`maximum` | Plan |
| Verdict | Model verdict plus a floor: any score at or below 3 forces `fail` | Cheap resistance to prompt injection; it can lower a verdict and never raise one | Orchestrator / Plan |
| Not applicable | A criterion the diff does not touch scores 10 | Otherwise the floor fails every backend PR on the UI criterion | Plan |
| Empty diff | `context/`-only PR: no model call, `pass`, comment says nothing was reviewable | Saves a paid call on a PR with nothing to review | Plan |
| Exit codes | `fail` exits 0; operational failures exit non-zero and set no pass label | The label carries the result, and the red run shows a failure | Orchestrator |
| Stale labels | Operational failure removes both result labels | A pass from an older commit must not survive a run that could not review the new one | Plan |
| Model call | One call, no tools, `max_retries=0`, `store=False`, low effort, 6000 output tokens, 180 s timeout | Bounded cost; the numbers can be tuned after the real run | Orchestrator / Plan |
| Credentials | Key only in the model step, `GH_TOKEN` only in posting steps | A hijacked model has neither tools nor a token | Research |
| Branch | One branch `ci-ai-code-review`, one PR | The whole change only runs on PRs | Orchestrator |

## Scope

**In scope:**

- `scripts/review/` (criteria, cost, runner)
- `.github/workflows/ai-review.yml`
- `tests/test_review*.py`
- A real run on the PR

**Out of scope:**

- Edits to `conversations/llm.py`, `CLAUDE.md`, `test-plan.md`, `ci.yml` (wording goes to the final report as proposals)
- Required check, `push` trigger, fork PRs, sticky comment, new dependencies

## Architecture / Approach

Diff → one structured model call → sanitised comment file plus a validated `verdict` output → a later step, holding only `GH_TOKEN`, posts the comment and sets labels. The diff and all model text count as untrusted: the model has no tools or token, its text reaches only a sanitised `--body-file`, and logs carry only fixed-format lines.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Criteria, schema, verdict floor and cost | Pure, tested logic, including a drift test | Criterion text too vague to score consistently |
| 2. Review script | Diff, prompt, call, comment, exit codes, sanitising | Model or diff text leaking into logs (guarded by a marker test) |
| 3. Workflow | `ai-review.yml` plus a YAML safety test | Label logic only provable on a real run |
| 4. Real run on the PR | Push, PR, real comment and label | Output cap, permissions and push scope are proven only here |

**Prerequisites:** the user sets `OPENAI_API_KEY` (the single planned gate). The key is not needed for Phases 1–3.
**Estimated effort:** about 1–2 sessions across 4 phases. Estimated at most about 0.14 USD per run, not yet measured.

## Open Risks & Assumptions

- `git push` may be rejected if the keychain credential lacks the `workflow` scope. A rejection changes nothing on the remote, and the user runs `gh auth refresh -s workflow` and `gh auth setup-git`.
- `pull-requests: write` should be enough; the first run proves it, and `issues: write` is the planned fallback.
- 6000 output tokens at low effort may truncate the answer. Then the run goes red with `cost: unknown`, and the cap gets raised.
- 3 of the last 5 merge diffs exceed 60k after exclusions, so large PRs are reviewed partially. The comment says what was dropped.
- Prompt injection can still change the text and the verdict. This is accepted, since the check is advisory.

## Success Criteria (Summary)

- `pytest` and `ruff` are green without a key or network.
- The PR shows the AI comment and one result label, and its run is green with a cost line in the logs.
- `ai-cr:review` re-runs the review and is removed afterwards.
