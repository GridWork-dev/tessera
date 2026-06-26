import { defineConfig, devices } from '@playwright/test';

/**
 * e2e harness over ALL surfaces (audit / e2e phase):
 *   - `app`  — the real FastAPI backend serving the built SPA over a freshly
 *              seeded throwaway catalog (scripts/e2e_serve.sh). Auth off.
 *   - `site` — the Astro marketing site (built + previewed).
 *
 * Run from frontend/: `npm run e2e` (builds the SPA first, then tests). Both web
 * servers boot automatically; locally an already-running server is reused.
 */
const APP = 'http://127.0.0.1:8788';
const SITE = 'http://127.0.0.1:4322';
const CI = !!process.env.CI;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  workers: CI ? 1 : undefined,
  reporter: CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: { trace: 'on-first-retry', screenshot: 'only-on-failure' },
  webServer: [
    {
      command: 'bash ../scripts/e2e_serve.sh',
      url: `${APP}/api/stats`,
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      command:
        'npm --prefix ../site run build && npm --prefix ../site run preview -- --port 4322 --host 127.0.0.1',
      url: `${SITE}/`,
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: 'app',
      testMatch: /app\..*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: APP },
    },
    {
      name: 'site',
      testMatch: /site\..*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: SITE },
    },
  ],
});
