// Visual gate for the UI contract (tokens.css + components.css).
// Risk: ui-visual-regression — a change to a token, a component rule or the home
// markup silently changes how home or a component state looks (colours, focus
// ring, hover, loading indicator) in the light or dark theme, on desktop or phone.
// Related: context/archive/2026-10-20-ui-home-tokens/plan.md, phase 4.
//
// Baselines live in ui-home.spec.ts-snapshots/ and are committed. Update them
// (npx playwright test tests/e2e/ui-home.spec.ts --update-snapshots) only for an
// intended visual change, and say what changed in the commit message.
//
// The tests create no data in e2e.sqlite3: the loading tests abort the start
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

        await page.getByRole('button', { name: /Dog walk/ }).click();
        await aborted;

        await expect(page.getByText('Agent is typing…')).toBeVisible();
        // base.html disables every button once a form is sent.
        await expect(page.getByRole('button', { name: 'Log out' })).toBeDisabled();
        await expect(page).toHaveScreenshot(shot('home-loading'), {
          mask: [signedInAs(page)],
        });
      });

      test('Surprise me shows the waiting state', async ({ page }) => {
        await openHomeWithTopicList(page);
        // Cancelled in the browser like the topic start above: no conversation.
        const aborted = page.waitForEvent('requestfailed', (request) =>
          request.url().endsWith('/conversations/start/random/'),
        );
        await page.route('**/conversations/start/random/', (route) => route.abort('aborted'));

        await page.getByRole('button', { name: 'Surprise me' }).click();
        await aborted;

        await expect(page.getByText('Agent is typing…')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Log out' })).toBeDisabled();
        await expect(page).toHaveScreenshot(shot('home-surprise-loading'), {
          mask: [signedInAs(page)],
        });
      });

      // Not the last category: "Social life" plus the footer is shorter than the
      // screen, so it never reaches the top and would pass without the padding.
      test('jump link shows the category heading below the sticky bar', async ({ page }) => {
        await openHomeWithTopicList(page);
        const nav = page.getByRole('navigation', { name: 'Topic categories' });
        const heading = page.getByRole('heading', { level: 3, name: 'Neighbours & small talk' });

        await nav.getByRole('link', { name: 'Neighbours & small talk' }).click();

        await expect(page).toHaveURL(/#small-talk$/);
        await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
        await expect(heading).toBeInViewport();
        // scroll-padding-top on html keeps the jump target out from under the
        // sticky bar; without it the heading lands at the top, behind the bar.
        const navBox = await nav.boundingBox();
        const headingBox = await heading.boundingBox();
        expect(navBox).not.toBeNull();
        expect(headingBox).not.toBeNull();
        expect(headingBox!.y).toBeGreaterThanOrEqual(navBox!.y + navBox!.height);
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

      test('kitchen sink with the pointer over a topic card', async ({ page }) => {
        await page.goto('/ui/');
        const item = page
          .getByRole('region', { name: 'Topic grid' })
          .getByRole('button', { name: /Supermarket/ });

        await item.hover();

        await expect(page).toHaveScreenshot(shot('ui-hover'));
      });
    });
  }
}
