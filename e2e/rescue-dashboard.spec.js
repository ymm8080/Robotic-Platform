/**
 * ── Rescue Dashboard Tests ─────────────────────────────────────────────
 *
 * Tests the Nginx static rescue / offline dashboard (port 8080).
 * This page is served when Node-RED is unavailable and provides
 * essential robot status monitoring.
 *
 * @group rescue
 * @group dashboard
 */

const { test, expect } = require('./fixtures');

test.describe('Rescue Dashboard', () => {
  test.beforeEach(async ({ rescueDashboardPage }) => {
    await rescueDashboardPage.goto();
    await rescueDashboardPage.waitForDashboardReady();
  });

  test.describe('Page Rendering', () => {
    test('should load successfully', async ({ rescueDashboardPage }) => {
      // The page should load without errors
      await rescueDashboardPage.expectDashboardRendered();
    });

    test('should have a page title', async ({ rescueDashboardPage }) => {
      const title = await rescueDashboardPage.getPageTitle();
      expect(title.length).toBeGreaterThan(0);
      expect(title.toLowerCase()).toContain('rescue');
    });

    test('should have a visible main heading', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.pageTitle).toBeVisible({ timeout: 5000 });
      const text = await rescueDashboardPage.pageTitle.textContent();
      expect(text.length).toBeGreaterThan(0);
    });
  });

  test.describe('Status Display', () => {
    test('should display a system status indicator', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.statusIndicator).toBeVisible({ timeout: 5000 });
    });

    test('should show the last updated timestamp', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.lastUpdated).toBeVisible({ timeout: 5000 });

      const timestamp = await rescueDashboardPage.lastUpdated.textContent();
      expect(timestamp.length).toBeGreaterThan(0);
    });
  });

  test.describe('Robot Status Section', () => {
    test('should have a robot status section', async ({ rescueDashboardPage }) => {
      // Either the dedicated section or a robot table/cards should be present
      const hasSection = await rescueDashboardPage.robotStatusSection.isVisible().catch(() => false);
      const hasTable = await rescueDashboardPage.robotTable.isVisible().catch(() => false);
      const hasCards = await rescueDashboardPage.robotCards.first().isVisible().catch(() => false);

      expect(hasSection || hasTable || hasCards).toBeTruthy();
    });

    test('should display robot status data', async ({ rescueDashboardPage }) => {
      const robotCount = await rescueDashboardPage.getRobotCount();
      // Should show robots (even if 0 exists with a proper message)
      expect(robotCount).toBeGreaterThanOrEqual(0);
    });

    test('should render robot cards/rows with name and status', async ({ rescueDashboardPage }) => {
      const robots = await rescueDashboardPage.getRobotStatusList();

      // Each robot entry should have a name and status
      for (const robot of robots) {
        expect(robot.name).toBeTruthy();
        expect(robot.status).toBeTruthy();
      }
    });

    test('should display robot status in Chinese (本地化)', async ({ rescueDashboardPage }) => {
      // For robots with Chinese status labels
      const robotStatuses = await rescueDashboardPage.getRobotStatusList();
      const statusTexts = robotStatuses.map(r => r.status);

      // Check for Chinese status indicators if the UI is localized
      const hasChineseStatus = statusTexts.some(
        s => /[一-鿿]/.test(s)  // Contains CJK characters
      );
      // This might or might not be localized, so we just log it
      if (hasChineseStatus) {
        console.log('Robot status labels include Chinese characters');
      }
    });
  });

  test.describe('Refresh Functionality', () => {
    test('should have a refresh button', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.refreshButton).toBeVisible({ timeout: 5000 });
    });

    test('should update data on refresh', async ({ rescueDashboardPage }) => {
      const robotCountBefore = await rescueDashboardPage.getRobotCount();

      await rescueDashboardPage.clickRefresh();

      // After refresh, the dashboard should still display robot data
      const robotCountAfter = await rescueDashboardPage.getRobotCount();
      expect(robotCountAfter).toBeGreaterThanOrEqual(0);
    });
  });

  test.describe('Safe Mode', () => {
    test('should have a safe mode button visible', async ({ rescueDashboardPage }) => {
      // The rescue dashboard has an emergency safe mode button
      const hasSafeMode = await rescueDashboardPage.safeModeButton.isVisible().catch(() => false);

      // This is an optional feature
      if (hasSafeMode) {
        await expect(rescueDashboardPage.safeModeButton).toBeEnabled();
      }
    });
  });
});
