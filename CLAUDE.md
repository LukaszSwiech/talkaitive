# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Response language — always Polish, always simple

The user writes in English but is a junior developer: **every chat response must be in Polish**, in every conversation, even when the question, the skill instructions or the source material are in English.

- Use plain, simple Polish: short sentences, one idea at a time. Explain each technical term the first time it appears (e.g. "zmienna środowiskowa (env var) — ustawienie trzymane poza kodem").
- Keep code, commands, file paths, identifiers and error messages as they are (don't translate them); explain around them in Polish.
- Code, code comments, commit messages and files written to disk keep the repo's existing language unless the user asks otherwise.
- Pull request titles and descriptions are always in English, and so are review messages written for GitHub (review requests, approval comments), even though chat stays Polish.

## Explain every tool call before making it

The user is still building trust in agents and wants to understand each action before approving it. The short tool-call description is not enough. Before **every** Bash command and every file change (Edit / Write), write a short Polish block in the chat:

- **Komendy** — list each CLI command in the call (including every part of a `&&` / `|` chain) with a one-line note on what it does and what its key flags mean.
- **Co i jak** — what will happen, step by step: which files or systems are touched, and whether it only reads or also changes something.
- **Dlaczego** — why this step is needed for the current task.
- **Ryzyko** — only when something changes: what could go wrong and whether it can be undone (e.g. "commit można cofnąć `git reset`", "push jest publiczny").

Also write the Bash tool's `description` field in Polish, and let it run to one full sentence instead of 5–10 words. For a plain read (e.g. `cat`, `ls`, `git status`), one or two sentences covering the same points are enough.

## TalkAItive — project notes

Django 6.1 web app for German conversation practice (B1–B2). Spec: `context/foundation/prd.md` (in Polish); stack rationale: `context/foundation/tech-stack.md`.

- Python ≥3.13, managed by uv (project venv runs 3.14). Run everything via `uv run python manage.py <cmd>` — Django lives only in `.venv/`. Add deps with `uv add` / `uv add --dev`, never `pip install`.
- Every query for conversations, errors or memory must be filtered to `request.user`. No user may ever see another user's data (PRD guardrail). Per-user models inherit from `accounts.ownership.UserOwned` and are read only via `Model.objects.for_user(request.user)`; never register them in the admin (`tests/test_ownership.py` guards the admin registry).
- Tests run with `uv run pytest` (pytest-django, settings `talkaitive.settings_test`); no type checker yet. Ruff (config in `pyproject.toml`) auto-formats and lints each edited `.py` file via a PostToolUse hook; whole-repo run: `uv run ruff check . && uv run ruff format .`. `mypy` + `django-stubs` are planned to make up for Django's weak typing, so type-hint new models, views and services.
- Dependency audit: `uv export --format requirements-txt --no-hashes > /tmp/req.txt && uvx pip-audit -r /tmp/req.txt`. Bare `uvx pip-audit` checks uvx's own environment, not the project's, and wrongly reports it clean.
- `talkaitive/settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` and `OPENAI_API_KEY` from env vars. Locally, with none set, it falls back to DEBUG on, a dev key and SQLite. On Railway (`RAILWAY_ENVIRONMENT` is set) DEBUG defaults to off. Outside DEBUG a missing `SECRET_KEY` or `OPENAI_API_KEY` crashes startup on purpose. In DEBUG a missing `OPENAI_API_KEY` only makes the first LLM call fail with a config error. Optional: `LLM_MODEL` (default `gpt-5.4`; it needs an entry in `LLM_PRICES_USD_PER_MTOK`, otherwise startup fails), `LLM_ANALYSIS_REASONING_EFFORT` (default `medium`, used by the post-conversation mistake analysis; `high` measured 3x slower and costlier), `DAILY_BUDGET_USD` (default `1.00`, per user per day, reset at midnight Europe/Berlin) and `OPENAI_BASE_URL` (default is the global endpoint `https://api.openai.com/v1`; EU data residency via `eu.api.openai.com` needs an OpenAI organization approved for it, which this account is not; our keys get a 401 there).
- Real LLM locally: put `OPENAI_API_KEY` in `.env` (gitignored; never commit or print it), then run `uv run --env-file .env python manage.py runserver`. Only `conversations/llm.py` calls OpenAI. Tests replace the SDK client or `generate_turn` with fakes, and `settings_test` sets a dummy key, so `uv run pytest` needs no key and makes no network calls.
- Mutation checks run locally and periodically, never in CI: `uv run python scripts/mutation/manual_mutants.py [ID ...]` (exit 0 = every result matches its expectation) and `uv run mutmut run` + `uv run mutmut results` (delete `mutants/` first after test-only changes, or mutmut shows stale results). Every survivor kept on purpose gets a row in `scripts/mutation/accepted_survivors.md`. How to add a test and confirm it with a mutant: `context/foundation/test-plan.md` §6.1.
- Production runs on Railway (`web` + Postgres, EU West) and `main` auto-deploys, but only after the GitHub Actions workflow `CI` (`.github/workflows/ci.yml`: ruff check, ruff format --check, pytest; runs on every PR and push to `main`) is green on that commit (Railway "Wait for CI"); a red run skips the deploy. Live resources, IDs, plan status and open TODOs are in `context/deployment/deploy-plan.md`. Railway ignores `railway.json`, so the `web` service settings (pre-deploy `migrate`, start command, health check) live only in Railway; their copy is `context/deployment/web-settings.json`. Update it whenever you change them.
- `.gitignore` excludes `.claude/`, `.agents/` and `.gitignore` itself, so edits to skills or settings there are not committed.
- Never edit inside the `<!-- BEGIN/END @przeprogramowani/10x-cli -->` block. `10x get` replaces it with each lesson's version, but skips it (`rules.action: conflict_skipped`) once it's been edited by hand. Put project-specific corrections to course text in this section instead.

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 3, Lesson 4 (E2E Tests)

**For E2E tests, use the two M3L4 skills in this order:**

1. **`/10x-e2e-setup`** — one-time setup: Playwright config (`webServer`,
   auth `setup` project, `storageState`), a green seed test, and `context/foundation/test-stack.md`.
2. **`/10x-e2e`** — the per-risk loop: risk → explore the running app with
   `playwright-cli` → generate → review against the five anti-patterns →
   re-prompt by name → verify with a deliberate break.

The skills' `references/` carry the full rules, anti-patterns, seed pattern, and
prompt-template.

A few hard rules that hold even before you invoke the skill:

- **Locators:** `getByRole` / `getByLabel` / `getByText` first; `getByTestId`
  only when accessibility attributes are ambiguous. Never CSS selectors, XPath,
  or DOM structure.
- **Never `page.waitForTimeout()`.** Wait for state: `toBeVisible()`,
  `waitForURL()`, `waitForResponse()`.
- **Test independence + cleanup.** Each test runs standalone — its own setup,
  action, assertion, and cleanup; unique ids (timestamp suffix) so parallel runs
  and re-runs don't collide.

Two boundaries to keep straight:

- **DOM (snapshot) is the default.** Vision (`--caps=vision`) is a supplement for
  visual-only risks (layout, z-index, animation); for pixel regression prefer
  deterministic tools (`toHaveScreenshot`, Argos, Lost Pixel). VLM model
  selection/cost is a debugging topic (Lesson 5), not testing.
- **A red test is a signal, not a chore.** A changed selector → update the
  locator in a reviewed diff. A changed business behavior → the test caught a
  bug; never edit the assertion to match it. Fixing failing tests is Lesson 5.

<!-- END @przeprogramowani/10x-cli -->
