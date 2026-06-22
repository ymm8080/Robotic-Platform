/**
 * ── Playwright Global Setup ─────────────────────────────────────────────
 *
 * Runs once before ALL test suites.
 * Use this to:
 *   - Verify Docker services are running before tests
 *   - Pre-warm Docker containers
 *   - Set up shared authentication state
 *   - Seed test data
 *
 * This file is referenced from playwright.config.js:
 *   globalSetup: require.resolve('./e2e/global-setup'),
 */

const { request } = require('@playwright/test');

async function globalSetup() {
  console.log(''); // blank line for readability
  console.log('═══ EWM Robot — Playwright Global Setup ═══');
  console.log('');

  // ── Configuration ──────────────────────────────────────────────────
  const NODE_RED_URL = process.env.BASE_URL || 'http://localhost:1880';
  const RESCUE_URL = process.env.RESCUE_BASE_URL || 'http://localhost:8080';
  const API_URL = process.env.API_BASE_URL || 'http://localhost:8000';

  const endpoints = [
    { name: 'Node-RED Admin', url: NODE_RED_URL },
    { name: 'Rescue Dashboard', url: RESCUE_URL },
    { name: 'SAP Bridge API', url: API_URL },
  ];

  // ── Service Readiness Check ────────────────────────────────────────
  let allReady = true;
  for (const svc of endpoints) {
    try {
      const response = await fetch(svc.url, { method: 'GET', signal: AbortSignal.timeout(5000) });
      console.log(`  ✓ ${svc.name} is reachable (HTTP ${response.status})`);
    } catch (err) {
      console.log(`  ⚠ ${svc.name} is NOT reachable: ${err.message}`);
      console.log(`    → Tests that need ${svc.name} will fail or skip.`);
      allReady = false;
    }
  }

  if (!allReady) {
    console.log('');
    console.log('  ⚠ Some services are not running.');
    console.log('  → Start services: docker compose up -d');
    console.log('  → Or run only API tests: npm run test:e2e:api');
  } else {
    console.log('');
    console.log('  ✓ All services are ready.');
  }

  console.log('');
  console.log('══════════════════════════════════════════════');
}

module.exports = globalSetup;
