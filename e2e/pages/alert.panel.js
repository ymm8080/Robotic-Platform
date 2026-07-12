const { expect } = require('@playwright/test');

/**
 * Page object for the Alert Panel in the dashboard.
 */
class AlertPanel {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    this.noAlertsMessage = page.getByText('No active alerts');
    this.filterAll = page.getByRole('button', { name: /All/i });
    this.filterP0 = page.getByRole('button', { name: /^P0$/ });
    this.filterP1 = page.getByRole('button', { name: /^P1$/ });
    this.filterP2 = page.getByRole('button', { name: /^P2$/ });
  }

  async filterBy(level) {
    const button =
      level === 'ALL'
        ? this.filterAll
        : level === 'P0'
        ? this.filterP0
        : level === 'P1'
        ? this.filterP1
        : this.filterP2;
    await button.click();
  }

  async acknowledgeFirstAlert() {
    await this.page.getByRole('button', { name: /Ack/i }).first().click();
    await expect(this.page.getByText('✓ Acked').first()).toBeVisible();
  }

  async expectNoAlerts() {
    await expect(this.noAlertsMessage).toBeVisible();
  }

  async expectAlertWithText(text) {
    await expect(this.page.getByText(text).first()).toBeVisible();
  }
}

module.exports = { AlertPanel };
