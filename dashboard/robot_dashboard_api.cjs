const { chromium } = require('playwright');

// ============================================================
// Robot Dashboard Automation Script
// Handles: Login, Check Alerts, Create Orders
// ============================================================

const DASHBOARD_URL = process.env.DASHBOARD_URL || 'http://localhost:5173/';
const LOGIN_EMAIL = process.env.DASHBOARD_LOGIN_EMAIL || 'admin@robot.local';
const LOGIN_PASSWORD = process.env.DASHBOARD_LOGIN_PASSWORD || '';
const LOGIN_ROLE = process.env.DASHBOARD_LOGIN_ROLE || 'admin';

async function login(context) {
  const page = await context.newPage();
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle' });
  
  // Fill login form
  await page.locator('input[placeholder*="email"]').fill(LOGIN_EMAIL);
  await page.locator('input[type="password"]').fill(LOGIN_PASSWORD);
  await page.locator('select').selectOption(LOGIN_ROLE);
  await page.locator('button[type="submit"]').click();
  
  await page.waitForTimeout(2000);
  await page.close();
  console.log("[LOGIN] Logged in as admin");
}

async function getAlerts(page) {
  // Click Alerts button
  await page.locator('button:has-text("Alerts")').click();
  await page.waitForTimeout(1500);
  
  // Extract alert text
  const bodyText = await page.evaluate(() => document.body.innerText);
  
  // Parse alerts - look for P0, P1, P2 entries
  const alerts = [];
  const lines = bodyText.split('\n');
  let currentPriority = '';
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('P0') || trimmed.startsWith('P1') || trimmed.startsWith('P2')) {
      currentPriority = trimmed;
    } else if (trimmed.includes('ORD-') || trimmed.includes('FAILED') || trimmed.includes('CANCELLED') || trimmed.includes('ERROR')) {
      alerts.push({ priority: currentPriority, message: trimmed });
    }
  }
  
  // Also count unacknowledged
  const unackMatch = bodyText.match(/(\d+) unacknowledged/);
  const unacknowledged = unackMatch ? parseInt(unackMatch[1]) : 0;
  
  // Get full page snapshot
  const fullHtml = await page.evaluate(() => document.body.innerHTML.substring(0, 5000));
  
  return { alerts, unacknowledged, raw: bodyText, html: fullHtml };
}

async function createOrder(page, robotName, action, targetX, targetY) {
  // Click Order button
  await page.locator('button:has-text("Order")').click();
  await page.waitForTimeout(1000);
  
  // Select robot from dropdown
  const robotSelect = page.locator('select').first();
  
  // Find the option that matches the robot
  const options = await robotSelect.locator('option').all();
  let matched = false;
  for (const opt of options) {
    const optText = await opt.textContent();
    if (optText.toLowerCase().includes(robotName.toLowerCase())) {
      const value = await opt.getAttribute('value');
      if (value) {
        await robotSelect.selectOption(value);
      } else {
        await opt.click();
      }
      matched = true;
      break;
    }
  }
  
  if (!matched) {
    // Try selecting by index - first robot
    await robotSelect.selectOption({ index: 0 });
    console.log(`[ORDER] Robot "${robotName}" not found, using first robot`);
  }
  
  // Fill Order ID (optional - auto-generated)
  const orderIdInput = page.locator('input[placeholder*="auto-generated"]');
  // Leave it empty for auto-generation
  
  // Select action
  const actionSelect = page.locator('select').nth(1);
  await actionSelect.selectOption(action);
  
  // Fill coordinates
  const coordInputs = page.locator('input[placeholder*="warehouse"]');
  await coordInputs.nth(0).fill(String(targetX));
  await coordInputs.nth(1).fill(String(targetY));
  
  // Click Send Order
  await page.locator('button:has-text("Send Order")').click();
  await page.waitForTimeout(2000);
  
  // Check result
  const bodyText = await page.evaluate(() => document.body.innerText);
  const success = bodyText.includes('success') || bodyText.includes('created') || bodyText.includes('Sent');
  
  return { success, message: bodyText.substring(0, 500) };
}

async function checkBattery(page) {
  // The battery info is on the main dashboard
  await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  
  const bodyText = await page.evaluate(() => document.body.innerText);
  
  // Parse robot battery info
  const robots = [];
  const lines = bodyText.split('\n');
  let currentRobot = '';
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.includes('KMR') || line.includes('MIR') || line.includes('OTTO')) {
      currentRobot = line;
      // Next line has status, next has battery
      const status = lines[i + 1]?.trim() || 'unknown';
      const batteryLine = lines[i + 2]?.trim() || '';
      const batteryMatch = batteryLine.match(/(\d+)%/);
      const battery = batteryMatch ? parseInt(batteryMatch[1]) : null;
      robots.push({ name: currentRobot, status, battery });
    }
  }
  
  return robots;
}

// ============================================================
// Export functions for use by the agent
// ============================================================
module.exports = { login, getAlerts, createOrder, checkBattery };

// ============================================================
// CLI mode - run directly
// ============================================================
async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'status';
  
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  
  // Always login first
  await login(context);
  
  if (command === 'alerts') {
    const page = await context.newPage();
    await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle' });
    const result = await getAlerts(page);
    console.log('\n=== ACTIVE ALERTS ===');
    console.log(`Unacknowledged: ${result.unacknowledged}`);
    result.alerts.forEach(a => console.log(`[${a.priority}] ${a.message}`));
    if (result.alerts.length === 0) console.log('No alerts found');
    await page.close();
  }
  
  else if (command === 'order') {
    const robot = args[1] || 'MIR-001';
    const action = args[2] || 'navigate';
    const x = parseInt(args[3]) || 10;
    const y = parseInt(args[4]) || 20;
    
    console.log(`\n=== CREATING ORDER ===`);
    console.log(`Robot: ${robot}, Action: ${action}, Target: (${x}, ${y})`);
    
    const page = await context.newPage();
    await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle' });
    const result = await createOrder(page, robot, action, x, y);
    console.log(`Result: ${result.success ? 'SUCCESS' : 'FAILED'}`);
    console.log(`Message: ${result.message}`);
    await page.close();
  }
  
  else if (command === 'battery') {
    const page = await context.newPage();
    const robots = await checkBattery(page);
    console.log('\n=== ROBOT BATTERY STATUS ===');
    robots.forEach(r => console.log(`${r.name} | Status: ${r.status} | Battery: ${r.battery !== null ? r.battery + '%' : 'N/A'}`));
    await page.close();
  }
  
  else {
    // Status: show all info
    const page = await context.newPage();
    await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle' });
    
    const [robots, alertResult] = await Promise.all([
      checkBattery(page),
      getAlerts(page)
    ]);
    
    console.log('\n=== DASHBOARD STATUS ===');
    console.log('\n--- Robots ---');
    robots.forEach(r => console.log(`${r.name} | ${r.status} | Battery: ${r.battery !== null ? r.battery + '%' : 'N/A'}`));
    
    console.log('\n--- Alerts ---');
    console.log(`Unacknowledged: ${alertResult.unacknowledged}`);
    alertResult.alerts.forEach(a => console.log(`[${a.priority}] ${a.message}`));
    if (alertResult.alerts.length === 0) console.log('No active alerts');
    
    await page.close();
  }
  
  await browser.close();
}

// Run if called directly
if (require.main === module) {
  main().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
  });
}
