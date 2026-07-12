const { expect } = require('@playwright/test');

/**
 * Page object for the Command Panel in the dashboard.
 */
class CommandPanel {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  /**
   * Get a command button by label.
   * @param {'Pause' | 'Resume' | 'Stop' | 'Cancel Order' | 'Recharge' | 'Reboot' | 'State' | 'Factsheet'} command
   */
  commandButton(command) {
    return this.page.getByRole('button', { name: new RegExp(`^${command}$`, 'i') }).first();
  }

  async sendCommand(robotId, command) {
    await this.commandButton(command).click();
  }

  async expectCommandSuccess(robotId, command) {
    await expect(
      this.page.getByText(new RegExp(`Command "${command.toLowerCase()}" sent`))
    ).toBeVisible();
  }

  async expectCommandError(text) {
    await expect(this.page.getByText(text).first()).toBeVisible();
  }

  async expectRobotVisible(robotId) {
    await expect(this.page.getByText(robotId)).toBeVisible();
  }
}

module.exports = { CommandPanel };
