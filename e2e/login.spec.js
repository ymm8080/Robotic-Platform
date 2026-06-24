/**
 * ── Node-RED Admin Login Tests ──────────────────────────────────────────
 *
 * Tests Node-RED admin auth via route-intercepted Basic Auth header.
 *
 * @group nodered
 * @group auth
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Admin Login', () => {
  test.describe('Page Rendering', () => {
    test('should load the editor when authenticated', async ({ authenticatedPage }) => {
      // authenticatedPage auto-routes all requests with Basic Auth
      // If the page loaded without redirecting to login, auth works
      const url = authenticatedPage.url();
      expect(url).not.toContain('login');
    });

    test('should have a page title', async ({ authenticatedPage }) => {
      const title = await authenticatedPage.title();
      expect(title.length).toBeGreaterThan(0);
    });
  });

  test.describe('Auth API — Negative Tests', () => {
    test('should reject wrong password via API', async ({ request }) => {
      const resp = await request.post('http://localhost:1880/auth/token', {
        data: { client_id: 'node-red-admin', grant_type: 'password', scope: '*', username: 'admin', password: 'wrongpassword' }
      });
      expect(resp.ok()).toBeFalsy();
    });

    test('should reject empty credentials via API', async ({ request }) => {
      const resp = await request.post('http://localhost:1880/auth/token', {
        data: { client_id: 'node-red-admin', grant_type: 'password', scope: '*', username: '', password: '' }
      });
      expect(resp.ok()).toBeFalsy();
    });
  });
});
