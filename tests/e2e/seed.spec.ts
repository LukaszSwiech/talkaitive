// Seed E2E test — the pattern every generated test copies (role-based locators,
// self-contained, waits for state, named after its risk).
// Risk: auth-gate-roundtrip — a signed-out visitor must never see a protected
// page, and after signing in must land back on the page they asked for.
// Related: context/foundation/test-plan.md risk #3 (privacy).
import { test, expect } from '@playwright/test';

// The risk is the signed-out path, so this test opts out of the saved session.
test.use({ storageState: { cookies: [], origins: [] } });

test('signed-out visitor is sent to log in and returns to the protected page after signing in', async ({
  page,
}) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    throw new Error('Set E2E_USERNAME and E2E_PASSWORD in .env.e2e (see context/foundation/test-stack.md, ## E2E)');
  }

  await page.goto('/account/delete/');

  // Gate: the login form instead of the protected page, which remembers where to return.
  await expect(page).toHaveURL('/login/?next=/account/delete/');
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Delete account' })).toBeHidden();

  await page.getByLabel('Email').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();

  // Round trip: back on the page the visitor asked for, now with its content.
  await expect(page).toHaveURL('/account/delete/');
  await expect(page.getByRole('heading', { name: 'Delete account' })).toBeVisible();

  // No cleanup: the test creates no app data, only its own login session (one
  // django_session row in the throwaway e2e.sqlite3). Logging out would be safe:
  // Django's logout ends only this browser's session, not the saved one in
  // playwright/.auth/user.json that other tests load.
});
