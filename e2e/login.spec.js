/**
 * ── Node-RED Admin Login Tests ──────────────────────────────────────────
 *
 * Tests the Node-RED admin authentication flow:
 *   - Login page renders correctly
 *   - Successful login with valid credentials
 *   - Failed login with invalid credentials
 *   - Logout flow
 *   - Session persistence
 *
 * @group nodered
 * @group auth
 */

const { test, expect } = require('./fixtures');

test.describe('Node-RED Admin Login', () => {
  test.describe('Login Page Rendering', () => {
    test('should display the login form when not authenticated', async ({ page, noderedLoginPage }) => {
      await noderedLoginPage.goto();

      // Verify the login form elements are present
      await noderedLoginPage.expectLoginFormVisible();

      // Verify we are on the login page (URL contains login)
      expect(page.url()).toContain('login');
    });

    test('should have a page title', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();

      const title = await noderedLoginPage.page.title();
      expect(title.length).toBeGreaterThan(0);
    });
  });

  test.describe('Authentication', () => {
    test('should successfully log in with valid admin credentials', async ({ page, noderedLoginPage }) => {
      await noderedLoginPage.login('admin', 'admin');

      // After successful login, we should be redirected away from the login page
      const currentUrl = page.url();
      expect(currentUrl).not.toContain('auth/login');

      // The page should show the Node-RED admin UI elements
      await expect(page.locator('#header, .red-ui-header')).toBeVisible({ timeout: 10000 });
    });

    test('should fail with wrong password and show error', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();
      await noderedLoginPage.enterUsername('admin');
      await noderedLoginPage.enterPassword('wrongpassword');
      await noderedLoginPage.clickLogin();

      // Should remain on the login page and show an error
      await expect(noderedLoginPage.page).toHaveURL(/.*login.*/);
      await noderedLoginPage.expectLoginError();
    });

    test('should fail with non-existent username', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();
      await noderedLoginPage.enterUsername('nonexistent_user');
      await noderedLoginPage.enterPassword('password123');
      await noderedLoginPage.clickLogin();

      // Should remain on the login page and show an error
      await expect(noderedLoginPage.page).toHaveURL(/.*login.*/);
      await noderedLoginPage.expectLoginError();
    });

    test('should reject empty username', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();
      await noderedLoginPage.enterUsername('');
      await noderedLoginPage.enterPassword('admin');
      await noderedLoginPage.clickLogin();

      // Should remain on the login page
      await expect(noderedLoginPage.page).toHaveURL(/.*login.*/);
    });

    test('should reject empty password', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();
      await noderedLoginPage.enterUsername('admin');
      await noderedLoginPage.enterPassword('');
      await noderedLoginPage.clickLogin();

      // Should remain on the login page
      await expect(noderedLoginPage.page).toHaveURL(/.*login.*/);
    });
  });

  test.describe('Session Management', () => {
    test('should maintain session after page refresh', async ({ authenticatedPage }) => {
      // After login, refresh the page and verify still authenticated
      await authenticatedPage.reload();
      await authenticatedPage.waitForLoadState('networkidle');

      // Should still see the admin UI, not the login page
      const currentUrl = authenticatedPage.url();
      expect(currentUrl).not.toContain('auth/login');
    });

    test('should successfully log out and return to login page', async ({ authenticatedPage, noderedDashboardPage }) => {
      await noderedDashboardPage.goto();
      await noderedDashboardPage.waitForDashboardReady();

      // Log out
      await noderedDashboardPage.logout();

      // Should be redirected to the login page
      await expect(authenticatedPage).toHaveURL(/.*login.*/);
    });

    test('should be redirected to login when accessing admin without auth', async ({ page }) => {
      // Try to access the admin dashboard directly without logging in
      await page.goto('/admin/');
      await page.waitForLoadState('networkidle');

      // Should be redirected to login
      expect(page.url()).toContain('login');
    });
  });

  test.describe('Login Page Security', () => {
    test('password field should be masked', async ({ noderedLoginPage }) => {
      await noderedLoginPage.goto();

      const inputType = await noderedLoginPage.passwordInput.getAttribute('type');
      expect(inputType).toBe('password');
    });

    test('should not expose credentials in URL after login', async ({ page, noderedLoginPage }) => {
      await noderedLoginPage.login('admin', 'admin');

      // Verify the URL does not contain the credentials
      const url = page.url();
      expect(url).not.toContain('admin');
      expect(url).not.toContain('password');
    });
  });
});
