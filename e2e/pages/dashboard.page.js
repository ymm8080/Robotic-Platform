const { BasePage } = require('./base.page');

/**
 * Page object for the Robot Dispatch Dashboard (React Vite app).
 */
class DashboardPage extends BasePage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    super(page);

    this.title = page.getByRole('heading', { name: /Robot Dispatch Dashboard/i });
    this.subtitle = page.getByText(/SAP-EWM · VDA5050/);
    this.logoutButton = page.getByRole('button', { name: /Logout/i });
    this.eStopButton = page.getByRole('button', { name: /E-STOP/i });

    this.tabs = {
      robots: page.getByRole('button', { name: /Robots/i }),
      map: page.getByRole('button', { name: /Map/i }),
      battery: page.getByRole('button', { name: /Battery/i }),
      orders: page.getByRole('button', { name: /Order/i }),
      tasks: page.getByRole('button', { name: /Tasks/i }),
      system: page.getByRole('button', { name: /System/i }),
      commands: page.getByRole('button', { name: /Commands/i }),
      alerts: page.getByRole('button', { name: /Alerts/i }),
      traffic: page.getByRole('button', { name: /Traffic/i }),
      zones: page.getByRole('button', { name: /Zones/i }),
      settings: page.getByRole('button', { name: /Settings/i }),
      admin: page.getByRole('button', { name: /Admin/i }),
    };

    this.authCard = page.getByText(/Robot Dispatch Platform/i);
    this.loginForm = page.getByLabel(/Email or Phone/i);
  }

  async goto() {
    await this.page.goto('/');
    await this.waitForLoad();
  }

  /**
   * Navigate to a tab by label.
   * @param {'robots' | 'map' | 'battery' | 'orders' | 'tasks' | 'system' | 'commands' | 'alerts' | 'traffic' | 'zones' | 'settings' | 'admin'} key
   */
  async gotoTab(key) {
    await this.tabs[key].click();
    await this.tabs[key].waitFor({ state: 'visible' });
  }

  async clickLogout() {
    await this.logoutButton.click();
    await this.loginForm.waitFor({ state: 'visible', timeout: 10000 });
  }

  async clickEStop() {
    await this.eStopButton.click();
  }

  async isAuthenticated() {
    try {
      await this.title.waitFor({ state: 'visible', timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }
}

module.exports = { DashboardPage };
