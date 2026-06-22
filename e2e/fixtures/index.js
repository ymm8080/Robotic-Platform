const { test: base, expect } = require('@playwright/test');

/**
 * ── Custom Fixtures for EWM Robot Dispatch Platform ──────────────────────
 *
 * Extends the base Playwright test object with fixtures specific to
 * the SAP-EWM Robot integration, including:
 *   - authenticatedPage  – a page that has logged into Node-RED admin
 *   - noderedLoginPage   – the login page POM
 *   - noderedDashboardPage – the dashboard POM
 *   - rescueDashboardPage – the rescue dashboard POM
 *   - sapBridgeApi       – API request context for the SAP Bridge service
 *
 * Usage:
 *   const { test } = require('../fixtures');
 *   test('my test', async ({ authenticatedPage }) => { ... });
 */

// ─── Credentials ───────────────────────────────────────────────────────
const NODE_RED_USER = process.env.NODE_RED_ADMIN_USER || 'admin';
const NODE_RED_PASS = process.env.NODE_RED_ADMIN_PASS || 'admin';

// ─── Fixture: authenticated Node-RED admin page ───────────────────────
const test = base.extend({
  /**
   * A page that has already completed Node-RED admin login.
   * Login is performed once per worker and cached via the worker-scoped
   * storageState fixture.
   */
  authenticatedPage: [
    async ({ page, context }, use) => {
      const { NodeRedLoginPage } = require('../pages/NodeRedLoginPage');
      const loginPage = new NodeRedLoginPage(page);

      await loginPage.goto();

      // Only login if we're still on the login page (not already authed)
      if (await loginPage.isLoginFormVisible()) {
        await loginPage.login(NODE_RED_USER, NODE_RED_PASS);
      }

      await use(page);
    },
    { scope: 'test' },
  ],

  /**
   * The Node-RED login page POM.
   */
  noderedLoginPage: [
    async ({ page }, use) => {
      const { NodeRedLoginPage } = require('../pages/NodeRedLoginPage');
      await use(new NodeRedLoginPage(page));
    },
    { scope: 'test' },
  ],

  /**
   * The Node-RED dashboard page POM.
   */
  noderedDashboardPage: [
    async ({ page }, use) => {
      const { NodeRedDashboardPage } = require('../pages/NodeRedDashboardPage');
      await use(new NodeRedDashboardPage(page));
    },
    { scope: 'test' },
  ],

  /**
   * The rescue dashboard page POM (Nginx static page on port 8080).
   */
  rescueDashboardPage: [
    async ({ page }, use) => {
      const { RescueDashboardPage } = require('../pages/RescueDashboardPage');
      await use(new RescueDashboardPage(page));
    },
    { scope: 'test' },
  ],

  /**
   * API request context for the SAP Bridge service.
   * Uses the API base URL from config or env var.
   */
  sapBridgeApi: [
    async ({ request }, use) => {
      const { SapBridgeApi } = require('../pages/SapBridgeApi');
      await use(new SapBridgeApi(request));
    },
    { scope: 'test' },
  ],
});

module.exports = { test, expect };
