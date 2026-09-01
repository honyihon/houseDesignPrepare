const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test, expect } = require('@playwright/test');
const {
  WALKTHROUGH_PATH,
  assertNoFrameworkOverlay,
  expectNoUnexpectedConsole,
  loadWalkthrough,
  monitorConsole,
  setRange,
  walkDebug,
} = require('./helpers.cjs');

const REPO_ROOT = path.resolve(__dirname, '..', '..');

test('desktop default scene has the intended identity and initial scope', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(page);

  await expect(page).toHaveURL(/structured\/parametric\/walkthrough\.html#/);
  await expect(page).toHaveTitle('參數化平面 · 走入式 3D');
  await expect(page.getByRole('heading', { name: '參數化情境 · 走入式 3D' })).toBeVisible();
  await expect(page.locator('#panel')).toContainText('舊版參數化情境');
  await expect(page.locator('#panel')).toContainText('不等於 A／B／C 原始 HTML 的格局');
  await expect(page.locator('a[href="../candidates/model3d.html"]')).toHaveText('原設計 HTML 3D');
  await assertNoFrameworkOverlay(page);

  const state = await walkDebug(page);
  expect(state.variant).toBe('f6000_g1');
  expect(state.state).toMatchObject({
    building: 'A', overview: false, floor: 'floor-1', walking: false,
    wheels: false, gap: 6000, room: '', filter: 'all',
  });
  expect(state.comparison).toEqual({ available: true, unmapped: 0 });
  expect(state.visibleRooms.length).toBeGreaterThan(0);
  expect(state.blockers).toBeGreaterThan(0);
  await expect(page.locator('#orientation')).toContainText('A 棟 1F');
  expectNoUnexpectedConsole(messages);
});

test('mapped, 3D-only, and intentional HTML-only rooms explain their relationship', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(page);

  await page.locator('#room-list [data-room="entry"]').click();
  await expect(page.locator('#inspector')).toBeVisible();
  await expect(page.locator('#info')).toContainText('原 HTML');
  await expect(page.locator('#info .mini-map rect.selected')).not.toHaveCount(0);
  await expect(page.locator('#info a.inline')).toHaveAttribute('href', /AbuildingView\.html#room-entry/);
  expect((await walkDebug(page)).state.room).toBe('entry');

  await page.locator('#room-list [data-room="corridor"]').click();
  await expect(page.locator('#info .relation')).toHaveText('參數化新增');
  await expect(page.locator('#info')).toContainText('參數化配置為了連通房間產生的走道');
  expect((await walkDebug(page)).state.room).toBe('corridor');

  await page.locator('#buildings [data-building="C"]').click();
  const sideyard = page.locator('#compare .compare-button').filter({ hasText: '側院' });
  await expect(sideyard).toHaveCount(1);
  await sideyard.click();
  await expect(page.locator('#info .relation')).toHaveText('只在原 HTML');
  await expect(page.locator('#info')).toContainText('沒有可高亮的 3D 區塊');
  await expect(page.locator('#info .mini-map rect.selected')).not.toHaveCount(0);
  await expect(page.locator('#info a.inline')).toHaveAttribute('href', /CbuildingView\.html#room-sideyard/);
  const state = await walkDebug(page);
  expect(state.state.room).toBe('');
  expect(state.inspectorOpen).toBe(true);
  expectNoUnexpectedConsole(messages);
});

test('actual frontage and garage sliders select the extreme variants', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(page);
  await page.locator('details.controls').evaluate((element) => { element.open = true; });

  await setRange(page.locator('#frontage'), 4);
  await expect.poll(async () => (await walkDebug(page)).variant).toBe('f10000_g1');
  await expect(page.locator('#v-frontage')).toHaveText('10.0 m');
  await expect(page.locator('#subtitle')).toContainText('10 ×');

  await setRange(page.locator('#bays'), 1);
  await expect.poll(async () => (await walkDebug(page)).variant).toBe('f10000_g2');
  await expect(page.locator('#v-bays')).toHaveText('2 車位');
  await expect(page).toHaveURL(/frontage=10000/);
  await expect(page).toHaveURL(/bays=2/);
  expect((await walkDebug(page)).comparison.unmapped).toBe(0);
  expectNoUnexpectedConsole(messages);
});

test('all 12 building and floor scopes remain selectable', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(page);

  for (const building of ['A', 'B', 'C']) {
    await page.locator(`#buildings [data-building="${building}"]`).click();
    for (const floor of ['floor-1', 'floor-2', 'floor-3', 'floor-rf']) {
      await page.locator(`#floors [data-floor="${floor}"]`).click();
      const state = await walkDebug(page);
      expect(state.state.building).toBe(building);
      expect(state.state.floor).toBe(floor);
      expect(state.state.overview).toBe(false);
      expect(state.visibleRooms.length).toBeGreaterThan(0);
      await expect(page.locator(`#buildings [data-building="${building}"]`))
        .toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator(`#floors [data-floor="${floor}"]`))
        .toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('#room-count')).toHaveText(/\d+ 間/);
    }
  }

  await expect(page.locator('#orientation')).toContainText('C 棟 RF');
  expectNoUnexpectedConsole(messages);
});

test('overview and auxiliary modes update real viewer state', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(page);
  await page.locator('details.controls').evaluate((element) => { element.open = true; });

  await page.locator('#buildings [data-building="overview"]').click();
  let state = await walkDebug(page);
  expect(state.state.overview).toBe(true);
  const screen = Object.fromEntries(state.onScreen.map((item) => [item.id, item.ndcX]));
  expect(screen.A).toBeGreaterThan(screen.B);
  expect(screen.B).toBeGreaterThan(screen.C);
  await expect(page.locator('#room-list')).toContainText('先選擇 A、B 或 C 棟');

  await setRange(page.locator('#gap'), 12000);
  await expect.poll(async () => (await walkDebug(page)).state.gap).toBe(12000);
  await expect(page.locator('#v-gap')).toHaveText('12.0 m');

  await page.locator('#allfloors').check();
  await page.locator('#wheels').check();
  state = await walkDebug(page);
  expect(state.state.wheels).toBe(true);
  await expect(page.locator('#allfloors')).toBeChecked();
  await expect(page).toHaveURL(/all=1/);
  await expect(page.locator('#stage')).toHaveClass(/wheels/);
  await expect(page.locator('#turnbadge')).toBeHidden();

  await page.locator('#rule-filters [data-filter="warning"]').click();
  expect((await walkDebug(page)).state.filter).toBe('warning');
  await expect(page.locator('#rule-filters [data-filter="warning"]'))
    .toHaveAttribute('aria-pressed', 'true');

  await page.locator('[data-view="walk"]').click();
  await expect.poll(async () => (await walkDebug(page)).state.walking).toBe(true);
  state = await walkDebug(page);
  expect(state.state).toMatchObject({ overview: false, building: 'A', walking: true });
  expect(state.blockers).toBeGreaterThan(0);
  await expect(page.locator('#crosshair')).toBeVisible();
  await expect(page.locator('#turnbadge')).toBeVisible();

  const before = state.walker;
  await page.keyboard.down('KeyW');
  await page.waitForTimeout(300);
  await page.keyboard.up('KeyW');
  const after = (await walkDebug(page)).walker;
  expect(after.x !== before.x || after.z !== before.z).toBe(true);

  await page.keyboard.press('Escape');
  await expect.poll(async () => (await walkDebug(page)).state.walking).toBe(false);
  await expect(page.locator('[data-view="orbit"]')).toHaveClass(/on/);
  await expect(page.locator('#crosshair')).toBeHidden();
  expectNoUnexpectedConsole(messages);
});

test('deep link restores scope and room; a no-ref finding does not invent a room', async ({ page }) => {
  const messages = monitorConsole(page);
  await loadWalkthrough(
    page,
    `${WALKTHROUGH_PATH}#building=B&floor=floor-3&frontage=10000&bays=2&view=orbit&room=flex_b&filter=warning&wheels=1&all=1`
  );

  let state = await walkDebug(page);
  expect(state.variant).toBe('f10000_g2');
  expect(state.state).toMatchObject({
    building: 'B', floor: 'floor-3', room: 'flex_b', filter: 'warning', wheels: true,
  });
  expect(state.inspectorOpen).toBe(true);
  await expect(page.locator('#info .name')).toBeVisible();
  await expect(page.locator('#room-list [data-room="flex_b"]')).toHaveAttribute('aria-pressed', 'true');

  await page.goto('about:blank');
  await loadWalkthrough(
    page,
    `${WALKTHROUGH_PATH}#building=A&floor=floor-1&frontage=7000&bays=1&view=orbit`
  );
  const noRef = page.locator('#rules .f').filter({ hasText: 'CAPACITY_OVERFLOW' });
  await expect(noRef).toHaveCount(1);
  await noRef.click();
  await expect(page.locator('#info')).toContainText('沒有可定位的單一房間 reference');
  state = await walkDebug(page);
  expect(state.variant).toBe('f7000_g1');
  expect(state.state.room).toBe('');
  expect(state.inspectorOpen).toBe(true);
  expectNoUnexpectedConsole(messages);
});

test('390x844 mobile layout stays readable and supports room selection', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await loadWalkthrough(page);

  await expect(page.locator('#app')).toHaveCSS('grid-template-columns', '390px');
  await expect(page.locator('details.controls')).toBeHidden();
  await expect(page.getByRole('img', { name: /舊版參數化走入式三維模型/ })).toBeVisible();
  const metrics = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    bodyWidth: document.body.scrollWidth,
    stage: document.querySelector('#stage').getBoundingClientRect().toJSON(),
    panel: document.querySelector('#panel').getBoundingClientRect().toJSON(),
  }));
  expect(metrics.bodyWidth).toBeLessThanOrEqual(metrics.innerWidth);
  expect(metrics.stage.width).toBe(390);
  expect(metrics.panel.width).toBe(390);

  await page.locator('#buildings [data-building="B"]').click();
  await page.locator('#floors [data-floor="floor-2"]').click();
  await page.locator('#room-list [data-room]').first().click();
  const state = await walkDebug(page);
  expect(state.state).toMatchObject({ building: 'B', floor: 'floor-2' });
  expect(state.inspectorOpen).toBe(true);
  await expect(page.locator('#inspector')).toBeVisible();
  const toggle = page.locator('#mobile-panel-toggle');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#app')).toHaveClass(/panel-collapsed/);
  expect((await walkDebug(page)).panelCollapsed).toBe(true);
  const collapsed = await page.evaluate(() => ({
    stageHeight: document.querySelector('#stage').getBoundingClientRect().height,
    panelHeight: document.querySelector('#panel').getBoundingClientRect().height,
  }));
  expect(collapsed.stageHeight).toBeGreaterThan(760);
  expect(collapsed.panelHeight).toBeLessThan(60);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('walkthrough remains self-contained when opened over file://', async ({ page }) => {
  const messages = monitorConsole(page);
  const fileUrl = pathToFileURL(
    path.join(REPO_ROOT, 'structured', 'parametric', 'walkthrough.html')
  ).href;
  await loadWalkthrough(page, fileUrl);

  await expect(page).toHaveURL(/^file:\/\//);
  await expect(page).toHaveTitle('參數化平面 · 走入式 3D');
  expect((await walkDebug(page)).variant).toBe('f6000_g1');
  await page.locator('#buildings [data-building="C"]').click();
  await page.locator('#floors [data-floor="floor-rf"]').click();
  expect((await walkDebug(page)).state).toMatchObject({ building: 'C', floor: 'floor-rf' });
  expectNoUnexpectedConsole(messages);
});
