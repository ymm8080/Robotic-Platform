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
    const cmdRegex = new RegExp(`^${command}$`, 'i');
    // Try to scope to the robot's card/row first; fall back to global search.
    const robotSection = this.page.locator(`[data-testid="robot-${robotId}"]`);
    const button = robotSection
      .getByRole('button', { name: cmdRegex })
      .or(
        this.page.getByRole('button', { name: cmdRegex })
      )
      .first();

    if (await button.count() === 0) {
      throw new Error(`Command button "${command}" not found for robot "${robotId}"`);
    }
    return button;
  }

  async sendCommand(robotId, command) {
    const button = await this.commandButton(robotId, command);
    await button.click();
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
