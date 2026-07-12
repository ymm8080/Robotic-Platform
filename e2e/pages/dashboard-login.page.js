const { expect } = require('@playwright/test');

/**
 * Page object for the dashboard login/register page.
 */
class DashboardLoginPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    this.signInTab = page.getByRole('button', { name: /Sign In/i });
    this.registerTab = page.getByRole('button', { name: /Register/i });

    this.loginForm = page.locator('[data-testid="login-form"]');
    this.credentialInput = page.getByLabel(/Email or Phone/i);
    this.passwordInput = page.getByLabel(/Password/i).first();
    this.roleSelect = page.getByLabel(/Role/i);
    this.loginSubmitButton = page.getByRole('button', { name: /Sign In/i });

    this.registerForm = page.locator('[data-testid="register-form"]');
    this.usernameInput = page.getByLabel(/Username/i);
    this.emailInput = page.getByLabel(/Email/i);
    this.phoneInput = page.getByLabel(/Phone/i);
    this.registerPasswordInput = page.locator('[data-testid="register-password-input"]').or(
      page.locator('input[type="password"]').nth(0)
    );
    this.registerConfirmInput = page.locator('[data-testid="register-confirm-password-input"]').or(
      page.locator('input[type="password"]').nth(1)
    );
    this.registerRoleSelect = this.page.locator('[data-testid="register-role-select"]').or(
      this.page.getByLabel(/Role/i).nth(1)
    );
    this.registerSubmitButton = page.getByRole('button', { name: /Create Account/i });

    this.errorBanner = page.getByRole('alert').or(page.locator('[data-testid="auth-error"]'));
  }

  async goto() {
    await this.page.goto('/');
    await this.page.waitForLoadState('networkidle');
  }

  async login(credential, password, role = 'admin') {
    await this.credentialInput.fill(credential);
    await this.passwordInput.fill(password);
    await this.roleSelect.selectOption(role);
    await this.loginSubmitButton.click();
  }

  async register(username, email, password, role = 'user') {
    await this.registerTab.click();
    await this.usernameInput.fill(username);
    await this.emailInput.fill(email);
    await this.registerPasswordInput.fill(password);
    await this.registerConfirmInput.fill(password);
    await this.registerRoleSelect.selectOption(role);
    await this.registerSubmitButton.click();
  }

  async expectLoginFormVisible() {
    await expect(this.loginForm.or(this.credentialInput)).toBeVisible({ timeout: 10000 });
  }

  async expectErrorVisible(message) {
    await expect(this.errorBanner).toBeVisible();
    if (message) {
      await expect(this.errorBanner).toContainText(message);
    }
  }
}

module.exports = { DashboardLoginPage };
