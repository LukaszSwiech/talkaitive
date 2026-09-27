---
project: talkaitive
researched_at: 2026-09-25
recommended_platform: Railway
runner_up: Render
context_type: mvp
tech_stack:
  language: Python 3.14 (local venv 3.14.6; requires-python >=3.13)
  framework: Django 6.1
  runtime: gunicorn (WSGI) behind Railway's edge proxy; Postgres; uv + uv.lock
---

## Recommendation

**Deploy on Railway (Hobby plan, region EU West Metal — Amsterdam).**

The MVP starts with one user who talks to fast, small LLMs, so response time matters and the project may end at MVP. Railway is the one option that combines an always-on process with no cold start, a single platform for the app and Postgres with a pre-deploy step for migrations, and a fixed cost of about $5/month that stays within the ~$10 budget. On the agent-friendly criteria it scored 4/5. It lost half a point for dashboard-only rollback and half a point for an unmanaged Postgres. The interview answers drove the result: request/response only for the MVP, developer experience over cost, no prior platform familiarity, a single region (Germany) and co-location preferred. Render scored 5/5 but costs about 2.5× more for one user; its advantage is managed Postgres with 3-day point-in-time restore. We close that gap on Railway with our own daily `pg_dump`.

## Platform Comparison

Scoring: Pass = 1, Partial = ½, Fail = 0. Researched 2026-09-25 against official docs.

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Total | Stack fit · co-location · cost (1 user) |
|---|---|---|---|---|---|---|---|
| Render | Pass | Pass | Pass | Pass | Pass | 5 | Native Python 3.14 + uv; Postgres in Frankfurt with PITR · ~$13–15/mo |
| Vercel | Pass | Pass | Pass | Pass | Partial | 4.5 | Zero-config Django (GA); DB = Neon (second vendor); no migration step; cold starts · $0 Hobby (non-commercial) |
| Cloudflare | Pass | Partial | Pass | Pass | Pass | 4.5 | **Effectively fails stack constraint** — Django on Python Workers, Django-on-Postgres path untested, no native Postgres |
| **Railway** | Partial | Partial | Pass | Pass | Pass | **4** | Railpack + uv; Postgres template in the same project; EU West · ~$5/mo |
| Fly.io | Pass | Partial | Pass | Pass | Partial | 4 | Needs hand-written uv Dockerfile; Managed Postgres $38 · ~$45–50/mo |
| mikr.us | Partial | Fail | Partial | Fail | Partial | 1.5 | Raw LXC container, IPv6-first, no ports 80/443, self-administered · ~$3/mo (paid yearly) |
| Netlify | — | — | — | — | — | dropped | No Python runtime; cannot host Django (hard filter) |

**Cloudflare Workers + Pages.** It has an excellent CLI (`wrangler`), docs in GitHub plus `llms.txt`, and MCP servers. For this stack it is not realistic yet:
- Python Workers went GA on 2026-09-21 and the Django adapters arrived on 2026-09-02.
- No Cloudflare example runs Django's Postgres ORM backend over Hyperdrive. The official Django path is `django-cf` v0.2.x (pre-1.0) on D1, which has no transactions and a limited admin.
- Cloudflare Containers (GA 2026-04-13) could run standard Django, but they need a JS Worker in front and an external Postgres.

Pages is effectively superseded by Workers.

**Vercel.** Django needs no configuration (GA 2026-04-09), with Python 3.13/3.14 and uv. It has a strong CLI (`vercel deploy --prod`, `vercel rollback`, `vercel logs`), `llms.txt` plus `.md` docs, and a Vercel MCP that is still beta.
- **Database:** Postgres is Neon via the Marketplace. The Neon Free plan scales to zero after 5 minutes and cannot be kept awake, and its restore window is 6 hours.
- **Migrations:** there is no release/pre-deploy step.
- **Hobby plan:** logs are kept 1 hour and rollback reaches only the previous deployment.
- **Limits:** request bodies are capped at 4.5 MB and WebSockets are beta.
- **Cold start:** for one user on fast models, almost every session starts cold (function start plus Neon wake-up).

Hobby is allowed because the use is private and non-commercial; donations are allowed.

**Netlify.** Functions run only JS/TS and Go, and Go through Lambda compatibility is deprecated. No Python function runtime means no Django, so it was dropped by the hard filter. Netlify Database (Neon-based, GA 2026-04-28) could only serve as an external Postgres.

**Fly.io.** Machines are persistent VMs in `fra`/`ams` with WebSockets and SSE, driven by a solid CLI (`fly deploy`, `fly logs`, `fly releases --image`). Its drawbacks for this project:
- **uv:** the `fly launch` scanner does not support uv and falls through to a Poetry Dockerfile, which breaks the build.
- **Timeouts:** gunicorn's default timeout is 30 s, and the proxy's idle timeout needs to be verified.
- **Database:** Managed Postgres Basic is $38/month, and legacy Fly Postgres is archived.
- **MCP:** marked experimental.
- **Cost:** 4–5× the budget.

**Railway.** Covered in detail in the shortlist below.

**Render.** Covered in detail in the shortlist below.

**mikr.us** (researched at the user's request). This is a Polish budget host: LXC containers with root in Hetzner Helsinki, billed yearly (plan 3.0, 2 GB, 130 PLN/year). IPv4 is shared with a few random forwarded ports and never 80/443. HTTPS comes from a provider subdomain (`*.wykr.es` and others) or a Cloudflare proxy. You administer everything yourself: OS, nginx, gunicorn, systemd, firewall and backups. There is no SLA, the API has no deploy or rollback, and the MCP/CLI tools are community-made only. The docs are Polish-only markdown on GitHub. It is a budget or learning fallback, not a fit for a DX-first, agent-operated deploy.

### Shortlisted Platforms

#### 1. Railway (Recommended)

Railway gives an always-on container with no cold start, which matters for fast-model latency. Its Postgres runs in the same project over the private network through `DATABASE_URL`. It has a dedicated `preDeployCommand` for migrations and auto-deploy from GitHub on merge to `main`, matching `tech-stack.md`.

The CLI covers deploy (`railway up`), logs (`railway logs --build/--lines/--since/--filter`), variables (`railway variable set`) and domains (`railway domain`). There is an MCP server (`mcp.railway.com`, or `railway mcp`) with no beta label, and docs as `llms.txt` plus `.md` with their source on GitHub (`railwayapp/docs`).

The HTTP request limit is 15 minutes while data flows, and 5 minutes with no data. WebSockets have no time limit, which keeps the post-MVP voice path open. The Hobby plan is $5/month and includes $5 of usage, which covers one small Django service plus Postgres for one user.

Gaps:
- Rollback is dashboard-only, and only within the 72 h image retention.
- The Postgres template is "unmanaged".
- Volume backups are "a newer feature that is still under development".

#### 2. Render

Render has the best criteria score (5/5):
- Native Python 3.14.3 with auto-installed uv.
- Frankfurt region.
- Managed Postgres with PITR: 3 days on the Hobby workspace.
- A 100-minute request limit.
- A GA CLI (v2.28) and a GA hosted MCP.
- Rollback through the REST API, which does not disable auto-deploy.

Its gap versus Railway is cost at this usage: Starter $7 plus Postgres $6 plus storage comes to about $13–15/month fixed. Two more drawbacks:
- A service's region is immutable after creation.
- The free Postgres expires after 30 days plus 14 days of grace.

It is the switch target if data safety starts to outweigh cost.

#### 3. Vercel

It is $0 for private use and has official Django support. It is third because of the two-vendor setup (Vercel plus Neon) and manual migrations. Other gaps: the 6-hour restore window and 1-hour logs on the free tiers, cold starts at the start of nearly every single-user session, and beta WebSockets.

## Anti-Bias Cross-Check: Railway

### Devil's Advocate — Weaknesses

1. **The default start command is wrong for this app.** Railpack starts Django with `python manage.py migrate && gunicorn {app}:application`, which has three problems:
   - Migrations run on every container start.
   - Gunicorn uses its default single sync worker.
   - Gunicorn keeps its default 30 s timeout.

   One sync worker means that while one LLM call is in flight, every other request queues, including a second tab, the admin, or a static page. A slow model call beyond 30 s gets killed and becomes a 502.
2. **Postgres is unmanaged and the backups are immature.** Railway itself calls the database templates "unmanaged — total control over configuration and maintenance". Volume backups are "still under development":
   - Wiping a volume deletes all its backups.
   - Restores only work inside the same project and environment.

   Deleting the project or wiping the volume therefore takes the backups with it. The error memory, the core of the product, has no off-platform copy unless we make one.
3. **Rollback is dashboard-only and time-boxed.** The agent cannot roll back from the CLI. `railway redeploy` only redeploys. Hobby keeps images for 72 h. After that, "redeploy" rebuilds from source with the original variables, which is slower and not guaranteed to be identical. Database migrations never roll back with the code.
4. **The Python version silently drifts.** Railpack ignores `requires-python`. It reads `RAILPACK_PYTHON_VERSION` or `.python-version`, and otherwise defaults to 3.13.2, while local is 3.14.6. It installs precompiled Python via mise and fails the build if a binary for that exact version is missing.
5. **Platform-level outages.** A platform-wide outage of about 8 h (2026-05-19, GCP account incident) and a US-East outage (2026-07-02) happened this year. A single instance in one region has no failover. That is acceptable for a one-person MVP, but nobody fixes it for us.

### Pre-Mortem — How This Could Fail

> The team connected the repo, and Railpack detected Django and uv and deployed on the first try. That early success hid the defaults. The service ran on Python 3.13 while development used 3.14, and a 3.14-only syntax change broke the next deploy with an error nobody understood. Gunicorn ran with one sync worker and a 30-second timeout. When the author switched to a slightly larger model for better corrections, long replies started failing with 502s, and opening a second tab froze the app while a reply was pending. Migrations ran inside the start command, so a slow migration made the health check time out and the deploy loop. They moved migrations to the pre-deploy step but left the timeout unset, and one migration waited on a lock forever and blocked all deploys. Nobody set up a `pg_dump`, trusting "Railway has backups". A cleanup of the project wiped the Postgres volume, and its backups went with it: two months of error memory were gone. A bad deploy on a Friday could not be rolled back from the terminal, and by Monday the 72-hour image window had closed.

### Unknown Unknowns

- **Railpack reads `.python-version`, not `pyproject.toml`'s `requires-python`.** Without the file, production runs Python 3.13.2. (Verified: railpack.com/languages/python.)
- **The pre-deploy command has no timeout by default.** A hanging migration holds the deployment "in progress" indefinitely. The *Pre-deploy Timeout* field (1–3600 s) only appears after a pre-deploy command is entered. The command runs in a separate container without volumes, so `collectstatic` output written there does not reach the app; `collectstatic` belongs in the start or build phase. (Verified: docs.railway.com/deployments/pre-deploy-command.)
- **Railway terminates TLS at its edge.** Django sees plain HTTP from the proxy. Without `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SECURE_SSL_REDIRECT` causes redirect loops and CSRF checks on the `*.up.railway.app` origin fail. `CSRF_TRUSTED_ORIGINS` must list the full `https://` origin.
- **The region follows the account's "preferred region".** It can be changed without downtime for stateless services. A service with a volume, such as Postgres, needs a volume migration to move. Pick EU West (`europe-west4-drams3a`) for both the app and Postgres before the first deploy. (Verified: docs.railway.com/deployments/regions.)
- **"Serverless" (formerly App Sleeping) is opt-in; leave it off.** When on, the first request after sleep may return a 502, and Django's open database connection keeps the service awake anyway. That brings a cold start back while saving nothing. (Verified: docs.railway.com/deployments/serverless.)

## Operational Story

- **Preview deploys:** Not used for the MVP. There is one `production` environment, auto-deployed on merge to `main`, and a PR is validated by GitHub Actions tests (per `tech-stack.md`). If previews become needed, Railway PR environments must get their own Postgres. PR environments were not verified in this research, so check before enabling. Never let a preview share the production `DATABASE_URL`.
- **Secrets:** Service variables live in Railway: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the LLM API key. `DATABASE_URL` is a reference variable (`${{Postgres.DATABASE_URL}}`) over the private network, so the database stays without public access, which is the default. Set values with `railway variable set KEY=VALUE`; each change triggers a redeploy. Workspace members can read them. To rotate, set the new value, let it redeploy, then revoke the old key at the provider.
- **Rollback:** The code is rolled back from the Dashboard: Service → Deployments → a previous successful deploy → Rollback. It takes about a minute and is possible within the 72 h image retention on Hobby; after that, use Redeploy of an older deployment, which rebuilds it. Data is restored separately: restore a volume backup in the Postgres service's Backups tab, where the restore is staged and must then be deployed, or `pg_restore` from the latest off-platform dump. Migrations do not roll back with the code, so write backward-compatible migrations and roll back the code first.
- **Approval:** These require a human:
  - merge to `main` (a production deploy)
  - any change to production variables or secrets
  - any database restore, volume wipe or service or project deletion
  - enabling public database access
  - plan or billing changes

  The agent may do these unattended:
  - read logs and status
  - run read-only queries against a local copy or dump
  - validate config
  - deploy to a non-production environment if one exists
- **Logs:** The agent reads logs read-only. Runtime: `railway logs --lines 200`, `railway logs --since 1h --filter "<text>"`. Build: `railway logs --build`. Status: `railway status`. The Railway MCP server (`railway mcp` or `mcp.railway.com`) is an option for structured access, but review its destructive tools before granting them.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Gunicorn single sync worker + 30 s timeout → queued requests and 502 on slow LLM calls | Devil's advocate | H | M | Explicit start command: `gunicorn talkaitive.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120` |
| Loss of error memory: unmanaged Postgres, in-platform backups deleted with the volume | Devil's advocate / Pre-mortem | M | H | **Corrected 2026-09-27:** the 2026-09-25 "Pro-only" observation was made on a Trial account; Railway docs name no plan restriction, so Hobby is unconfirmed. After upgrading to Hobby, turn on the daily and weekly backup schedules. **User decision (2026-09-27):** if Hobby has them, skip the off-platform `pg_dump` and accept that backups are deleted with the volume; if not, the daily `pg_dump` (GitHub Actions cron) is top priority. See `context/deployment/deploy-plan.md`. |
| Production runs Python 3.13.2 instead of 3.14 | Unknown unknowns | H | M | Commit `.python-version` with `3.14`; confirm the version in the build log |
| Migration hangs and blocks all deploys | Unknown unknowns / Pre-mortem | L | M | Set a Pre-deploy Timeout (e.g. 300 s) after adding `preDeployCommand` |
| Migrations run on every start (Railpack default) | Devil's advocate | H | L | Override `startCommand`; run `migrate` only in `preDeployCommand` |
| No CLI rollback; images kept only 72 h on Hobby | Devil's advocate / Research finding | M | M | Rollback is a human dashboard action (see Approval); keep migrations backward-compatible; tag releases in git so a rebuild from source is reproducible |
| HTTPS redirect loop / CSRF failures behind the edge proxy | Unknown unknowns | H | M | `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS=https://<app>.up.railway.app`, `ALLOWED_HOSTS` from env |
| Service or DB lands in a US region | Unknown unknowns | M | L | Set the preferred region to EU West before creating services; verify both services show `europe-west4-drams3a` |
| Platform outage (8 h on 2026-05-19) | Research finding | L | M | Accept for a one-user MVP; keep off-platform dumps so a move to Render stays possible |
| Serverless/App Sleeping reintroduces cold starts and 502s | Unknown unknowns | L | M | Keep Serverless disabled on the web service |
| Monthly cost creeps above $5 (Postgres idle RAM + app) | Research finding | L | L | Check usage in the dashboard after the first month; set a usage limit alert |
| Nixpacks deprecation affects old guides | Research finding | M | L | Use Railpack (default for new services); ignore Nixpacks-based tutorials |

## Getting Started

Checked 2026-09-25 against the Railway and Railpack docs for this repo: Django 6.1, uv + `uv.lock`, `WSGI_APPLICATION = "talkaitive.wsgi.application"`, local Python 3.14.6.

1. **Pin the runtime and add the production dependencies.**
   - Run `echo "3.14" > .python-version`, because Railpack reads this file, not `requires-python`.
   - Run `uv add gunicorn "psycopg[binary]" whitenoise dj-database-url`.
2. **Make `talkaitive/settings.py` environment-driven,** as CLAUDE.md already flags:
   - Read `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` from the environment.
   - Set `DATABASES["default"]` from `DATABASE_URL` with `dj_database_url`, falling back to SQLite locally.
   - Set `STATIC_ROOT` and add WhiteNoise middleware and storage.
   - Set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.
3. **Add `railway.json` (config as code) at the repo root,** so the defaults are overridden in version control:
   - `build.builder = "RAILPACK"`
   - `deploy.preDeployCommand = ["python manage.py migrate --noinput"]`
   - `deploy.startCommand = "python manage.py collectstatic --noinput && gunicorn talkaitive.wsgi --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120"`
   - `deploy.healthcheckPath` pointing at a cheap unauthenticated URL, such as the login page.

   Then set the Pre-deploy Timeout (e.g. 300 s) in service settings.
4. **Create the project and database** with the Railway CLI. The official installer is `curl -fsSL agents.railway.com | sh`; it also runs `railway setup agent`, and the docs describe a variant without agent configuration.
   - Run `railway login`.
   - Run `railway init --name talkaitive`.
   - Run `railway add --database postgres`.
   - Set the preferred region to **EU West (Amsterdam)** first.
   - Connect the GitHub repo to the web service for auto-deploy on `main`. This is a one-time manual step in the dashboard.
5. **Configure and verify.**
   - Run `railway variable set SECRET_KEY=... DEBUG=False ALLOWED_HOSTS=... CSRF_TRUSTED_ORIGINS=https://...`, and reference `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
   - Run `railway domain` to generate the `*.up.railway.app` domain.
   - Merge to `main` and watch `railway logs --build`, then `railway logs`.
   - Create the first account with `railway ssh`, then `python manage.py createsuperuser`, since accounts are created by the owner outside the product.
   - Enable Postgres backup schedules.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration
- CI/CD pipeline setup (GitHub Actions test workflow, the `pg_dump` cron job)
- Production-scale architecture (multi-region, HA, DR)
- Voice/WebSocket architecture after the MVP. Railway's WebSocket support was noted, but not designed for.
