const { test, expect } = require('@playwright/test');
const {
  assertNoFrameworkOverlay,
  expectNoUnexpectedConsole,
  monitorConsole,
} = require('./helpers.cjs');

test('shared HTML model3d viewer loads and its primary controls respond', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html', { waitUntil: 'load' });

  await expect(page).toHaveTitle('三棟量體 3D 檢視器');
  await expect(page.getByRole('heading', { name: '三棟量體 3D 檢視器' })).toBeVisible();
  await expect(page.locator('canvas#canvas')).toBeVisible();
  await expect(page.locator('#subtitle')).not.toBeEmpty();
  await expect(page.locator('#compare')).toContainText('只在 HTML：側院');
  await assertNoFrameworkOverlay(page);

  await page.locator('#geom-source [data-geom="declared"]').click();
  await expect(page.locator('#geom-source [data-geom="declared"]')).toHaveClass(/on/);
  await page.locator('#color-mode [data-mode="provenance"]').click();
  await expect(page.locator('#color-mode [data-mode="provenance"]')).toHaveClass(/on/);
  await page.locator('#view-plan').click();
  await expect(page.locator('#view-plan')).toHaveClass(/on/);
  await expect(page.locator('#compass')).toContainText('俯視');
  await expect(page.locator('#compass')).toContainText('對 HTML 格位');
  await page.locator('#openings').check();
  await expect(page.locator('#openings')).toBeChecked();
  expectNoUnexpectedConsole(messages);
});

test('R000 review dashboard blocks historical geometry from becoming current 3D', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/reviews/R000/index.html', { waitUntil: 'load' });

  await expect(page).toHaveTitle('住宅設計檢核中心 · R000');
  await expect(page.getByRole('heading', { name: '現行 revision 3D' })).toBeVisible();
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
