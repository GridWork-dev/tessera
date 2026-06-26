import { expect, test } from '@playwright/test';

// Settings → License panel (Spec J). Asserts the Free state, the three Pro
// features, the soft upgrade note, and the OFFLINE invalid-token rejection.
test.describe('Settings → License', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('shows free status, pro features, and the $29 upgrade note', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'License' })).toBeVisible();
    await expect(page.getByText('Free', { exact: true })).toBeVisible();

    // exact: the soft upgrade-note sentence also contains these phrases.
    await expect(page.getByText('Bulk export', { exact: true })).toBeVisible();
    await expect(page.getByText('Remote compute routing', { exact: true })).toBeVisible();
    await expect(page.getByText('Priority support', { exact: true })).toBeVisible();

    // Soft, dismissible upgrade note with the one-time price.
    await expect(page.getByText('$29')).toBeVisible();
    await expect(page.getByText(/no content is ever gated/i)).toBeVisible();
  });

  test('rejects an invalid token offline with an inline error', async ({ page }) => {
    await page
      .getByPlaceholder(/Paste your license token/)
      .fill('MPL-PRO-this-is-not-a-real-signed-token');
    await page.getByRole('button', { name: 'Activate' }).click();

    await expect(page.getByText(/couldn.t be verified/i)).toBeVisible();
    // Still Free — a bad token never elevates.
    await expect(page.getByText('Free', { exact: true })).toBeVisible();
  });
});
