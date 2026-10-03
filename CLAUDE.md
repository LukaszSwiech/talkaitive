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
- `talkaitive/settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `DATABASE_URL` from env vars. Locally, with none set, it falls back to DEBUG on, a dev key and SQLite. On Railway (`RAILWAY_ENVIRONMENT` is set) DEBUG defaults to off and a missing `SECRET_KEY` crashes on purpose.
- Production runs on Railway (`web` + Postgres, EU West) and `main` auto-deploys. Live resources, IDs, plan status and open TODOs are in `context/deployment/deploy-plan.md`. Railway ignores `railway.json`, so the `web` service settings (pre-deploy `migrate`, start command, health check) live only in Railway; their copy is `context/deployment/web-settings.json`. Update it whenever you change them.
- `.gitignore` excludes `.claude/`, `.agents/` and `.gitignore` itself, so edits to skills or settings there are not committed.
- Never edit inside the `<!-- BEGIN/END @przeprogramowani/10x-cli -->` block. `10x get` replaces it with each lesson's version, but skips it (`rules.action: conflict_skipped`) once it's been edited by hand. Put project-specific corrections to course text in this section instead.

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 2, Lesson 3

Review AI-generated code before merge with the **implementation review chain**:

```
/10x-implement -> /10x-impl-review -> triage -> (/10x-lesson | fix | skip | disagree)
```

`/10x-impl-review` is the lesson focus. Review is a quality gate, not an instruction to fix every finding.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Code review (lesson focus)** | |
| `/10x-impl-review <change-id>` | You have implemented code and want a structured review before merge. The skill checks plan adherence, scope discipline, safety and quality, architecture, pattern consistency, and success criteria, then presents findings for triage. |
| **Recurring lesson outcome** | |
| `/10x-lesson` | A finding reveals a recurring project rule or agent failure pattern. Record it in `context/foundation/lessons.md` instead of treating it as a one-off note. |

### Triage discipline

- Severity says how bad the finding is. Impact says how much the decision matters now.
- Valid outcomes: fix now, fix differently, skip, accept as risk, record as recurring rule (`/10x-lesson`), disagree.
- Fix critical findings. Do not burn hours on low-impact observations just because the agent found them.
- Conscious skipping of low-impact findings is a valid review outcome, not negligence.
- If you disagree with a finding, record why. Wrong agent reasoning is also signal.

### Review boundaries

- This lesson reviews implemented code. It does not create the plan, execute new phases, or teach CI review.
- Testing strategy and quality gates are introduced in Module 3.
- Do not use `/10x-contract` as a triage outcome in this lesson.

### Paths used by this lesson

- `context/changes/<change-id>/plan.md` - expected implementation contract
- `context/changes/<change-id>/reviews/` - review output
- `context/foundation/lessons.md` - recurring lessons

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
