import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from '@playwright/test';

// Full-page captures of every marketing page for the visual audit (Phase 5).
// Output: frontend/screenshots/site/ (gitignored). Capture-only, asserts nothing.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, '..', 'screenshots', 'site');

const PAGES: Array<[string, string]> = [
  ['home', '/'],
  ['features', '/features'],
  ['pricing', '/pricing'],
  ['download', '/download'],
  ['docs', '/docs'],
  ['about', '/about'],
  ['contact', '/contact'],
  ['license', '/license'],
  ['privacy', '/privacy'],
  ['aup', '/aup'],
  ['changelog', '/changelog'],
];

for (const [name, route] of PAGES) {
  test(`shot:site-${name}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  });
}
