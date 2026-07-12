const { expect } = require('@playwright/test');

/**
 * Base page object for the EWM Robot Dispatch Platform.
 *
 * Encapsulates shared selectors and waits. Concrete page objects extend this
 * class and implement `goto()`.
 */
class BasePage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  /**
   * Navigate to the page. Subclasses must implement this.
   * @abstract
   */
  async goto() {
    throw new Error('goto() must be implemented by subclass');
  }

  /**
   * Wait for the page network to settle.
   */
  async waitForLoad() {
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Get a toast/alert message.
   * @returns {import('@playwright/test').Locator}
   */
  get toast() {
    return this.page.getByRole('alert');
  }

  /**
   * Get the page heading (level 1).
   * @returns {import('@playwright/test').Locator}
   */
  get heading() {
    return this.page.getByRole('heading', { level: 1 });
  }

  /**
   * Assert that the current URL matches the expected path.
   * @param {string | RegExp} path
   */
  async expectURL(path) {
    await this.page.waitForURL(path);
  }

  /**
   * Wait for an element to become hidden.
   * @param {import('@playwright/test').Locator} locator
   */
  async waitForHidden(locator) {
    await locator.waitFor({ state: 'hidden' });
  }
}

module.exports = { BasePage };
