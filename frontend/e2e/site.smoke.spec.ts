import { expect, test } from '@playwright/test';

// Every marketing page renders (200 + a visible heading), pricing carries the
// one-time price, and unknown paths 404.
const PAGES = [
  '/',
  '/features',
  '/pricing',
  '/download',
  '/docs',
  '/about',
  '/contact',
  '/license',
  '/privacy',
  '/aup',
  '/changelog',
];

for (const path of PAGES) {
  test(`marketing page ${path} renders`, async ({ page }) => {
    const res = await page.goto(path);
    expect(res?.status(), `status for ${path}`).toBeLessThan(400);
    await expect(page.locator('h1, h2').first()).toBeVisible();
  });
}

test('pricing shows the $29 one-time price', async ({ page }) => {
  await page.goto('/pricing');
  await expect(page.getByText('$29')).toBeVisible();
});

test('unknown path returns 404', async ({ page }) => {
  const res = await page.goto('/this-page-does-not-exist-xyz');
  expect(res?.status()).toBe(404);
});
