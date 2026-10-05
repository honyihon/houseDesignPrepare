const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { assertNoFrameworkOverlay, expectNoUnexpectedConsole, monitorConsole } = require('./helpers.cjs');

const root = path.resolve(__dirname, '../..');
const python = process.env.PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
let directory;
test.beforeAll(() => {
  if (process.env.HOUSE_COORDINATION_E2E_DIR) {
    directory = path.resolve(process.env.HOUSE_COORDINATION_E2E_DIR);
    return;
  }
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'house-coordination-e2e-'));
  execFileSync(python, ['-m', 'scripts.demo_coordination_review', '--output', output], { cwd: root, stdio: 'pipe' });
  directory = path.join(output, 'reviews', 'DEMO-R2');
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`coordination review interaction and print overlay ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const messages = monitorConsole(page);
    const url = pathToFileURL(path.join(directory, 'index.html')).href;
    await page.goto(url);
    await expect(page).toHaveURL(url);
    await expect(page).toHaveTitle(/住宅設計檢核中心.*DEMO-R2/);
    await expect(page.locator('#readinessHeading')).toBeVisible();
    await assertNoFrameworkOverlay(page);
    await expect(page.locator('#comparisonBody')).toContainText('B-swing');
    await expect(page.locator('#comparisonBody')).toContainText('已解決');
    await expect(page.locator('#comparisonBody .change')).toHaveCount(6);
    await page.locator('#statusFilter').selectOption('unknown');
    await expect(page.locator('#findingsBody')).toContainText('武轎暫估收納不能當作實測搬運');
    await page.locator('tr[data-id="COORD-B-carry"]').click();
    await expect(page.locator('#inspectorContent')).toContainText('搬運外廓尚未實測');
    await page.screenshot({ path: path.join(os.tmpdir(), `house-coordination-dashboard-${viewport.width}.png`), fullPage: false });
    await page.getByRole('link', { name: '列印建築／裝潢套繪' }).click();
    await expect(page).toHaveTitle('圖面協調檢核');
    await expect(page.getByRole('heading', { name: '建築與裝潢套繪檢核' })).toBeVisible();
    await expect(page.locator('svg .turn')).toHaveCount(1);
    await expect(page.locator('svg .projection')).toHaveCount(2);
    await expect(page.locator('svg .route')).toHaveCount(1);
    await expect(page.locator('table')).toContainText('B-carry');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(os.tmpdir(), `house-coordination-print-${viewport.width}.png`), fullPage: false });
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('svg').first()).toBeVisible();
    expectNoUnexpectedConsole(messages);
  });
}
