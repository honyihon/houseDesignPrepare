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
