#!/usr/bin/env node
/**
 * Standalone API smoke test — bypasses Playwright test runner.
 *
 * Tests the same endpoints as api-health.spec.js and api-robots.spec.js
 * using Node.js built-in fetch. Works with Node >= 18.
 *
 * Usage:
 *   node e2e/api-smoke-direct.js
 *   API_BASE_URL=http://localhost:8000 node e2e/api-smoke-direct.js
 */

const BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';

let passed = 0;
let failed = 0;
const failures = [];

async function test(name, fn) {
  try {
    await fn();
    passed++;
    process.stdout.write('.');
  } catch (e) {
    failed++;
    failures.push({ name, error: e.message });
    process.stdout.write('F');
  }
}

async function assert(condition, msg) {
  if (!condition) throw new Error(msg || 'Assertion failed');
}

async function main() {
  console.log(`\n🧪 API Smoke Tests — ${BASE_URL}\n`);

  // ── Health endpoints ──────────────────────────

  await test('GET /health returns 200', async () => {
    const r = await fetch(`${BASE_URL}/health`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /health returns JSON with status', async () => {
    const r = await fetch(`${BASE_URL}/health`);
    const body = await r.json();
    assert(body.status, 'Missing status field');
  });

  await test('GET /health indicates healthy', async () => {
    const r = await fetch(`${BASE_URL}/health`);
    const body = await r.json();
    assert(body.status === 'healthy' || body.health === 'healthy', 'Not healthy');
  });

  await test('GET /health responds within 5s', async () => {
    const start = Date.now();
    await fetch(`${BASE_URL}/health`);
    assert(Date.now() - start < 5000, 'Too slow');
  });

  await test('GET /ready returns 200', async () => {
    const r = await fetch(`${BASE_URL}/ready`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /live returns 200', async () => {
    const r = await fetch(`${BASE_URL}/live`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /health no secrets exposed', async () => {
    const r = await fetch(`${BASE_URL}/health`);
    const text = JSON.stringify(await r.json()).toLowerCase();
    assert(!text.includes('password'), 'Contains password');
    assert(!text.includes('secret'), 'Contains secret');
  });

  await test('GET /health/nonexistent returns 404', async () => {
    const r = await fetch(`${BASE_URL}/health/nonexistent`);
    assert(r.status === 404, `Expected 404, got ${r.status}`);
  });

  await test('POST /health returns 405', async () => {
    const r = await fetch(`${BASE_URL}/health`, { method: 'POST' });
    assert([405, 400, 404].includes(r.status), `Expected 405/400/404, got ${r.status}`);
  });

  // ── Robot Status API ──────────────────────────

  await test('GET /api/v1/robots/status returns 200', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/robots/status`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /api/v1/robots/status returns array', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/robots/status`);
    const body = await r.json();
    assert(Array.isArray(body.robots ?? body), 'Expected robots array');
  });

  await test('GET /api/v1/robots/status has robot data', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/robots/status`);
    const body = await r.json();
    const robots = body.robots ?? body;
    if (robots.length > 0) {
      assert(robots[0].id !== undefined, 'Robot missing id');
      assert(robots[0].state || robots[0].status, 'Robot missing state');
    }
  });

  // ── Order API ─────────────────────────────────

  await test('GET /api/v1/orders returns 200', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/orders`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /api/v1/orders returns orders array', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/orders`);
    const body = await r.json();
    assert(Array.isArray(body.orders ?? body), 'Expected orders array');
  });

  // ── Stats & health ────────────────────────────

  await test('GET /metrics returns 200', async () => {
    const r = await fetch(`${BASE_URL}/metrics`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  await test('GET /api/v1/sap/health returns 200', async () => {
    const r = await fetch(`${BASE_URL}/api/v1/sap/health`);
    assert(r.status === 200, `Expected 200, got ${r.status}`);
  });

  // ── Results ───────────────────────────────────

  console.log(`\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  if (failures.length > 0) {
    for (const f of failures) {
      console.log(`  ❌ ${f.name}: ${f.error}`);
    }
  }
  console.log(`\n  ✅ ${passed} passed, ❌ ${failed} failed / ${passed + failed} total`);
  console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('\n❌ Fatal:', e.message);
  process.exit(1);
});
