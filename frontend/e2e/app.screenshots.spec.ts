import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from '@playwright/test';

const HERE = path.dirname(fileURLToPath(import.meta.url));

// Capture full-page screenshots of every app surface for the visual design audit
// (Phase 5). Runs against the seeded throwaway catalog with license-clean
// placeholder media, so grids/tiles/posters render real pixels. Output lands in
// frontend/screenshots/app/ (gitignored). These tests only CAPTURE — they assert
// nothing, so they never gate CI; the smoke specs do the asserting.
const OUT = path.resolve(HERE, '..', 'screenshots', 'app');

const SURFACES: Array<[string, string]> = [
  ['home', '/'],
  ['videos', '/videos'],
  ['people', '/people'],
  ['places', '/places'],
  ['events', '/events'],
  ['dashboard', '/dashboard'],
  ['learn', '/learn'],
  ['settings', '/settings'],
  ['training', '/training'],
];

for (const [name, route] of SURFACES) {
  test(`shot:${name}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForTimeout(1500); // settle thumbnails (avoids networkidle hang on polled surfaces)
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  });
}

test('shot:lightbox', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const grid = page.getByRole('listbox', { name: 'Asset grid' });
  await grid.getByRole('option').first().click();
  await page.waitForTimeout(600); // let the inspector/lightbox settle
  await page.screenshot({ path: path.join(OUT, 'lightbox.png') });
});

// A couple of mobile-viewport captures so the audit can judge responsive layout.
const MOBILE = { width: 390, height: 844 };
for (const [name, route] of [
  ['home', '/'],
  ['dashboard', '/dashboard'],
  ['settings', '/settings'],
] as Array<[string, string]>) {
  test(`shot:mobile-${name}`, async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto(route);
    await page.waitForTimeout(1500); // settle thumbnails (avoids networkidle hang on polled surfaces)
    await page.screenshot({ path: path.join(OUT, `mobile-${name}.png`), fullPage: true });
  });
}
