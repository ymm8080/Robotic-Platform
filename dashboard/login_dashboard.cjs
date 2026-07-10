const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log("Step 1: Loading page...");
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });

  // Fill login form
  console.log("Step 2: Filling login form...");
  const emailInput = page.locator('input[placeholder*="email"]');
  await emailInput.fill('admin@robot.local');
  
  const passwordInput = page.locator('input[type="password"]');
  await passwordInput.fill('admin123');
  
  // Select Admin role
  console.log("Step 3: Selecting Admin role...");
  const roleSelect = page.locator('select');
  await roleSelect.selectOption('admin');

  // Click Sign In
  console.log("Step 4: Clicking Sign In...");
  const signInBtn = page.locator('button[type="submit"]');
  await signInBtn.click();

  // Wait for navigation/dashboard to load
  await page.waitForTimeout(3000);
  
  const currentUrl = page.url();
  console.log("Current URL after login:", currentUrl);
  
  // Screenshot after login
  await page.screenshot({ path: 'tmp_after_login.png', fullPage: true });
  console.log("Post-login screenshot saved");

  // Get page content
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log("\n=== Dashboard body text ===");
  console.log(bodyText.substring(0, 3000));

  // Get all interactive elements on the dashboard
  const elements = await page.evaluate(() => {
    const selectors = 'input, button, select, textarea, a, [role="button"], [role="tab"], nav *, [class*="panel"], [class*="card"], [class*="alert"]';
    return Array.from(document.querySelectorAll(selectors)).slice(0, 80).map(el => ({
      tag: el.tagName,
      type: el.getAttribute('type') || '',
      id: el.id || '',
      class: (el.className || '').substring(0, 80),
      text: (el.innerText || el.textContent || '').substring(0, 80).trim(),
      href: el.getAttribute('href') || '',
      visible: el.offsetParent !== null
    }));
  });

  console.log("\n=== Dashboard elements ===");
  elements.forEach((el, i) => {
    if (el.text || el.id) console.log(`[${i}] <${el.tag}> id=${el.id} class=${el.class} text="${el.text}" visible=${el.visible}`);
  });

  // Save login state
  await context.storageState({ path: 'dashboard_login_state.json' });
  console.log("\nLogin state saved!");

  await browser.close();
  console.log("Done!");
})();
