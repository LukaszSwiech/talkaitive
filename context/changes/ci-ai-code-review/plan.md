# AI code review agent in GitHub Actions Implementation Plan

## Overview

On every same-repo PR to `main`, a standalone Python script reviews the PR's diff with OpenAI in one structured call. A workflow then posts one comment and sets the label `ai-cr:passed` or `ai-cr:failed`. The check is advisory: it never blocks a merge. The purpose is 10xChampion evidence: a pipeline view with a job, job logs with a cost line, and an LLM review comment on a PR.

## Current State Analysis

- `.github/workflows/ci.yml` runs ruff and pytest and needs no edit: `ruff .` and `pytest` (`testpaths = ["tests"]`) already cover `scripts/review/` and `tests/test_review*.py`.
- `talkaitive.settings` can be imported without Django apps and without any secret, as long as `DEBUG=False` and `RAILWAY_ENVIRONMENT` are not set. `conversations.budget` and `scripts.eval.cost` cannot be imported that way, so `turn_cost` has to be mirrored and tied to the original by a drift test.
- `openai` is a direct dependency and `pydantic` a transitive one already used by `conversations/llm.py:29`. No `uv add` is needed.
- No `ai-cr:*` label exists yet, and the secret `OPENAI_API_KEY` was not set when research ran.

## Desired End State

- `uv run pytest` and `uv run ruff check . && uv run ruff format .` are green, with no network and no real key.
- PR `ci-ai-code-review` → `main` is open, with an English title and body.
- That PR shows one AI review comment and exactly one of `ai-cr:passed` / `ai-cr:failed`.
- The workflow run is green and its log shows the cost line and no diff or model text.
- Adding `ai-cr:review` to the PR re-runs the review, and the label is gone afterwards.

Verify with Phase 4.

### Key Discoveries:

- Price formula to mirror: `conversations/budget.py:27-45`. Usage fields: `conversations/llm.py:351-353`.
- Parse call pattern: `conversations/llm.py:301-308`. Client construction: `:202-207`. `ValidationError` text quotes model output, so only the fact is logged: `:323-329`. `output_parsed is None` means a refusal or an empty answer: `:331-335`.
- Script conventions to copy: usage docstring with exit codes, `main(argv) -> int`, `ConfigError` mapped to exit 2 (`scripts/eval/run_eval.py:1-51`, `:89`, `:604-626`).
- Test fakes: `FakeResponses` + `monkeypatch.setattr(<module>, "OpenAI", ...)` (`tests/test_llm.py:28-67`) for call arguments; real SDK on `httpx2.MockTransport` (`tests/fake_provider.py:44`, `:124-127`) for what the SDK does. `FakeProvider.reply(...)` returns JSON that does not fit the review schema, which yields a real `ValidationError` without touching `fake_provider.py`. `FakeProvider.fail(500)` proves `max_retries=0` means one request.
- Observed in this planning session, offline: `openai.lib._pydantic.to_strict_json_schema` accepts both `Field(ge=1, le=10)` and `Literal[1, ..., 10]`, and it inlines a nested model that has a `description` so the description survives.
- PyYAML 6.0.3 is installed through `mutmut → libcst` (dev group), under the lock marker `python_full_version >= '3.14'`; below 3.14 `libcst` pulls `pyyaml-ft` instead. `.python-version` is `3.14` and `ci.yml` runs `uv sync --locked`, which installs the dev group, so a test can read YAML without a new dependency. The no-dev install used by the workflow has no `yaml` and no `pytest`, and needs neither.
- `git diff` sorts paths alphabetically, so `context/` would use up the 60k cap ahead of `conversations/`. 3 of the last 5 merge diffs exceed 60k even after the exclusions (research, section 5).
- `context/foundation/roadmap.md` has no item with this change ID, so it stays untouched.

## What We're NOT Doing

- No edit to `conversations/llm.py`, `CLAUDE.md`, `context/foundation/test-plan.md` or `.github/workflows/ci.yml`. The now inaccurate "only module that imports `openai`" wording (`llm.py:1`, `CLAUDE.md:43`) and the note that this workflow is a deliberate exception to `test-plan.md:98` become proposals in the final report.
- No `django.setup()` and no review function in `conversations/llm.py`. The script is standalone.
- No required check and no branch protection. The review never blocks a merge.
- No `push` trigger, because Railway waits for all workflows on a commit.
- No `pull_request_target`, no fork PR reviews.
- No sticky comment: each run posts one new comment. `--edit-last` was not verified with `GITHUB_TOKEN`.
- No rewriting of Markdown links in the comment. Only @mentions, image syntax and raw HTML are neutralised, because those notify people or fetch URLs by themselves.
- No inline review comments, no tools for the model, no second model call, no retry.
- No promptfoo, TypeScript or extra vendor. No new dependencies. No `scripts/mutation/` mutants for the script.
- No Linear issue.

## Implementation Approach

The script is built test-first in two steps: pure logic, then the I/O around it. The workflow comes after that because it only wires a working script to `gh`. Verification comes last because it is the only step that needs a key and costs money.

Trust boundary: the diff and everything the model returns are untrusted. The model holds no tools and no GitHub token, and its text reaches only a sanitised file posted with `--body-file`. The only value it influences outside that file is `verdict`, written to `$GITHUB_OUTPUT` after `Literal` validation.

## Branches and PRs

One branch `ci-ai-code-review` and one PR for all phases; the branch already exists and no phase is deployed on its own, since the whole change only runs on PRs.

Git rules for every commit:

- `uv run ruff check . && uv run ruff format .` and `uv run pytest` are green first.
- Stage by explicit path. Never stage `CLAUDE.md`, which holds the user's uncommitted edits.
- Never push to `main`, never merge, never force-push.
- `context/changes/ci-ai-code-review/` is still untracked, so the Phase 1 commit adds it by explicit file paths.

Implementation uses `/10x-tdd` for Phases 1–2 and `/10x-implement` for Phases 3–4.

## Critical Implementation Details

- **`on:` in PyYAML**: YAML 1.1 parses the key `on` as boolean `True`, so the workflow test reads `workflow[True]`, not `workflow["on"]`.
- **`uv run` re-syncs**: the workflow installs with `uv sync --locked --no-dev`, and a plain `uv run` would then reinstall the dev group. Use `uv run --no-sync`.
- **Dispatch guard goes first**: on `workflow_dispatch`, the `isCrossRepository` check must run before checkout, so no fork code is checked out or installed. `pull_request` runs are filtered by the job `if`.
- **Unrelated labels must not cancel a review**: a `labeled` event for any other label starts a run that is skipped by the job `if`. With one concurrency group per PR it could still cancel a running review, so such events get their own group (`github.run_id`).
- **Output order**: the comment file is written before `verdict` reaches `$GITHUB_OUTPUT`, so a set verdict always means the comment exists.
- **Tolerating only a 404**: `gh api` exits non-zero on every HTTP error, so `|| true` would also swallow the 403 that Phase 4 needs to see. The label steps must tell a 404 apart from the error output. A `:` in a label name in a URL path is encoded (`ai-cr%3Apassed`).
- **Mutation copies have no `.github`**: `scripts/mutation/manual_mutants.py` excludes it (`COPY_EXCLUDES`) and mutmut copies only `also_copy`, `tests/` and lock files, so a test that reads workflow files would turn both tools' baselines red.

## Phase 1: Criteria, schema, verdict floor and cost

### Overview

The pure part of the script: what is scored, how the final verdict is decided, and what a run costs. No git, no network, no I/O.

### Changes Required:

#### 1. Package marker

**File**: `scripts/review/__init__.py`

**Intent**: Make `scripts.review` importable from tests and by `python -m`, like `scripts/eval/`.

**Contract**: Empty file.

#### 2. Criteria and schema

**File**: `scripts/review/criteria.py`

**Intent**: Define the six TalkAItive criteria as named fields, so the schema itself forces all six, and state in each description what 1 and 10 mean. A criterion that the diff does not touch scores 10, otherwise the floor below would fail every backend PR on the UI criterion.

**Contract**:

- `Score = Literal[1, ..., 10]`. `Literal` is chosen over `Field(ge=1, le=10)`: both pass the local strict conversion, but only a real call could prove the server accepts `minimum`/`maximum`, while `enum` is the existing pattern (`llm.py:121`).
- `CriterionScore(BaseModel)`: `score: Score`, `rationale: str`.
- `Review(BaseModel)` with these fields, each `Field(description=...)` saying what 1 and 10 mean:
  - `data_isolation`: queries go through `Model.objects.for_user(request.user)`, and per-user models stay out of the admin.
  - `type_hints`: new models, views and services are type-hinted.
  - `tests`: changed behaviour has tests.
  - `no_secrets`: no keys, tokens or passwords in code.
  - `openai_boundary`: application code calls OpenAI only through `conversations/llm.py`; `scripts/review/` and `tests/` are exempt, and the text says so.
  - `ui_contract`: the tokens and components contract from `CLAUDE.md` (no colours, `<style>` or `style=` in templates; `data-variant`; colour values only in `tokens.css`).
- `Review` also has `verdict: Literal["pass", "fail"]` and `summary: str` (Markdown).
- `FAIL_FLOOR = 3`.
- `final_verdict(review: Review) -> Literal["pass", "fail"]` returns `fail` if the model said `fail` or any criterion is at or below `FAIL_FLOOR`. It can lower a verdict and never raises one, which makes a prompt-injected "pass" harder to obtain.

#### 3. Cost

**File**: `scripts/review/cost.py`

**Intent**: Compute cost without Django. `talkaitive.settings` supplies the prices.

**Contract**:

- `cost_usd(prices, input_tokens, cached_input_tokens, output_tokens) -> Decimal`, same three-term formula as `turn_cost`, where `input_tokens` includes the cached ones.
- `worst_case_usd(prices, input_chars, max_output_tokens) -> Decimal`, an estimate at `CHARS_PER_TOKEN_ESTIMATE = 3`, no cached discount.
- `cost_line(...)` and `unknown_cost_line(...)` return the two fixed log formats: `cost: 0.001350 USD (model=gpt-5.4 input=1200 cached=1000 output=40)` and `cost: unknown (worst case about 0.14 USD)`.

#### 4. Tests

**File**: `tests/test_review_criteria.py`

**Intent**: Pin the above with hand-computed numbers and no network.

**Contract**:

- All six criteria are present in the strict schema (`to_strict_json_schema`) as required properties, each with a description containing both a "1" and a "10" meaning.
- A score of 0 or 11 is rejected by `Review`.
- `openai_boundary`'s description names both exemptions.
- `final_verdict` cases: model `pass` with all scores above the floor → `pass`; model `fail` with high scores → `fail`; model `pass` with one score exactly at `FAIL_FLOOR` → `fail`; one score at `FAIL_FLOOR + 1` → `pass`.
- `cost_usd` with the `gpt-5.4` prices and usage 1200/1000/40 equals `Decimal("0.00135")` (200 × 2.50 + 1000 × 0.25 + 40 × 15.00, divided by 1,000,000).
- Drift: `cost_usd` equals `conversations.budget.turn_cost` for the same numbers.
- `worst_case_usd(prices, 60_000, 6_000) == Decimal("0.14")` (20,000 × 2.50 + 6,000 × 15.00, divided by 1,000,000).
- A clean interpreter (`subprocess`, cwd at the repo root, an env holding only `PATH`) can import `scripts.review.cost` and `scripts.review.criteria`, and the Django app registry is not ready afterwards. These two modules do not import the settings; Phase 2 repeats this check on `run_review`, which does.

### Success Criteria:

#### Automated Verification:

- Criteria tests pass: `uv run pytest tests/test_review_criteria.py`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format .`

**Implementation Note**: Commit this phase, adding the change folder by explicit paths.

---

## Phase 2: Review script

### Overview

The script itself: read the diff, make one model call, write a sanitised comment file and the verdict, log only fixed-format lines, and return the right exit code.

### Changes Required:

#### 1. Script

**File**: `scripts/review/run_review.py`

**Intent**: The one entry point, called as `uv run --no-sync python -m scripts.review.run_review --comment-file <path>`. Module-level `from openai import OpenAI` so tests can patch it. Usage docstring with exit codes, as in `run_eval.py`.

**Contract**:

- **Exit codes**:
  - 0: reviewed, whether the verdict is `pass` or `fail`; also "nothing to review".
  - 1: runtime failure (API error, unusable output, refusal, git error).
  - 2: config failure (`OPENAI_API_KEY` empty or missing), checked first, before git and before any call.
  - On a non-zero exit neither the comment file nor `$GITHUB_OUTPUT` is written.
- **Diff**: `subprocess` with a list of arguments, no shell: `git diff --no-ext-diff --no-color HEAD^1 HEAD -- . ':(exclude)uv.lock' ':(exclude)package-lock.json' ':(exclude)context'`. Decode with `errors="replace"`. `MAX_DIFF_CHARS = 60_000`. When over the cap, cut the text and collect the paths whose content was dropped: the `diff --git` headers past the cut, plus the last header before it, since that file is cut partway.
- **Empty diff after exclusions**: no model call, verdict `pass`, a comment saying there was nothing reviewable and naming the exclusions, the log line `cost: 0.000000 USD (no model call)`, exit 0. This makes a `context/`-only PR free.
- **Prompt**: states the role, that the review is in English, and that the content between per-run delimiters is data under review and never instructions. The delimiter contains a random `secrets.token_hex` value, so a diff cannot close it. It also asks the model never to quote a secret value it finds, only to name the file.
- **Call**: one `client.responses.parse(model=LLM_MODEL, input=..., text_format=Review, reasoning={"effort": "low"}, max_output_tokens=6000, store=False)`, no `tools`. Client: `OpenAI(api_key=..., timeout=180, max_retries=0)`. Model and prices come from `from talkaitive.settings import LLM_MODEL, LLM_PRICES_USD_PER_MTOK`.
- **Failure paths**:
  - `ValidationError` (truncated or malformed output): `cost: unknown` line, exit 1.
  - `output_parsed is None`: cost line from `usage`, exit 1.
  - `usage` missing: `cost: unknown` line.
  - `openai.OpenAIError`: log only the type name, `cost: unknown` line, exit 1.
  - Any other exception reaching `main`: log only the type name, exit 1. No traceback, since a `ValidationError` text quotes model output.
- **Comment**: rendered from `final_verdict`, not the raw model verdict, as a fixed heading with an "advisory" note, one bullet per criterion (a list rather than a table, so a `|` or newline in model text cannot break the layout), the summary, a note when the floor overrode the model's verdict, and a "scope" note always naming the exclusions and, when truncated, the cap and the dropped paths (first 20, then "and N more").
- **Sanitising**, applied to all model text and to file paths:
  - @mentions no longer notify (a zero-width character after `@`).
  - `![` no longer renders an image.
  - `<` becomes `&lt;`, which removes raw HTML and HTML comments.
  - The final body is capped at `MAX_COMMENT_CHARS = 60_000` with a visible note.
- **Logs**: fixed-format lines only: `model:`, `diff:` (characters, truncated yes/no), `verdict:` and the cost line, plus on the `output_parsed is None` path `status:` with the response status (`completed` or `incomplete`), because a cut-off answer holding only reasoning also lands there and otherwise looks like a refusal. Never the diff, model text or file paths.
- **`$GITHUB_OUTPUT`**: appends `verdict=pass|fail` only, after the comment file is written. When the env var is unset (a local run), it writes nothing there.

#### 2. Tests

**File**: `tests/test_review_script.py`

**Intent**: Cover every exit path with fake clients and a throwaway git repo in `tmp_path`; no network, no real key. Set or clear `OPENAI_API_KEY` with `monkeypatch`, since the script reads the real env var. An autouse fixture also clears `GITHUB_OUTPUT` (`ci.yml` runs pytest inside Actions, where it is set) and `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` (set inside git hooks, they would point the test's git commands at the real repo). Test commits pass their identity with `-c user.name=... -c user.email=...` and `-c commit.gpgsign=false`, since CI has no git identity.

**Contract**:

- Git, against a real temporary repo with a merge commit:
  - excluded paths are absent from the diff;
  - a `git clone --depth 2 file://<repo>` of that merge commit is really shallow (`git rev-parse --is-shallow-repository` is `true`) and still gives the same `HEAD^1 HEAD` diff, which turns the research's inference about `fetch-depth: 2` into a tested fact. The `file://` form is required: a plain local path ignores `--depth` and the test would prove nothing (observed);
  - a diff over the cap is cut, and the dropped paths are named, including the file the cut falls inside.
- Standalone path: a clean interpreter (`subprocess`, cwd at the repo root, an env holding only `PATH`) can import `scripts.review.run_review`, the Django app registry is not ready afterwards, and `talkaitive.settings` is loaded. This is the settings import the workflow relies on; the dev venv cannot show the no-dev install, which only the real run covers.
- Call arguments (`FakeResponses`): `max_output_tokens`, `store=False`, `reasoning`, no `tools`, the delimiter wraps the diff and does not occur in it.
- Real SDK (`FakeProvider.make_client`): `FakeProvider().fail(500)` yields exactly one request and exit 1. `reply("x")` (a body not matching `Review`) yields a real `ValidationError`, exit 1 and the `cost: unknown` line. The request body sent carries `store: false`, `max_output_tokens` and a strict schema with all six criteria.
- Exit paths: pass → 0 and `verdict=pass`; model pass with a score at the floor → 0 and `verdict=fail`; missing key → 2 and no client built; refusal → 1 with a cost line and `status: completed`; `output_parsed is None` on an `incomplete` response → 1 with a cost line and `status: incomplete`; empty diff → 0 with no client built.
- Operational failures write neither the comment file nor `$GITHUB_OUTPUT`.
- Log purity: a marker placed in the diff, in the model's text and in the `ValidationError` input never appears in captured stdout or stderr, across the success path and every failure path.
- Sanitising: `@octocat`, `![x](http://evil)` and `<img src=x>` in model text and in a file path are all neutralised in the comment. The body cap holds on an oversized summary.

### Success Criteria:

#### Automated Verification:

- Script tests pass: `uv run pytest tests/test_review_script.py`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format .`
- Without a key, the script stops before any call: `env -u OPENAI_API_KEY uv run python -m scripts.review.run_review --comment-file /dev/null` exits 2 with one config line

---

## Phase 3: Workflow

### Overview

Wire the script to GitHub with split credentials and pin its safety properties with a test.

### Changes Required:

#### 1. Workflow

**File**: `.github/workflows/ai-review.yml`

**Intent**: Run the script on same-repo PRs to `main`, post the result, and keep the labels consistent.

**Contract**:

- **Triggers**: `pull_request` with `branches: [main]` and `types: [opened, synchronize, reopened, labeled]`; `workflow_dispatch` with a required number input `pr_number`. No `push`.
- **Permissions**: `contents: read`, `pull-requests: write` only. Add `issues: write` solely if the real run proves it is needed (Phase 4).
- **Job `if`**: as in research section 5: dispatch, or same-repo head and (not `labeled`, or the label is `ai-cr:review`). Note (added at implementation, orchestrator's decision, it can only lower cost): on `pull_request` the condition also requires `github.event.pull_request.state == 'open'`, so adding `ai-cr:review` to a closed or merged PR starts no paid run. The workflow test asserts this.
- **Concurrency**: `cancel-in-progress: true`, group keyed on the PR number; a `labeled` event for any other label gets a group with `github.run_id` instead.
- **Job**: `ubuntu-latest`, `timeout-minutes: 10`. Job-level env: `PR_NUMBER` (`github.event.pull_request.number || inputs.pr_number`) and `GH_REPO`.
- **Steps, in order**:
  1. `guard` (dispatch only, `GH_TOKEN`): `gh pr view` refuses when `isCrossRepository` is true, the base is not `main`, or the PR is not open.
  2. Ensure labels (`GH_TOKEN`, `gh api` only): for `ai-cr:passed` green, `ai-cr:failed` red and `ai-cr:review` neutral, GET the label and POST it only if missing. This runs before the model step, so `ai-cr:review` exists for a retry even when the first run goes red.
  3. Checkout, using the SHA pinned in `ci.yml`: `persist-credentials: false`, `fetch-depth: 2`; on dispatch `ref: refs/pull/<n>/merge`.
  4. setup-uv, using the SHA pinned in `ci.yml`, then `uv sync --locked --no-dev`.
  5. `review` (the only step with `OPENAI_API_KEY`, `timeout-minutes: 5`): `uv run --no-sync python -m scripts.review.run_review --comment-file "$RUNNER_TEMP/ai-review-comment.md"`.
  6. Post (only when `steps.review.outputs.verdict` is set, `GH_TOKEN`; the verdict arrives through `env:`): `gh pr comment "$PR_NUMBER" --body-file ...`; `gh api` DELETE of the opposite label, tolerating only a 404; `gh api` POST of the result label. This ends with exactly one result label.
  7. Failure cleanup (`failure()` and the guard did not fail, `GH_TOKEN`): DELETE both result labels, tolerating only a 404. A pass label from an older commit must not survive a run that could not review the new one.
  8. Retry cleanup (not cancelled and the guard did not fail, `GH_TOKEN`): DELETE `ai-cr:review`, tolerating only a 404, so the label can be added again.
- **Actions**: `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` and `astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884`, the same SHAs as `ci.yml`.
- **Never** `${{ }}` inside `run:`; all values reach the shell through `env:`. `RAILWAY_ENVIRONMENT` and `DEBUG` stay unset, so the settings import works. `LLM_MODEL` stays unset, so the default applies.

#### 2. Workflow safety test

**File**: `tests/test_review_workflow.py`

**Intent**: Stop a later edit from quietly removing a safety property. PyYAML is imported directly with no `importorskip`, so a guard cannot silently vanish if `mutmut` ever drops it. The module skips only when `.github/workflows/ci.yml` is also missing, which means a mutation copy without `.github` (see Critical Implementation Details). If `ci.yml` exists and `ai-review.yml` does not, the test fails, so deleting the workflow cannot pass as a skip.

**Contract**: Parses `.github/workflows/ai-review.yml` and asserts:

- Every `uses:` is pinned to a 40-hex SHA, and those SHAs match the ones in `ci.yml`.
- Permissions are exactly the allowed set, or that set plus `issues: write`.
- Triggers are exactly `pull_request` and `workflow_dispatch`; `pull_request_target` appears nowhere; `labeled` is listed.
- No `run:` block contains `${{`. That one rule covers the PR title and body, branch names, label names, inputs and step outputs.
- `OPENAI_API_KEY` is only in the `review` step's env, not at workflow or job level. `GH_TOKEN` is not in the `review` step, and neither appears at workflow or job level.
- Checkout has `persist-credentials: false` and `fetch-depth: 2`.
- `gh pr edit` appears nowhere, and `--body-file` is the only way a body is passed.
- The job `if` contains the `head.repo.full_name` check. `cancel-in-progress` is true, and the concurrency group mentions `github.run_id` for unrelated labels.
- `guard` is the first step, and no `uses:` step comes before it. Ensure labels comes before `review`, and `review` before the post and cleanup steps.
- The post step's `if` reads `steps.review.outputs.verdict`. The failure cleanup's `if` has `failure()` and the guard check. The retry cleanup's `if` has the cancelled check and the guard check, and comes after the failure cleanup.
- `|| true` appears in no `run:` block, since only a 404 may be tolerated.

This pins the workflow's shape only. Whether the labels really behave is proven in Phase 4.

### Success Criteria:

#### Automated Verification:

- Workflow tests pass: `uv run pytest tests/test_review_workflow.py`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format .`

**Implementation Note**: Every push to an open PR is one paid run, so hold the first push until `/10x-impl-review` findings on Phases 1–3 are fixed, where the orchestrator's sequence allows it.

---

## Phase 4: Real run on the PR

### Overview

Push, open the PR and prove the whole path on real infrastructure. This phase holds the plan's single user gate: the user sets the OpenAI key.

### Changes Required:

#### 1. Push and PR

**Intent**: Publish the branch and open the PR that the done criteria refer to.

**Contract**:

- `git push -u origin ci-ai-code-review` (never `main`, never force).
- `gh pr create` with an English title and body, the body ending with the attribution line from the session.
- Then `ccd_pr` `bind_pr` / `get_status`; do not poll CI by hand.
- A rejected push (missing `workflow` scope, research section 7) changes nothing on the remote. It falls under the brief's "missing permission" return: the user runs `gh auth refresh -s workflow` and `gh auth setup-git`.

#### 2. Secret (user gate)

**Intent**: The real call needs a dedicated CI key, which only the user creates and sets.

**Contract**:

- Check the name only: `gh secret list`. Never read or print a value.
- If `OPENAI_API_KEY` is missing, ask the user to create a dedicated key with a monthly limit in a separate OpenAI project and run `gh secret set OPENAI_API_KEY`, without pasting it into chat.
- A first run before the key is set is expected to go red with exit 2 and set no result label. That is useful evidence for the failure path. Afterwards, re-run with `ai-cr:review`.

#### 3. Tuning from real evidence (only if the run demands it)

**Intent**: Three facts can only be proven by the real run. A commit on this branch fixes whatever it disproves. Each fix is a new paid run.

**Contract**:

- A 403 on a label or comment call: add `issues: write`, with the workflow test allowing exactly that addition.
- `cost: unknown` from a truncated answer, or `status: incomplete`: raise `max_output_tokens` and update the bound test.
- A timeout: raise the client timeout.

### Success Criteria:

#### Automated Verification:

- The PR exists and targets `main`: `gh pr view ci-ai-code-review --json baseRefName,state`
- The AI review run is green: `gh run list --workflow ai-review.yml --branch ci-ai-code-review --limit 1`
- The log has the cost line and no diff or model text: `gh run view <id> --log`, then grep for `cost:` and grep for a sentence of the posted summary and a line of the PR's diff, which must not match
- Exactly one result label is set, and the comment exists: `gh pr view ci-ai-code-review --json labels,comments`
- Full suite and lint are green on the final commit: `uv run pytest` and `uv run ruff check . && uv run ruff format .`

#### Manual Verification:

- User gate: the user has set `OPENAI_API_KEY` with a dedicated CI key and a monthly limit
- Adding `ai-cr:review` to the PR starts a second run, and the label is gone afterwards
- The comment reads as a useful review, in English, with the advisory note and the scope note
- The user takes 3 screenshots in Brave (pipeline view, job logs, LLM comment), with no tokens or private data visible

**Implementation Note**: The orchestrator's final report, in Polish, lists what the user still does (merge, Mission Log, 10xChampion acceptance) and these proposals: `llm.py:1` and `CLAUDE.md:43` wording ("the only application module"), and a `test-plan.md` note that this workflow is an advisory exception to line 98.

---

## Testing Strategy

### Unit Tests:

- Pure logic with hand-computed numbers: schema shape, verdict floor at the boundary, cost, worst-case bound and drift against `turn_cost`.
- Sanitising and body cap on model text and on file paths.

### Integration Tests:

- A real git repo in `tmp_path`, including a depth-2 clone of a merge commit.
- The real SDK on the fake transport: one request only, a real `ValidationError` path, and the actual request body.
- `main(argv)` through every exit code, with a log-purity marker.
- The workflow file parsed as data for its safety properties.

### Manual Testing Steps:

1. Open the PR and watch the first run. Without a key it should go red with no result label.
2. With the key set, add `ai-cr:review`, then check the comment, label and cost line.
3. Add an unrelated label during a run and confirm the review is not cancelled.

## Performance Considerations

- Cost is an estimate until measured: at most about 0.14 USD per run (20k input tokens, from 60,000 characters at 3 per token, at 2.50/M plus 6k output tokens at 15.00/M; the short prompt adds under 0.01 USD). Every push to an open PR and every retry is one run.
- Output cap and reasoning effort are coupled, because `max_output_tokens` includes reasoning tokens. That is why the effort is `low`.
- A cancelled call may still be billed.

## Migration Notes

None: no data and no production code change. Removing the workflow file disables everything. The labels stay on the repo until deleted.

Known limits, stated rather than solved:

- No run starts while a PR has a merge conflict (GitHub docs).
- `workflow_dispatch` is unavailable until the file is on `main`, and it is not needed for the done criteria.
- A dispatch run attaches to the tip of `main`, so a red one might hold a Railway deploy (inference, research section 3). Use dispatch only when no deploy is pending.

## References

- Brief: `context/changes/ci-ai-code-review/requirements.md`
- Related research: `context/changes/ci-ai-code-review/research.md`
- Similar implementation: `conversations/llm.py:301-308`, `scripts/eval/run_eval.py:604-626`, `.github/workflows/ci.yml:4-30`
- Fakes: `tests/test_llm.py:28-67`, `tests/fake_provider.py:44`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Criteria, schema, verdict floor and cost

#### Automated

- [x] 1.1 Criteria tests pass: `uv run pytest tests/test_review_criteria.py` — f41a680
- [x] 1.2 Full suite passes: `uv run pytest` — f41a680
- [x] 1.3 Lint and format are clean: `uv run ruff check . && uv run ruff format .` — f41a680

### Phase 2: Review script

#### Automated

- [x] 2.1 Script tests pass: `uv run pytest tests/test_review_script.py` — 84ee1c8
- [x] 2.2 Full suite passes: `uv run pytest` — 84ee1c8
- [x] 2.3 Lint and format are clean: `uv run ruff check . && uv run ruff format .` — 84ee1c8
- [x] 2.4 Without a key, the script stops before any call: `env -u OPENAI_API_KEY uv run python -m scripts.review.run_review --comment-file /dev/null` exits 2 with one config line — 84ee1c8

### Phase 3: Workflow

#### Automated

- [x] 3.1 Workflow tests pass: `uv run pytest tests/test_review_workflow.py` — 3361ac5
- [x] 3.2 Full suite passes: `uv run pytest` — 3361ac5
- [x] 3.3 Lint and format are clean: `uv run ruff check . && uv run ruff format .` — 3361ac5

### Phase 4: Real run on the PR

#### Automated

- [ ] 4.1 The PR exists and targets `main`: `gh pr view ci-ai-code-review --json baseRefName,state`
- [ ] 4.2 The AI review run is green: `gh run list --workflow ai-review.yml --branch ci-ai-code-review --limit 1`
- [ ] 4.3 The log has the cost line and no diff or model text: `gh run view <id> --log`, then grep for `cost:` and grep for a sentence of the posted summary and a line of the PR's diff, which must not match
- [ ] 4.4 Exactly one result label is set, and the comment exists: `gh pr view ci-ai-code-review --json labels,comments`
- [ ] 4.5 Full suite and lint are green on the final commit: `uv run pytest` and `uv run ruff check . && uv run ruff format .`

#### Manual

- [ ] 4.6 User gate: the user has set `OPENAI_API_KEY` with a dedicated CI key and a monthly limit
- [ ] 4.7 Adding `ai-cr:review` to the PR starts a second run, and the label is gone afterwards
- [ ] 4.8 The comment reads as a useful review, in English, with the advisory note and the scope note
- [ ] 4.9 The user takes 3 screenshots in Brave (pipeline view, job logs, LLM comment), with no tokens or private data visible
