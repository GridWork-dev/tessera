import { expect, test } from '@playwright/test';

// In-app surfaces that carry the shared command-bar nav. Each must mount the SPA
// and throw no uncaught JS error. Deep links work via the backend SPA fallback.
// (/training is an immersive keyboard surface with no shared nav — tested below.)
const ROUTES = [
  '/',
  '/videos',
  '/people',
  '/places',
  '/events',
  '/dashboard',
  '/learn',
  '/settings',
];

for (const path of ROUTES) {
  test(`surface ${path} renders with shared nav and no JS errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(String(e)));

    await page.goto(path);

    // Shared command-bar nav => SPA mounted and the route didn't crash.
    await expect(page.getByRole('link', { name: 'Grid' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
    expect(errors, `uncaught page errors on ${path}`).toEqual([]);
  });
}

test('home grid renders seeded assets', async ({ page }) => {
  await page.goto('/');
  // 12 seeded images surface as an accessible asset grid. (Thumbnails 404 with
  // no media files, so the <img> tiles have zero size — assert the semantic grid
  // the data populated, not the broken images.)
  const grid = page.getByRole('listbox', { name: 'Asset grid' });
  await expect(grid).toBeVisible();
  await expect(grid.getByRole('option').first()).toBeVisible();
});

test('training is an immersive surface that mounts cleanly', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto('/training');
  // No shared nav here by design — assert the training toolbar mounted instead.
  await expect(page.getByRole('group', { name: 'Queue source' })).toBeVisible();
  expect(errors, 'uncaught page errors on /training').toEqual([]);
});

test('primary nav moves between surfaces', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Videos' }).click();
  await expect(page).toHaveURL(/\/videos$/);
  await page.getByRole('link', { name: 'Dashboard' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page).toHaveURL(/\/settings$/);
});
