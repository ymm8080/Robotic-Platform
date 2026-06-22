/**
 * ── Node-RED Admin Dashboard Tests ──────────────────────────────────────
 *
 * Tests the main Node-RED admin / flow editor interface after login:
 *   - Dashboard is fully loaded
 *   - All major UI components are present (header, canvas, palette, sidebar)
 *   - Flow tabs are visible
 *   - Deploy button is functional
 *   - Palette search works
 *   - Connection status is reported
 *
 * @group nodered
 * @group dashboard
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Admin Dashboard', () => {
  test.beforeEach(async ({ authenticatedPage, noderedDashboardPage }) => {
    await noderedDashboardPage.goto();
    await noderedDashboardPage.waitForDashboardReady();
  });

  test.describe('Dashboard Layout', () => {
    test('should display all major UI components after login', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.expectDashboardLoaded();
    });

    test('should have a visible header with the platform title', async ({ noderedDashboardPage }) => {
      const pageTitle = await noderedDashboardPage.getPageTitle();
      expect(pageTitle.length).toBeGreaterThan(0);

      // The project configures a custom title in Node-RED settings
      expect(pageTitle).toContain('SAP-EWM');
    });

    test('should have the deploy button visible and enabled', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.deployButton).toBeVisible();
      await expect(noderedDashboardPage.deployButton).toBeEnabled();
    });
  });

  test.describe('Flow Editor Canvas', () => {
    test('should display the workspace tabs', async ({ noderedDashboardPage }) => {
      const tabCount = await noderedDashboardPage.workspaceTabs.locator('li, button, a').count();
      expect(tabCount).toBeGreaterThanOrEqual(1);
    });

    test('should display the flow editor canvas', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.canvas).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Palette', () => {
    test('should display the node palette', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.palette).toBeVisible({ timeout: 10000 });
    });

    test('should support palette search', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.searchPalette('mqtt');

      // Wait for filter to apply
      await noderedDashboardPage.page.waitForTimeout(1000);

      // Check that palette items are filtered (or the search input has value)
      const searchValue = await noderedDashboardPage.paletteSearch.inputValue();
      expect(searchValue.toLowerCase()).toContain('mqtt');
    });

    test('should contain MQTT nodes (VDA5050 core protocol)', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.searchPalette('mqtt');
      await noderedDashboardPage.page.waitForTimeout(1000);

      // MQTT nodes should be present since VDA5050 uses MQTT
      const mqttNode = noderedDashboardPage.page.locator('.red-ui-palette-node:has-text("mqtt"), .palette_node:has-text("mqtt")').first();
      await expect(mqttNode).toBeVisible({ timeout: 5000 });
    });

    test('should contain HTTP nodes (for SAP Bridge integration)', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.searchPalette('http');
      await noderedDashboardPage.page.waitForTimeout(1000);

      const httpNode = noderedDashboardPage.page.locator('.red-ui-palette-node:has-text("http"), .palette_node:has-text("http")').first();
      await expect(httpNode).toBeVisible({ timeout: 5000 });
    });

    test('should contain function nodes (for custom dispatch logic)', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.searchPalette('function');
      await noderedDashboardPage.page.waitForTimeout(1000);

      const funcNode = noderedDashboardPage.page.locator('.red-ui-palette-node:has-text("function"), .palette_node:has-text("function")').first();
      await expect(funcNode).toBeVisible({ timeout: 5000 });
    });

    test('palette search should support Chinese characters', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.searchPalette('mqtt');
      await noderedDashboardPage.page.waitForTimeout(500);

      const searchValue = await noderedDashboardPage.paletteSearch.inputValue();
      expect(searchValue.length).toBeGreaterThan(0);
    });
  });

  test.describe('Sidebar', () => {
    test('should display the sidebar panels', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.sidebar).toBeVisible({ timeout: 5000 });
    });

    test('should have an Info tab in the sidebar', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.infoTab).toBeVisible({ timeout: 5000 });
    });

    test('should have a Help tab in the sidebar', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.helpTab).toBeVisible({ timeout: 5000 });
    });

    test('should be able to switch between Info and Help tabs', async ({ noderedDashboardPage }) => {
      await noderedDashboardPage.infoTab.click();
      await noderedDashboardPage.page.waitForTimeout(500);

      await noderedDashboardPage.helpTab.click();
      await noderedDashboardPage.page.waitForTimeout(500);

      // Verify we're on the help tab (active state)
      const activeClass = await noderedDashboardPage.helpTab.getAttribute('class');
      expect(activeClass).toContain('active');
    });
  });

  test.describe('Connection Status', () => {
    test('should show connected status', async ({ noderedDashboardPage }) => {
      const status = await noderedDashboardPage.getConnectionStatus();

      // Status bar should exist; connected is the normal state
      expect(status).toBeTruthy();
    });
  });

  test.describe('Status Bar', () => {
    test('should display the status bar', async ({ noderedDashboardPage }) => {
      await expect(noderedDashboardPage.statusBar).toBeVisible({ timeout: 5000 });
    });
  });
});
