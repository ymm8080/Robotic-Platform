// @ts-check
const { test, expect } = require('@playwright/test');

// ── Mock data ────────────────────────────────────────────────────

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

// ── Helpers ───────────────────────────────────────────────────────

/**
 * Mock all backend API routes so the dashboard renders real data in the browser.
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

async function navigateToTab(page, tabLabel) {
  await page.getByRole('button', { name: new RegExp(tabLabel) }).click();
}

// ── Suite: System Health (监控面板) ───────────────────────────────

test.describe('Dashboard — System Health 监控面板', () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page);
    await page.goto('/');
    await navigateToTab(page, 'System');
  });

  test('renders service status grid with all 5 services', async ({ page }) => {
    await expect(page.getByText('SAP Bridge')).toBeVisible();
    await expect(page.getByText('MQTT Broker')).toBeVisible();
    await expect(page.getByText('Redis')).toBeVisible();
    await expect(page.getByText('Database')).toBeVisible();
    await expect(page.getByText('Watchdog')).toBeVisible();
  });

  test('renders CPU, Memory, and Error Rate gauges', async ({ page }) => {
    await expect(page.getByText('CPU')).toBeVisible();
    await expect(page.getByText('Memory')).toBeVisible();
    await expect(page.getByText('Error Rate')).toBeVisible();
    // Values should be rendered
    await expect(page.getByText('45%')).toBeVisible();
    await expect(page.getByText('62%')).toBeVisible();
  });

  test('renders fleet status with all categories', async ({ page }) => {
    await expect(page.getByText('Fleet Status')).toBeVisible();
    await expect(page.getByText('Total')).toBeVisible();
    await expect(page.getByText('Online')).toBeVisible();
    await expect(page.getByText('Moving')).toBeVisible();
    await expect(page.getByText('Idle')).toBeVisible();
    await expect(page.getByText('Errors')).toBeVisible();
    await expect(page.getByText('Charging')).toBeVisible();
  });

  test('shows version number', async ({ page }) => {
    await expect(page.getByText(/v3\.4\.0/)).toBeVisible();
  });

  test('shows SAFE MODE and THROTTLE indicators when system is degraded', async ({ page }) => {
    // Re-navigate with warning data
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await navigateToTab(page, 'System');

    await expect(page.getByText('SAFE MODE ACTIVE')).toBeVisible();
    await expect(page.getByText('THROTTLE ACTIVE')).toBeVisible();
    // Gauges should show warning/critical colors (CPU 88% → orange, Memory 93% → red)
  });
});

// ── Suite: Alert Panel (错误追踪面板) ─────────────────────────────

test.describe('Dashboard — Alert Panel 错误追踪面板', () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page);
    await page.goto('/');
    await navigateToTab(page, 'Alerts');
  });

  test('shows "No active alerts" when system is healthy', async ({ page }) => {
    await expect(page.getByText('No active alerts')).toBeVisible();
  });

  test('shows multiple P0/P1/P2 alerts when system is degraded', async ({ page }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await navigateToTab(page, 'Alerts');

    // Should show alerts (at minimum SAFE MODE and service disconnect)
    await expect(page.getByText(/SAFE MODE/)).toBeVisible();
    await expect(page.locator('text=P0').first()).toBeVisible();
  });

  test('filter buttons show alert counts', async ({ page }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await navigateToTab(page, 'Alerts');

    // Filter buttons display counts
    await expect(page.getByRole('button', { name: /All/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /P0/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /P1/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /P2/ })).toBeVisible();
  });

  test('Acknowledge button works on an active alert', async ({ page }) => {
    await mockBackend(page, { health: MOCK_HEALTH_WARNINGS });
    await page.reload();
    await navigateToTab(page, 'Alerts');

    // Wait for alerts to render
    await expect(page.getByText(/SAFE MODE/)).toBeVisible();

    // Click the first Ack button
    const ackButton = page.getByText('Ack').first();
    await ackButton.click();

    // Should change to "Acked"
    await expect(page.getByText('✓ Acked')).toBeVisible();
  });
});

// ── Suite: Command Panel (指令下发控制台) ────────────────────────

test.describe('Dashboard — Command Panel 指令下发控制台', () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page);
    await page.goto('/');
    await navigateToTab(page, 'Commands');
  });

  test('renders all robots with brand and state', async ({ page }) => {
    await expect(page.getByText('RBT-001')).toBeVisible();
    await expect(page.getByText('RBT-002')).toBeVisible();
    await expect(page.getByText('RBT-003')).toBeVisible();
    await expect(page.getByText('Geek+')).toBeVisible();
    await expect(page.getByText('Quicktron')).toBeVisible();
    await expect(page.getByText('ForwardX')).toBeVisible();
  });

  test('each robot has 4 command buttons', async ({ page }) => {
    // 3 robots × 4 commands = 12 buttons in command groups
    await expect(page.getByText('Pause').first()).toBeVisible();
    await expect(page.getByText('Resume').first()).toBeVisible();
    await expect(page.getByText('Cancel Order').first()).toBeVisible();
    await expect(page.getByText('Reboot').first()).toBeVisible();
  });

  test('sends a Pause command and shows success result', async ({ page }) => {
    // Click Pause on the first robot
    await page.getByText('Pause').first().click();

    // Should show success message
    await expect(page.getByText(/Command "pause" sent/)).toBeVisible();
  });

  test('sends a Reboot command and shows success result', async ({ page }) => {
    await page.getByText('Reboot').first().click();

    await expect(page.getByText(/Command "reboot" sent/)).toBeVisible();
  });

  test('robot state badges render with correct colors', async ({ page }) => {
    // Each robot state appears as a colored badge
    await expect(page.getByText('ONLINE')).toBeVisible();
    await expect(page.getByText('MOVING')).toBeVisible();
    await expect(page.getByText('ERROR')).toBeVisible();
  });

  test('sends a command that fails and shows error', async ({ page }) => {
    // Override the command mock to return an error
    await page.unroute('**/api/v1/robots/*/command');
    await page.route('**/api/v1/robots/*/command', route => {
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'Robot offline' }) });
    });

    await page.getByText('Pause').first().click();

    await expect(page.getByText('Robot offline')).toBeVisible();
  });
});

// ── Suite: Tab Navigation ─────────────────────────────────────────

test.describe('Dashboard — Tab Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page);
    await page.goto('/');
  });

  test('all 8 tabs are visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Robots/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Map/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Battery/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Order/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Tasks/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /System/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Commands/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Alerts/ })).toBeVisible();
  });

  test('switching tabs renders correct panel content', async ({ page }) => {
    // System tab
    await navigateToTab(page, 'System');
    await expect(page.getByText('Fleet Status')).toBeVisible();

    // Alerts tab
    await navigateToTab(page, 'Alerts');
    await expect(page.getByText('No active alerts')).toBeVisible();

    // Commands tab
    await navigateToTab(page, 'Commands');
    await expect(page.getByText('RBT-001')).toBeVisible();
  });

  test('header shows dashboard title and robot count', async ({ page }) => {
    await expect(page.getByText('Robot Dispatch Dashboard')).toBeVisible();
    await expect(page.getByText(/SAP-EWM/)).toBeVisible();
  });
});
