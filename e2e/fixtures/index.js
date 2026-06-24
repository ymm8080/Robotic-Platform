const { test: base, expect } = require('@playwright/test');

/**
 * ── Custom Fixtures for EWM Robot Dispatch Platform ─────────────────────
 *
 * Provides:
 *   - authenticatedPage: auto-auth via Basic Auth header interception
 *   - sapBridgeApi: API request context for SAP Bridge (port 8000)
 */

const NODE_RED_USER = process.env.NODE_RED_ADMIN_USER || 'admin';
const NODE_RED_PASS = process.env.NODE_RED_ADMIN_PASS || 'admin';

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
      const { SapBridgeApi } = require('../pages/SapBridgeApi');
      await use(new SapBridgeApi(request));
    },
    { scope: 'test' },
  ],
});

module.exports = { test, expect };
