const { expect } = require('@playwright/test');

/**
 * Page Object Model for the Node-RED admin dashboard / flow editor.
 *
 * After successful login the user lands in the flow editor at /admin/.
 * This POM covers the main editor chrome: sidebar, header, palette, and
 * the robot-dispatch‑specific tabs installed by the project.
 */
class NodeRedDashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    // ── Header / Toolbar ──────────────────────────────────────────────
    this.header = page.locator('#header, .red-ui-header');
    this.deployButton = page.locator('#btn-deploy, button:has-text("Deploy"), button:has-text("部署")');
    this.mainMenuButton = page.locator('#btn-menu, .red-ui-header-button[title*="Menu"]');

    // ── Sidebar ───────────────────────────────────────────────────────
    this.sidebar = page.locator('#sidebar, .red-ui-sidebar');
    this.infoTab = page.locator('#tab-info, .red-ui-tab:has-text("Info"), button:has-text("信息")');
    this.helpTab = page.locator('#tab-help, .red-ui-tab:has-text("Help"), button:has-text("帮助")');

    // ── Flow editor canvas ────────────────────────────────────────────
    this.canvas = page.locator('#canvas, .red-ui-workspace-canvas, svg[data-theme]');
    this.workspaceTabs = page.locator('.red-ui-workspace-chart-tabs, .red-ui-tabs');

    // ── Palette (node types) ──────────────────────────────────────────
    this.palette = page.locator('#palette, .red-ui-palette');
    this.paletteSearch = page.locator('#palette-search, input[placeholder*="search" i], input[placeholder*="搜索" i]');

    // ── Robot dispatch tabs (project-specific) ────────────────────────
    this.orderManagementTab = page.locator('li:has-text("Order"), a:has-text("Order"), span:has-text("订单")');
    this.robotStatusTab = page.locator('li:has-text("Robot"), a:has-text("Robot"), span:has-text("机器人")');
    this.systemHealthTab = page.locator('li:has-text("Health"), a:has-text("Health"), span:has-text("健康")');

    // ── Status bar ────────────────────────────────────────────────────
    this.statusBar = page.locator('#status-bar, .red-ui-status-bar');
    this.connectionStatus = page.locator('.red-ui-status-bar-right');
  }

  /**
   * Navigate to the Node-RED admin dashboard.
   */
  async goto() {
    await this.page.goto('/admin/');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for the dashboard to be fully loaded and interactive.
   */
  async waitForDashboardReady() {
    await expect(this.header).toBeVisible({ timeout: 20000 });
    await expect(this.canvas).toBeVisible({ timeout: 10000 });
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Check the Node-RED connection status indicator.
   * Returns the text content of the connection status element.
   */
  async getConnectionStatus() {
    if (await this.connectionStatus.isVisible()) {
      return (await this.connectionStatus.textContent()).trim().toLowerCase();
    }
    return null;
  }

  /**
   * Assert that the dashboard has fully loaded with all major UI elements.
   */
  async expectDashboardLoaded() {
    await expect(this.header).toBeVisible({ timeout: 20000 });
    await expect(this.canvas).toBeVisible({ timeout: 10000 });
    await expect(this.deployButton).toBeVisible({ timeout: 5000 });
    await expect(this.sidebar).toBeVisible({ timeout: 5000 });
    await expect(this.palette).toBeVisible({ timeout: 5000 });
    await expect(this.statusBar).toBeVisible({ timeout: 5000 });
  }

  /**
   * Deploy the current flow (click Deploy button and confirm).
   */
  async deployFlow() {
    await this.deployButton.click();
    // Wait for deployment to complete — look for success indicator
    await this.page.waitForTimeout(2000); // allow deploy dialog to open
    const confirmBtn = this.page.locator('button:has-text("Deploy"), button:has-text("Confirm"), button:has-text("确认")');
    if (await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await confirmBtn.click();
    }
    // Wait for the deploy to complete
    await this.page.waitForSelector('.red-ui-notification--success', { timeout: 30000 }).catch(() => {
      // Deployment may succeed without notification; continue
    });
  }

  /**
   * Search for a node type in the palette.
   * @param {string} nodeType - e.g. "mqtt", "http", "function"
   */
  async searchPalette(nodeType) {
    await this.paletteSearch.waitFor({ state: 'visible', timeout: 5000 });
    await this.paletteSearch.fill('');
    await this.paletteSearch.fill(nodeType);
  }

  /**
   * Open a specific workspace tab / flow tab by its label.
   * @param {string} tabLabel - The label of the tab (e.g. "Flow 1", "Main")
   */
  async openFlowTab(tabLabel) {
    const tab = this.workspaceTabs.locator(`text="${tabLabel}"`);
    await tab.click();
    await this.page.waitForTimeout(500);
  }

  /**
   * Log out of Node-RED admin via the main menu.
   */
  async logout() {
    await this.mainMenuButton.click();
    const logoutItem = this.page.locator('a:has-text("Logout"), a:has-text("Sign Out"), a:has-text("退出")');
    await logoutItem.click();
    await this.page.waitForURL(/\/admin\/auth\/login\//, { timeout: 10000 });
  }

  /**
   * Get the page title text.
   */
  async getPageTitle() {
    return this.page.title();
  }
}

module.exports = { NodeRedDashboardPage };
