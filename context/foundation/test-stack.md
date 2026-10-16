# Test stack

## E2E

<!-- Written by /10x-e2e-setup. Re-run it to change this section; other skills only read it. -->

- runner: Playwright Test, @playwright/test 1.64.1
- config: playwright.config.ts
- single-spec command: npx playwright test tests/e2e/<name>.spec.ts
- full-suite command: npx playwright test
- base URL: http://127.0.0.1:8000
- port: 8000 (detected default of Django runserver / gunicorn; override with E2E_PORT)
- web server command: uv run python manage.py migrate --noinput && uv run python manage.py collectstatic --noinput && uv run python manage.py shell < tests/e2e/ensure_e2e_user.py && uv run gunicorn talkaitive.wsgi --bind 127.0.0.1:$E2E_PORT --workers 2 --threads 4 --timeout 120 (env: DEBUG=True, DATABASE_URL=sqlite e2e.sqlite3, OPENAI_API_KEY empty); reuseExistingServer outside CI
- auth setup project: setup (tests/e2e/auth.setup.ts), credentials from E2E_USERNAME / E2E_PASSWORD in .env.e2e
- storageState: playwright/.auth/user.json (gitignored)
- seed: tests/e2e/seed.spec.ts — protects auth-gate-roundtrip (a signed-out visitor never sees a protected page and returns to it after signing in; related to test-plan.md risk #3)
- browser CLI: playwright-cli, command skill at .claude/skills/playwright-cli/SKILL.md
- updated: 2026-10-16
