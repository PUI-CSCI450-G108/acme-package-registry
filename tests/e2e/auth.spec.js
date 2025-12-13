import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage before each test
    await page.goto('/front-end/login.html');
    await page.evaluate(() => localStorage.clear());
  });

  test('should show login form with required fields', async ({ page }) => {
    await page.goto('/front-end/login.html');

    // Verify login form is present
    await expect(page.locator('#login-form')).toBeVisible();

    // Verify all required fields are present
    await expect(page.locator('#api-url-input')).toBeVisible();
    await expect(page.locator('#username-input')).toBeVisible();
    await expect(page.locator('#password-input')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();

    // Verify login button text
    await expect(page.locator('button[type="submit"]')).toHaveText('Login');
  });

  test('should logout and redirect to login page', async ({ page, context }) => {
    // First, set up an authenticated state
    await page.goto('/front-end/login.html');
    await page.evaluate(() => {
      // Set fake auth token to simulate logged-in state
      localStorage.setItem('authToken', 'bearer fake.token.here');
      localStorage.setItem('apiBaseUrl', 'https://436cwsdtp3.execute-api.us-east-1.amazonaws.com');
    });

    // Navigate to index page
    await page.goto('/front-end/index.html');

    // Click logout button
    await page.click('.logout-btn');

    // Should redirect to login page
    await page.waitForURL('**/login.html', { timeout: 5000 });
    await expect(page).toHaveURL(/login\.html/);

    // Verify auth token was cleared
    const authToken = await page.evaluate(() => localStorage.getItem('authToken'));
    expect(authToken).toBeNull();
  });
});
