import { test, expect } from '@playwright/test';

test.describe('Artifact Viewing', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated state
    await page.goto('/front-end/index.html');
    await page.evaluate(() => {
      localStorage.setItem('authToken', 'bearer fake.token.here');
      localStorage.setItem('apiBaseUrl', 'https://436cwsdtp3.execute-api.us-east-1.amazonaws.com');
    });
  });

  test('should display artifact list', async ({ page }) => {
    await page.goto('/front-end/index.html');

    // Wait for the page to load and show either artifacts or empty state
    await page.waitForTimeout(2000); // Give time for API call

    // Check if artifacts grid is present
    const artifactsGrid = page.locator('#artifacts-grid');
    await expect(artifactsGrid).toBeVisible();

    // Check for either artifact cards or empty state
    const loadingState = page.locator('#loading');
    const errorState = page.locator('#error-state');
    const emptyState = page.locator('#empty-state');
    const artifactCards = page.locator('.artifact-card');

    // Verify we're not stuck in loading state
    await expect(loadingState).toBeHidden();

    // Should either have cards or show empty state (not error state ideally)
    const cardCount = await artifactCards.count();
    const emptyVisible = await emptyState.isVisible();

    // Either we have artifacts or we see empty state (both are valid)
    expect(cardCount > 0 || emptyVisible).toBeTruthy();
  });

  test('should open and close artifact detail modal', async ({ page }) => {
    await page.goto('/front-end/index.html');

    // Wait for artifacts to load
    await expect(page.locator('#loading')).toBeHidden();

    // Check if we have any artifact cards
    const artifactCards = page.locator('.artifact-card');
    const cardCount = await artifactCards.count();

    if (cardCount > 0) {
      // Click the first artifact card
      await artifactCards.first().click();

      // Wait for modal to appear
      const detailModal = page.locator('#detail-modal');
      await expect(detailModal).toBeVisible({ timeout: 3000 });

      // Verify modal has content
      const modalContent = page.locator('#detail-modal .modal-content');
      await expect(modalContent).toBeVisible();

      // Close the modal by clicking the close button
      const closeBtn = page.locator('#detail-modal .close-btn');
      await closeBtn.click();

      // Verify modal is closed
      await expect(detailModal).toBeHidden();
    } else {
      // If no artifacts, this test is not applicable
      test.skip();
    }
  });
});
