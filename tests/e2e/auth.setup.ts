import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('sign in once and save the session', async ({ page }) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    throw new Error('Set E2E_USERNAME and E2E_PASSWORD in .env.e2e (see context/foundation/test-stack.md, ## E2E)');
  }

  await page.goto('/login/');
  // The login form is plain server-rendered HTML (no client-side framework), so
  // input typed right after load is kept: no hydration wait or retry needed.
  await page.getByLabel('Email').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();

  // Only a signed-in user leaves /login/ and sees their own email on home.
  await page.waitForURL((url) => !url.pathname.startsWith('/login/'));
  await expect(page.getByText(`Signed in as ${username}`)).toBeVisible();

  await page.context().storageState({ path: authFile });
});
