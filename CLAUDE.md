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

## Branches — never work on `main`

This section is the single source for branch rules across `/10x-new` → `/10x-research` → `/10x-plan` → `/10x-implement` / `/10x-tdd` → `/10x-impl-review` → `/10x-archive`. Skill files are not edited for this (they are gitignored and `10x get` overwrites them), and `lessons.md` is not read by `/10x-new` or `/10x-archive`.

- **Before `/10x-new`** (or any other work that will change files), check the current branch. On `main`, first create a branch from an up-to-date `main` (`git switch main && git pull --ff-only && git switch -c <change-id>`), named after the change-id, and only then create the change folder. Propose the branch name and wait for the user's OK before creating it.
- **`/10x-plan` decides the branch layout.** A change may use one branch for everything, or a separate branch (and PR) per phase or group of phases. Analyse the phases — size, risk, whether a phase can be merged and deployed on its own (`main` auto-deploys), and whether later phases depend on earlier ones being merged — and add a `## Branches and PRs` section right after `## Implementation Approach` in `plan.md` with a one-sentence recommendation, e.g. "One branch `<change-id>` and one PR for all phases." or "Phases 1–2 on `<change-id>-p1`, phase 3 on `<change-id>-p3` after the first PR is merged." Mention it when presenting the plan, so the user confirms or changes it.
- **Starting a phase that the plan puts on a new branch:** before its first edit, create that branch from an up-to-date `main` once the previous PR is merged (or from the previous branch, if the plan says the branches stack).
- **`/10x-archive`, plan close-outs and review fixes** run on the change's branch, never on `main`. Commit straight to `main` only when the user explicitly asks for it.

## TalkAItive — project notes

Django 6.1 web app for German conversation practice (B1–B2). Spec: `context/foundation/prd.md` (in Polish); stack rationale: `context/foundation/tech-stack.md`.

- Python ≥3.13, managed by uv (project venv runs 3.14). Run everything via `uv run python manage.py <cmd>` — Django lives only in `.venv/`. Add deps with `uv add` / `uv add --dev`, never `pip install`.
- Every query for conversations, errors or memory must be filtered to `request.user`. No user may ever see another user's data (PRD guardrail). Per-user models inherit from `accounts.ownership.UserOwned` and are read only via `Model.objects.for_user(request.user)`; never register them in the admin (`tests/test_ownership.py` guards the admin registry).
- Tests run with `uv run pytest` (pytest-django, settings `talkaitive.settings_test`); no type checker yet. Ruff (config in `pyproject.toml`) auto-formats and lints each edited `.py` file via a PostToolUse hook; whole-repo run: `uv run ruff check . && uv run ruff format .`. `mypy` + `django-stubs` are planned to make up for Django's weak typing, so type-hint new models, views and services.
- Dependency audit: `uv export --format requirements-txt --no-hashes > /tmp/req.txt && uvx pip-audit -r /tmp/req.txt`. Bare `uvx pip-audit` checks uvx's own environment, not the project's, and wrongly reports it clean.
- `talkaitive/settings.py` reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` and `OPENAI_API_KEY` from env vars. Locally, with none set, it falls back to DEBUG on, a dev key and SQLite. On Railway (`RAILWAY_ENVIRONMENT` is set) DEBUG defaults to off. Outside DEBUG a missing `SECRET_KEY` or `OPENAI_API_KEY` crashes startup on purpose. In DEBUG a missing `OPENAI_API_KEY` only makes the first LLM call fail with a config error. Optional: `LLM_MODEL` (default `gpt-5.4`; it needs an entry in `LLM_PRICES_USD_PER_MTOK`, otherwise startup fails), `LLM_ANALYSIS_REASONING_EFFORT` (default `medium`, used by the post-conversation mistake analysis; `high` measured 3x slower and costlier), `DAILY_BUDGET_USD` (default `1.00`, per user per day, reset at midnight Europe/Berlin) and `OPENAI_BASE_URL` (default is the global endpoint `https://api.openai.com/v1`; EU data residency via `eu.api.openai.com` needs an OpenAI organization approved for it, which this account is not; our keys get a 401 there).
- Real LLM locally: put `OPENAI_API_KEY` in `.env` (gitignored; never commit or print it), then run `uv run --env-file .env python manage.py runserver`. In the application, only `conversations/llm.py` calls OpenAI; the standalone CI review script `scripts/review/` is the one deliberate exception. Tests replace the SDK client or `generate_turn` with fakes, and `settings_test` sets a dummy key, so `uv run pytest` needs no key and makes no network calls.
- Mutation checks run locally and periodically, never in CI: `uv run python scripts/mutation/manual_mutants.py [ID ...]` (exit 0 = every result matches its expectation) and `uv run mutmut run` + `uv run mutmut results` (delete `mutants/` first after test-only changes, or mutmut shows stale results). Every survivor kept on purpose gets a row in `scripts/mutation/accepted_survivors.md`. How to add a test and confirm it with a mutant: `context/foundation/test-plan.md` §6.1.
- AI eval on the real model runs locally and manually, never in CI, and is not part of `uv run pytest` (only its scorer and golden-set consistency tests are): `uv run --env-file .env python scripts/eval/run_eval.py run [--suite analysis,turn,memory,latency] [--repeats 3] [--max-usd 5]`, then `uv run python scripts/eval/run_eval.py compare <baseline>.json <new>.json` against the committed baseline in `scripts/eval/results/`. Run it before and after changing the turn prompt, the analysis prompt, the memory block text, `LLM_MODEL` or a reasoning effort. It bypasses the app's daily budget and has its own cap (default 5 USD; the full K=3 run cost 0.83 USD and ~12 min on 2026-10-19) and uses the same OpenAI account as production. How to run, read and extend it: `context/foundation/test-plan.md` §6.5.
- Production runs on Railway (`web` + Postgres, EU West) and `main` auto-deploys, but only after the GitHub Actions workflow `CI` (`.github/workflows/ci.yml`: ruff check, ruff format --check, pytest; runs on every PR and push to `main`) is green on that commit (Railway "Wait for CI"); a red run skips the deploy. Live resources, IDs, plan status and open TODOs are in `context/deployment/deploy-plan.md`. Railway ignores `railway.json`, so the `web` service settings (pre-deploy `migrate`, start command, health check) live only in Railway; their copy is `context/deployment/web-settings.json`. Update it whenever you change them.
- `.gitignore` excludes `.claude/`, `.agents/` and `.gitignore` itself, so edits to skills or settings there are not committed.
- Never edit inside the `<!-- BEGIN/END @przeprogramowani/10x-cli -->` block. `10x get` replaces it with each lesson's version, but skips it (`rules.action: conflict_skipped`) once it's been edited by hand. Put project-specific corrections to course text in this section instead.

### UI: tokens and components

The design-system contract (from change `ui-home-tokens`). Read it before touching any template or CSS.

- Colour values live only in `accounts/static/ui/css/tokens.css`: shadcn token names, light theme in `:root`, dark in `@media (prefers-color-scheme: dark)`, source the tweakcn export `context/archive/2026-10-20-ui-home-tokens/theme-source.css`. Write each colour value as `oklch(L C H)` or `var(--token)` only (the contrast test parses just these; `--shadow-sm` is not a colour token and keeps tweakcn's `hsl()`), with a comment giving the tweakcn value when it differs. Both themes must pass WCAG AA: a new text/background pair gets a row in `CONTRAST_PAIRS` (`tests/test_ui.py`). `color-mix()` goes in `components.css`, never in `tokens.css`.
- Components live in `accounts/static/ui/css/components.css` and read only `var(--…)`: `btn` (primary; `data-variant="secondary"` / `"destructive"`; works on `<a>`), `link` (`data-variant="destructive"`), `alert` (`data-variant="destructive"` / `"success"` / `"warning"`; `"error"` only as the alias for Django messages), `page-footer`, `topic-grid` (`<ul class="topic-grid">`, one `<li>` per card), `topic-card` (`{% include "ui/topic-card.html" with topic=topic type="submit" only %}`, add `disabled=True` for the disabled state; it is a `<button>`, so each card sits in its own `<form>`), `category-nav` (sticky `<nav class="category-nav" aria-label="…">` of `#<category key>` links; `html:has(.category-nav)` sets `scroll-padding-top` so jumped-to sections land below it), `icon` (inline Tabler SVG from `accounts/templates/ui/icons/`: `{% include "ui/icons/<name>.svg" %}` or `{% include topic.icon_template %}`; colour from `currentColor`, `aria-hidden="true"`, sized by `.icon`, `.btn .icon` inside a button). A bare `<button>` gets the secondary look; `.notice` and `.error` are aliases for pages not yet on components. Check this list before adding a component, and add a new one there.
- Wide pages (the topic grid): `{% block body_class %}page-wide{% endblock %}` in the page template; `base.html` puts the block on `<body class="…">` and `body.page-wide` widens the column.
- Adding a topic or icon: (1) add a `Topic` to `TOPICS` in `conversations/topics.py` with `key`, `title`, `scenario` and the card fields `name`, `subtitle`, `category` (a key from `CATEGORIES`) and `icon` (a Tabler outline icon name, no `.svg`); never change an existing `key` (it is stored on `Conversation.topic` and selects the user's memory). (2) A new icon: copy `icons/outline/<name>.svg` from the Tabler release pinned in `accounts/templates/ui/icons/README.md` into that folder, change only the `<svg>` root as the README lists (drop the comment and `width`/`height`, add `class="icon" aria-hidden="true" focusable="false"`, one line), and add a row (and bump the file count) in the README's table; an icon used outside topic cards also goes into `NON_TOPIC_ICONS` in `tests/test_topics.py`. (3) A new category: a `Category(key=…, label=…)` in `CATEGORIES` (tuple order = page order) with at least one topic, and a key that does not read as a hex colour after `#` (no `add` or `cafe`, nor 3–8 hex letters before a `-`, e.g. `face-to-face`). (4) `uv run pytest tests/test_topics.py` checks the rest: card fields, known and non-empty categories, icon files exist and keep the unified root, no orphan icons, no hex-like category keys.
- Variants only through `data-variant` (Basecoat convention: `<button class="btn" data-variant="destructive">`), never `btn-*` classes. Disabled: `disabled` on a `<button>`, `aria-disabled="true"` on an `<a>` without `href`.
- A component with more than one HTML element, used in 2+ places, becomes `accounts/templates/ui/<name>.html` (folder reserved for components), called via `{% include "ui/<name>.html" with … only %}` and built from the same classes. If it contains a form, pass `csrf_token=csrf_token` explicitly (`only` drops it).
- No colours, `<style>` or `style=` in templates; page CSS goes into `components.css`. `tests/test_ui.py` guards the templates and `components.css`.
- `/ui/` (kitchen sink, view `conversations.views.ui_kitchen_sink`, template `accounts/templates/accounts/ui_kitchen_sink.html`, DEBUG only, 404 elsewhere) shows every component in every state. Every new component or state goes there.
- Screenshot gate: `npx playwright test tests/e2e/ui-home.spec.ts`, local only, never CI (if a dev server holds port 8000, prefix `E2E_PORT=8001`). Update baselines with `--update-snapshots` only for an intended visual change, and describe that change in the commit message.
- Django messages render as `<p class="flash alert" data-variant="{{ message.level_tag }}">` in `base.html`. `class="flash` must stay at the start of that markup: negative assertions in `tests/test_conversation_views.py` look for it.

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 4, Lesson 2 (Project Map)

Get up to speed in an unfamiliar or legacy repo from evidence, not from directory trees: **Wide Scan first, Deep Focus later.**

```
git history + dependency graph + contributors -> context/map/repo-map.md -> focused /10x-research
```

### Task Router - Where to start

| Skill / prompt | Use it when |
| --- | --- |
| `/10x-repo-map` | One-run Project Map. It ranks business capabilities by criticality × buzz, keeps its evidence in `context/map/evidence/`, and writes `context/map/repo-map.md` with risk zones, a first-day reading list and explicit unknowns. Use `--replace` to refresh; the previous run moves to `context/archive/`. |
| `m4l2-1-territory-git-history` -> `m4l2-2-structure-dependency-cruiser` -> `m4l2-3-contributors-git` -> `m4l2-repo-map-synthesis` | The same map built step by step, one artifact at a time, so you can see what each evidence source adds. |
| `/10x-research` | A question about one feature or area. The map covers breadth and takes no target; depth belongs to research. |

### Hard rules

- **Let tools collect evidence outside the context window.** Use git, the forge and graph tools to gather data, then interpret only their condensed output. Never read the repo file by file.
- **Exclude the noise.** Leave out lockfiles, generated code, bulk formatting commits, bot commits and agent-authored commits when ranking activity.
- **Unknowns are part of the map.** Mark what the evidence can't show as unknown instead of filling the gap with a guess.

<!-- END @przeprogramowani/10x-cli -->
