const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/browser',
  testMatch: '*.spec.cjs',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: 'python3 scripts/build_pages.py && python3 -m http.server 8765 --bind 127.0.0.1 --directory _site',
    url: 'http://127.0.0.1:8765/figgie-rl/',
    reuseExistingServer: !process.env.CI,
  },
});
