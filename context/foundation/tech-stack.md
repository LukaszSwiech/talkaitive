---
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
---

## Why this stack

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
$10/month budget. CI on GitHub Actions (`.github/workflows/ci.yml`: ruff check,
ruff format --check, pytest) runs on every pull request and every push to `main`;
Railway deploys a `main` commit only after that workflow is green ("Wait for CI")
and skips the deploy when it fails.
