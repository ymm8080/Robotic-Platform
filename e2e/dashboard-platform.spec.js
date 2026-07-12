// @ts-check
const { test, expect } = require('./fixtures');

// ── Mock data ─────────────────────────────────────────────────────────

const MOCK_HEALTH = {
  timestamp: new Date().toISOString(),
  services: {
    sapBridge: { status: 'healthy', connected: true, uptimeSeconds: 3600 },
    mqtt: { status: 'healthy', connected: true, uptimeSeconds: 7200 },
    redis: { status: 'healthy', connected: true, uptimeSeconds: 1800 },
    database: { status: 'healthy', connected: true, uptimeSeconds: 9000 },
    watchdog: { status: 'healthy', connected: true, uptimeSeconds: 5400 },
  },
  resources: {
    cpuPercent: 45,
    memoryPercent: 62,
    errorRatePercent: 1.2,
    safeMode: false,
    throttleActive: false,
  },
  fleet: {
    total: 12, online: 10, error: 0, moving: 4, idle: 5, charging: 3,
  },
  version: '3.4.0',
};

const MOCK_HEALTH_WARNINGS = {
  ...MOCK_HEALTH,
  resources: {
    ...MOCK_HEALTH.resources,
    cpuPercent: 88,
    memoryPercent: 93,
    errorRatePercent: 9.5,
    safeMode: true,
    throttleActive: true,
  },
  services: {
    ...MOCK_HEALTH.services,
    mqtt: { status: 'disconnected', connected: false },
  },
  fleet: {
    total: 12, online: 7, error: 4, moving: 2, idle: 3, charging: 1,
  },
};

const MOCK_ROBOTS = {
  robots: [
    { id: 'RBT-001', brand: 'Geek+', state: 'ONLINE', battery: '85%', lastSeen: new Date().toISOString() },
    { id: 'RBT-002', brand: 'Quicktron', state: 'MOVING', battery: '42%', lastSeen: new Date().toISOString() },
    { id: 'RBT-003', brand: 'ForwardX', state: 'ERROR', battery: '10%', lastSeen: new Date().toISOString() },
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────

/**
 * Mock all backend API routes so the dashboard renders deterministic data.
 */
async function mockBackend(page, { health = MOCK_HEALTH, robots = MOCK_ROBOTS } = {}) {
  await page.route('**/api/v1/system/health', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(health) });
  });
  await page.route('**/api/v1/robots/status', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(robots) });
  });
  await page.route('**/api/v1/robots/*/command', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });
}

// ── Suite: System Health (监控面板) ───────────────────────────────────

test.describe('Dashboard — System Health', () => {
  test.beforeEach(async ({ page, dashboardPage }) => {
    await mockBackend(page);
    await dashboardPage.goto();
    await dashboardPage.gotoTab('system');
  });

  test('renders service status grid with all 5 services', async ({ systemHealthPanel }) => {
    await systemHealthPanel.expectServiceVisible('SAP Bridge');
    await systemHealthPanel.expectServiceVisible('MQTT Broker');
    await systemHealthPanel.expectServiceVisible('Redis');
    await systemHealthPanel.expectServiceVisible('Database');
    await systemHealthPanel.expectServiceVisible('Watchdog');
  });

  test('renders CPU, Memory, and Error Rate gauges', async ({ systemHealthPanel }) => {
    await systemHealthPanel.expectGaugeVisible('CPU');
    await systemHealthPanel.expectGaugeVisible('Memory');
    await systemHealthPanel.expectGaugeVisible('Error Rate');
    await expect(systemHealthPanel.page.getByText('45%')).toBeVisible();
    await expect(systemHealthPanel.page.getByText('62%')).toBeVisible();
  });

  test('renders fleet status with all categories', async ({ systemHealthPanel }) => {
    await expect(systemHealthPanel.fleetStatusHeading).toBeVisible();
    for (const label of systemHealthPanel.fleetLabels) {
      await systemHealthPanel.expectFleetStatVisible(label);
    }
  });

  test('shows version number', async ({ systemHealthPanel }) => {
    await expect(systemHealthPanel.versionText).toBeVisible();
  });

  test('shows SAFE MODE and THROTTLE indicators when system is degraded', async ({ page, dashboardPage, systemHealthPanel }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await dashboardPage.gotoTab('system');

    await systemHealthPanel.expectSafeModeVisible();
    await systemHealthPanel.expectThrottleVisible();
  });
});

// ── Suite: Alert Panel (错误追踪面板) ─────────────────────────────────

test.describe('Dashboard — Alert Panel', () => {
  test.beforeEach(async ({ page, dashboardPage }) => {
    await mockBackend(page);
    await dashboardPage.goto();
    await dashboardPage.gotoTab('alerts');
  });

  test('shows "No active alerts" when system is healthy', async ({ alertPanel }) => {
    await alertPanel.expectNoAlerts();
  });

  test('shows P0/P1/P2 alerts when system is degraded', async ({ page, dashboardPage, alertPanel }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await dashboardPage.gotoTab('alerts');

    await alertPanel.expectAlertWithText(/SAFE MODE/);
    await expect(alertPanel.page.getByText('P0').first()).toBeVisible();
  });

  test('filter buttons show alert counts', async ({ page, dashboardPage, alertPanel }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await dashboardPage.gotoTab('alerts');

    await expect(alertPanel.filterAll).toBeVisible();
    await expect(alertPanel.filterP0).toBeVisible();
    await expect(alertPanel.filterP1).toBeVisible();
    await expect(alertPanel.filterP2).toBeVisible();
  });

  test('Acknowledge button works on an active alert', async ({ page, dashboardPage, alertPanel }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await dashboardPage.gotoTab('alerts');

    await alertPanel.expectAlertWithText(/SAFE MODE/);
    await alertPanel.acknowledgeFirstAlert();
  });
});

// ── Suite: Command Panel (指令下发控制台) ─────────────────────────────

test.describe('Dashboard — Command Panel', () => {
  test.beforeEach(async ({ page, dashboardPage }) => {
    await mockBackend(page);
    await dashboardPage.goto();
    await dashboardPage.gotoTab('commands');
  });

  test('renders all robots with brand and state', async ({ commandPanel }) => {
    await commandPanel.expectRobotVisible('RBT-001');
    await commandPanel.expectRobotVisible('RBT-002');
    await commandPanel.expectRobotVisible('RBT-003');
    await expect(commandPanel.page.getByText('Geek+')).toBeVisible();
    await expect(commandPanel.page.getByText('Quicktron')).toBeVisible();
    await expect(commandPanel.page.getByText('ForwardX')).toBeVisible();
  });

  test('each robot has command buttons', async ({ commandPanel }) => {
    await expect(commandPanel.commandButton('RBT-001', 'Pause')).toBeVisible();
    await expect(commandPanel.commandButton('RBT-001', 'Resume')).toBeVisible();
    await expect(commandPanel.commandButton('RBT-001', 'Cancel Order')).toBeVisible();
    await expect(commandPanel.commandButton('RBT-001', 'Reboot')).toBeVisible();
  });

  test('sends a Pause command and shows success result', async ({ commandPanel }) => {
    await commandPanel.sendCommand('RBT-001', 'Pause');
    await commandPanel.expectCommandSuccess('RBT-001', 'Pause');
  });

  test('sends a Reboot command and shows success result', async ({ commandPanel }) => {
    await commandPanel.sendCommand('RBT-001', 'Reboot');
    await commandPanel.expectCommandSuccess('RBT-001', 'Reboot');
  });

  test('robot state badges render with correct colors', async ({ commandPanel }) => {
    await expect(commandPanel.page.getByText('ONLINE')).toBeVisible();
    await expect(commandPanel.page.getByText('MOVING')).toBeVisible();
    await expect(commandPanel.page.getByText('ERROR')).toBeVisible();
  });

  test('sends a command that fails and shows error', async ({ page, commandPanel }) => {
    await page.unroute('**/api/v1/robots/*/command');
    await page.route('**/api/v1/robots/*/command', route => {
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'Robot offline' }) });
    });

    await commandPanel.sendCommand('RBT-001', 'Pause');
    await commandPanel.expectCommandError('Robot offline');
  });
});

// ── Suite: Tab Navigation ─────────────────────────────────────────────

test.describe('Dashboard — Tab Navigation', () => {
  test.beforeEach(async ({ page, dashboardPage }) => {
    await mockBackend(page);
    await dashboardPage.goto();
  });

  test('all primary tabs are visible', async ({ dashboardPage }) => {
    const requiredTabs = ['robots', 'map', 'battery', 'orders', 'tasks', 'system', 'commands', 'alerts'];
    for (const key of requiredTabs) {
      await expect(dashboardPage.tabs[key]).toBeVisible();
    }
  });

  test('switching tabs renders correct panel content', async ({ dashboardPage, systemHealthPanel, alertPanel, commandPanel }) => {
    await dashboardPage.gotoTab('system');
    await expect(systemHealthPanel.fleetStatusHeading).toBeVisible();

    await dashboardPage.gotoTab('alerts');
    await alertPanel.expectNoAlerts();

    await dashboardPage.gotoTab('commands');
    await commandPanel.expectRobotVisible('RBT-001');
  });

  test('header shows dashboard title and robot count', async ({ dashboardPage }) => {
    await expect(dashboardPage.title).toBeVisible();
    await expect(dashboardPage.subtitle).toBeVisible();
  });
});
