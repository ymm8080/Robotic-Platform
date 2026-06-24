const { expect } = require('@playwright/test');

/**
 * Page Object Model for the Nginx rescue dashboard
 * (served at http://localhost:8080 as a static offline fallback).
 *
 * @see nginx/rescue-dashboard-offline.html
 */
class RescueDashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    // ── Page structure ────────────────────────────────────────────────
    this.pageTitle = page.locator('h1, .dashboard-title, header h1');
    this.statusIndicator = page.locator('#status, #connBadge, .status-badge, .health-indicator');
    this.robotStatusSection = page.locator('#robot-status, #robotTable, .robot-status-panel, [data-testid="robot-status"]');
    this.systemHealthSection = page.locator('#system-health, .system-health-panel, [data-testid="system-health"]');
    this.lastUpdated = page.locator('#last-updated, .last-updated, [data-testid="last-updated"]');

    // ── Robot cards / table rows ──────────────────────────────────────
    this.robotCards = page.locator('.robot-card, .robot-item, [data-testid="robot-card"]');
    this.robotTable = page.locator('table.robots, .robot-table, [data-testid="robot-table"]');
    this.robotTableRows = page.locator('table.robots tbody tr, .robot-table tbody tr');

    // ── Action buttons ────────────────────────────────────────────────
    this.refreshButton = page.locator('button:has-text("Refresh"), a:has-text("Refresh"), button:has-text("刷新")');
    this.safeModeButton = page.locator('button:has-text("Safe Mode"), button:has-text("安全模式")');
  }

  /**
   * Navigate to the rescue dashboard.
   */
  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for the dashboard content to be fully loaded.
   */
  async waitForDashboardReady() {
    await expect(this.pageTitle).toBeVisible({ timeout: 20000 });
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Get the main status text.
   */
  async getStatus() {
    if (await this.statusIndicator.isVisible()) {
      return (await this.statusIndicator.textContent()).trim().toLowerCase();
    }
    return 'unknown';
  }

  /**
   * Count the number of robot cards or table rows visible.
   */
  async getRobotCount() {
    // Try cards first, then table rows
    const cardCount = await this.robotCards.count();
    if (cardCount > 0) return cardCount;

    const rowCount = await this.robotTableRows.count();
    return rowCount;
  }

  /**
   * Get the text of all visible robot status items.
   * @returns {Promise<Array<{name: string, status: string}>>}
   */
  async getRobotStatusList() {
    const robots = [];

    // Try card layout first
    const cardCount = await this.robotCards.count();
    if (cardCount > 0) {
      for (let i = 0; i < cardCount; i++) {
        const card = this.robotCards.nth(i);
        robots.push({
          name: await card.locator('.robot-name, [data-testid="robot-name"]').textContent() || `robot-${i}`,
          status: await card.locator('.robot-status, [data-testid="robot-status"]').textContent() || 'unknown',
        });
      }
      return robots;
    }

    // Fall back to table layout
    const rowCount = await this.robotTableRows.count();
    for (let i = 0; i < rowCount; i++) {
      const row = this.robotTableRows.nth(i);
      const cells = row.locator('td');
      robots.push({
        name: await cells.nth(0).textContent() || `robot-${i}`,
        status: await cells.nth(1).textContent() || 'unknown',
      });
    }
    return robots;
  }

  /**
   * Click the refresh button and wait for updated data.
   */
  async clickRefresh() {
    if (await this.refreshButton.isVisible()) {
      await this.refreshButton.click();
      await this.page.waitForTimeout(2000); // allow data to refresh
      await this.page.waitForLoadState('networkidle');
    }
  }

  /**
   * Assert that the rescue dashboard renders correctly.
   */
  async expectDashboardRendered() {
    await expect(this.pageTitle).toBeVisible({ timeout: 10000 });
    // At least one of the main sections should be present
    const hasStatus = await this.statusIndicator.isVisible().catch(() => false);
    const hasRobotSection = await this.robotStatusSection.isVisible().catch(() => false);
    const hasTable = await this.robotTable.isVisible().catch(() => false);
    expect(hasStatus || hasRobotSection || hasTable).toBeTruthy();
  }

  /**
   * Get the page title text.
   */
  async getPageTitle() {
    return this.page.title();
  }
}

module.exports = { RescueDashboardPage };
