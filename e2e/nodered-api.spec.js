/**
 * ── Node-RED Internal API Tests ─────────────────────────────────────────
 *
 * @group nodered
 * @group api
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Internal API', () => {
  test.describe('API endpoints accessible', () => {
    test('should reach Node-RED health endpoint', async ({ page }) => {
      const resp = await page.request.get('http://localhost:1880/');
      expect(resp.status()).toBe(200);
    });
  });
});
