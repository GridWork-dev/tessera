import { defineConfig, devices } from '@playwright/test';

/**
 * Marketing asset capture — runs against the ALREADY-RUNNING license-clean staging
 * demo on :8010 (real Pexels/geo photos, tiers populated). NOT the gradient e2e
 * server. Retina viewport for crisp screenshots. Capture-only; asserts nothing.
 *
 *   cd frontend && ./node_modules/.bin/playwright test -c playwright.marketing.config.ts
 */
const APP = 'http://127.0.0.1:8010';

export default defineConfig({
  testDir: './e2e',
  testMatch: /marketing\.capture\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 90_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: APP,
    ...devices['Desktop Chrome'],
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
    screenshot: 'off',
  },
});
