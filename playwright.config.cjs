const { defineConfig, devices } = require('@playwright/test');

const port = Number(process.env.FIGGIE_TEST_PORT || 8765);

module.exports = defineConfig({
  testDir: './tests/browser',
  testMatch: '*.spec.cjs',
  fullyParallel: true,
  use: { baseURL: `http://127.0.0.1:${port}`, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command: `python3 scripts/build_pages.py && python3 -m http.server ${port} --bind 127.0.0.1 --directory _site`,
    url: `http://127.0.0.1:${port}/figgie-rl/`,
    reuseExistingServer: !process.env.CI,
  },
});
