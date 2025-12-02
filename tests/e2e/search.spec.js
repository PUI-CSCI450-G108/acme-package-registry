import { test, expect } from '@playwright/test';

test.describe('Search Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated state
    await page.goto('/front-end/index.html');
    await page.evaluate(() => {
      localStorage.setItem('authToken', 'bearer fake.token.here');
      localStorage.setItem('apiBaseUrl', 'https://436cwsdtp3.execute-api.us-east-1.amazonaws.com');
    });
  });

  test('should have search functionality available', async ({ page }) => {
    await page.goto('/front-end/index.html');

    // Verify search elements are present
    const searchInput = page.locator('#search-input');
    const searchBtn = page.locator('.search-btn');

    await expect(searchInput).toBeVisible();
    await expect(searchBtn).toBeVisible();

    // Verify search input has correct attributes
    await expect(searchInput).toHaveAttribute('type', 'search');
    await expect(searchInput).toHaveAttribute('placeholder', 'Search by name or ID');

    // Verify search button text
    await expect(searchBtn).toHaveText('Search');
  });

  test('should allow entering search terms', async ({ page }) => {
    await page.goto('/front-end/index.html');

    // Enter a search term
    const searchInput = page.locator('#search-input');
    await searchInput.fill('test-search-term');

    // Verify the value was entered
    await expect(searchInput).toHaveValue('test-search-term');

    // Verify search button is enabled
    const searchBtn = page.locator('.search-btn');
    await expect(searchBtn).toBeEnabled();
  });
});
