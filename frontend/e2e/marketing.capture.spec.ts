import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type Page, test } from '@playwright/test';

// Fresh marketing capture against the real-photo staging demo (:8010). Output
// lands in frontend/screenshots/marketing/ (gitignored). Capture-only — asserts
// nothing, so a missing interaction degrades one shot rather than failing a gate.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, '..', 'screenshots', 'marketing');

const settle = (page: Page, ms = 1800) => page.waitForTimeout(ms);

async function tryClick(makers: Array<() => ReturnType<Page['getByRole']>>) {
  for (const make of makers) {
    try {
      const el = make().first();
      if (await el.isVisible()) {
        await el.click();
        return true;
      }
    } catch {
      /* best-effort */
    }
  }
  return false;
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
  await settle(page, 1200);
  await tryClick([
    () => page.getByRole('button', { name: 'Semantic' }),
    () => page.getByText('Semantic', { exact: true }),
  ]);
  await settle(page, 300);
  try {
    const box = page.getByPlaceholder(/Search/i).first();
    await box.click({ timeout: 5000 });
    await box.pressSequentially('woman on a beach at sunset', { delay: 40 });
    await settle(page, 600);
    await page.screenshot({ path: path.join(OUT, 'hero-typed.png') }).catch(() => {});
    await box.press('Enter').catch(() => {});
    await page.waitForTimeout(2500);
  } catch {
    /* best-effort */
  }
  await page.screenshot({ path: path.join(OUT, 'search-results.png') }).catch(() => {});
  await page.screenshot({ path: path.join(OUT, 'hero-results.png') }).catch(() => {});
});

test('inspector-and-similar', async ({ page }) => {
  await page.goto('/');
  await settle(page, 1500);
  try {
    const grid = page.getByRole('listbox', { name: 'Asset grid' });
    await grid.getByRole('option').nth(2).click();
    await settle(page, 1100);
    await page.screenshot({ path: path.join(OUT, 'inspector.png') });
    await tryClick([
      () => page.getByRole('button', { name: /similar/i }),
      () => page.getByText(/find similar/i),
    ]);
    await settle(page, 2000);
    await page.screenshot({ path: path.join(OUT, 'find-similar.png') });
    await page.screenshot({ path: path.join(OUT, 'hero-similar.png') });
  } catch {
    /* best-effort */
  }
});

for (const [name, route] of [
  ['places', '/places'],
  ['events', '/events'],
  ['videos', '/videos'],
  ['dashboard', '/dashboard'],
] as Array<[string, string]>) {
  test(`page-${name}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState('networkidle').catch(() => {});
    await settle(page, 1900);
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: name === 'dashboard' });
  });
}
