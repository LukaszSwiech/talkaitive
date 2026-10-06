# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Response language — always Polish, always simple

The user writes in English but is a junior developer: **every chat response must be in Polish**, in every conversation, even when the question, the skill instructions or the source material are in English.

- Use plain, simple Polish: short sentences, one idea at a time. Explain each technical term the first time it appears (e.g. "zmienna środowiskowa (env var) — ustawienie trzymane poza kodem").
- Keep code, commands, file paths, identifiers and error messages as they are (don't translate them); explain around them in Polish.
- Code, code comments, commit messages and files written to disk keep the repo's existing language unless the user asks otherwise.

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
- `talkaitive/settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` and `OPENAI_API_KEY` from env vars. Locally, with none set, it falls back to DEBUG on, a dev key and SQLite. On Railway (`RAILWAY_ENVIRONMENT` is set) DEBUG defaults to off. Outside DEBUG a missing `SECRET_KEY` or `OPENAI_API_KEY` crashes startup on purpose. In DEBUG a missing `OPENAI_API_KEY` only makes the first LLM call fail with a config error. Optional: `LLM_MODEL` (default `gpt-5.4`; it needs an entry in `LLM_PRICES_USD_PER_MTOK`, otherwise startup fails), `DAILY_BUDGET_USD` (default `1.00`, per user per day, reset at midnight Europe/Berlin) and `OPENAI_BASE_URL` (default is the global endpoint `https://api.openai.com/v1`; EU data residency via `eu.api.openai.com` needs an OpenAI organization approved for it, which this account is not; our keys get a 401 there).
- Real LLM locally: put `OPENAI_API_KEY` in `.env` (gitignored; never commit or print it), then run `uv run --env-file .env python manage.py runserver`. Only `conversations/llm.py` calls OpenAI. Tests replace the SDK client or `generate_turn` with fakes, and `settings_test` sets a dummy key, so `uv run pytest` needs no key and makes no network calls.
- Production runs on Railway (`web` + Postgres, EU West) and `main` auto-deploys. Live resources, IDs, plan status and open TODOs are in `context/deployment/deploy-plan.md`. Railway ignores `railway.json`, so the `web` service settings (pre-deploy `migrate`, start command, health check) live only in Railway; their copy is `context/deployment/web-settings.json`. Update it whenever you change them.
- `.gitignore` excludes `.claude/`, `.agents/` and `.gitignore` itself, so edits to skills or settings there are not committed.
- Never edit inside the `<!-- BEGIN/END @przeprogramowani/10x-cli -->` block. `10x get` replaces it with each lesson's version, but skips it (`rules.action: conflict_skipped`) once it's been edited by hand. Put project-specific corrections to course text in this section instead.

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 2, Lesson 5

Scale the single-change cycle into parallel work with **worktrees, goal-directed delegation, and multi-session orchestration**:

```
worktree per change -> /goal or claude -p -> PR -> review -> merge
```

The lesson focus is safe throughput: isolated contexts, choosing the right execution mode, and capping parallelism at review capacity.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Code isolation** | |
| `git worktree add` | You need a separate working directory for a parallel change. One change per worktree, one fresh agent context per worktree. |
| **Complex changes** | |
| `/10x-implement <change-id> phase <n>` | The change has multiple phases, needs manual gates, or benefits from interactive decision-making during execution. |
| **Simple changes** | |
| `/goal` | You have a clear, bounded task and want goal-directed delegation. The agent works autonomously toward the stated goal with a stop condition. |
| `claude -p` | You want headless execution for a well-defined task. The Ralph Wiggum loop (run, check, retry) is the universal autonomous pattern. |
| **Multi-session orchestration** | |
| Superset / Conductor / Antigravity / VS Code Agent View | You are running multiple agent sessions in parallel and need visibility, coordination, or session management across them. |

### Parallel work rules

- One change per worktree or isolated workspace. One fresh agent context per change.
- Choose interactive `/10x-implement` for complex changes, `/goal` or `claude -p` for simple ones.
- Parallelism is capped by review capacity. More agents without review means more unreviewed code, not higher throughput.
- The quality pain from faster shipping is intentional — it bridges into Module 3 testing gates.

### Lesson boundaries

- Do not reteach interactive `/10x-implement` or `/10x-impl-review`; those are Lessons 2 and 3.
- Do not introduce testing strategy here. The quality pain is the motivation for Module 3.
- Worktrees are a mechanism for isolation, not the topic of a full git tutorial.

### Paths used by this lesson

- `context/changes/<change-id>/` - active change folder
- `context/changes/<change-id>/plan.md` - implementation input for any execution mode

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
