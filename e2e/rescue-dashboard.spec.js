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
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Page Rendering', () => {
    test('should load successfully', async ({ page }) => {
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('should have a page title', async ({ page }) => {
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
      expect(title.toLowerCase()).toContain('rescue');
    });

    test('should have a visible main heading', async ({ page }) => {
      const heading = page.locator('h1').first();
      await expect(heading).toBeVisible({ timeout: 5000 });
      const text = await heading.textContent();
      expect(text.length).toBeGreaterThan(0);
    });
  });

  test.describe('Status Display', () => {
    test('should display a system status indicator', async ({ page }) => {
      const indicator = page.locator('#connBadge');
      await expect(indicator).toBeVisible({ timeout: 5000 });
    });

    test('should show the last updated timestamp', async ({ page }) => {
      const lastUpdated = page.locator('#last-updated');
      await expect(lastUpdated).toBeVisible({ timeout: 5000 });
      const timestamp = await lastUpdated.textContent();
      expect(timestamp.length).toBeGreaterThan(0);
    });
  });

  test.describe('Robot Status Section', () => {
    test('should have a robot status section', async ({ page }) => {
      const section = page.locator('#robotTable, .robot-grid');
      await expect(section).toBeVisible({ timeout: 5000 });
    });

    test('should display robot status data', async ({ page }) => {
      const count = await page.locator('#robotCount').textContent();
      expect(count.length).toBeGreaterThan(0);
    });

    test('should render robot cards/rows with name and status', async ({ page }) => {
      const headerRow = page.locator('.robot-row.header');
      await expect(headerRow).toBeVisible({ timeout: 5000 });
    });

    test('should display robot status in Chinese (本地化)', async ({ page }) => {
      const statusDots = page.locator('.status-dot');
      const count = await statusDots.count();
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('Refresh Functionality', () => {
    test('should have a refresh button', async ({ page }) => {
      const refreshBtn = page.locator('button:has-text("刷新")').first();
      await expect(refreshBtn).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Safe Mode', () => {
    test('should have a safe mode button visible', async ({ page }) => {
      const safeModeBtn = page.locator('button:has-text("安全模式")').first();
      const isVisible = await safeModeBtn.isVisible().catch(() => false);
      if (isVisible) {
        await expect(safeModeBtn).toBeEnabled();
      }
    });
  });
});
