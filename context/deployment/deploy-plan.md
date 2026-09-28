# First deploy of TalkAItive to Railway

## Status (checked 2026-09-28)

Legend used on the step headings below: ✅ done as planned · ⚠️ done, but differently (see the linked deviation) · ❌ not done.

- **Deployed and working** at `https://web-production-5e685.up.railway.app`, verified on deploy `8331c90` (2026-09-25). A push to `main` auto-deploys, with no CI gate.
- **Biggest open risk: the database has no backup at all.** Railway backups are Pro only, and the off-platform `pg_dump` is not set up yet. See [TODO](#todo).
- All plan steps (0–10) are finished. Steps 4, 5, 7 and 9 went differently from the plan; the step headings link to the matching deviation.
- Open work: [TODO](#todo).

## Prerequisites

What must exist before the deploy (or a redeploy from scratch) can run. "You" = done by hand; "agent" = done from the session.

**Accounts**
- [x] GitHub account `LukaszSwiech`, logged in with `gh auth login` (you)
- [x] Railway account, logged in with `railway login` (you)
- [x] Railway plan **Hobby** (since 2026-09-28; the first deploy ran on Trial) (you)

**Tools on the Mac**
- [x] `uv` with the project venv on Python 3.14 (agent)
- [x] `gh` and `railway`, installed with `brew install gh railway` (agent)

**Access and one-time setup**
- [x] Workspace preferred region `europe-west4-drams3a`, set **before** creating any service (you, dashboard; verified by the agent through the API)
- [x] Railway GitHub App installed for the `talkaitive` repo only. Without it, `railway service source connect` and auto-deploy do not work (you)
- [x] SSH key `talkaitive-mac` (`~/.ssh/id_ed25519_railway`) added to Railway. Always pass `-i ~/.ssh/id_ed25519_railway`; the default `id_ed25519` belongs to another Railway account (you)
- [x] `ssh.railway.com` host key accepted once in a real terminal (you)

**Limits to plan around**
- The agent shell and `!` have no TTY (interactive terminal). The first SSH connection and `createsuperuser` must run in your own terminal.
- You approve every command that writes production variables.

## Context (state before the deploy, 2026-09-25)

`context/foundation/infrastructure.md` picked **Railway (Hobby, EU West/Amsterdam)** with Postgres in the same project, and `tech-stack.md` set GitHub auto-deploy on merge to `main`. The repo is still a bare `startproject`:
- `settings.py` has a hard-coded `SECRET_KEY`, `DEBUG = True`, `ALLOWED_HOSTS = []` and SQLite.
- Only `/admin/` is routed.
- There are no git commits and no remote.
- `railway` and `gh` are not installed.

This plan makes the app production-ready according to the infrastructure risk register, pushes it to a new private GitHub repo, and wires up Railway so a merge to `main` deploys. The approved plan is saved as this file, `context/deployment/deploy-plan.md`, as the audit trail. (On 2026-09-28 it briefly lived under `context/changes/deployment/` and was moved back here to match the course convention.)

Decisions made: GitHub + auto-deploy (I install `gh`); the first commit contains only the core app and `context/`.

**Human gates** (you do these; I stop and tell you exactly what to do; their current status is in [Prerequisites](#prerequisites)): `gh auth login`, `railway login`, the Railway dashboard steps (region, GitHub connection, pre-deploy timeout, backups), approving production variable writes, and `createsuperuser`.

## Step 0: Save the plan — ✅ done (now at `context/deployment/deploy-plan.md`)
- Copy this plan to `context/deployment/deploy-plan.md`.

## Step 1: Pin the runtime and add dependencies (automated) — ✅ done
- Create `.python-version` containing `3.14`. Railpack reads this file and ignores `requires-python`; without it production would run 3.13.2.
- Run `uv add gunicorn "psycopg[binary]" whitenoise dj-database-url`.

## Step 2: Make `talkaitive/settings.py` environment-driven (automated) — ✅ done
- `import os`, `import dj_database_url`.
- `DEBUG`: read from the `DEBUG` env var. It defaults to `"False"` when `RAILWAY_ENVIRONMENT` is present (Railway injects it) and to `"True"` locally. This fails safe if `DEBUG` is forgotten in production, and `runserver` works locally with no env setup.
- `SECRET_KEY`: `os.environ["SECRET_KEY"]` when not DEBUG, so a missing key crashes the app instead of silently using the dev key. Keep the existing dev key as the fallback only when DEBUG is on.
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`: comma-separated env vars. Locally they default to `localhost,127.0.0.1` and empty.
- `DATABASES["default"] = dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600, conn_health_checks=True)`.
- Static files:
  - `STATIC_ROOT = BASE_DIR / "staticfiles"`, which is already in `.gitignore`.
  - Add `whitenoise.middleware.WhiteNoiseMiddleware` right after `SecurityMiddleware`.
  - Set `STORAGES` with `staticfiles` → `whitenoise.storage.CompressedManifestStaticFilesStorage`.
- When not DEBUG:
  - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
  - `SECURE_SSL_REDIRECT = True`
  - `SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]`, because Railway's health probe is plain HTTP and a 301 would fail it
  - `SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True`
- HSTS is left out for now, since `*.up.railway.app` is not our domain.

## Step 3: Health-check endpoint (automated) — ✅ done
- In `talkaitive/urls.py`, add `path("healthz/", ...)`, a tiny function view returning `HttpResponse("ok")`. It is unauthenticated, makes no database call, and responds fast.
- Add a type hint (`HttpRequest -> HttpResponse`), per CLAUDE.md.

## Step 4: `railway.json` at the repo root (automated) — ⚠️ replaced: Railway ignores the file, settings set through the API and the file deleted → Deviation 1
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "RAILPACK" },
  "deploy": {
    "preDeployCommand": ["python manage.py migrate --noinput"],
    "startCommand": "python manage.py collectstatic --noinput && gunicorn talkaitive.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120",
    "healthcheckPath": "/healthz/",
    "healthcheckTimeout": 120,
    "restartPolicyType": "ON_FAILURE"
  }
}
```
This covers four risk-register rows: the single sync worker with its 30 s timeout, migrations running on every start, `collectstatic` in pre-deploy not reaching the app, and the health check.

## Step 5: Verify locally before committing (automated) — ⚠️ done with changes → Deviations 4 (`mail.E001`) and 5 (no gunicorn smoke test)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run python manage.py check`, then `uv run python manage.py runserver` and `curl localhost:8000/healthz/` → `ok`.
- Simulate production: `DEBUG=False SECRET_KEY=x ALLOWED_HOSTS=localhost uv run python manage.py check --deploy`. Expect only the HSTS warning (accepted, see Step 2).
- `DEBUG=False SECRET_KEY=x uv run python manage.py collectstatic --noinput --dry-run` to confirm WhiteNoise storage works.
- `uv run gunicorn talkaitive.wsgi --bind 127.0.0.1:8001` as a smoke test, then stop it.

## Step 6: First commit and GitHub repo — ✅ done
- (automated) `git add` explicitly: `manage.py talkaitive/ pyproject.toml uv.lock .python-version railway.json CLAUDE.md context/`. This excludes `.DS_Store`, the mega-assessment files, `.10x-cli.json` and `skills-lock.json`. Commit on `main` with the attribution trailer.
- (automated) `brew install gh railway`. Using brew instead of the curl installer avoids its side-effecting `railway setup agent`.
- **(you)** `! gh auth login`.
- (automated) `gh repo create talkaitive --private --source . --push`.

## Step 7: Create the Railway project (mix) — ⚠️ done; region checked through the API and `web` pinned from the CLI → Deviation 3
- **(you)** `! railway login`.
- **(you, dashboard)** Account settings → set the **preferred region to EU West (Amsterdam)** before creating anything.
- (automated) `railway init --name talkaitive`, then `railway add --database postgres`.
- (automated) Create an empty web service named `web` with `railway add --service web`. I'll check `railway add --help` first, because the exact flags depend on the CLI version.
- **(you, dashboard)** Confirm both services show region `europe-west4-drams3a`.

## Step 8: Variables and domain (automated, you approve each command) — ✅ done
- `railway domain --service web`, which generates `web-xxxx.up.railway.app`.
- Set on `web`:
  - `DATABASE_URL='${{Postgres.DATABASE_URL}}'` (single-quoted so the shell doesn't expand it)
  - `SECRET_KEY="$(uv run python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())')"`, so the key never appears in the command text
  - `DEBUG=False`
  - `ALLOWED_HOSTS=<domain>,healthcheck.railway.app`
  - `CSRF_TRUSTED_ORIGINS=https://<domain>`
- The LLM API key is not set now; no LLM code exists yet.

## Step 9: Connect GitHub and deploy (you, dashboard) — ⚠️ partly: GitHub connected from the CLI (Deviation 2), pre-deploy timeout set through the API (Deviation 1), ❌ backups not available (Pro only, see Verification)
- In the `web` service → Settings → Source → connect `talkaitive`, branch `main`. This triggers the first deploy.
- In Settings → Deploy → **Pre-deploy Timeout = 300 s** (this field appears once `preDeployCommand` is known from `railway.json`).
- Leave **Serverless** off.
- In the Postgres service → Backups → enable the daily and weekly schedules.

## Step 10: Verify the deploy (automated, read-only) — ✅ done; `createsuperuser` ran in your own terminal (Deviation 6)
- `railway logs --build`: confirm Python **3.14.x**, uv install from `uv.lock`, Railpack builder.
- `railway logs`: migrations ran in pre-deploy, gunicorn started with 2 workers, health check passed.
- `curl -sI https://<domain>/healthz/` → 200; `curl -sI http://<domain>/admin/` → 301 to https.
- `curl -s https://<domain>/admin/login/` → 200, the login form served with static CSS. Checking `/static/admin/css/base.*.css` → 200 confirms WhiteNoise.
- **(you)** `! railway ssh --service web`, then `python manage.py createsuperuser`, then log in to `/admin/` in the browser. This end-to-end check confirms CSRF behind the proxy and the Postgres writes.

## Out of scope / follow-ups
- Daily off-platform `pg_dump` (GitHub Actions cron) and a GitHub Actions test workflow. The infra doc lists both as out of scope; they are the next change.
- Custom domain + HSTS, LLM API key, and a usage alert after the first month.

---

## Execution log (2026-09-25): what actually happened

### Live resources
| Item | Value |
|---|---|
| GitHub repo | `LukaszSwiech/talkaitive` (private). A push to `main` auto-deploys `web` (trigger checked 2026-09-28: branch `main`, `checkSuites` off, so no CI gate). No GitHub Actions for now; CI/CD comes in a later stage (user decision 2026-09-28). |
| Railway project | `talkaitive` (`8f6d357b-b551-4247-8863-183f57ea6acc`), workspace preferred region `europe-west4-drams3a` |
| Railway plan | **Hobby** since 2026-09-28. Before that the account was on Trial; the 2026-09-25 run wrongly assumed Hobby. The Postgres volume (`4fd1fea4-0e5e-49a5-a92d-adaf64c1d18c` in `production`) is still 500 MB, the Trial size; Hobby allows up to 5 GB. |
| Environment | `production` (`3a4465d3-f273-472e-a82c-0441375014a5`) |
| Services | `web` (`9e0786d6-5cc8-4f28-9724-81c55c7e1dcf`, EU West, 1 replica); `Postgres` (template `postgres-ssl:18`, volume `postgres-volume` in `europe-west4-drams3a`) |
| Public URL | `https://web-production-5e685.up.railway.app` |
| `web` variables | `SECRET_KEY` (generated, set via `--stdin`, never displayed), `DATABASE_URL=${{Postgres.DATABASE_URL}}` (resolves to `postgres.railway.internal`), `DEBUG=False`, `ALLOWED_HOSTS=web-production-5e685.up.railway.app,healthcheck.railway.app`, `CSRF_TRUSTED_ORIGINS=https://web-production-5e685.up.railway.app` |
| SSH | Key `talkaitive-mac` (`~/.ssh/id_ed25519_railway`). Always pass `-i ~/.ssh/id_ed25519_railway`, because the default `id_ed25519` belongs to another Railway account |

### Deviations from the plan
1. **`railway.json` is ignored for new services.** Railway deprecated Config as Code: new services cannot use it, and legacy services lose it on 2026-12-01. The first deploy therefore ran with `preDeployCommand`, `healthcheckPath` and the timeout all unset. As a result, **no migrations ran**, and `createsuperuser` failed with `relation "auth_user" does not exist`. Railpack picked up `startCommand` from the file only at build time.
   The fix: the `web` service settings are now set through the GraphQL API (`serviceInstanceUpdate`), and `railway.json` is deleted. Current service settings:
   - `preDeployCommand = ["python manage.py migrate --noinput"]`, `preDeployTimeoutSeconds = 300`
   - `startCommand = sh -c 'python manage.py collectstatic --noinput && exec gunicorn talkaitive.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120'`
   - `healthcheckPath = /healthz/`, `healthcheckTimeout = 120`, `restartPolicyType = ON_FAILURE`

   These settings live only in Railway. Their copy is `context/deployment/web-settings.json` (IDs + input, read back from the live service on 2026-09-27; `preDeployTimeoutSeconds` taken from this log). Update the file whenever the settings change.
   To re-apply them: `railway api 'mutation($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) { serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input) }' --variables @context/deployment/web-settings.json`. For a recreated service, change `serviceId` / `environmentId` first.
   **Follow-up:** move this into Infrastructure as Code (`.railway/railway.ts` via `railway config init`, then `railway config plan`). Review the plan carefully first, because a whole-project file deletes resources it doesn't declare, such as Postgres.
2. **GitHub was connected from the CLI** (`railway service source connect --repo … --branch main --service web`) after you installed the Railway GitHub App for this repo only. The dashboard source step was not needed.
3. **Region:** the workspace `preferredRegion` was verified through the API before anything was created. `web` was pinned with `railway service scale --service web eu-west=1`.
4. **`check --deploy` reports `mail.E001`** (console email backend). Nothing sends email in the MVP, so this is accepted for now.
5. **The local gunicorn smoke test** was replaced by Django test-client checks plus `gunicorn --check-config`.
6. **SSH needs a real terminal the first time**, to accept the `ssh.railway.com` host key. Neither the agent shell nor `!` has a TTY. The same applies to `createsuperuser`, which skips itself without a TTY.

### Verification (Step 10), deploy `8331c90`
- Build: Railpack 0.40.0, Python 3.14.7 (from `.python-version`), `uv sync --locked --no-dev`.
- Pre-deploy migrate ran; `showmigrations` shows 18 applied and 0 pending. The `/healthz/` health check passed.
- gunicorn 26.2.0 runs 2 gthread workers.
- HTTP checks:
  - `/healthz/` returns 200.
  - `http://` redirects with 301 to `https://`.
  - `/admin/login/` returns 200.
  - Static CSS returns 200 with an `immutable` cache header (WhiteNoise).
  - A 404 shows no debug page.
- The superuser was created in a real terminal, and the browser admin login succeeded. That confirms CSRF and sessions behind the proxy and Postgres writes.
- Postgres backups could not be turned on: the dashboard showed backups and PITR as locked (checked 2026-09-25, on Trial). **Confirmed on Hobby (2026-09-28):** the Backups tab says "Creating backups and enabling point-in-time recovery (PITR) are only available for customers on the Pro plan. Backups you already have … can always be restored." `volumeInstanceBackupScheduleUpdate` through `railway api` returns `Not Authorized`. Railway's docs pages (backups, plans, pricing) do not state this restriction. There are no existing backups.

### TODO
- [x] Upgrade to Hobby (done 2026-09-28).
- [x] Check Railway backups on Hobby (2026-09-28): not available, Pro only (see Verification).
- [ ] **Daily off-platform `pg_dump`**, plus one test restore. Hobby has no Railway backups, so the database has no backup at all. Do this before the app holds real data; on 2026-09-28 it holds only the admin account. This follows the 2026-09-27 user decision: skip `pg_dump` only if Hobby had backups.
  - Not via GitHub Actions for now (user decision 2026-09-28): the mechanism is chosen in the later CI/CD stage.
  - Postgres has no public TCP proxy (checked 2026-09-28). A runner outside Railway needs one enabled first, or the dump must run inside Railway.
  - **Needs:** the mechanism decision from the CI/CD stage, and a place to run the dump (a TCP proxy on Postgres for an outside runner, or a job inside Railway).
- [ ] Grow the Postgres volume from 500 MB before the data nears it (about 116 MB used on 2026-09-28; Hobby allows up to 5 GB).
  - **Needs:** the Hobby plan (done). Nothing else blocks it.
- [ ] If upgrading to Pro later: turn on the daily and weekly backup schedules and consider PITR. Keep the `pg_dump`, because Railway backups are deleted with the volume.
  - **Needs:** the Pro plan.
- [ ] Tests on PRs (CI). Deferred to the later CI/CD stage (user decision 2026-09-28); until then nothing runs tests before a deploy.
  - **Needs:** tests in the repo (none exist yet) and the CI/CD stage.
- [ ] Move `web` service settings to Infrastructure as Code (`.railway/railway.ts`) and review `railway config plan` before any apply.
  - **Needs:** a config file that also declares Postgres, so an apply doesn't delete it.
