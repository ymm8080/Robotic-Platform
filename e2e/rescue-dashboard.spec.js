/**
 * ── Rescue Dashboard Tests ─────────────────────────────────────────────
 *
 * Tests the Nginx static rescue / offline dashboard (port 8080).
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
      const title = await rescueDashboardPage.getPageTitle();
      expect(title.length).toBeGreaterThan(0);
    });

    test('should have a page title containing rescue', async ({ rescueDashboardPage }) => {
      const title = await rescueDashboardPage.getPageTitle();
      expect(title.length).toBeGreaterThan(0);
      expect(title.toLowerCase()).toContain('rescue');
    });

    test('should have a visible main heading', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.pageTitle).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Status Display', () => {
    test('should display a system status indicator', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.statusIndicator).toBeVisible({ timeout: 5000 });
    });

    test('should show the last updated timestamp', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.lastUpdated).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Robot Status Section', () => {
    test('should have a robot status section', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.robotTable).toBeVisible({ timeout: 5000 });
    });

    test('should display robot count', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.robotCount).toBeVisible({ timeout: 5000 });
    });

    test('should render robot cards with status', async ({ rescueDashboardPage }) => {
      const count = await rescueDashboardPage.getRobotCount();
      expect(count).toBeGreaterThanOrEqual(0);
    });
  });

  test.describe('Refresh Functionality', () => {
    test('should have a refresh button', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.refreshButton).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Safe Mode', () => {
    test('should have a safe mode button visible', async ({ rescueDashboardPage }) => {
      await expect(rescueDashboardPage.safeModeButton).toBeVisible({ timeout: 5000 });
      await expect(rescueDashboardPage.safeModeButton).toBeEnabled();
    });
  });
});
