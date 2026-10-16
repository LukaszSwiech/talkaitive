import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

// E2E_USERNAME / E2E_PASSWORD come from the gitignored .env.e2e. The app's .env
// is deliberately not loaded: it holds the real OPENAI_API_KEY, and E2E must
// never call the paid model. In CI the file is absent and the job sets them.
if (existsSync('.env.e2e')) process.loadEnvFile('.env.e2e');

// 8000 is the default port of Django's runserver and of gunicorn.
// E2E_PORT overrides it when that port is taken on this machine.
const PORT = Number(process.env.E2E_PORT ?? 8000);
// 127.0.0.1, not localhost: on macOS localhost can resolve to ::1 first, while
// gunicorn binds IPv4 only, and the webServer readiness check would never pass.
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],
  webServer: {
    // Production-like: the same collectstatic + gunicorn as Railway
    // (context/deployment/web-settings.json), plus migrate (Railway's pre-deploy
    // step) and the test user, on a throwaway SQLite database.
    command: [
      'uv run python manage.py migrate --noinput',
      'uv run python manage.py collectstatic --noinput',
      'uv run python manage.py shell < tests/e2e/ensure_e2e_user.py',
      `uv run gunicorn talkaitive.wsgi --bind 127.0.0.1:${PORT} --workers 2 --threads 4 --timeout 120`,
    ].join(' && '),
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      // DEBUG=False forces HTTPS redirects and secure cookies (settings.py),
      // which plain-HTTP localhost cannot satisfy.
      DEBUG: 'True',
      DATABASE_URL: `sqlite:///${join(__dirname, 'e2e.sqlite3')}`,
      // Empty on purpose: any model call fails with a config error, never a bill.
      OPENAI_API_KEY: '',
    },
  },
});
