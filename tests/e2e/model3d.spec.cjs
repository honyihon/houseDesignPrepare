const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const {
  assertNoFrameworkOverlay,
  expectNoUnexpectedConsole,
  monitorConsole,
} = require('./helpers.cjs');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const localPython = process.platform === 'win32'
  ? path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe')
  : path.join(REPO_ROOT, '.venv', 'bin', 'python');
const python = process.env.PYTHON || (fs.existsSync(localPython) ? localPython : (process.platform === 'win32' ? 'python' : 'python3'));

test.beforeAll(() => {
  execFileSync(python, [path.join(__dirname, 'prepare_current_model3d.py')], { cwd: REPO_ROOT, stdio: 'pipe' });
});

test('original HTML model3d viewer loads and its primary controls respond', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html', { waitUntil: 'load' });

  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect(page.getByRole('heading', { name: '原設計 HTML · 三棟 3D 對照' })).toBeVisible();
  await expect(page.locator('canvas#canvas')).toBeVisible();
  await expect(page.getByRole('img', { name: /原始 HTML 草圖/ })).toBeVisible();
  await expect(page.locator('#subtitle')).not.toBeEmpty();
  await expect(page.locator('#compare')).toContainText('只在 HTML：側院');
  await expect(page.locator('#orientation')).toContainText('道路／前方');
  await expect(page.locator('a[href="../parametric/walkthrough.html"]')).toBeVisible();
  await assertNoFrameworkOverlay(page);

  await page.locator('#geom-source [data-geom="declared"]').click();
  await expect(page.locator('#geom-source [data-geom="declared"]')).toHaveClass(/on/);
  await page.locator('#color-mode [data-mode="provenance"]').click();
  await expect(page.locator('#color-mode [data-mode="provenance"]')).toHaveClass(/on/);
  await page.locator('#view-plan').click();
  await expect(page.locator('#view-plan')).toHaveClass(/on/);
  await expect(page.locator('#compass')).toContainText('俯視');
  await expect(page.locator('#compass')).toContainText('上方是道路');
  await page.locator('#openings').check();
  await expect(page.locator('#openings')).toBeChecked();
  expectNoUnexpectedConsole(messages);
});

test('original HTML room and 3D use a reversible deep link', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/AbuildingView.html#room-living', { waitUntil: 'load' });

  await expect(page.locator('.design-bridge')).toContainText('原設計討論草圖 · A 棟');
  await expect(page.locator('#floor-1')).toHaveClass(/active/);
  await expect(page.locator('#room-living')).toHaveClass(/room-active/);
  await expect(page.locator('.design-bridge-floor-link')).toHaveCount(4);
  const roomLink = page.locator('#room-living .design-bridge-room-link');
  await expect(roomLink).toHaveAttribute('href', /model3d\.html#building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=plan/);

  await roomLink.click();
  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state)).toEqual({
    building: 'A', floor: 'floor-1', room: 'A:floor-1:living', view: 'plan',
  });
  await expect(page.locator('#scope-buildings [data-building="A"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#scope-floors [data-floor="floor-1"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#scope-rooms [data-room="A:floor-1:living"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#info')).toContainText('客廳');
  await expect(page.locator('#info')).toContainText('道路側／前段（平面 y=1200 mm）');
  const backLink = page.locator('#info .info-link');
  await expect(backLink).toHaveAttribute('href', /AbuildingView\.html#room-living$/);

  await backLink.click();
  await expect(page).toHaveURL(/AbuildingView\.html#room-living$/);
  await expect(page.locator('#floor-1')).toHaveClass(/active/);
  await expect(page.locator('#room-living')).toHaveClass(/room-active/);
  expectNoUnexpectedConsole(messages);
});

test('original HTML bridge and deep-linked model work over file protocol', async ({ page }) => {
  const messages = monitorConsole(page);
  const htmlUrl = `${pathToFileURL(path.join(REPO_ROOT, 'AbuildingView.html')).href}#room-living`;
  await page.goto(htmlUrl, { waitUntil: 'load' });

  await expect(page.locator('.design-bridge')).toBeVisible();
  await expect(page.locator('#room-living')).toHaveClass(/room-active/);
  await page.locator('#room-living .design-bridge-room-link').click();
  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room))
    .toBe('A:floor-1:living');
  expectNoUnexpectedConsole(messages);
});

test('original HTML model mobile controls collapse to expose the 3D viewport', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#building=C&floor=floor-1&view=plan', { waitUntil: 'load' });

  await expect(page.locator('#app')).toHaveCSS('grid-template-columns', '390px');
  const toggle = page.locator('#mobile-panel-toggle');
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#app')).toHaveClass(/panel-collapsed/);
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).panelCollapsed).toBe(true);
  const sizes = await page.evaluate(() => ({
    stage: document.querySelector('#stage').getBoundingClientRect().height,
    panel: document.querySelector('#panel').getBoundingClientRect().height,
    body: document.body.scrollWidth,
    inner: innerWidth,
  }));
  expect(sizes.stage).toBeGreaterThan(760);
  expect(sizes.panel).toBeLessThan(60);
  expect(sizes.body).toBeLessThanOrEqual(sizes.inner);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('R000 review dashboard blocks historical geometry from becoming current 3D', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/reviews/R000/index.html', { waitUntil: 'load' });

  await expect(page).toHaveTitle('住宅設計檢核中心 · R000');
  await expect(page.getByRole('heading', { name: '現行空間量體模型' })).toBeVisible();
  const readiness = page.locator('#model3dReadiness');
  await expect(readiness.locator('#model3dStatus')).toHaveText('已阻擋');
  await expect(readiness).toContainText('0/99');
  await expect(readiness).toContainText('REVISION_LEGACY_ASSUMPTION');
  await expect(readiness).toContainText('COORDINATE_SYSTEM_UNVERIFIED');
  await expect(readiness).toContainText('不會建立或連結為現行 3D');
  await expect(page.locator('a[href*="walkthrough"], a[href*="model3d"]')).toHaveCount(0);
  await assertNoFrameworkOverlay(page);

  await page.getByRole('button', { name: /現行 3D/ }).click();
  await expect.poll(() => readiness.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const headerBottom = document.querySelector('.app-header').getBoundingClientRect().bottom;
    return box.top >= headerBottom && box.top < window.innerHeight;
  })).toBe(true);
  expectNoUnexpectedConsole(messages);
});

test('dashboard modal traps focus, closes with Escape and returns focus', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/reviews/R000/index.html', { waitUntil: 'load' });
  const trigger = page.locator('#importButton');
  await trigger.click();
  const dialog = page.locator('#importDialog');
  await expect(dialog).toHaveClass(/open/);
  await expect(dialog).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#closeDialog')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator('#closeDialog')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toHaveClass(/open/);
  await expect(dialog).toHaveAttribute('aria-hidden', 'true');
  await expect(trigger).toBeFocused();
  expectNoUnexpectedConsole(messages);
});

test('dashboard mobile navigation is compact and reveals location tree on demand', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/structured/reviews/R000/index.html', { waitUntil: 'load' });

  await expect(page.locator('.nav')).toHaveCSS('display', 'grid');
  expect((await page.locator('.nav').evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length))).toBe(3);
  await expect(page.locator('#locationTree')).toBeHidden();
  const toggle = page.locator('#locationToggle');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#locationTree')).toBeVisible();
  const widths = await page.evaluate(() => ({ inner: innerWidth, body: document.body.scrollWidth }));
  expect(widths.body).toBeLessThanOrEqual(widths.inner);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('current revision space-block artifact selects a real building, floor and room', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/test-results/runtime-current/model3d.html', { waitUntil: 'load' });

  await expect(page).toHaveTitle('空間量體模型 · RQA');
  await expect(page.getByRole('heading', { name: '空間量體模型' })).toBeVisible();
  await expect(page.getByRole('img', { name: /RQA 空間量體三維模型/ })).toBeVisible();
  await expect(page.locator('.warning')).toContainText('不是施工精度 walkthrough');
  await assertNoFrameworkOverlay(page);

  await page.locator('#buildings [data-building="B"]').click();
  await page.locator('#floors [data-floor="floor-2"]').click();
  await page.locator('#room-list [data-room="B-bedroom"]').click();
  const state = await page.evaluate(() => window.__spaceBlockDebug());
  expect(state.state).toEqual({ building: 'B', floor: 'floor-2', room: 'B-bedroom' });
  expect(state.visible).toEqual(['B-bedroom']);
  await expect(page.locator('#info')).toContainText('B 棟臥室');
  expectNoUnexpectedConsole(messages);
});

test('current space-block mobile controls collapse to expose the 3D viewport', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/test-results/runtime-current/model3d.html', { waitUntil: 'load' });

  const toggle = page.locator('#panel-toggle');
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#app')).toHaveClass(/panel-collapsed/);
  expectNoUnexpectedConsole(messages);
  await context.close();
});
