const { defineConfig, devices } = require('@playwright/test');
require('dotenv').config({ path: '.env' });

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  // Look for test files in the e2e directory
  testDir: './e2e',

  // Run tests in files in parallel by default
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only (flaky network/container startup)
  retries: process.env.CI ? 2 : 0,

  // Limit workers on CI; use many locally
  workers: process.env.CI ? 1 : undefined,

  // Timeout for each test (30s — Node-RED UI can be slow to render)
  timeout: 30000,

  // Timeout for each expect() assertion
  expect: {
    timeout: 15000,
  },

  // Reporter configuration
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: process.env.CI ? 'never' : 'on-failure' }],
    ['list'],
    ...(process.env.CI ? [['junit', { outputFile: 'test-results/junit.xml' }]] : []),
  ],

  // Shared settings for all projects
  use: {
    // Base URL defaults to Node-RED admin UI (the primary web interface)
    baseURL: process.env.BASE_URL || 'http://localhost:1880',

    // Collect trace on first retry (CI) or on failure (local)
    trace: process.env.CI ? 'on-first-retry' : 'retain-on-failure',

    // Capture screenshot only when a test fails
    screenshot: 'only-on-failure',

    // Record video on failure for debugging complex flows
    video: process.env.CI ? 'on-first-retry' : 'retain-on-failure',

    // Ignore HTTPS errors (self-signed certs in dev)
    ignoreHTTPSErrors: true,

    // Action timeout (10s for Playwright actions like click, fill)
    actionTimeout: 10000,

    // Navigate timeout (20s for page loads)
    navigationTimeout: 20000,
  },

  // =========================================================================
  // Projects
  // =========================================================================
  projects: [
    // ── Node-RED Admin UI ──────────────────────────────────────────────
    {
      name: 'nodered-chromium',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /.*\.spec\.js/,
    },
    {
      name: 'nodered-firefox',
      use: { ...devices['Desktop Firefox'] },
      testMatch: /.*\.spec\.js/,
      // Firefox can be slower with Node-RED; give it more time
      timeout: 45000,
    },
    {
      name: 'nodered-webkit',
      use: { ...devices['Desktop Safari'] },
      testMatch: /.*\.spec\.js/,
    },

    // ── Rescue Dashboard (Nginx static page) ──────────────────────────
    // Runs against port 8080 — uses a dedicated test file
    {
      name: 'rescue-dashboard-chromium',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.RESCUE_BASE_URL || 'http://localhost:8080',
      },
      testMatch: /rescue-dashboard\.spec\.js/,
    },

    // ── API Smoke Tests ───────────────────────────────────────────────
    // No browser context needed — only APIRequestContext
    {
      name: 'api-smoke',
      testMatch: /api-.*\.spec\.js/,
      use: {
        baseURL: process.env.API_BASE_URL || 'http://localhost:8000',
      },
    },
  ],

  // =========================================================================
  // Global setup / teardown
  // =========================================================================
  // globalSetup: require.resolve('./e2e/global-setup'),
  // globalTeardown: require.resolve('./e2e/global-teardown'),

  // =========================================================================
  // Local dev server (optional — start containers before running tests)
  // =========================================================================
  // Uncomment and adjust for CI/pipeline to auto-start services:
  // webServer: [
  //   {
  //     command: 'docker compose up -d nodered nginx',
  //     port: 1880,
  //     timeout: 120000,
  //     reuseExistingServer: !process.env.CI,
  //   },
  // ],
});
