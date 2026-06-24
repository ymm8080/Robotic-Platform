const { expect } = require('@playwright/test');

/**
 * Page Object Model for Node-RED 3.x login dialog.
 *
 * Node-RED 3.x uses an overlay login dialog on the main page (/)
 * instead of a separate login page. The dialog is rendered by JS
 * and contains username/password inputs and a "Sign in" button.
 *
 * @see https://nodered.org/docs/user-guide/editor/
 */
class NodeRedLoginPage {
  constructor(page) {
    this.page = page;

    // Node-RED 3.x login dialog — rendered overlay on /
    this.dialog = page.locator('.red-ui-dialog, [class*="login"], [class*="dialog"]');
    this.usernameInput = page.locator('#dialog-login-username, #node-red-ui-login-username, input[type="text"]').first();
    this.passwordInput = page.locator('#dialog-login-password, #node-red-ui-login-password, input[type="password"]').first();
    this.loginButton = page.locator('button:has-text("Sign in"), button:has-text("登录"), button[type="submit"]').first();
    this.loginError = page.locator('.red-ui-dialog .error, .red-ui-dialog [role="alert"], .red-ui-dialog .alert').first();
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  async enterUsername(username) {
    await this.usernameInput.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
    await this.usernameInput.fill('');
    await this.usernameInput.fill(username);
  }

  async enterPassword(password) {
    await this.passwordInput.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    await this.passwordInput.fill('');
    await this.passwordInput.fill(password);
  }

  async clickLogin() {
    await this.loginButton.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    await this.loginButton.click();
  }

  async login(username = 'admin', password = 'admin') {
    await this.goto();
    // If already authenticated (via httpCredentials), the dialog won't appear
    const dialogVisible = await this.usernameInput.isVisible().catch(() => false);
    if (!dialogVisible) {
      return; // already logged in
    }
    await this.enterUsername(username);
    await this.enterPassword(password);
    await this.clickLogin();
    // Wait for the editor to load (dialog disappears)
    await this.page.waitForTimeout(2000);
    await this.page.waitForLoadState('networkidle');
  }

  async isLoginFormVisible() {
    return this.usernameInput.isVisible().catch(() => false);
  }

  async getErrorMessage() {
    if (await this.loginError.isVisible().catch(() => false)) {
      return this.loginError.textContent();
    }
    return null;
  }

  async expectLoginFormVisible() {
    await expect(this.usernameInput).toBeVisible({ timeout: 10000 });
    await expect(this.passwordInput).toBeVisible();
    await expect(this.loginButton).toBeVisible();
  }

  async expectLoginError(expectedMessage) {
    await expect(this.loginError).toBeVisible({ timeout: 10000 });
    if (expectedMessage) {
      await expect(this.loginError).toContainText(expectedMessage);
    }
  }
}

module.exports = { NodeRedLoginPage };
