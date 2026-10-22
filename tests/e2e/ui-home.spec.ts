// Visual gate for the UI contract (tokens.css + components.css).
// Risk: ui-visual-regression — a change to a token, a component rule or the home
// markup silently changes how home or a component state looks (colours, focus
// ring, hover, loading indicator) in the light or dark theme, on desktop or phone.
// Related: context/changes/ui-home-tokens/plan.md, phase 4.
//
// Baselines live in ui-home.spec.ts-snapshots/ and are committed. Update them
// (npx playwright test tests/e2e/ui-home.spec.ts --update-snapshots) only for an
// intended visual change, and say what changed in the commit message.
//
// The tests create no data in e2e.sqlite3: the loading test aborts the start
// request in the browser, so it never reaches the server.
import { test, expect, type Page } from '@playwright/test';

const THEMES = ['light', 'dark'] as const;
const DEVICES = {
  desktop: { width: 1280, height: 720 },
  phone: { width: 390, height: 844 },
};

// The E2E user's email depends on .env.e2e, so it is masked in every home shot.
const signedInAs = (page: Page) => page.getByText(/^Signed in as /);

// ensure_e2e_user.py deletes the user's conversations and paid calls when the
// server starts. A reused server (reuseExistingServer) skips that script, so
// check the state first: a failure here is about data, not about the look.
async function openHomeWithTopicList(page: Page) {
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Choose a topic' }),
    'home must show the topic list: the E2E user needs no active conversation and an unspent daily limit (restart the E2E server so ensure_e2e_user.py runs)',
  ).toBeVisible();
}

for (const colorScheme of THEMES) {
  for (const [device, viewport] of Object.entries(DEVICES)) {
    test.describe(`${colorScheme} theme, ${device}`, () => {
      test.use({ colorScheme, viewport });
      const shot = (name: string) => `${name}-${colorScheme}-${device}.png`;

      test('home with the topic list', async ({ page }) => {
        await openHomeWithTopicList(page);

        await expect(page).toHaveScreenshot(shot('home-default'), {
          fullPage: true,
          mask: [signedInAs(page)],
        });
      });

      test('home while a topic is starting', async ({ page }) => {
        await openHomeWithTopicList(page);
        // Cancel the start request in the browser, so the server never sees it
        // and no conversation is created. A request held open would block every
        // locator until the navigation finishes; a cancelled one (ERR_ABORTED)
        // leaves the page as the submit handler made it: indicator shown,
        // buttons disabled.
        const aborted = page.waitForEvent('requestfailed', (request) =>
          request.url().endsWith('/conversations/start/'),
        );
        await page.route('**/conversations/start/', (route) => route.abort('aborted'));

        await page.getByRole('button', { name: 'Walking the dog' }).click();
        await aborted;

        await expect(page.getByText('Agent is typing…')).toBeVisible();
        // base.html disables every button once a form is sent.
        await expect(page.getByRole('button', { name: 'Log out' })).toBeDisabled();
        await expect(page).toHaveScreenshot(shot('home-loading'), {
          mask: [signedInAs(page)],
        });
      });

      test('kitchen sink with every component', async ({ page }) => {
        await page.goto('/ui/');
        await expect(page.getByRole('heading', { name: 'UI kitchen sink' })).toBeVisible();

        await expect(page).toHaveScreenshot(shot('ui-kitchen-sink'), { fullPage: true });
      });

      test('kitchen sink with keyboard focus on a button', async ({ page }) => {
        await page.goto('/ui/');
        await expect(page.getByRole('heading', { name: 'UI kitchen sink' })).toBeVisible();

        // The first focusable element on the page is the primary button.
        await page.keyboard.press('Tab');

        await expect(page.getByRole('button', { name: 'Primary', exact: true })).toBeFocused();
        await expect(page).toHaveScreenshot(shot('ui-focus'));
      });

      test('kitchen sink with the pointer over a choice list item', async ({ page }) => {
        await page.goto('/ui/');
        const item = page
          .getByRole('region', { name: 'Choice list' })
          .getByRole('button', { name: 'Supermarket' });

        await item.hover();

        await expect(page).toHaveScreenshot(shot('ui-hover'));
      });
    });
  }
}
