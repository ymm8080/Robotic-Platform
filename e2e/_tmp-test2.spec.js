const { test, expect } = require('@playwright/test');

test.describe('tmp2', () => {
  test('passes', async ({ page }) => {
    await page.goto('about:blank');
    await expect(page).toHaveURL('about:blank');
  });
});
