#!/usr/bin/env node
/**
 * Mock Robot Fleet Server — simulates live robot operations for Dashboard testing.
 *
 * Start:  node scripts/mock-robot-server.js
 * Port:   8000 (Vite proxies /api → localhost:8000)
 *
 * Each robot has:
 *   - A dedicated charging station (positioned on the warehouse map)
 *   - Current position (x, y in warehouse coordinates)
 *   - An optional active task (orderId)
 *   - Recharge command → if no task, robot navigates to its station, then charges
 */

const http = require('http');

// ── Warehouse layout (matches dashboard WarehouseMap zones) ─────────

const CHARGING_ZONE = { x: 10, y: 160, w: 180, h: 130 };
const CHARGE_STATIONS = [
  { id: 'CS-1', x: 40,  y: 190 },
  { id: 'CS-2', x: 80,  y: 190 },
  { id: 'CS-3', x: 120, y: 190 },
  { id: 'CS-4', x: 40,  y: 230 },
  { id: 'CS-5', x: 80,  y: 230 },
  { id: 'CS-6', x: 120, y: 230 },
];

const BRANDS = ['Geek+', 'Quicktron', 'ForwardX'];
const IDLE_POSITIONS = [
  { x: 260, y: 150 }, { x: 480, y: 150 },  // Storage A/B
  { x: 690, y: 60 },  { x: 690, y: 200 },   // Picking / Shipping
  { x: 300, y: 50 },  { x: 520, y: 50 },    // Storage A top
];

// ── Robot factory ──────────────────────────────────────────────────

function createRobot(idx) {
  const station = CHARGE_STATIONS[idx - 1];
  const pos = IDLE_POSITIONS[idx - 1];
  return {
    id: `RBT-${String(idx).padStart(3, '0')}`,
    brand: BRANDS[idx % BRANDS.length],
    state: 'IDLE',
    battery: Math.floor(Math.random() * 40 + 50), // 50-90%
    lastSeen: new Date().toISOString(),
    paused: false,
    emergencyStopped: false,
    // Position & navigation
    position: { x: pos.x, y: pos.y },
    targetPosition: null,       // { x, y } — set when navigating to station
    chargingStation: station,   // Dedicated station per robot
    // Task
    orderId: null,              // null = free, string = has active task
    // Recharge state machine
    returningToCharge: false,   // true = navigating to station
  };
}

let robots = Array.from({ length: 6 }, (_, i) => createRobot(i + 1));

// ── Movement simulation ────────────────────────────────────────────

function moveToward(robot) {
  if (!robot.targetPosition) return false;
  const dx = robot.targetPosition.x - robot.position.x;
  const dy = robot.targetPosition.y - robot.position.y;
  const dist = Math.sqrt(dx * dx + dy * dy);

  if (dist < 5) {
    // Arrived at target
    robot.position = { ...robot.targetPosition };
    robot.targetPosition = null;
    return true; // arrived
  }

  // Move 8 units per tick toward target
  const step = 8;
  robot.position.x += (dx / dist) * step;
  robot.position.y += (dy / dist) * step;
  return false;
}

// Movement loop — runs every 500ms
setInterval(() => {
  robots.forEach(robot => {
    if (robot.returningToCharge) {
      // Navigate toward charging station
      robot.state = 'MOVING';
      robot.battery = Math.max(0, robot.battery - 0.2); // drain slightly while moving
      const arrived = moveToward(robot);
      if (arrived) {
        // Reached station — start charging
        robot.state = 'CHARGING';
        robot.returningToCharge = false;
      }
    } else if (robot.state === 'CHARGING') {
      // Charge at station
      robot.battery = Math.min(100, robot.battery + 2);
      if (robot.battery >= 95) {
        robot.state = 'IDLE';
      }
    } else if (!robot.paused && !robot.emergencyStopped &&
               robot.state !== 'UNAVAILABLE' && robot.state !== 'ERROR') {
      // Autonomous idle wandering (slow battery drain)
      if (robot.battery > 15 && Math.random() < 0.03) {
        const states = ['IDLE', 'MOVING', 'EXECUTING', 'IDLE'];
        robot.state = states[Math.floor(Math.random() * states.length)];
        robot.battery = Math.max(5, robot.battery - 0.5);
      }
    }
    robot.lastSeen = new Date().toISOString();
  });
}, 500);

// ── System health ──────────────────────────────────────────────────

function getHealth() {
  const online = robots.filter(r => r.state !== 'ERROR' && r.state !== 'UNAVAILABLE').length;
  const errors = robots.filter(r => r.state === 'ERROR').length;
  const moving = robots.filter(r => r.state === 'MOVING' || r.state === 'EXECUTING').length;
  const idle = robots.filter(r => r.state === 'IDLE' || r.state === 'ONLINE').length;
  const charging = robots.filter(r => r.state === 'CHARGING').length;
  const cpu = 30 + Math.random() * 40 + (moving * 3);
  const mem = 40 + Math.random() * 30;

  return {
    timestamp: new Date().toISOString(),
    services: {
      sapBridge: { status: 'healthy', connected: true, uptimeSeconds: 14400 },
      mqtt: { status: 'healthy', connected: true, uptimeSeconds: 28800 },
      redis: { status: 'healthy', connected: true, uptimeSeconds: 7200 },
      database: { status: 'healthy', connected: true, uptimeSeconds: 36000 },
      watchdog: { status: 'healthy', connected: true, uptimeSeconds: 21600 },
    },
    resources: {
      cpuPercent: Math.round(cpu),
      memoryPercent: Math.round(mem),
      errorRatePercent: Math.round(errors * 1.5 * 10) / 10,
      safeMode: errors > 3,
      throttleActive: cpu > 80,
    },
    fleet: { total: robots.length, online, error: errors, moving, idle, charging },
    version: '3.4.0',
  };
}

// ── HTTP API ───────────────────────────────────────────────────────

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') {
    res.writeHead(204); res.end(); return;
  }

  const url = new URL(req.url, 'http://localhost');

  // GET /api/v1/system/health
  if (req.method === 'GET' && url.pathname === '/api/v1/system/health') {
    res.writeHead(200);
    res.end(JSON.stringify(getHealth()));
    return;
  }

  // GET /api/v1/robots/status
  if (req.method === 'GET' && url.pathname === '/api/v1/robots/status') {
    const robotList = robots.map(r => ({
      id: r.id,
      brand: r.brand,
      state: r.state,
      battery: `${Math.round(r.battery)}%`,
      lastSeen: r.lastSeen,
      position: r.position,
      orderId: r.orderId,
      returningToCharge: r.returningToCharge,
      chargingStation: r.chargingStation,
    }));
    res.writeHead(200);
    res.end(JSON.stringify({ robots: robotList }));
    return;
  }

  // GET /api/v1/charging-stations
  if (req.method === 'GET' && url.pathname === '/api/v1/charging-stations') {
    res.writeHead(200);
    res.end(JSON.stringify({
      stations: CHARGE_STATIONS.map((cs, i) => ({
        ...cs,
        assignedRobot: robots[i]?.id || null,
        occupied: robots[i]?.state === 'CHARGING' || robots[i]?.returningToCharge,
      })),
    }));
    return;
  }

  // GET /api/v1/strategies
  if (req.method === 'GET' && url.pathname === '/api/v1/strategies') {
    res.writeHead(200);
    res.end(JSON.stringify({ strategies: BRANDS.map(b => ({ brand: b, protocol: 'VDA5050' })) }));
    return;
  }

  // GET /api/v1/orders?limit=50
  if (req.method === 'GET' && url.pathname === '/api/v1/orders') {
    res.writeHead(200);
    res.end(JSON.stringify({ orders: [] }));
    return;
  }

  // POST /api/v1/robots/:id/command
  const cmdMatch = url.pathname.match(/^\/api\/v1\/robots\/(.+)\/command$/);
  if (req.method === 'POST' && cmdMatch) {
    const robotId = decodeURIComponent(cmdMatch[1]);
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const { action } = JSON.parse(body);
        const robot = robots.find(r => r.id === robotId);

        if (!robot) {
          res.writeHead(404);
          res.end(JSON.stringify({ error: `Robot ${robotId} not found` }));
          return;
        }

        switch (action) {
          case 'pause':
            robot.paused = true;
            robot.state = 'PAUSED';
            robot.targetPosition = null;
            break;

          case 'resume':
            robot.paused = false;
            robot.emergencyStopped = false;
            if (robot.returningToCharge) {
              robot.state = 'MOVING';
            } else {
              robot.state = 'IDLE';
            }
            break;

          case 'cancel_order':
            robot.orderId = null;
            robot.state = 'IDLE';
            robot.targetPosition = null;
            robot.returningToCharge = false;
            break;

          case 'recharge':
            if (robot.orderId) {
              // Has active task — reject
              res.writeHead(409);
              res.end(JSON.stringify({
                ok: false,
                error: `Robot ${robotId} has active order ${robot.orderId}. Cancel order first.`,
              }));
              return;
            }
            // Navigate to its dedicated charging station
            robot.targetPosition = { ...robot.chargingStation };
            robot.returningToCharge = true;
            robot.state = 'MOVING';
            robot.paused = false;
            robot.emergencyStopped = false;
            console.log(`[RECHARGE] ${robotId} → navigating to station (${robot.chargingStation.x},${robot.chargingStation.y})`);
            break;

          case 'reboot':
            robot.state = 'UNAVAILABLE';
            robot.targetPosition = null;
            robot.returningToCharge = false;
            setTimeout(() => {
              robot.state = 'ONLINE';
              robot.paused = false;
              robot.emergencyStopped = false;
            }, 5000);
            break;

          case 'emergency_stop':
            robot.emergencyStopped = true;
            robot.state = 'PAUSED';
            robot.targetPosition = null;
            robot.returningToCharge = false;
            break;

          default:
            res.writeHead(400);
            res.end(JSON.stringify({ error: `Unknown action: ${action}` }));
            return;
        }

        robot.lastSeen = new Date().toISOString();
        console.log(`[CMD] ${robotId} ← ${action} → state=${robot.state} battery=${Math.round(robot.battery)}%`);

        res.writeHead(200);
        res.end(JSON.stringify({
          ok: true, robotId, action, newState: robot.state,
          returningToCharge: robot.returningToCharge,
          chargingStation: robot.chargingStation,
        }));
      } catch (e) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'Invalid JSON body' }));
      }
    });
    return;
  }

  // POST /api/v1/orders
  if (req.method === 'POST' && url.pathname === '/api/v1/orders') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, orderId: `ORD-${Date.now()}` }));
    });
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Not found' }));
});

const PORT = 8000;
server.listen(PORT, () => {
  console.log(`\n🤖 Mock Robot Fleet Server running on http://localhost:${PORT}`);
  console.log(`   ${robots.length} robots, each with dedicated charging station`);
  console.log(`   Movement loop: 500ms ticks`);
  console.log(`   Recharge: robot navigates to station → arrives → charges\n`);
  console.log(`   Dashboard: http://localhost:5173\n`);
});
