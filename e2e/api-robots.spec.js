/**
 * ── Robot Status API Tests ──────────────────────────────────────────────
 *
 * Tests the SAP Bridge robot status endpoints that query Redis
 * for live VDA5050 robot state information.
 *
 * Endpoints tested:
 *   GET /api/v1/robots/status       — all robots
 *   GET /api/v1/robots/status/:id   — single robot by ID
 *   GET /api/v1/orders              — current orders
 *
 * @group api
 * @group robots
 */

const { test, expect } = require('./fixtures');
const robotTestData = require('./test-data/robots.json');

test.describe('Robot Status API', () => {
  /**
   * GET /api/v1/robots/status — Fetch all robots.
   */
  test.describe('GET /api/v1/robots/status', () => {
    test('should return 200 OK', async ({ sapBridgeApi }) => {
      await sapBridgeApi.expectRobotsStatusArray();
    });

    test('should return a list of connected robots', async ({ sapBridgeApi }) => {
      const { status, body } = await sapBridgeApi.getRobotsStatus();
      expect(status).toBe(200);

      // Normalize: the response can be an array, or wrapped in an object
      const robots = Array.isArray(body) ? body : (body.robots || body.data || []);
      expect(Array.isArray(robots)).toBe(true);
    });

    test('each robot should have the required VDA5050 fields', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getRobotsStatus();

      const robots = Array.isArray(body) ? body : (body.robots || body.data || []);
      if (robots.length === 0) {
        test.skip(); // No robots connected — skip
        return;
      }

      for (const robot of robots) {
        // VDA5050 mandatory fields
        expect(robot.robotId || robot.id || robot.robot_id).toBeDefined();
        // Should have a status/state field
        const state = robot.state || robot.status || robot.robot_status;
        if (state !== undefined) {
          expect(robotTestData.states).toContain(state);
        }
      }
    });

    test('should not expose internal Redis details', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getRobotsStatus();
      const bodyStr = JSON.stringify(body).toLowerCase();

      // Should not leak Redis connection details
      expect(bodyStr).not.toContain('redis');
      expect(bodyStr).not.toContain('6379');
    });

    test('robot states should be valid VDA5050 states', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getRobotsStatus();
      const robots = Array.isArray(body) ? body : (body.robots || body.data || []);
      if (robots.length === 0) {
        test.skip();
        return;
      }

      const validStates = robotTestData.states;
      for (const robot of robots) {
        const state = robot.state || robot.status || robot.robot_status;
        if (state !== undefined) {
          expect(validStates).toContain(state);
        }
      }
    });

    test('should respond quickly (under 3s)', async ({ sapBridgeApi }) => {
      const start = Date.now();
      await sapBridgeApi.getRobotsStatus();
      const elapsed = Date.now() - start;
      expect(elapsed).toBeLessThan(3000);
    });
  });

  /**
   * GET /api/v1/robots/status/:id — Fetch a single robot.
   */
  test.describe('GET /api/v1/robots/status/:id', () => {
    test('should return 404 for a non-existent robot ID', async ({ sapBridgeApi }) => {
      const { status } = await sapBridgeApi.getRobotStatus('NONEXISTENT_ROBOT_999');
      expect(status).toBe(404);
    });

    test('should return robot details for a valid robot ID', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getRobotsStatus();
      const robots = Array.isArray(body) ? body : (body.robots || body.data || []);

      if (robots.length === 0) {
        test.skip(); // No robots to test against
        return;
      }

      const firstRobotId = robots[0].robotId || robots[0].id || robots[0].robot_id;
      const { status, body: robotDetail } = await sapBridgeApi.getRobotStatus(firstRobotId);
      expect(status).toBe(200);
      expect(robotDetail).toBeDefined();
    });

    test('should reject invalid robot ID formats', async ({ request }) => {
      // SQL injection attempt
      const resp1 = await request.get('/api/v1/robots/status/; DROP TABLE robots');
      expect([400, 404, 422, 500]).toContain(resp1.status());

      // Special characters
      const resp2 = await request.get('/api/v1/robots/status/../admin');
      expect([400, 404, 422]).toContain(resp2.status());
    });
  });

  /**
   * GET /api/v1/orders — Fetch current orders.
   */
  test.describe('GET /api/v1/orders', () => {
    test('should return 200 OK', async ({ sapBridgeApi }) => {
      const { status } = await sapBridgeApi.getOrders();
      expect(status).toBe(200);
    });

    test('should return a list of orders', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getOrders();

      const orders = Array.isArray(body) ? body : (body.orders || body.data || []);
      expect(Array.isArray(orders)).toBe(true);

      for (const order of orders) {
        expect(order.orderNo || order.order_no || order.id).toBeDefined();
      }
    });

    test('orders should have valid status transitions', async ({ sapBridgeApi }) => {
      const { body } = await sapBridgeApi.getOrders();
      const orders = Array.isArray(body) ? body : (body.orders || body.data || []);

      if (orders.length === 0) {
        test.skip();
        return;
      }

      const validStatuses = robotTestData.orders.map(o => o.status);
      for (const order of orders) {
        const status = order.status || order.order_status;
        if (status !== undefined) {
          expect(validStatuses).toContain(status);
        }
      }
    });
  });
});
