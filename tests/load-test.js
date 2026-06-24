// k6 load test — SAP-EWM Robot Dispatch Platform
// Simulates 100 concurrent robot sessions creating orders and checking status
// Run: k6 run tests/load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:1880';
const ROBOT_BRANDS = ['KUKA', 'MIR', 'OTTO', 'GeekPlus', 'HaiRobotics', 'Quicktron'];
const ORDER_TYPES = ['PICK', 'PUT', 'MOVE', 'CHARGE'];

const errorRate = new Rate('errors');
const orderCreateTrend = new Trend('order_create_duration');
const orderStatusTrend = new Trend('order_status_duration');

export let options = {
  stages: [
    { duration: '1m', target: 20 },   // Ramp up to 20 users
    { duration: '2m', target: 50 },   // Ramp to 50
    { duration: '3m', target: 100 },  // Ramp to 100
    { duration: '2m', target: 100 },  // Stay at 100
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    errors: ['rate<0.10'],             // <10% error rate
    http_req_duration: ['p(95)<2000'], // 95% of requests under 2s
    order_create_duration: ['p(95)<3000'],
  },
};

function randomRobot() {
  const brand = ROBOT_BRANDS[Math.floor(Math.random() * ROBOT_BRANDS.length)];
  const serial = `${brand}-${Math.floor(Math.random() * 1000)}`;
  return { brand, serial };
}

function randomOrder() {
  return {
    orderId: `LOAD-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    orderType: ORDER_TYPES[Math.floor(Math.random() * ORDER_TYPES.length)],
    priority: Math.floor(Math.random() * 4),
    nodes: [],
    edges: [],
    source: 'load-test',
  };
}

export default function () {
  const robot = randomRobot();

  // 1. Check robots status
  {
    const res = http.get(`${BASE_URL}/api/v1/robots/status`, {
      tags: { name: 'robotStatus' },
    });
    check(res, {
      'robot status 200': (r) => r.status === 200,
      'has robots array': (r) => {
        try { return JSON.parse(r.body).robots !== undefined; }
        catch { return false; }
      },
    });
    errorRate.add(res.status !== 200);
    orderStatusTrend.add(res.timings.duration);
  }

  // 2. Create order
  {
    const order = randomOrder();
    const payload = JSON.stringify({
      manufacturer: robot.brand,
      serialNumber: robot.serial,
      ...order,
    });
    const res = http.post(`${BASE_URL}/api/v1/orders`, payload, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'createOrder' },
    });
    check(res, {
      'order created 200/202': (r) => r.status === 200 || r.status === 202,
      'has orderId': (r) => {
        try { return JSON.parse(r.body).orderId !== undefined; }
        catch { return false; }
      },
    });
    errorRate.add(!(res.status === 200 || res.status === 202));
    orderCreateTrend.add(res.timings.duration);

    // 3. Check order status
    if (res.status === 200) {
      const body = JSON.parse(res.body);
      if (body.orderId) {
        sleep(0.5);
        const statusRes = http.get(`${BASE_URL}/api/v1/orders/${body.orderId}`, {
          tags: { name: 'orderStatus' },
        });
        check(statusRes, {
          'order status 200': (r) => r.status === 200,
          'has status': (r) => {
            try { return JSON.parse(r.body).status !== undefined; }
            catch { return false; }
          },
        });
      }
    }
  }

  // 4. Check queue depth
  {
    http.get(`${BASE_URL}/api/v1/orders/queue`, {
      tags: { name: 'queueDepth' },
    });
  }

  // 5. Periodically check SAP health
  if (Math.random() < 0.1) {
    const res = http.get(`${BASE_URL}/api/v1/sap/health`, {
      tags: { name: 'sapHealth' },
    });
    check(res, {
      'sap health connected': (r) => {
        try {
          const body = JSON.parse(r.body);
          return Object.values(body).some((v) => v?.connected === true);
        } catch { return false; }
      },
    });
  }

  sleep(1);
}
