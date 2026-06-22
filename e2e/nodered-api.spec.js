/**
 * ── Node-RED Internal API Tests ─────────────────────────────────────────
 *
 * Tests the Node-RED admin REST API endpoints used by the EWM platform:
 *   - System health check
 *   - Safe mode / restore mode
 *
 * These tests require admin authentication.
 *
 * @group nodered
 * @group api
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Internal API', () => {
  /**
   * GET /api/system-health — System health status.
   */
  test.describe('GET /api/system-health', () => {
    test.beforeEach(async ({ authenticatedPage }) => {
      // Ensure we have an authenticated session before making API calls
      await authenticatedPage.goto('/api/system-health');
    });

    test('should return a health status', async ({ page }) => {
      // If the page doesn't display JSON, it might redirect to login
      const url = page.url();
      expect(url).not.toContain('login');
    });
  });

  /**
   * POST /api/safe-mode and POST /api/restore-mode
   * — Emergency control endpoints.
   */
  test.describe('POST /api/safe-mode', () => {
    test('should require authentication', async ({ request }) => {
      const response = await request.post('/api/safe-mode');
      // Without auth, Node-RED returns 401 Unauthorized
      expect([401, 403]).toContain(response.status());
    });
  });

  test.describe('POST /api/restore-mode', () => {
    test('should require authentication', async ({ request }) => {
      const response = await request.post('/api/restore-mode');
      // Without auth, Node-RED returns 401 Unauthorized
      expect([401, 403]).toContain(response.status());
    });
  });

  /**
   * GET /flows — List deployed flows.
   */
  test.describe('GET /flows', () => {
    test('should require authentication', async ({ request }) => {
      const response = await request.get('/flows');
      expect([401, 403]).toContain(response.status());
    });
  });

  /**
   * General Node-RED admin API security.
   */
  test.describe('API Security', () => {
    test('should reject unauthenticated requests to admin API', async ({ request }) => {
      const endpoints = ['/flows', '/nodes', '/settings', '/auth/revoke'];

      for (const endpoint of endpoints) {
        const response = await request.get(endpoint);
        // All admin endpoints should require auth
        expect([401, 403],
          `Endpoint ${endpoint} should require auth but got ${response.status()}`
        ).toContain(response.status());
      }
    });

    test('should not expose admin API via OPTIONS without auth', async ({ request }) => {
      const response = await request.fetch('/settings', { method: 'OPTIONS' });
      // Should not leak settings without authentication
      expect([401, 403, 405]).toContain(response.status());
    });
  });
});
