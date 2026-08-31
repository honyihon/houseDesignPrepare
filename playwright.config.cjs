const fs = require('node:fs');
const path = require('node:path');
const { defineConfig } = require('@playwright/test');

const port = Number(process.env.PLAYWRIGHT_PORT || 8770);
const localPython = process.platform === 'win32'
  ? path.join(__dirname, '.venv', 'Scripts', 'python.exe')
  : path.join(__dirname, '.venv', 'bin', 'python');
const python = process.env.PYTHON || (fs.existsSync(localPython)
  ? localPython
  : (process.platform === 'win32' ? 'python' : 'python3'));
const quotedPython = `"${python.replace(/"/g, '\\"')}"`;

module.exports = defineConfig({
  testDir: './tests/e2e',
  outputDir: 'test-results/playwright',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
  },
  webServer: {
    command: `${quotedPython} -m http.server ${port} --bind 127.0.0.1`,
    url: `http://127.0.0.1:${port}/structured/parametric/walkthrough.html`,
    cwd: __dirname,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
