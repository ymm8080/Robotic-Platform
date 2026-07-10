const { chromium } = require('playwright');

// ============================================================
// Robot Dashboard Interactive Tool
// For: CowAgent - browse Dashboard in WeChat
//
// Usage: node dashboard_tool.cjs <command> [args]
//
// Commands:
//   status       — Show full dashboard status (text)
//   alerts       — Show active alerts
//   screenshot   — Take screenshot, save to file
//   order <robot> <action> <x> <y> — Create order
// ============================================================

const DASHBOARD_URL = 'http://localhost:5173/';
const STATE_FILE = __dirname + '/dashboard_state.json';

async function startBrowser() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  
  // Try restore login state
  try {
    const { readFileSync, existsSync } = require('fs');
    if (existsSync(STATE_FILE)) {
      const savedState = JSON.parse(readFileSync(STATE_FILE, 'utf-8'));
      // Quick check if expired — if we have cookies, use them
      if (savedState && savedState.cookies && savedState.cookies.length > 0) {
        await context.addCookies(savedState.cookies);
      }
    }
  } catch(e) { /* ignore */ }
  
  const page = await context.newPage();
  await page.setViewportSize({ width: 1280, height: 900 });
  
  return { browser, context, page };
}

async function ensureLoggedIn(page) {
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);
  
  const text = await page.evaluate(() => document.body.innerText);
  
  if (text.includes('Sign In') || text.includes('sign in')) {
    // Need to login
    await page.locator('input[placeholder*="email"]').fill('admin@robot.local');
    await page.locator('input[type="password"]').fill('admin123');
    await page.locator('select').selectOption('admin');
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(2000);
    
    // Save state
    try {
      const cookies = await page.context().cookies();
      const { writeFileSync } = require('fs');
      writeFileSync(STATE_FILE, JSON.stringify({ cookies }), 'utf-8');
    } catch(e) { /* non-critical */ }
    
    return true; // just logged in
  }
  
  return false; // was already logged in
}

async function cmdStatus(page) {
  // Get the page content
  const text = await page.evaluate(() => document.body.innerText);
  const lines = text.split('\n');
  
  console.log(text);
}

async function cmdAlerts(page) {
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1000);
  
  // Click Alerts button
  try {
    await page.locator('button:has-text("Alerts")').click();
    await page.waitForTimeout(1500);
  } catch(e) { /* already on alerts */ }
  
  const text = await page.evaluate(() => document.body.innerText);
  const lines = text.split('\n').map(l => l.trim()).filter(l => l);
  
  console.log('🚨 DASHBOARD ALERTS');
  console.log('━━━━━━━━━━━━━━━━');
  
  let inAlert = false;
  for (const line of lines) {
    if (/^(P0|P1|P2)\b/.test(line) || line.includes('All')) {
      inAlert = true;
    }
    if (inAlert) {
      console.log(line);
    }
  }
  
  // Count unacknowledged
  const unackMatch = text.match(/(\d+) unacknowledged/);
  if (unackMatch) console.log(`\n⚠️ ${unackMatch[1]} unacknowledged`);
}

async function cmdScreenshot(page) {
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);
  
  const path = __dirname + '/tmp_dashboard_screenshot.png';
  await page.screenshot({ path, fullPage: true });
  console.log('📸 SCREENSHOT:' + path);
}

async function cmdOrder(page, args) {
  const robot = args[1] || 'MIR-001';
  const action = args[2] || 'navigate';
  const x = args[3] || '10';
  const y = args[4] || '20';
  
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1000);
  
  // Click Order
  try {
    await page.locator('button:has-text("Order")').click();
    await page.waitForTimeout(1000);
  } catch(e) {}
  
  // Fill form
  const robotSelect = page.locator('select').first();
  await robotSelect.selectOption(robot);
  
  const actionSelect = page.locator('select').nth(1);
  await actionSelect.selectOption(action);
  
  // Fill coordinates
  const inputs = await page.locator('input').all();
  let coordCount = 0;
  for (const input of inputs) {
    const ph = await input.getAttribute('placeholder');
    if (ph && ph.includes('warehouse')) {
      if (coordCount === 0) {
        await input.fill(x);
        coordCount++;
      } else {
        await input.fill(y);
        break;
      }
    }
  }
  
  // Submit
  const sendBtn = page.locator('button:has-text("Send Order")');
  await sendBtn.click();
  await page.waitForTimeout(2500);
  
  const resultText = await page.evaluate(() => document.body.innerText);
  const taskMatch = resultText.match(/Task List \((\d+)\)/);
  
  console.log(`📦 ORDER: ${robot} ${action} (${x}, ${y})`);
  console.log(`   Tasks: ${taskMatch ? taskMatch[1] : 'N/A'}`);
  console.log(`   Status: Submitted ✅`);
}

// ============ MAIN ============
async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'status';
  
  const { browser, context, page } = await startBrowser();
  
  try {
    await ensureLoggedIn(page);
    
    switch(command) {
      case 'alerts': await cmdAlerts(page); break;
      case 'screenshot': await cmdScreenshot(page); break;
      case 'status': await cmdStatus(page); break;
      case 'order': await cmdOrder(page, args); break;
      default: await cmdStatus(page);
    }
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
  });
}
