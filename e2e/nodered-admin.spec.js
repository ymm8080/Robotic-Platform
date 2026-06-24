/**
 * ── Node-RED Admin Dashboard Tests ──────────────────────────────────────
 *
 * Tests the Node-RED admin editor UI via authenticatedPage (Basic Auth).
 *
 * @group nodered
 * @group dashboard
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Admin Dashboard', () => {
  test.describe('Dashboard Layout', () => {
    test('should load the editor when authenticated', async ({ authenticatedPage }) => {
      const url = authenticatedPage.url();
      expect(url).not.toContain('login');
    });

    test('should have a visible header with title', async ({ authenticatedPage }) => {
      const title = await authenticatedPage.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('should have the deploy button visible', async ({ authenticatedPage }) => {
      const deployBtn = authenticatedPage.locator('#red-ui-header .deploy-button, [class*="deploy"], button:has-text("Deploy")').first();
      await expect(deployBtn).toBeVisible({ timeout: 5000 });
    });
  });
});
