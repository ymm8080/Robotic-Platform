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
   * Get a command button by label, optionally scoped to a specific robot.
   * @param {string} robotId - The robot ID to scope the button search to.
   * @param {'Pause' | 'Resume' | 'Stop' | 'Cancel Order' | 'Recharge' | 'Reboot' | 'State' | 'Factsheet'} command
   */
  commandButton(robotId, command) {
    // Try to scope to the robot's card/row first; fall back to global search.
    const robotSection = this.page.locator(`[data-testid="robot-${robotId}"]`);
    return robotSection
      .getByRole('button', { name: new RegExp(`^${command}$`, 'i') })
      .or(
        this.page.getByRole('button', { name: new RegExp(`^${command}$`, 'i') })
      )
      .first();
  }

  async sendCommand(robotId, command) {
    await this.commandButton(robotId, command).click();
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
