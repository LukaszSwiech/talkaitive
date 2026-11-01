---
date: 2026-10-31T21:08:25+0100
researcher: Claude Code (10x-research subagent)
git_commit: 3446ed89156a558ccf4fc02be6be0ad9d73c9471
branch: ci-ai-code-review
repository: LukaszSwiech/talkaitive
topic: "AI code review agent in GitHub Actions: facts needed to plan scripts/review/ and ai-review.yml"
tags: [research, ci, github-actions, openai, llm, security, ci-ai-code-review]
status: complete
last_updated: 2026-10-31
last_updated_by: Claude Code (10x-research subagent)
---

# Research: AI code review agent in GitHub Actions

**Date**: 2026-10-31T21:08:25+0100
**Researcher**: Claude Code (10x-research subagent)
**Git Commit**: 3446ed89156a558ccf4fc02be6be0ad9d73c9471
**Branch**: ci-ai-code-review
**Repository**: LukaszSwiech/talkaitive

## Research Question

Brief: `context/changes/ci-ai-code-review/requirements.md`. Six questions: (1) LLM settings, cost, API shape, reusing prices without Django, and the "only `llm.py`" rule; (2) layout of `scripts/` and what picks up `scripts/review/`; (3) `ci.yml` structure, SHAs and whether it needs an edit; (4) test fakes for the OpenAI client; (5) workflow design and security facts; (6) installed SDK and parse helper. Plus: can the missing `workflow` token scope block the push?

## Summary

1. **Prices can be read without booting Django.** `import talkaitive.settings` succeeded with an empty environment (`env -i`, run 2026-10-31): `LLM_PRICES_USD_PER_MTOK` had `gpt-5.4`, `DEBUG` was true, the app registry was not ready, `openai` was not imported. `conversations.budget` and `scripts.eval.cost` both failed to import in the same conditions, so `turn_cost` cannot be reused directly; the three-term formula has to be repeated in the script and tied to `turn_cost` by a drift test.
2. **No test enforces the "only `llm.py`" rule.** It exists as text (`conversations/llm.py:1`, `CLAUDE.md:43`). `scripts/eval/` respects it by calling `conversations.llm` after `django.setup()`. A direct `openai` import in `scripts/review/` breaks no test, but it makes those two sentences inaccurate, and the new review criterion must exempt `scripts/review/` or the PR will flag itself.
3. **`ci.yml` needs no edit.** `ruff .` and `pytest` (testpaths `tests`) already cover the new files. Reuse `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1) and `astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884` (v10.3.0).
4. **`issues: write` should not be needed.** GitHub's docs accept either Issues or Pull requests write for adding a label, creating a label and commenting. The risk is `gh pr edit`, not the permission model: cli/cli#6274 (open on 2026-10-31) reports `gh pr edit` failing with only `pull-requests: write`. Use `gh api` REST calls for labels. First real proof comes from the PR run.
5. **The 60k cap will truncate most real PRs, and diff order makes that worse.** Of the last 5 merge diffs, 4 exceed it raw and 3 still exceed it after excluding lockfiles and `context/` (table below). `context/` sorts before `conversations/`, so unless it is excluded it consumes the budget ahead of application code.
6. **A truncated answer loses its cost data.** `max_output_tokens` includes reasoning tokens; `responses.parse` raises `ValidationError` on cut-off JSON, so no `usage` reaches the caller. The cost line needs an explicit "unknown" path.
7. **The push may be rejected.** `git` authenticates through `osxkeychain`, not through `gh`, so the `gh` scopes do not settle it. A rejected push changes nothing and is a user-permission gate.

## Assumptions

The skill's interview was skipped: this agent cannot talk to the user. Conservative choices, all open to change in `/10x-plan`:

- **Delegation:** the investigation ran in one agent rather than parallel workers. The host's tool policy says not to spawn agents unless asked, and the questions were already bounded.
- **`change.md` not touched:** the task allowed writing only this document, so `mark-researched` was not run and status stays `new`. Whoever continues the chain should run it (see Open Questions).
- **Direct `openai` import in `scripts/review/`** is treated as an accepted exception to the rule, because the brief says the script makes the call itself. The alternative is in section 1.
- **"One PR comment" means one new comment per run**, not one comment edited in place. `--edit-last` was not verified under `GITHUB_TOKEN`.
- **Verdict `fail` keeps the job green; an operational failure (missing key, API error, unusable output) makes it red.** This follows "advisory only" and the done criterion "run is green", and it keeps failures visible. Nothing can block merging anyway (branch protection returns 403).
- **Cost numbers below are estimates** from assumed token ratios, not measurements. The PR run measures them.

## Detailed Findings

### 1. LLM settings, cost, API shape and the `llm.py` rule

**Settings** (`talkaitive/settings.py`):

- `LLM_MODEL` comes from the env var, default `gpt-5.4` (`:59`). `OPENAI_BASE_URL` defaults to the global endpoint (`:58`).
- `LLM_PRICES_USD_PER_MTOK` has exactly one entry, `gpt-5.4`: input 2.50, cached_input 0.25, output 15.00, as `Decimal` (`:86-92`).
- An unpriced `LLM_MODEL` raises `ImproperlyConfigured` at import (`:94-98`). Observed with `LLM_MODEL=gpt-x`. This is a useful fail-fast before a paid call.
- Reasoning: turn `none` (`:61`), analysis `medium` (`:73-75`). Analysis timeout 150 s, 0 retries (`:81-82`).

**Cost:** `conversations/budget.py:27-45`, `turn_cost(model, input_tokens, cached_input_tokens, output_tokens)` = `((input - cached) * input_price + cached * cached_price + output * output_price) / 1_000_000`. `input_tokens` includes the cached ones (`:32`). Usage comes from `usage.input_tokens`, `usage.input_tokens_details.cached_tokens` and `usage.output_tokens` (`conversations/llm.py:351-353`).

**API, on the two call paths in `conversations/llm.py`:**

- Responses API through `client.responses.parse(...)` with `text_format=<Pydantic model>`, `reasoning={"effort": ...}`, `store=False` (`:301-308`, `:386-393`).
- Neither path passes `max_output_tokens`, so the review script is the first caller to set it (searched `conversations/llm.py`).
- Client built with explicit `api_key`, `base_url`, `timeout`, `max_retries` (`:202-207`).
- `output_parsed is None` means a refusal or empty answer (`:331-335`). `ValidationError` means truncated or malformed output, and its text quotes the model output, so only the fact is logged (`:323-329`).

**Reusing prices from a standalone script**, tested with `uv run --no-sync` under `env -i`:

| Import | Result |
| --- | --- |
| `talkaitive.settings` (empty env) | works, apps not ready, `openai` not imported |
| `talkaitive.settings` with `DEBUG=False` and no `SECRET_KEY` | `KeyError: 'SECRET_KEY'` (`settings.py:47`) |
| `talkaitive.settings` with unpriced `LLM_MODEL` | `ImproperlyConfigured` |
| `conversations.budget` | fails: `INSTALLED_APPS ... not configured` (it imports models at `budget.py:20-22`) |
| `scripts.eval.cost` | fails the same way (`cost.py:16-17`) |

Conditions for the first row in Actions: the workflow must not set `DEBUG=False` or `RAILWAY_ENVIRONMENT` (`settings.py:37-38`), and Django must be installed, which `uv sync --locked` does. No `SECRET_KEY` or `OPENAI_API_KEY` is needed for that import.

Recommended shape (inference): the script does `from talkaitive.settings import LLM_MODEL, LLM_PRICES_USD_PER_MTOK`, keeps a pure `cost_usd(prices, input, cached, output)` function, and a test asserts it equals `conversations.budget.turn_cost` for the same numbers, so the duplicated formula cannot drift. Rejected alternative: moving prices into a new dependency-free module. It changes production settings for no functional gain.

**The rule:**

- Text: `conversations/llm.py:1` ("The only module that imports `openai`") and `CLAUDE.md:43` ("Only `conversations/llm.py` calls OpenAI"). `context/foundation/lessons.md` has no entry for it (grep for `llm.py|openai|OpenAI`).
- Modules with a top-level `import openai` or `from openai` under `accounts conversations talkaitive tests scripts`: exactly `conversations/llm.py`, `tests/fake_provider.py:18`, `tests/test_llm.py:4`.
- **No guard exists** on the inspected paths: `tests/test_ownership.py`, `tests/test_ui.py`, `tests/test_topics.py`, `tests/test_eval_*.py`, `scripts/eval/*.py` and `scripts/mutation/manual_mutants.py` contain no mention of `openai`. The other matches in the inspected grep output (first 30 lines) use the SDK's error classes or describe its constants.
- `scripts/eval/` avoids the question by calling `conversations.llm` directly (`run_eval.py:3`, `cost.py:3`), after `_setup_django()` (`run_eval.py:131-136`).

**Consequences for the plan:**

- Criterion 5 ("OpenAI only in `conversations/llm.py`") must say that `scripts/review/` and `tests/` are exempt, or the bot flags its own PR.
- `llm.py:1` should get a one-word correction ("the only application module"), which the plan should name explicitly.
- `CLAUDE.md:43` needs the same note, but `CLAUDE.md` has the user's uncommitted edits and must not be staged. Those edits do not touch the `llm.py` lines (`git diff` count 0). Leave this as a proposal to the user.
- Alternative that keeps the rule literally true: add a review function to `conversations/llm.py` and run the script through `django.setup()`, as eval does. Rejected: it puts CI-only prompts in a module deployed to production and contradicts the brief's standalone script. It is cheap to revisit.

### 2. Layout of `scripts/`, packaging and tooling

- `scripts/__init__.py` and `scripts/eval/__init__.py` exist; `scripts/mutation/` has no `__init__.py` (directory listing). Tests import `scripts.eval.*`, for example `tests/test_eval_runner.py` (`from scripts.eval.run_eval import main`). So `scripts/review/` needs an `__init__.py`.
- Running a file puts its own directory first on `sys.path`. `run_eval.py:620-626` solves it with `sys.path.insert(0, str(REPO))` under `__main__`, with `REPO = Path(__file__).resolve().parents[2]` (`:72`). `uv run python -m scripts.review.<module>` from the repo root is the alternative.
- Conventions worth copying from `run_eval.py`: a long usage docstring with exit codes (`:1-51`), `main(argv) -> int` (`:604`), a `ConfigError` mapped to exit 2 (`:89`, `:612-614`).
- **pytest** (`pyproject.toml:33-37`): `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `pythonpath = ["."]`. Nothing under `scripts/` is collected; tests go in `tests/test_review*.py`.
- **ruff** (`pyproject.toml:24-31`): excludes only migrations and `mutants`, so `ruff check .` picks up `scripts/review/`.
- **mutmut** (`pyproject.toml:42-53`): `only_mutate` lists 4 files, none in `scripts/`; `also_copy` already includes `scripts`, so the new tests' imports resolve in `mutants/`. No config change.
- **manual mutants:** `COPY_EXCLUDES` drops `.github` and `context` (`manual_mutants.py:39-50`), not `scripts`. New tests run there without network. Adding mutants for the script is optional.
- **Dependencies:** `openai` is direct (`pyproject.toml:9`). `pydantic` is only transitive, and `llm.py:29` already imports it that way. `uv add` is not needed.
- `git check-ignore` reports neither `scripts/review/x.py` nor `.github/workflows/ai-review.yml` as ignored.

### 3. `.github/workflows/ci.yml`

- **No edit needed** (inference from section 2): lint and tests already cover the new paths, and the new tests need no secret.
- Structure: triggers `push` to main, `pull_request`, `workflow_dispatch` (`:4-9`); top-level `permissions: contents: read` (`:11-12`); one job, `ubuntu-latest`, 10-minute timeout (`:15-17`).
- Steps: checkout with `persist-credentials: false` (`:21-23`), setup-uv (`:25`), `uv sync --locked` (`:26`), ruff check, ruff format check, pytest (`:27-30`).
- Python: no setup-python. `.python-version` is `3.14` and uv reads it (`:24`).
- SHAs checked against tags through the GitHub API on 2026-10-31:

| Action | SHA | Tag | Latest release |
| --- | --- | --- | --- |
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` | v7.0.1 (matches) | v7.0.1 |
| `astral-sh/setup-uv` | `1c37ad07a6a961277cf70c0d37d6f313000f5884` | v10.3.0 (matches) | v10.3.3 |

Reuse both as they are, so the two workflows stay aligned.

**Railway interaction:** Railway waits for **all** workflows on a commit, so slow workflows must not run on `push` (`context/deployment/deploy-plan.md:151`). `ai-review.yml` must not have a `push` trigger. Recent merges to `main` are merge commits (`git log --merges`: #23 to #27), so a `pull_request` run is not on the deployed commit (inference, not tested against Railway). One small remaining case: a `workflow_dispatch` run on `main` does attach to the `main` tip (inference from the `GITHUB_SHA` definition below).

### 4. Test fakes for the OpenAI client

Two existing patterns, both without network:

- **Fake client class** (`tests/test_llm.py`): `FakeResponses` records kwargs and returns or raises a queued outcome (`:28-38`); `make_response` builds a `SimpleNamespace(output_parsed=..., usage=...)` (`:41-53`); the `fake_openai` fixture does `monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)` (`:56-67`). They are local to that file, not shared. For the script, patch `<review module>.OpenAI`, which requires `from openai import OpenAI` at module level. Best for checking call arguments such as `max_output_tokens`, `store`, `max_retries`.
- **Real SDK on a fake transport** (`tests/fake_provider.py:44`, `:124-127`): real `openai.OpenAI` on `httpx2.MockTransport`. The `fake_provider` fixture patches `llm.OpenAI` only (`tests/conftest.py:19`), so the script's tests need their own patch using `provider.make_client`. Best for what the SDK itself does, in particular a truncated answer raising `ValidationError` and `max_retries=0` meaning one request.

`settings_test.py` sets `OPENAI_API_KEY = "test-key"` for Django settings only. The script reads the real env var, so tests must set or clear it with `monkeypatch.setenv` / `delenv`.

### 5. Workflow design facts

**Triggers**

- Default `pull_request` types are `opened`, `synchronize`, `reopened`; `labeled` needs the `types` keyword (GitHub, events-that-trigger-workflows). Listing `types` replaces the default, so list all four.
- Filter with `branches: [main]`, per the brief's "PR to `main`".
- A plain `labeled` trigger fires for any label added by a person, so the job condition must check the name. Suggested condition:

```yaml
if: >-
  github.event_name == 'workflow_dispatch' ||
  (github.event.pull_request.head.repo.full_name == github.repository &&
   (github.event.action != 'labeled' || github.event.label.name == 'ai-cr:review'))
```

- Labels the workflow adds with `GITHUB_TOKEN` create no new run: for `pull_request`, only `opened`, `synchronize`, `reopened` create (approval-required) runs, and `labeled` does not (GitHub, concepts/security/github_token). No recursion.
- `labeled` fires when a label is added, so the job must remove `ai-cr:review` at the end to allow a second retry (inference). The label must also exist before a person can add it.
- No run starts while the PR has a merge conflict (GitHub docs). That is expected, and a limitation worth one line in the docs.
- Recommended (inference): `concurrency` keyed on the PR number with `cancel-in-progress: true`, so a late run cannot overwrite a newer verdict. A cancelled call may still be billed.

**Fork filtering**

- Fork PRs get no secrets and a read-only `GITHUB_TOKEN` (GitHub docs). The `head.repo.full_name` check avoids a guaranteed-failing run.
- Never use `pull_request_target`. It runs with write token and secrets (GitHub, securely-using-pull_request_target).
- `workflow_dispatch` has no such payload, so that path must check `gh pr view "$PR" --json isCrossRepository` (inference).

**Permissions**

Job-level `contents: read`, `pull-requests: write`. Unlisted permissions become `none` (workflow-syntax). The repo default is read (`default_workflow_permissions: read`, observed via API).

| Operation | Required (docs) | Source |
| --- | --- | --- |
| `POST /repos/{o}/{r}/labels` (`gh label create`) | Issues write **or** Pull requests write | GHES 3.10 labels docs |
| `POST /issues/{n}/labels` | Issues write **or** Pull requests write | GHES 3.10 labels docs |
| `POST /issues/{n}/comments` | Issues write **or** Pull requests write | GHES 3.10 comments docs |

Limits of this evidence:

- The current docs page, as fetched, omits these permission sections, so the table comes from the GHES 3.10 version.
- A third-party issue quotes a real response header on the add-labels endpoint: `issues=write; pull_requests=write`. GitHub's troubleshooting page defines semicolon-separated lists as alternatives.
- One third-party workflow comment claims `issues: write` is needed for labels. That contradicts the docs and is unverified. Per the brief, add `issues: write` only if the PR run proves it.

Tool choice:

- **Avoid `gh pr edit --add-label`.** cli/cli#6274 (state `open` on 2026-10-31) reports it failing with only `pull-requests: write`, because it reads extra PR fields over GraphQL; a commenter reports needing more read permissions on private repos. Whether gh 2.102 still does this was not tested.
- **Use REST:** `gh api --method POST "repos/$GH_REPO/issues/$PR/labels" -f "labels[]=ai-cr:passed"`.
- Removal: `DELETE .../issues/{n}/labels/{name}` returns 404 when the label is not set (labels docs), so tolerate that. `:` in the name should be URL-encoded (`ai-cr%3Apassed`).
- `gh label create NAME --color ... --force` is idempotent (`gh label create --help`).
- `gh pr comment "$PR" --body-file FILE` for the comment. `--edit-last --create-if-none` exist (gh manual), not verified with `GITHUB_TOKEN`.
- `gh` is preinstalled on GitHub-hosted runners and each step needs `GH_TOKEN` (GitHub, use-github-cli). With `persist-credentials: false`, set `GH_REPO` too or pass `--repo`.
- None of `ai-cr:*` exists yet (`gh label list`, 2026-10-31).

**Getting the diff**

- On `pull_request`, `GITHUB_SHA` is the merge commit and `GITHUB_REF` is `refs/pull/N/merge` (GitHub docs), and checkout uses that commit.
- With `fetch-depth: 2`, both parents should be present (inference from depth semantics; not run in Actions), so `git diff --no-ext-diff HEAD^1 HEAD` gives the PR's effect without fetching the base.
- Local check on merge commit `254b61d` (PR #27): 3 words from `rev-list --parents` (the commit plus 2 parents), and `^1 ..` vs `^1...^2` gave the same stat, 75 files, +1644/-45. The two forms can differ when `main` moved, and the merge-parent form is the one that shows what merging would change.
- Run git via `subprocess` with a list of arguments, no shell.

Observed sizes of the last 5 merge diffs, in bytes (`context` here is the `context/` tree):

| Merge | All | Without `uv.lock`, `package-lock.json`, `context` |
| --- | --- | --- |
| `254b61d` | 141,305 | 78,371 |
| `6193c92` | 164,091 | 55,796 |
| `f46133d` | 467,320 | 326,024 |
| `b34ecd0` | 200,258 | 102,065 |
| `146c106` | 14,680 | 7,806 |

So 4 of these 5 raw diffs exceed 60k (all but `146c106`), and 3 of 5 still do after the exclusions. The figures are bytes, used here as an approximation of characters. `git diff` orders paths alphabetically, so without exclusions `accounts/` and `context/` come ahead of `conversations/`. Recommend excluding those three paths via pathspec and stating both the exclusions and the truncation in the comment. Consider a per-file note listing dropped files, so a reader knows what was not reviewed.

**`workflow_dispatch`**

- Docs: the file must exist on the default branch for the trigger; they also say that after a first run it can be dispatched against any branch via API or CLI. Treat dispatch as unavailable until merge. It is not needed for the done criteria.
- Identify the PR with `inputs: pr_number: {type: number, required: true}`, then `with: ref: refs/pull/<n>/merge` on checkout, so the rest of the job is the same as the PR path. Pass the number to shell only through `env:`.

**Missing secret**

- An unset secret evaluates to an empty string; the step still runs, and secrets cannot be used directly in `if:` (workflow-syntax).
- SDK 3.24.0: `self.api_key = api_key or ""`, then raises `OpenAIError("Missing credentials...")` (`openai/_client.py:252-276`). So an empty key fails at client construction, before any network call.
- The script should check first and exit 2 with a clear one-line message, following `run_eval.py`. Today this is the actual state of the repo: no secret is set.

**Security: the diff is untrusted input and the output is posted with a write token**

Must never be interpolated with `${{ }}` into a `run:` block: `github.event.pull_request.title`, `.body`, `.head.ref`, `.head.label`, `github.event.label.name`, commit messages, `github.head_ref`, inputs, and any model output or step output derived from it. The GitHub-recommended fix is an intermediate `env:` variable (secure-use reference). Using these in `if:` or `with:` is not shell interpolation. PR number goes through `env:` as well, for consistency.

Other measures (inference from the threat, not repo facts):

- **Log only fixed-format lines.** Never print the diff or model text to stdout. The runner parses `::command::` workflow commands, so a printed diff line could be interpreted. The cost line and diff size are enough.
- **Comment body only through `--body-file`**, never `--body "$X"`.
- **Nothing derived from the model goes into `$GITHUB_ENV` or `$GITHUB_PATH`.** `$GITHUB_OUTPUT` gets only `verdict=pass|fail`, after validation through a `Literal`.
- **Split credentials by step.** `OPENAI_API_KEY` only in the model step, `GH_TOKEN` only in the posting steps, `persist-credentials: false`. A hijacked model has no tools and no token.
- **The model gets no tools and one call.** Prompt injection can then only change the text and the verdict. That is acceptable because the check is advisory, but the comment should say the verdict is advisory.
- **Sanitise the posted text.** Neutralise `@mentions` so the bot cannot be made to notify people. Consider dropping `![` image syntax and raw HTML, since rendered images fetch external URLs.
- **Prompt:** wrap the diff in clear delimiters and state it is data under review, never instructions. This reduces the risk but does not remove it.
- **`store=False`**, as `llm.py:307`. Diffs of a private repo go to OpenAI, including anything accidentally committed.
- **Secret exposure model:** anyone with write access can read repository secrets through a workflow (secure-use reference), and `pull_request` runs the workflow from the merge commit, so a same-repo PR can change the workflow itself. Acceptable here: private, one contributor, dedicated key with a spend limit (brief).

**Exit status and cost**

- Verdict `fail` exits 0; the label carries the result.
- `max_retries=0`: SDK default is 2 (`openai/_constants.py:8`), which would break "ONE model call" and could bill up to three times.
- Cost line: on success from `usage`. On `ValidationError`, `usage` is lost (section 6), so print `cost: unknown` with the worst-case bound.
- Worst-case estimate, assumptions stated: 60k characters at 3 to 4 characters per token plus a short prompt is at most about 21,000 input tokens, 21,000 x 2.50 / 1M = 0.0525 USD. An output cap of 4,000 tokens adds 4,000 x 15.00 / 1M = 0.06 USD, and 6,000 adds 0.09 USD. So one run is at most roughly 0.11 to 0.14 USD. Every push to an open PR is one run. Not measured.
- Output cap and effort: the cap includes reasoning, so `medium` effort plus a low cap risks truncation. `llm.py` has no precedent. Measured analysis took 52 s at `medium` on a 20-turn conversation (`settings.py:70-72`), so a diff may take longer than the 150 s analysis timeout allows for. Recommend a low effort and tune on the PR run.

**Structured output shape**

- Prefer six **named** fields over a list, so the schema itself enforces all six criteria.
- `Literal` is the existing pattern (`llm.py:121`). Whether `Field(ge=1, le=10)` is accepted by the strict schema was not tested. If not, use `Literal[1, ..., 10]` or validate after parsing.
- `verdict` comes from the model per the brief. A deterministic floor (for example, fail when any criterion is very low) would resist injection better; that is a plan choice.
- GitHub's comment limit is reported as 65,536 characters (not confirmed in docs this session). A 6,000-token cap stays far below it at normal token sizes, and the script should still cap the body.

### 6. Installed SDK

- `openai` 3.24.0 in `uv.lock:431-432` and in `.venv` (`openai-3.24.0.dist-info`). `pydantic` 2.13.5 in `uv.lock:532-533`.
- `Responses.parse` exists with `text_format` and `max_output_tokens` (`openai/resources/responses/responses.py:1334-1345`), and `llm.py` uses it. The SDK's HTTP client is `httpx2` (dev dependency for tests: `pyproject.toml:17`).
- `max_output_tokens` covers "visible output tokens and reasoning tokens" (`responses.py:242-244`).
- `lib/_parsing/_responses.py` has no handling of `status` or `incomplete` (grep), and `parse_text` calls `model_parse_json` (`:146-161`). So truncated text raises `ValidationError` from inside `.parse()`, before the caller holds a response. This agrees with `llm.py:323-329`. A refusal gives `output_parsed = None` with usage intact (`llm.py:332-335`).
- `parse_text` returns `None` for a message `phase` other than `final_answer` (`:153-154`), so `None` is not strictly limited to refusals.

### 7. Can the missing `workflow` scope block the push?

- Observed: `origin` is `https://github.com/LukaszSwiech/talkaitive.git`; the only credential config is `credential.helper osxkeychain`; `gh` holds its own token in the keyring with scopes `gist, read:org, repo`, and no `gh auth git-credential` helper appears in `git config --get-regexp credential`.
- So `git push` uses whatever is in the keychain. **Its scopes are unknown** and were not inspected, because that means reading a secret. The `gh` scope list does not describe it.
- Fact: pushing a new or changed workflow file with an OAuth or classic token lacking `workflow` is rejected with `refusing to allow an OAuth App to create or update workflow ... without workflow scope` (cli/cli discussion #7251). The exemption for an identical file on another branch does not apply to a new file.
- Weak positive signal: `ci.yml` changes reached `main` on 2026-10-15 (`1926b76`), so some credential could push workflow files then. That does not prove it is the same one today (inference).
- Practical path: just try the push. A rejection is atomic and changes nothing on the remote. If rejected, the user runs `gh auth refresh -s workflow`, then `gh auth setup-git` (the second is what points git at the `gh` token, and changes git config). `gh pr create` and `gh secret set` go through the API and are not affected.

## Code References

- `conversations/llm.py:1` - rule text; `:29` pydantic; `:199-207` client; `:301-308`, `:386-393` parse calls; `:323-329` truncated output; `:351-353` usage fields
- `talkaitive/settings.py:37-38`, `:47`, `:58-61`, `:73-75`, `:81-82`, `:86-98` - debug default, secret key, LLM settings, prices, fail-fast
- `conversations/budget.py:27-45` - `turn_cost`
- `scripts/eval/cost.py:3`, `:16-17`; `scripts/eval/run_eval.py:1-51`, `:72`, `:89`, `:131-136`, `:604-626` - eval conventions
- `scripts/mutation/manual_mutants.py:39-50` - copy excludes
- `pyproject.toml:9`, `:17`, `:24-31`, `:33-37`, `:42-53` - deps and tool config
- `.github/workflows/ci.yml:4-30` - existing workflow
- `tests/test_llm.py:28-38`, `:41-53`, `:56-67`; `tests/fake_provider.py:44`, `:124-127`; `tests/conftest.py:19` - fakes
- `context/deployment/deploy-plan.md:151` - Railway waits for all workflows
- `CLAUDE.md:43` - rule text
- `.venv/.../openai/_client.py:252-276`, `_constants.py:8`, `resources/responses/responses.py:242-244`, `:1334-1345`, `lib/_parsing/_responses.py:146-161` - SDK 3.24.0

External sources (read 2026-10-31):

- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://docs.github.com/en/actions/concepts/security/github_token
- https://docs.github.com/en/actions/reference/security/secure-use
- https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-github-cli
- https://docs.github.com/en/rest/issues/labels and https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api
- https://help.github.com/en/enterprise-server@3.10/rest/issues/labels and https://docs.github.com/enterprise-server@3.10/rest/issues/comments
- https://cli.github.com/manual/gh_pr_comment and https://cli.github.com/manual/gh_pr_edit
- https://github.com/cli/cli/issues/6274 and https://github.com/cli/cli/discussions/7251
- https://github.com/sonicverse-eu/audiostreaming-stack/issues/155 (third-party, quotes the header)

## Architecture Insights

- The repo prefers small own scripts over libraries for LLM tooling (test-plan line on `scripts/eval/`), deterministic scoring and pinned hand-computed numbers in tests.
- LLM code logs the error type and status, never conversation or model text (`llm.py:314-329`). The review script should keep that habit, and CI gives it a stronger reason.
- Cost honesty is a repo theme: `LLMError.billed_without_usage` (`llm.py:155-174`) and `CostMeter` count failed calls. The "unknown cost" line follows the same idea.

## Historical Context (from prior changes)

- `context/archive/2026-10-14-testing-suite-trust-and-ci/research.md` - origin of the CI gate. Branch protection returned 403 on this plan; Railway "Wait for CI" is the gate.
- `context/archive/2026-10-16-testing-ai-eval-layer/research.md` - eval goes through `conversations.llm` with no database.
- `context/foundation/test-plan.md:98` says the eval should not run in CI on every PR (cost, nondeterminism). That line is about the eval, not this review. This workflow is a deliberate, advisory exception with its own cap, and the plan should say so.

## Related Research

- The two archived research documents above. No other change touches `.github/workflows/` since 2026-10-15 (`git log -- .github/workflows/ci.yml`).

## Open Questions

None of these changes scope, cost or security enough to stop planning. All are settled by the first PR run or by the plan:

1. **Secret not set yet.** The verifying PR run needs `OPENAI_API_KEY`; the user sets it. Expected and in the brief.
2. **Push credential scope unknown** (section 7). Known only at the first push. Falls under the brief's "missing permission" gate.
3. **Permissions proven only at runtime.** If `pull-requests: write` is rejected for label creation, add `issues: write`.
4. **`Field(ge=, le=)` under strict schema, real token use, and a working output cap** need the first real call.
5. **`CLAUDE.md:43` wording** needs the user, since the file holds uncommitted edits.
6. **`change.md` status** still `new`. To advance: `node .claude/skills/10x-research/scripts/metadata-guard.mjs mark-researched context/changes/ci-ai-code-review --expected-sha256 <value from inspect> --date 2026-10-31`.
