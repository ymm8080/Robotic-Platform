// Full mock layer on port 8001 — proxies unknown requests to :8000, handles robots/orders locally
const http = require('http');

const CHARGE_STATIONS = [
  { id: 'CS-1', x: 40, y: 190 }, { id: 'CS-2', x: 80, y: 190 }, { id: 'CS-3', x: 120, y: 190 },
  { id: 'CS-4', x: 40, y: 230 }, { id: 'CS-5', x: 80, y: 230 }, { id: 'CS-6', x: 120, y: 230 },
];

const IDLE_POS = [
  { x: 260, y: 150 }, { x: 480, y: 150 }, { x: 690, y: 60 },
  { x: 690, y: 200 }, { x: 300, y: 50 },  { x: 520, y: 50 },
];

// ── Local task store ──────────────────────────────────────────────

let orders = [
  { orderId: 'ORD-001', robotId: 'RBT-001', status: 'IN_PROGRESS', createdAt: new Date(Date.now() - 300000).toISOString(), actionType: 'navigate', targetX: 690, targetY: 60 },
  { orderId: 'ORD-002', robotId: 'RBT-003', status: 'ASSIGNED',    createdAt: new Date(Date.now() - 120000).toISOString(), actionType: 'pick',    targetX: 650, targetY: 60 },
  { orderId: 'ORD-003', robotId: 'RBT-005', status: 'COMPLETED',   createdAt: new Date(Date.now() - 600000).toISOString(), actionType: 'place',   targetX: 650, targetY: 200 },
];

function getOrderForRobot(robotId) {
  return orders.find(o => o.robotId === robotId && o.status !== 'COMPLETED' && o.status !== 'CANCELLED') || null;
}

// ── Proxy helper ──────────────────────────────────────────────────

function proxyTo8000(req, res, transform) {
  const opts = { hostname: '127.0.0.1', port: 8000, path: req.url, method: req.method, headers: req.headers };
  const preq = http.request(opts, (pres) => {
    if (transform) {
      let body = '';
      pres.on('data', c => body += c);
      pres.on('end', () => {
        res.writeHead(pres.statusCode, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
        res.end(transform(body));
      });
    } else {
      res.writeHead(pres.statusCode, pres.headers);
      pres.pipe(res);
    }
  });
  req.pipe(preq);
}

// ── Server ────────────────────────────────────────────────────────

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, 'http://localhost');

  // GET /api/v1/robots/status — inject positions + task links
  if (req.method === 'GET' && url.pathname === '/api/v1/robots/status') {
    proxyTo8000(req, res, (body) => {
      try {
        const data = JSON.parse(body);
        if (data.robots) {
          data.robots = data.robots.map((r, i) => {
            const task = getOrderForRobot(r.id);
            return {
              ...r,
              position: IDLE_POS[i] || { x: 100, y: 100 },
              chargingStation: CHARGE_STATIONS[i] || CHARGE_STATIONS[0],
              orderId: task ? task.orderId : null,
              returningToCharge: r.state === 'CHARGING',
            };
          });
        }
        return JSON.stringify(data);
      } catch { return body; }
    });
    return;
  }

  // GET /api/v1/orders — return local task list
  if (req.method === 'GET' && url.pathname === '/api/v1/orders') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ orders: orders.map(o => ({ ...o, manufacturer: 'mock', serialNumber: o.robotId })) }));
    return;
  }

  // POST /api/v1/orders — create task and assign to robot
  if (req.method === 'POST' && url.pathname === '/api/v1/orders') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { manufacturer, serialNumber, orderId, nodes } = JSON.parse(body);
        const robotId = serialNumber; // serialNumber = robot ID from form
        const oid = orderId || `ORD-${Date.now().toString(36).toUpperCase()}`;
        const task = {
          orderId: oid,
          robotId,
          status: 'ASSIGNED',
          createdAt: new Date().toISOString(),
          actionType: nodes?.[0]?.actions?.[0]?.actionType || 'navigate',
          targetX: nodes?.[0]?.nodePosition?.x || 0,
          targetY: nodes?.[0]?.nodePosition?.y || 0,
        };
        orders.unshift(task);
        console.log(`[ORDER] ${oid} → ${robotId}`);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, orderId: oid }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Invalid body' }));
      }
    });
    return;
  }

  // POST /api/v1/robots/:id/command — handle recharge etc.
  const cmdMatch = url.pathname.match(/^\/api\/v1\/robots\/(.+)\/command$/);
  if (req.method === 'POST' && cmdMatch) {
    const robotId = decodeURIComponent(cmdMatch[1]);
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { action } = JSON.parse(body);
        if (action === 'recharge') {
          const task = getOrderForRobot(robotId);
          if (task) {
            res.writeHead(409, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: false, error: `${robotId} has active order ${task.orderId}. Cancel order first.` }));
            return;
          }
        }
        // Forward other commands to real server
        proxyTo8000(req, res);
      } catch { proxyTo8000(req, res); }
    });
    return;
  }

  // All other requests → proxy to 8000
  proxyTo8000(req, res);
});

server.listen(8001, () => {
  console.log('Mock layer on :8001 (positions + tasks + orders) → :8000');
});
