const { test: base, expect } = require('@playwright/test');

// Custom fixtures can be defined here.
// Example:
// const { test: base } = require('@playwright/test');
// exports.test = base.extend({
//   authenticatedPage: async ({ page }, use) => {
//     await page.goto('/login');
//     await page.fill('[name="username"]', 'admin');
//     await page.fill('[name="password"]', 'password');
//     await page.click('button[type="submit"]');
//     await use(page);
//   },
// });

exports.test = base;
exports.expect = expect;
