const { expect } = require('@playwright/test');

/**
 * Page Object Model for the Node-RED admin login page.
 *
 * Node-RED v3/v4 uses a built-in login form at /admin/auth/login/
 * when adminAuth is enabled.
 */
class NodeRedLoginPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.usernameInput = page.locator('input#username, input[name="username"]');
    this.passwordInput = page.locator('input#password, input[name="password"]');
    this.loginButton = page.locator('button[type="submit"], button:has-text("Sign In"), button:has-text("登录")');
    this.loginForm = page.locator('form[action*="login"], form:has(input#username)');
    this.loginError = page.locator('.error, .alert-error, .notification-error, [role="alert"]');
    this.forgotPasswordLink = page.locator('a:has-text("forgot"), a:has-text("reset")');
  }

  /**
   * Navigate to the Node-RED login page.
   */
  async goto() {
    await this.page.goto('/admin/auth/login/');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Fill in the username field.
   * @param {string} username
   */
  async enterUsername(username) {
    await this.usernameInput.waitFor({ state: 'visible', timeout: 15000 });
    await this.usernameInput.fill('');
    await this.usernameInput.fill(username);
  }

  /**
   * Fill in the password field.
   * @param {string} password
   */
  async enterPassword(password) {
    await this.passwordInput.waitFor({ state: 'visible', timeout: 5000 });
    await this.passwordInput.fill('');
    await this.passwordInput.fill(password);
  }

  /**
   * Click the login / sign-in button.
   */
  async clickLogin() {
    await this.loginButton.waitFor({ state: 'visible', timeout: 5000 });
    await this.loginButton.click();
  }

  /**
   * Perform a complete login flow.
   * @param {string} username - Node-RED admin username (default: admin)
   * @param {string} password - Node-RED admin password (default: admin)
   */
  async login(username = 'admin', password = 'admin') {
    await this.goto();
    await this.enterUsername(username);
    await this.enterPassword(password);
    await this.clickLogin();
    // Wait for the redirect away from the login page
    await this.page.waitForURL(/\/admin\/(?!auth\/login)/, { timeout: 15000 }).catch(() => {
      // Fallback: wait for the page to settle if URL doesn't change as expected
      return this.page.waitForLoadState('networkidle', { timeout: 10000 });
    });
  }

  /**
   * Check whether the login form is visible on the page.
   */
  async isLoginFormVisible() {
    return this.loginForm.isVisible();
  }

  /**
   * Get the current error message text (if any).
   */
  async getErrorMessage() {
    if (await this.loginError.isVisible()) {
      return this.loginError.textContent();
    }
    return null;
  }

  /**
   * Assert that the login page is displayed correctly.
   */
  async expectLoginFormVisible() {
    await expect(this.usernameInput).toBeVisible({ timeout: 10000 });
    await expect(this.passwordInput).toBeVisible();
    await expect(this.loginButton).toBeVisible();
  }

  /**
   * Assert that login failed with an error message shown.
   */
  async expectLoginError(expectedMessage) {
    await expect(this.loginError).toBeVisible({ timeout: 10000 });
    if (expectedMessage) {
      await expect(this.loginError).toContainText(expectedMessage);
    }
  }
}

module.exports = { NodeRedLoginPage };
