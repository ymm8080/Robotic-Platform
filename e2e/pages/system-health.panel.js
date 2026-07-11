const { expect } = require('@playwright/test');

/**
 * Page object for the System Health panel in the dashboard.
 */
class SystemHealthPanel {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;

    this.fleetStatusHeading = page.getByRole('heading', { name: /Fleet Status/i });
    this.safeModeIndicator = page.getByText('SAFE MODE ACTIVE');
    this.throttleIndicator = page.getByText('THROTTLE ACTIVE');
    this.versionText = page.getByText(/v\d+\.\d+\.\d+/);

    this.serviceNames = ['SAP Bridge', 'MQTT Broker', 'Redis', 'Database', 'Watchdog'];
    this.gaugeLabels = ['CPU', 'Memory', 'Error Rate'];
    this.fleetLabels = ['Total', 'Online', 'Moving', 'Idle', 'Errors', 'Charging'];
  }

  async expectServiceVisible(name) {
    await expect(this.page.getByText(name)).toBeVisible();
  }

  async expectGaugeVisible(label) {
    await expect(this.page.getByText(label)).toBeVisible();
  }

  async expectFleetStatVisible(label) {
    await expect(this.page.getByText(label)).toBeVisible();
  }

  async expectSafeModeVisible() {
    await expect(this.safeModeIndicator).toBeVisible();
  }

  async expectThrottleVisible() {
    await expect(this.throttleIndicator).toBeVisible();
  }
}

module.exports = { SystemHealthPanel };
