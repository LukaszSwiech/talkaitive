# ci-ai-code-review: AI code review agent in GitHub Actions (variant A, OpenAI)

## Start here (for a fresh agent in a new window)

State when this was written (2026-10-31):
- Branch `ci-ai-code-review` already exists and is checked out. Verify with
  `git branch --show-current`. Never work on `main`.
- This folder exists with `change.md` (status: new). Do NOT run `/10x-new`
  again (it refuses an existing folder).
- `CLAUDE.md` has pre-existing UNCOMMITTED edits by the user. Never stage or
  commit it unless the user says so.
- Read `CLAUDE.md` first. Its rules still apply: chat in Polish and simple,
  explain every Bash/Edit/Write call in Polish before making it, PR title and
  description in English.

First steps:
1. Preflight (read-only): `gh auth status`; `gh secret list` (names only, never
   read values) to see whether `OPENAI_API_KEY` exists; check branch
   protection of `main` with `gh api`. Missing secret is NOT a blocker for
   writing code and tests; ask the user for it only when the PR run needs it.
2. `/10x-research ci-ai-code-review` using this file as the brief, then
   `/10x-plan ci-ai-code-review`, then `/10x-plan-review`.
3. Present the plan to the user and get ONE confirmation. This is the only
   planned gate before implementation.
4. After confirmation work autonomously (see Operating mode).

## Goal

On every PR to `main` (same-repo only), a Python script reviews the diff with
OpenAI, posts one PR comment and sets the label `ai-cr:passed` or
`ai-cr:failed`. Purpose: 10xChampion evidence (pipeline view with a job, job
logs, LLM review comment on a PR). The user takes the screenshots himself.

## Operating mode

- Orchestrate, do not implement yourself. Delegate each phase to subagents
  (criteria, script + tests, workflow, verification) and review their results
  before moving on.
- Use the 10x chain: research, plan, plan-review, then
  `/10x-implement` (or `/10x-tdd` for the script), then `/10x-impl-review`.
- Return to the user ONLY for: (a) a missing secret or permission,
  (b) a real ambiguity that changes scope, cost or security, (c) a quality
  gate that failed 3 times. Everything else: pick the conservative option
  and record it in the final report.
- Final report in Polish: what was done, assumptions, decisions made on the
  user's behalf, what the user must do.

## Permissions granted by the user (2026-10-31)

- `git push` to any branch EXCEPT `main` is allowed. Never push to `main`.
  Never merge. Never force-push.
- Opening a PR from `ci-ai-code-review` to `main` is allowed (title and body in
  English). Afterwards use the ccd_pr tools: `get_status`, `bind_pr` if
  needed; do not poll CI yourself.
- `.github/workflows/ci.yml` may be edited if required to finish the task.
  Keep the existing ruff and pytest steps working.
- Deployment to Railway is not a concern for this task.

## Hard rules

- Never print, log or commit any key. Never read secret values.
- Pin every third-party action to a commit SHA. Minimal permissions
  (`contents: read`, `pull-requests: write`; add more only if proven needed).
- Tests use a fake OpenAI client: no network and no real key in `pytest`.
- Python only. Add dependencies with `uv add`, never `pip install`.
  `uv run ruff check . && uv run ruff format .` and `uv run pytest` must be
  green before every commit.
- No promptfoo, no TypeScript, no extra vendor (no Anthropic).

## Scope

- `scripts/review/`: reads `git diff`, makes ONE model call, structured output
  (Pydantic): 6 criteria scored 1-10 with rationale, verdict pass/fail,
  summary (markdown). Hard caps: max diff size (truncate with a visible note),
  max output tokens. Log cost per run (reuse the price table approach from
  `conversations/llm.py` / `LLM_PRICES_USD_PER_MTOK`).
- Criteria tailored to TalkAItive: `for_user(request.user)` data isolation,
  type hints, tests, no secrets in code, OpenAI only in
  `conversations/llm.py`, UI tokens/components contract from CLAUDE.md.
  Each criterion's description explains what 1 and 10 mean.
- Workflow `.github/workflows/ai-review.yml`: trigger `pull_request` (and
  `workflow_dispatch` for manual tests); skip PRs from forks; secret
  `OPENAI_API_KEY` (a separate CI key, not the production one); posts the
  comment and label with `gh` using `GITHUB_TOKEN`.
- Advisory only: not a required check, does not block merge.
- A `pull_request` workflow runs from the PR branch, so it can be verified on
  the PR itself without merging first.

## Defaults for open decisions (do not ask, just record)

- Model: the existing `LLM_MODEL` default; it must have a price entry.
- Review comment language: English.
- Labels: `ai-cr:passed` green, `ai-cr:failed` red (create if missing).
- Retry: adding the label `ai-cr:review` re-runs the review.
- Max diff size: about 120k characters, truncated with a note in the comment.
- No Linear issue.

## Done when

`pytest` and `ruff` are green; PR is open; the AI review comment and label are
visible on that PR; the workflow run is green and its logs show the cost
line; the final report is delivered.

## User does manually

- Create a dedicated OpenAI CI key with a monthly spending limit in a separate
  OpenAI project and set it himself: `gh secret set OPENAI_API_KEY`
  (never paste it into chat).
- Take the 3 screenshots in Brave: pipeline view with a job, job logs, the LLM
  comment on the PR. Check that no tokens or private data are visible.
- Merge the PR and claim badges in Mission Log.
- Confirm in Mission Log that this pipeline is accepted for 10xChampion
  (the lesson text does not say if a custom agent is required).
