---
bootstrapped_at: 2026-09-21T12:34:23Z
starter_id: django
starter_name: Django
project_name: talkaitive
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

Verbatim copy of `context/foundation/tech-stack.md`.

```yaml
starter_id: django
package_manager: uv
project_name: talkaitive
hints:
  language_family: python
  team_size: solo
  deployment_target: railway
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: true
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: true
  has_background_jobs: false
```

### Why this stack

A solo author shipping a German-conversation MVP in 10 weeks of after-hours time,
with Python named as the preferred language, needs a batteries-included starter
rather than an assembly job. Django is the recommended default for `(web, python)`
and covers the account surface directly: email + password auth, migrations, an ORM
for conversations and error memory, and an admin UI for the invite-only account
creation and password resets the PRD places outside the product. Scaffolding
confidence is verified. Django fails the explicit-types gate — optional type hints
and a duck-typed ORM — so `quality_override` is set: the generated instruction file
should pin model/view conventions and add `mypy` with `django-stubs` to compensate.
FastAPI was the typed alternative but would trade away the built-in auth and admin
that FR-001 and FR-013 lean on. Railway replaces the card's Fly.io default: a
first-time deployer gets a web UI, one-click Postgres and push-to-deploy inside a
$10/month budget. CI on GitHub Actions runs tests on pull requests only, since
Railway handles deploys on merge to `main`.

## Pre-scaffold verification

| Signal      | Value                                          | Severity | Notes                                                                                     |
| ----------- | ---------------------------------------------- | -------- | ----------------------------------------------------------------------------------------- |
| npm package | not run                                        | n/a      | non-JS starter (`language_family: python`); `cmd_template` invokes no npm-distributed CLI  |
| GitHub repo | not run                                        | n/a      | card `docs_url` is `https://docs.djangoproject.com`, not a `github.com/<owner>/<repo>` URL; `gh` is also not installed on this machine |
| PyPI release (supplementary) | django v6.1.1 published 2026-09-02 | fresh    | 19 days old at run time; queried from `pypi.org/pypi/django/json` as a stand-in for the two spec'd signals, both of which were unavailable |

**Toolchain note surfaced by the recency check**: Django 6.1.1 declares
`requires-python >=3.12`; the system interpreter on this machine is Python 3.11.
`uv` resolved this by fetching CPython 3.14.6 into the project environment, so the
mismatch never reached the scaffold step.

## Scaffold log

**Resolved invocation**: `django-admin startproject talkaitive .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: `manage.py`, `talkaitive/__init__.py`, `talkaitive/settings.py`, `talkaitive/urls.py`, `talkaitive/asgi.py`, `talkaitive/wsgi.py`
**Files written by CLI**: 6
**Pre-existing files preserved**: none of the pre-flight paths existed in cwd, so no file was overwritten and no `.scaffold` sibling was created. `context/`, `CLAUDE.md`, `.gitignore`, `.claude/`, `.agents/`, `.10x-cli.json`, `skills-lock.json` and `.git/` were all untouched by the CLI.

### Substitution deviation (recorded deliberately)

`scaffold-merge.md` § Substitution rules specifies `{name}` → `.` for the
`native-cwd` strategy. The Django card's `cmd_template` is
`django-admin startproject {name} .` — the trailing `.` is already the
"scaffold into the current directory" argument, so `{name}` is Django's *project
package name*, not a target directory. Literal substitution would have produced
`django-admin startproject . .`, which `django-admin` rejects (`.` is not a valid
project name) and which would have tripped the Step 2 HARD-STOP.

`{name}` was therefore substituted with the hand-off's `project_name`
(`talkaitive`). The user confirmed this at the Step 0 confirm-or-correct gate
before the scaffold ran. Worth pinning in `bootstrapper-config.yaml` or the
substitution rules in a future revision: the `native-cwd` strategy has two shapes
(`{name}` *is* the directory, vs `{name}` is a name and the directory is a separate
literal argument) and the current rule only covers the first.

### Environment preparation (card `pre` step)

The Django card carries `pre: "pip install django"`, but the hand-off pins
`package_manager: uv`. The `pre` step was translated to the uv equivalent rather
than run verbatim, so the project gets a lockfile and a managed interpreter
instead of a loose global install:

| Step | Command | Exit | Result |
| ---- | ------- | ---- | ------ |
| 1 | `uv init --bare --vcs none --python 3.13` | 0 | created `pyproject.toml` only (`--bare` suppresses `main.py`/`README.md`; `--vcs none` leaves the existing `.git/` and `.gitignore` alone) |
| 2 | `uv add django` | 0 | fetched CPython 3.14.6, created `.venv/`, wrote `uv.lock`, installed `django==6.1.1`, `asgiref==3.12.1`, `sqlparse==0.6.0` |

Additional files written by this step: `pyproject.toml`, `uv.lock`, `.venv/`.

### Post-scaffold adjustments

| File | Change | Rationale |
| ---- | ------ | --------- |
| `pyproject.toml` | `name` changed from `10xdevs4` to `talkaitive` | `uv init` defaults the project name to the cwd directory name; realigned to the hand-off's `project_name` |
| `.gitignore` | append-merged with a `# from django` separator block: `__pycache__/`, `*.py[cod]`, `.venv/`, `db.sqlite3`, `.env`, `/staticfiles/`, `/media/` | `django-admin startproject` ships no `.gitignore`, and neither does `uv init --vcs none`. Without these lines the freshly-created `.venv/` (hundreds of files) would show up untracked in `git status`. Existing lines (`.agents/`, `.claude/`, `.gitignore`) kept in order, per the conflict matrix's append-merge rule. |

**Sanity check**: `uv run python manage.py check` → `System check identified no issues (0 silenced).`

## Post-scaffold audit

**Tool**: `pip-audit` (invoked as `uvx pip-audit -r <exported-requirements> --format json`)
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: 1 direct dependency (`django`), 3 transitive (`asgiref`, `sqlparse`, `tzdata` — the last is `sys_platform == 'win32'` only). No findings in either tier.

### Invocation note

`pip-audit` is not installed on this machine and was run through `uvx`. A bare
`uvx pip-audit` audits *uvx's own isolated environment*, not the project's — it
reported "No known vulnerabilities found" for the wrong dependency tree. The audit
was re-run against the project's actual resolved set, exported with
`uv export --format requirements-txt --no-hashes`, which is the result recorded
above. Anyone repeating this audit should use the `-r` form, not bare `uvx pip-audit`.

### Raw output

```json
{"dependencies": [{"name": "asgiref", "version": "3.12.1", "vulns": []}, {"name": "django", "version": "6.1.1", "vulns": []}, {"name": "sqlparse", "version": "0.6.0", "vulns": []}], "fixes": []}
```

#### CRITICAL findings

None.

#### HIGH findings

None.

#### MODERATE findings

None.

#### LOW / INFO findings

None.

## Hints recorded but not acted on

| Hint | Value |
| ---- | ----- |
| bootstrapper_confidence | verified |
| quality_override | true |
| path_taken | standard |
| self_check_answers | null |
| team_size | solo |
| deployment_target | railway |
| ci_provider | github-actions |
| ci_default_flow | auto-deploy-on-merge |
| has_auth | true |
| has_payments | false |
| has_realtime | false |
| has_ai | true |
| has_background_jobs | false |

**`quality_override: true`** is the one that carries a real follow-up. Django was
selected past the explicit-types quality gate, and the hand-off rationale names the
compensation: pin model/view conventions in the agent instruction file and add
`mypy` with `django-stubs`. v1 of this skill surfaces that gap but does not close
it — neither the type-checking setup nor the instruction file was generated.

**`deployment_target: railway`**, **`ci_provider: github-actions`** and
**`ci_default_flow: auto-deploy-on-merge`** were logged only. No CI workflow files,
Railway config, or deploy manifests were written.

**`has_auth: true`** and **`has_ai: true`** were logged only. Django's built-in
`django.contrib.auth` ships enabled in the generated `settings.py`, but that is the
starter's default rather than a response to the flag; no AI dependency was added.

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- Your repo already has a `.git/` and history is yours — no `git init` needed. The scaffold added no upstream history.
- No `.scaffold` siblings were created this run; nothing to review or reconcile.
- No audit findings to address.
- Carry the `quality_override` compensation forward: `uv add --dev mypy django-stubs` and a `[tool.mypy]` block in `pyproject.toml` are the concrete form of what the stack rationale committed to.
- `talkaitive/settings.py` ships with the SQLite default and a generated `SECRET_KEY` in source. Both want attention before the Railway deploy the hand-off names: Postgres via `DATABASES`, and the key moved to an environment variable.
