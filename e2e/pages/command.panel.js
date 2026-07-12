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
  async commandButton(robotId, command) {
    // Try to scope to the robot's card/row first; fall back to global search
    // only when the robot section is not present on the page.
    const btnRegex = new RegExp(`^${command}$`, 'i');
    const robotSection = this.page.locator(`[data-testid="robot-${robotId}"]`);
    const sectionExists = await robotSection.count() > 0;
    if (sectionExists) {
      return robotSection.getByRole('button', { name: btnRegex }).first();
    }
    return this.page.getByRole('button', { name: btnRegex }).first();
  }

  async sendCommand(robotId, command) {
    const btn = await this.commandButton(robotId, command);
    await btn.click();
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
