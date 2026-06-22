/**
 * ── Playwright Global Teardown ──────────────────────────────────────────
 *
 * Runs once after ALL test suites complete.
 * Use this to:
 *   - Generate consolidated reports
 *   - Clean up test data
 *   - Stop Docker containers (if started by globalSetup)
 *
 * This file is referenced from playwright.config.js:
 *   globalTeardown: require.resolve('./e2e/global-teardown'),
 */

async function globalTeardown() {
  console.log('');
  console.log('═══ EWM Robot — Playwright Global Teardown ═══');
  console.log('  ✓ Test run complete.');
  console.log('  → Report: playwright-report/index.html');
  console.log('═══════════════════════════════════════════════');
}

module.exports = globalTeardown;
