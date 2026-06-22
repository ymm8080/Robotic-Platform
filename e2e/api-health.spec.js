/**
 * ── SAP Bridge Health API Tests ─────────────────────────────────────────
 *
 * Tests the SAP Bridge service health/readiness endpoints.
 * These are the foundation probes that Kubernetes/Docker uses
 * to verify service availability.
 *
 * Endpoints tested:
 *   GET /health  — basic health check
 *   GET /ready   — readiness probe
 *   GET /live    — liveness probe
 *
 * @group api
 * @group health
 */

const { test, expect } = require('./fixtures');

test.describe('SAP Bridge Health API', () => {
  /**
   * GET /health — Basic health check.
   * Expected: 200 OK with a JSON body containing a status field.
   */
  test.describe('GET /health', () => {
    test('should return 200 OK', async ({ sapBridgeApi }) => {
      const { status } = await sapBridgeApi.health();
      expect(status).toBe(200);
    });

    test('should return a JSON body with a status field', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.health();

      expect(body).toBeDefined();
      // The status field may be named 'status' or 'health'
      const statusVal = body.status || body.health;
      expect(statusVal).toBeDefined();
    });

    test('should indicate healthy status', async ({ sapBridgeApi }) => {
      await sapBridgeApi.expectHealthy();
    });

    test('should respond within 5 seconds', async ({ sapBridgeApi }) => {
      const start = Date.now();
      await sapBridgeApi.health();
      const elapsed = Date.now() - start;
      expect(elapsed).toBeLessThan(5000);
    });
  });

  /**
   * GET /ready — Readiness probe.
   * Indicates whether the service is ready to accept traffic.
   * Expected: 200 OK when ready.
   */
  test.describe('GET /ready', () => {
    test('should return 200 OK when ready', async ({ sapBridgeApi }) => {
      await sapBridgeApi.expectReady();
    });

    test('should return a JSON body', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.ready();
      expect(body).toBeDefined();
    });
  });

  /**
   * GET /live — Liveness probe.
   * Indicates whether the service process is alive.
   * Expected: 200 OK when alive.
   */
  test.describe('GET /live', () => {
    test('should return 200 OK when alive', async ({ sapBridgeApi }) => {
      await sapBridgeApi.expectLive();
    });

    test('should return a JSON body', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.live();
      expect(body).toBeDefined();
    });
  });

  /**
   * All endpoints — consistency checks.
   */
  test.describe('Consistency', () => {
    test('all three health endpoints should return 200', async ({ sapBridgeApi }) => {
      const [health, ready, live] = await Promise.all([
        sapBridgeApi.health(),
        sapBridgeApi.ready(),
        sapBridgeApi.live(),
      ]);
      expect(health.status).toBe(200);
      expect(ready.status).toBe(200);
      expect(live.status).toBe(200);
    });

    test('health endpoint should not expose sensitive information', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.health();
      const bodyStr = JSON.stringify(body).toLowerCase();

      // Should not expose passwords, secrets, or internal configuration
      expect(bodyStr).not.toContain('password');
      expect(bodyStr).not.toContain('secret');
      expect(bodyStr).not.toContain('api_key');
    });
  });

  /**
   * Edge cases — invalid methods, paths, etc.
   */
  test.describe('Edge Cases', () => {
    test('should return 404 for unknown health sub-paths', async ({ request }) => {
      const response = await request.get('/health/nonexistent');
      expect(response.status()).toBe(404);
    });

    test('should return 405 for POST on health endpoint', async ({ request }) => {
      const response = await request.post('/health');
      // FastAPI typically returns 405 Method Not Allowed
      expect([405, 400, 404]).toContain(response.status());
    });
  });
});
