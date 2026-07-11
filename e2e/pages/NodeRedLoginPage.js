const { expect } = require('@playwright/test');

/**
 * Page Object Model for Node-RED 3.x login dialog.
 *
 * Node-RED 3.x renders an overlay login dialog on the main page (/).
 * The dialog contains username/password inputs and a "Sign in" button.
 *
 * @see https://nodered.org/docs/user-guide/editor/
 */
class NodeRedLoginPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    this.usernameInput = page.getByPlaceholder(/username/i);
    this.passwordInput = page.getByPlaceholder(/password/i);
    this.loginButton = page.getByRole('button', { name: /sign in/i });
    this.loginError = page.getByRole('alert');
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  async enterUsername(username) {
    await this.usernameInput.fill(username);
  }

  async enterPassword(password) {
    await this.passwordInput.fill(password);
  }

  async clickLogin() {
    await this.loginButton.click();
  }

  async login(username = 'admin', password = 'admin') {
    await this.goto();

    const dialogVisible = await this.usernameInput.isVisible().catch(() => false);
    if (!dialogVisible) {
      return; // already authenticated
    }

    await this.enterUsername(username);
    await this.enterPassword(password);
    await this.clickLogin();

    // Wait for the editor to load (dialog disappears)
    await this.usernameInput.waitFor({ state: 'hidden', timeout: 15000 });
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
