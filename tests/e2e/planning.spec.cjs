const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const { assertNoFrameworkOverlay, expectNoUnexpectedConsole, monitorConsole } = require('./helpers.cjs');

const root = path.resolve(__dirname, '../..');
const python = process.env.PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
let output;
test.beforeAll(() => {
  output = fs.mkdtempSync(path.join(os.tmpdir(), 'house-planning-e2e-'));
  for (const command of ['site-compare', 'envelope', 'risk-review', 'brief']) {
    execFileSync(python, ['-m', 'house_design', 'predesign', command, '--output-root', output], { cwd: root, stdio: 'pipe' });
  }
  execFileSync(python, ['-m', 'house_design', 'predesign', 'meeting-pack', '--source-root', output, '--output-root', output], { cwd: root, stdio: 'pipe' });
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`site unknowns and transport limitations remain readable ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const messages = monitorConsole(page);
    const siteUrl = pathToFileURL(path.join(output, 'site-compare.html')).href;
    await page.goto(siteUrl);
    await expect(page).toHaveURL(siteUrl);
    await expect(page).toHaveTitle(/候選土地淘汰比較/);
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('body')).toContainText('資料不足');
    await expect(page.locator('body')).toContainText('三筆地界相鄰');
    await assertNoFrameworkOverlay(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(os.tmpdir(), `house-site-evidence-${viewport.width}.png`), fullPage: false });
    await page.goto(pathToFileURL(path.join(output, 'envelope.html')).href);
    await expect(page).toHaveTitle(/可建量體假設情境/);
    await expect(page.locator('body')).toContainText('抬桿與轉彎需求未確認');
    await expect(page.locator('body')).toContainText('實際路徑搬運演練');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await assertNoFrameworkOverlay(page);
    expectNoUnexpectedConsole(messages);
  });
  test(`planning filters, decision details and print ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const messages = monitorConsole(page);
    const url = pathToFileURL(path.join(output, 'risk-review.html')).href;
    await page.goto(url);
    await expect(page).toHaveURL(url);
    await expect(page).toHaveTitle('三棟防漏項與決策總表');
    await expect(page.getByRole('heading', { name: '三棟防漏項與決策總表', exact: true })).toBeVisible();
    await expect(page.locator('#coverage')).toContainText('66/66');
    await expect(page.locator('#coverage')).toContainText('12/12');
    await assertNoFrameworkOverlay(page);
    await page.locator('#bucket').selectOption('all');
    await expect(page.locator('article:visible')).toHaveCount(105);
    await page.locator('#building').selectOption('B');
    await page.locator('#topic').selectOption('ritual');
    await page.locator('#phase').selectOption('site_search');
    await expect(page.locator('article:visible')).toHaveCount(2);
    await expect(page.locator('article:visible').first()).toContainText('祭祀用火');
    await page.locator('article:visible').first().locator('summary').click();
    await expect(page.locator('article:visible').first().locator('details')).toHaveAttribute('open', '');
    await expect(page.locator('article:visible').first()).toContainText('驗收證據');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(os.tmpdir(), `house-planning-${viewport.width}.png`), fullPage: false });
    await page.locator('#status').selectOption('verified');
    await expect(page.locator('#count')).toHaveText('目前顯示 0 項');
    await page.locator('#status').selectOption('unknown');
    await page.evaluate(() => { window.print = () => window.__printed = true; });
    await page.getByRole('button', { name: '列印目前篩選' }).click();
    expect(await page.evaluate(() => window.__printed)).toBe(true);
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('article:visible')).toHaveCount(2);
    await expect(page.locator('article:visible').last().locator('details')).toHaveAttribute('open', '');
    await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
    await page.emulateMedia({ media: 'screen' });
    await expect(page.locator('article:visible').last().locator('details')).not.toHaveAttribute('open', '');
    expectNoUnexpectedConsole(messages);
  });
}

test('brief and architect packet link to the same offline decision register', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto(pathToFileURL(path.join(output, 'design-brief.html')).href);
  await page.getByRole('link', { name: '完整情境／驗收總表' }).click();
  await expect(page).toHaveTitle('三棟防漏項與決策總表');
  await page.goto(pathToFileURL(path.join(output, 'meeting-pack/architect/index.html')).href);
  await expect(page.getByRole('heading', { name: '9. 防漏項與當期決策' })).toBeVisible();
  await page.getByRole('link', { name: '完整情境與驗收總表' }).click();
  await expect(page).toHaveTitle('三棟防漏項與決策總表');
  expectNoUnexpectedConsole(messages);
});
