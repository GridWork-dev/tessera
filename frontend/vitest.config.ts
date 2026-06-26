import { defineConfig } from 'vitest/config';

// Pure-logic unit tests only (registry / store / label-color helpers). No app
// plugins (router/babel/vanilla-extract) — those are for the SPA build, not unit
// logic, and loading them under vitest is slow + brittle. jsdom is unnecessary
// for the pure functions under test; node env keeps it fast.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globals: false,
  },
});
