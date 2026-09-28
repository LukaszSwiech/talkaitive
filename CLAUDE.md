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
- Every query for conversations, errors or memory must be filtered to `request.user`. No user may ever see another user's data (PRD guardrail).
- No tests or type checker yet. Ruff (config in `pyproject.toml`) auto-formats and lints each edited `.py` file via a PostToolUse hook; whole-repo run: `uv run ruff check . && uv run ruff format .`. `mypy` + `django-stubs` are planned to make up for Django's weak typing, so type-hint new models, views and services.
- Dependency audit: `uv export --format requirements-txt --no-hashes > /tmp/req.txt && uvx pip-audit -r /tmp/req.txt`. Bare `uvx pip-audit` checks uvx's own environment, not the project's, and wrongly reports it clean.
- `talkaitive/settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `DATABASE_URL` from env vars. Locally, with none set, it falls back to DEBUG on, a dev key and SQLite. On Railway (`RAILWAY_ENVIRONMENT` is set) DEBUG defaults to off and a missing `SECRET_KEY` crashes on purpose.
- Production runs on Railway (`web` + Postgres, EU West) and `main` auto-deploys. Live resources, IDs, plan status and open TODOs are in `context/deployment/deploy-plan.md`. Railway ignores `railway.json`, so the `web` service settings (pre-deploy `migrate`, start command, health check) live only in Railway; their copy is `context/deployment/web-settings.json`. Update it whenever you change them.
- `.gitignore` excludes `.claude/`, `.agents/` and `.gitignore` itself, so edits to skills or settings there are not committed.
- Never edit inside the `<!-- BEGIN/END @przeprogramowani/10x-cli -->` block. `10x get` replaces it with each lesson's version, but skips it (`rules.action: conflict_skipped`) once it's been edited by hand. Put project-specific corrections to course text in this section instead.

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 2, Lesson 1

Move from sprint-zero setup to project orchestration with the **roadmap chain**:

```
(Module 1 foundation docs) -> /10x-roadmap -> backlog-ready roadmap items
```

`/10x-roadmap` is the lesson focus. `/10x-new` is intentionally introduced in Module 2, Lesson 2, when a selected roadmap item becomes an implementation change folder.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Roadmap (lesson focus)** | |
| `/10x-roadmap` | You have `context/foundation/prd.md` and a scaffolded project baseline, and you need a vertical-first MVP roadmap. The skill reads the PRD, inspects the code baseline, uses available foundation docs such as `tech-stack.md`, `infrastructure.md`, and `deploy-plan.md`, then writes `context/foundation/roadmap.md`. Use it BEFORE creating per-change folders or implementation plans. |
| **Re-run upstream if needed** | |
| `/10x-shape` / `/10x-prd` / `/10x-tech-stack-selector` / `/10x-bootstrapper` / `/10x-agents-md` / `/10x-infra-research` | Bundled from Module 1 so foundation contracts can be fixed before roadmap sequencing. If roadmap generation exposes a PRD gap, repair the PRD before pretending the backlog is ready. |

### How the chain hands off

- `/10x-roadmap` bridges product and implementation. It does not choose frameworks, design schemas, or write a per-change implementation plan.
- The output is `context/foundation/roadmap.md`: ordered milestones, vertical slices, bounded foundations, dependencies, unknowns, risk, and backlog handoff fields.
- Roadmap items should receive stable human-readable identifiers in backlog tools. The actual `context/changes/<change-id>/` folder is created in Lesson 2 with `/10x-new`.

### Roadmap boundaries

- Default to vertical slices: user-visible outcomes that cross UI, data, business logic, and integrations.
- Horizontal work is allowed only as a bounded enabler that names the downstream vertical milestone it unlocks.
- Avoid orphan horizontal work such as "build the whole database", "build all API endpoints", or "design the whole UI" before the first user-visible flow.
- Roadmap is not a calendar estimate. Do not invent dates, story points, or sprint velocity unless the user explicitly asks for a separate planning artifact.

### Foundation paths used by this lesson

- `context/foundation/prd.md` - input
- `context/foundation/tech-stack.md` - optional input
- `context/foundation/infrastructure.md` - optional input
- `context/deployment/deploy-plan.md` - optional input
- `context/foundation/roadmap.md` - output
- `context/foundation/lessons.md` - recurring rules and pitfalls
- `docs/reference/contract-surfaces.md` - load-bearing names registry

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
