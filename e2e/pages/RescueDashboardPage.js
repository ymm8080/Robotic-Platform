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

    this.pageTitle = page.getByRole('heading', { name: /急救控制台|Rescue/i });
    this.statusIndicator = page.getByTestId('status');
    this.robotTable = page.getByRole('heading', { name: /机器人状态|Robot Status/i });
    this.robotCards = page.getByTestId('robot-card');
    this.lastUpdated = page.getByText(/\d{1,2}:\d{2}:\d{2}/);
    this.refreshButton = page.getByRole('button', { name: /刷新|Refresh/i });
    this.safeModeButton = page.getByRole('button', { name: /安全模式|Safe Mode/i });
    this.eStopButton = page.getByRole('button', { name: /紧急停止|E-Stop/i });
    this.robotCount = page.getByText(/\d+\s*台机器人/);
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  async waitForDashboardReady() {
    await expect(this.pageTitle).toBeVisible({ timeout: 20000 });
    await this.page.waitForLoadState('networkidle');
  }

  async getStatus() {
    if (await this.statusIndicator.isVisible()) {
      return (await this.statusIndicator.textContent()).trim();
    }
    return 'unknown';
  }

  async getRobotCount() {
    const count = await this.robotCards.count();
    return count;
  }

  async getPageTitle() {
    return this.page.title();
  }

  async clickRefresh() {
    await this.refreshButton.click();
    await this.page.waitForLoadState('networkidle');
  }

  async expectDashboardRendered() {
    await expect(this.pageTitle).toBeVisible({ timeout: 10000 });
    const hasStatus = await this.statusIndicator.isVisible().catch(() => false);
    const hasRobotSection = await this.robotTable.isVisible().catch(() => false);
    expect(hasStatus || hasRobotSection).toBeTruthy();
  }
}

module.exports = { RescueDashboardPage };
