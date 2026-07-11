const { test, expect } = require('./fixtures');

test.describe('tmp', () => {
  test('passes', async ({ page }) => {
    await page.goto('about:blank');
    await expect(page).toHaveURL('about:blank');
  });
});
