const { test: base, expect } = require('@playwright/test');

/**
 * ── Custom Fixtures for EWM Robot Dispatch Platform ─────────────────────
 *
 * Provides:
 *   - authenticatedPage: auto-auth via Basic Auth header interception
 *   - sapBridgeApi: API request context for SAP Bridge (port 8000)
 *   - dashboardPage: Robot Dispatch Dashboard page object
 *   - dashboardLoginPage: Dashboard login page object
 *   - systemHealthPanel: System Health panel page object
 *   - alertPanel: Alert panel page object
 *   - commandPanel: Command panel page object
 *   - rescueDashboardPage: Rescue dashboard page object
 *   - nodeRedLoginPage: Node-RED login page object
 */

const NODE_RED_USER = process.env.NODE_RED_ADMIN_USER || 'admin';
const NODE_RED_PASS = process.env.NODE_RED_ADMIN_PASS || 'admin';

const { DashboardPage } = require('../pages/dashboard.page');
const { DashboardLoginPage } = require('../pages/dashboard-login.page');
const { SystemHealthPanel } = require('../pages/system-health.panel');
const { AlertPanel } = require('../pages/alert.panel');
const { CommandPanel } = require('../pages/command.panel');
const { RescueDashboardPage } = require('../pages/RescueDashboardPage');
const { NodeRedLoginPage } = require('../pages/NodeRedLoginPage');
const { SapBridgeApi } = require('../pages/SapBridgeApi');

const test = base.extend({
  // ── Authenticated page (Node-RED basic auth) ──────────────────────────
  authenticatedPage: [
    async ({ page }, use) => {
      const authHeader = 'Basic ' + Buffer.from(`${NODE_RED_USER}:${NODE_RED_PASS}`).toString('base64');
      await page.route('**/*', (route) => {
        const headers = route.request().headers();
        headers['Authorization'] = authHeader;
        route.continue({ headers });
      });
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await use(page);
    },
    { scope: 'test' },
  ],

  // ── SAP Bridge API (port 8000) ────────────────────────────────────────
  sapBridgeApi: [
    async ({ request }, use) => {
      await use(new SapBridgeApi(request));
    },
    { scope: 'test' },
  ],

  // ── Dashboard page objects ────────────────────────────────────────────
  dashboardPage: [
    async ({ page }, use) => {
      await use(new DashboardPage(page));
    },
    { scope: 'test' },
  ],

  dashboardLoginPage: [
    async ({ page }, use) => {
      await use(new DashboardLoginPage(page));
    },
    { scope: 'test' },
  ],

  systemHealthPanel: [
    async ({ page }, use) => {
      await use(new SystemHealthPanel(page));
    },
    { scope: 'test' },
  ],

  alertPanel: [
    async ({ page }, use) => {
      await use(new AlertPanel(page));
    },
    { scope: 'test' },
  ],

  commandPanel: [
    async ({ page }, use) => {
      await use(new CommandPanel(page));
    },
    { scope: 'test' },
  ],

  rescueDashboardPage: [
    async ({ page }, use) => {
      await use(new RescueDashboardPage(page));
    },
    { scope: 'test' },
  ],

  nodeRedLoginPage: [
    async ({ page }, use) => {
      await use(new NodeRedLoginPage(page));
    },
    { scope: 'test' },
  ],
});

module.exports = { test, expect };
