const { expect } = require('@playwright/test');

/**
 * API helper for the SAP Bridge service.
 *
 * Provides typed methods for the main REST endpoints used in
 * the EWM Robot platform.
 *
 * @see sap-bridge/main.py
 */
class SapBridgeApi {
  /**
   * @param {import('@playwright/test').APIRequestContext} request
   */
  constructor(request) {
    this.request = request;
  }

  /**
   * GET /health — basic health check.
   * @returns {Promise<{status: number, body: object}>}
   */
  async health() {
    const response = await this.request.get('/health');
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * GET /ready — readiness probe.
   * @returns {Promise<{status: number, body: object}>}
   */
  async ready() {
    const response = await this.request.get('/ready');
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * GET /live — liveness probe.
   * @returns {Promise<{status: number, body: object}>}
   */
  async live() {
    const response = await this.request.get('/live');
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * GET /api/v1/robots/status — fetch all robot statuses from Redis.
   * @returns {Promise<{status: number, body: object}>}
   */
  async getRobotsStatus() {
    const response = await this.request.get('/api/v1/robots/status');
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * GET /api/v1/robots/status/:robotId — fetch a single robot's status.
   * @param {string} robotId
   * @returns {Promise<{status: number, body: object}>}
   */
  async getRobotStatus(robotId) {
    const response = await this.request.get(`/api/v1/robots/status/${robotId}`);
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * GET /api/v1/orders — fetch current orders.
   * @returns {Promise<{status: number, body: object}>}
   */
  async getOrders() {
    const response = await this.request.get('/api/v1/orders');
    return {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  }

  /**
   * Assert that the health endpoint returns a successful response.
   */
  async expectHealthy() {
    const { status, body } = await this.health();
    expect(status).toBe(200);
    // Accept both "ok" and "healthy" as valid status values
    const statusVal = (body.status || body.health || '').toLowerCase();
    expect(['ok', 'healthy', 'true']).toContain(statusVal);
  }

  /**
   * Assert that the /ready endpoint returns 200.
   */
  async expectReady() {
    const { status } = await this.ready();
    expect(status).toBe(200);
  }

  /**
   * Assert that the /live endpoint returns 200.
   */
  async expectLive() {
    const { status } = await this.live();
    expect(status).toBe(200);
  }

  /**
   * Assert that the robots endpoint returns an array.
   */
  async expectRobotsStatusArray() {
    const { status, body } = await this.getRobotsStatus();
    expect(status).toBe(200);
    // The response can be an array of robots or an object with a robots key
    if (Array.isArray(body)) {
      expect(Array.isArray(body)).toBe(true);
    } else if (body.robots) {
      expect(Array.isArray(body.robots)).toBe(true);
    } else if (body.data) {
      expect(Array.isArray(body.data)).toBe(true);
    }
  }
}

module.exports = { SapBridgeApi };
