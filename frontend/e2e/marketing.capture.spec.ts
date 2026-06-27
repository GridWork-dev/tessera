import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type Page, test } from '@playwright/test';

// Fresh marketing capture against the real-photo staging demo (:8010). Output
// lands in frontend/screenshots/marketing/ (gitignored). Capture-only — asserts
// nothing, so a missing interaction degrades one shot rather than failing a gate.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, '..', 'screenshots', 'marketing');

const settle = (page: Page, ms = 1800) => page.waitForTimeout(ms);

// Switch to Semantic mode and type a natural-language query. The mode button is
// labelled "Semantic"; the input placeholder then becomes "Describe what you
// want…". Search is reactive (debounced) — no Enter needed.
async function semanticSearch(page: Page, query: string) {
  await page
    .getByRole('button', { name: 'Semantic' })
    .click()
    .catch(() => {});
  await settle(page, 400);
  const box = page.getByPlaceholder(/Describe|Search/i).first();
  await box.click({ timeout: 5000 }).catch(() => {});
  await box.pressSequentially(query, { delay: 42 }).catch(() => {});
  await settle(page, 3200);
}

test('browse', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await settle(page);
  await page.screenshot({ path: path.join(OUT, 'browse.png') });
  await page.screenshot({ path: path.join(OUT, 'hero-grid.png') });
});

test('semantic-search', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await settle(page, 1200);
  await semanticSearch(page, 'city skyline at dusk');
  await page.screenshot({ path: path.join(OUT, 'search-results.png') });
  await page.screenshot({ path: path.join(OUT, 'hero-results.png') });
});

test('inspector-and-similar', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await settle(page, 1000);
  // Search first so the grid is cities (not the portrait set), then open the
  // top result — the inspector shows caption, tags, place, and metadata.
  await semanticSearch(page, 'city skyline at dusk');
  try {
    const grid = page.getByRole('listbox', { name: 'Asset grid' });
    await grid.getByRole('option').nth(0).click();
    await settle(page, 1600);
    await page.screenshot({ path: path.join(OUT, 'inspector.png') });
  } catch {
    /* best-effort */
  }
});

for (const [name, route] of [
  ['people', '/people'],
  ['places', '/places'],
  ['events', '/events'],
  ['videos', '/videos'],
  ['training', '/training'],
  ['dashboard', '/dashboard'],
] as Array<[string, string]>) {
  test(`page-${name}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState('networkidle').catch(() => {});
    await settle(page, 1900);
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: name === 'dashboard' });
  });
}
