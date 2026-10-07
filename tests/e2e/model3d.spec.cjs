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

test('shared facade HTML opens a complete exterior and reversible indoor room view', async ({page})=>{
  const messages=monitorConsole(page);
  await page.goto('/BbuildingView.html#facade-proposal');
  const panel=page.locator('.shared-facade-proposal');
  await expect(panel).toHaveAttribute('data-geometry-source','tour_mm');
  await expect.poll(()=>panel.locator('img').first().evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
  const shared=await page.evaluate(()=>window.HOUSE_CONCEPT_LAYOUT.facade);
  const record=shared.buildings.find(b=>b.id==='B');
  await expect(panel.locator('[data-facade-pending-id]')).toHaveCount(record.pending.length);
  await panel.locator('.facade-exterior-link').click();
  await expect(page).toHaveURL(/view=exterior/);
  let debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.state).toEqual({building:'B',floor:'',room:'',view:'exterior'});
  expect(debug.facade.allFloors).toHaveLength(4);
  expect(debug.facade.componentIds.sort()).toEqual(record.components.filter(c=>c.rendered).map(c=>c.id).sort());
  expect(debug.facade.compliance).toBe('unknown');expect(debug.furniture.visibleItems).toBe(0);
  expect(debug.tour.rooms.every(r=>!r.architectureVisible)).toBe(true);
  expect(debug.facade.screenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1)).toBe(true);
  await page.locator('#exterior-oblique').click();await expect(page).toHaveURL(/angle=oblique/);
  await page.locator('#scope-buildings [data-building="overview"]').click();
  debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.facade.allFloors).toHaveLength(12);expect(debug.visibleRooms).toHaveLength(105);
  await page.reload();debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.facade.active).toBe(true);expect(debug.facade.angle).toBe('oblique');
  await page.locator('#scope-buildings [data-building="B"]').click();
  await page.locator('#scope-floors [data-floor="floor-1"]').click();
  debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.facade.active).toBe(false);expect(debug.state.floor).toBe('floor-1');
  expect(debug.visibleRooms).toContain('B:floor-1:storage');expect(debug.visibleRooms).toContain('B:floor-1:shrine');
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Amaster-bath&view=front&focus=room');
  await page.locator('#architecture').uncheck();await page.locator('#navigation').uncheck();
  for(const [id,value] of [['cut','900'],['explode','600']])await page.locator('#'+id).evaluate((input,v)=>{
    input.value=v;input.dispatchEvent(new Event('input',{bubbles:true}));
  },value);
  const before=await page.evaluate(()=>window.__htmlModel3dDebug());
  await page.locator('#view-exterior').click();await page.locator('#exterior-return').click();
  const after=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(after.state).toEqual(before.state);expect(after.roomCloseup).toBe(true);
  expect(after.facade.controls).toEqual(before.facade.controls);
  expect(after.furniture.pendingItems).toEqual(before.furniture.pendingItems);
  await assertNoFrameworkOverlay(page);expectNoUnexpectedConsole(messages);
});

test('mobile exterior share link ignores stale room selection and provides a stage-level indoor return',async({page})=>{
  const messages=monitorConsole(page);
  await page.setViewportSize({width:390,height:844});
  await page.goto('/structured/candidates/model3d.html#mode=diagnostic&building=C&floor=floor-1&room=A:floor-2:master-bath&view=exterior&angle=oblique');
  await page.locator('#mobile-panel-toggle').click();
  await expect.poll(()=>page.evaluate(()=>window.__htmlModel3dDebug().facade.screenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1))).toBe(true);
  let debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.state).toEqual({building:'C',floor:'',room:'',view:'exterior'});expect(debug.presentation).toBe('tour');
  expect(debug.facade.allFloors).toHaveLength(4);expect(debug.furniture.items).toBe(129);
  await expect(page.locator('#exterior-return')).toBeVisible();
  await page.locator('#exterior-return').click();
  debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.facade.active).toBe(false);expect(debug.state).toEqual({building:'C',floor:'floor-1',room:'',view:'front'});
  expect(debug.visibleRooms).toContain('C:floor-1:elder');
  expect(debug.facade.controls.navigation.checked).toBe(true);expect(debug.facade.controls['full-walls'].checked).toBe(false);
  await assertNoFrameworkOverlay(page);expectNoUnexpectedConsole(messages);
});

test('whole-floor tour defaults to complete A 1F care proposal without falsely credited parking', async ({ page }) => {
  const messages=monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html');
  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  const debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.presentation).toBe('tour');
  expect(debug.state).toEqual({building:'A',floor:'floor-1',room:'',view:'front'});
  expect(debug.visibleRooms).toHaveLength(9);
  expect(debug.visibleRooms).toContain('A:floor-1:flex1');
  expect(debug.visibleRooms).toContain('A:floor-1:bath1');
  expect(debug.visibleRooms).not.toContain('A:floor-1:garage');
  expect(debug.furniture.shapes.filter(i=>['car','motorcycle'].includes(i.shape)&&i.visible)).toHaveLength(0);
  expect(debug.furniture.shapes.filter(i=>i.id.startsWith('A:floor-1:flex1:')&&i.visible).map(i=>i.shape))
    .toEqual(expect.arrayContaining(['bed','cabinet']));
  const care=debug.layoutReview.checks.find(c=>c.id==='A-1F-care-functions');
  expect(care.site_legality).toBe('unknown');
  expect(care.professional_accessibility).toBe('unknown');
  expect(care.routes.elder_to_bath).toEqual(['A:floor-1:flex1','A:floor-1:rear-hall1','A:floor-1:bath1']);
  expect(debug.tour.rooms.find(r=>r.id==='A:floor-1:living').features.hvac.indoor).toBe(true);
  expect(debug.tour.rooms.filter(r=>!r.outdoor).every(r=>r.architectureParts>0)).toBe(true);
  await expect(page.locator('#tour-notice')).toContainText('A 棟已補回一樓孝親房與淋浴');
  await expect(page.locator('#tour-notice')).toContainText('主案不計車位');
  await expect(page.locator('#stage-title')).toContainText('與 HTML 共用家具圖同步');
  await expect(page.locator('.nav-label.entry:visible')).toContainText(['主入口（示意）']);
  for(const [x,y] of debug.screenBounds){expect(Math.abs(x)).toBeLessThan(1);expect(Math.abs(y)).toBeLessThan(1);}
  await page.locator('#architecture').uncheck();
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).tour.rooms.every(r=>!r.architectureVisible)).toBe(true);
  await page.locator('#architecture').check();
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).tour.rooms.filter(r=>!r.outdoor).every(r=>r.architectureVisible)).toBe(true);
  await page.locator('#full-walls').check();
  await page.locator('#full-walls').uncheck();
  await assertNoFrameworkOverlay(page);
  expectNoUnexpectedConsole(messages);
});

test('tour prioritizes B worship/transport and C care without falsely fitting cars in the arcade',async({page})=>{
  const messages=monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html');
  await page.locator('#tour-actions').getByRole('link',{name:'B 棟完整 1F',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.__htmlModel3dDebug().state.building)).toBe('B');
  let debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.visibleRooms).toHaveLength(10);
  expect(debug.visibleRooms).toContain('B:floor-1:shrine');
  expect(debug.furniture.shapes.find(i=>i.shape==='palanquin')).toMatchObject({width:1200,depth:1700});
  await page.locator('#tour-actions').getByRole('link',{name:'C 棟完整 1F',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.__htmlModel3dDebug().state.building)).toBe('C');
  debug=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(debug.visibleRooms).toHaveLength(11);
  expect(debug.furniture.shapes.filter(i=>['car','motorcycle'].includes(i.shape)&&i.visible)).toHaveLength(0);
  expect(debug.tour.rooms.find(r=>r.id==='C:floor-1:elder').features.hvac.indoor).toBe(true);
  expect(debug.tour.rooms.some(r=>r.id==='C:floor-1:front-service')).toBe(false);
  const living = debug.tour.rooms.find(r=>r.id==='C:floor-1:living');
  expect(living.features.hvac_units[0].route.outdoor_room).toBe('C:floor-2:balcony2f');
  expect(living.features.hvac_units[0].route.compliance).toBe('unknown');
  const elder = debug.tour.rooms.find(r=>r.id==='C:floor-1:elder');
  expect(elder.features.hvac_units[0].route.outdoor_room).toBe('C:floor-2:rear-service');
  expect(elder.features.hvac_units[0].route.compliance).toBe('unknown');
  await expect(page.locator('#layout-review-note')).toContainText('兩車＋機車');
  expectNoUnexpectedConsole(messages);
});

test('room entry, full-floor return and next-storey navigation preserve the chosen scope in URL',async({page})=>{
  const messages=monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front');
  await page.locator('#scope-rooms [data-room="C:floor-1:elder"]').click();
  await expect(page.locator('#info')).toContainText('床頭不直吹');
  await expect(page.locator('#info')).toContainText('綠色門框為入口提案');
  await expect(page.locator('.furniture-label:visible')).toHaveCount(3);
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).visibleRooms).toHaveLength(11);
  await page.locator('#back-to-floor').click();
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).state.room).toBe('');
  await page.locator('#next-storey').click();
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).state.floor).toBe('floor-2');
  await expect(page).toHaveURL(/mode=tour/);
  await page.reload();
  expect((await page.evaluate(()=>window.__htmlModel3dDebug())).state.floor).toBe('floor-2');
  await page.locator('#scope-floors [data-floor="floor-4"]').click();
  await expect(page.locator('#next-storey')).toBeDisabled();
  expectNoUnexpectedConsole(messages);
});

test('whole-floor tour mobile labels and room selection stay readable without hiding the floor', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front');
  await page.locator('#mobile-panel-toggle').click();
  await expect(page.locator('#mobile-panel-toggle')).toHaveAttribute('aria-expanded', 'false');
  const hiddenAElder = page.locator('.nav-label.room[data-room="A:floor-1:flex1"]');
  await expect(hiddenAElder).toHaveCount(1);
  await expect(hiddenAElder).toContainText('孝親房');
  await expect(hiddenAElder).toBeHidden();
  const cElder = page.locator('.nav-label.room[data-room="C:floor-1:elder"]');
  await expect(cElder).toHaveCount(1);
  await expect(cElder).toContainText('孝親房');
  await expect(cElder).toBeVisible();
  await cElder.click();
  await expect(page).toHaveURL(/room=C%3Afloor-1%3Aelder/);
  await expect(page.locator('.furniture-label:visible')).toHaveCount(2);
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).visibleRooms).toHaveLength(11);
  await expect.poll(async () => page.locator('.nav-label:visible, .furniture-label:visible').evaluateAll((elements) => {
    const rects = elements.map(element => element.getBoundingClientRect());
    return rects.every(rect => rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight)
      && rects.every((a, index) => rects.slice(index + 1).every(b =>
        Math.min(a.right, b.right) <= Math.max(a.left, b.left) || Math.min(a.bottom, b.bottom) <= Math.max(a.top, b.top)));
  })).toBe(true);
  await assertNoFrameworkOverlay(page);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('mobile room closeup uses shared geometry, keeps floor context and restores through the URL', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&room=C%3Afloor-1%3Aelder&view=front');
  await page.locator('#mobile-panel-toggle').click();
  const before = await page.evaluate(() => window.__htmlModel3dDebug());
  await page.locator('#focus-room').click();
  await expect(page.locator('#focus-room')).toHaveAttribute('aria-pressed', 'true');
  await expect(page).toHaveURL(/focus=room/);
  await expect.poll(async () => page.evaluate(() => {
    const debug = window.__htmlModel3dDebug();
    return debug.roomCloseup && debug.focusedScreenBounds.every(([x, y]) => Math.abs(x) < 1 && Math.abs(y) < 1);
  })).toBe(true);
  const focused = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(focused.visibleRooms).toEqual(before.visibleRooms);
  expect(focused.furniture.shapes).toEqual(before.furniture.shapes);
  await expect.poll(async () => page.locator('.nav-label:visible').evaluateAll(labels =>
    labels.length > 0 && labels.every(label => label.getAttribute('data-room') === 'C:floor-1:elder'))).toBe(true);
  await page.reload();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).roomCloseup).toBe(true);
  await page.locator('#view-plan').click();
  await page.locator('#mobile-panel-toggle').click();
  await expect(page.locator('#focus-room')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#room-overview').click();
  const overview = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(overview.state.room).toBe('');
  expect(overview.roomCloseup).toBe(false);
  expect(overview.visibleRooms).toEqual(before.visibleRooms);
  await expect(page.locator('#room-view-actions')).toBeHidden();
  expectNoUnexpectedConsole(messages);
  await context.close();
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`room cutaway clears architecture at fixture bodies and restores full walls (${viewport.width}px)`, async ({ browser }) => {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const messages = monitorConsole(page);
    await page.goto('/structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Amaster-bath&view=front');
    const before = await page.evaluate(() => window.__htmlModel3dDebug());
    await page.locator('#focus-room').click();
    let focused = await page.evaluate(() => window.__htmlModel3dDebug());
    const checkBodies = debug => {
      expect(debug.roomCutaway.active).toBe(true);
      expect(debug.roomCutaway.heightMm).toBe(550);
      expect(debug.roomCutaway.fixtureSightlines).toHaveLength(3);
      expect(debug.roomCutaway.fixtureSightlines.every(i => i.samples === 5 && i.unobstructedSamples >= 3)).toBe(true);
    };
    checkBodies(focused);
    expect(focused.visibleRooms).toEqual(before.visibleRooms);
    expect(focused.tour.rooms).toEqual(before.tour.rooms);
    expect(focused.furniture.shapes).toEqual(before.furniture.shapes);
    expect(focused.roomCutaway.parts.some(p => p.room !== 'A:floor-2:master-bath')).toBe(true);
    await expect(page.locator('#room-cutaway-status')).toContainText('非拆牆');
    await page.locator('#room-cutaway').uncheck();
    expect((await page.evaluate(() => window.__htmlModel3dDebug())).roomCutaway.parts).toEqual([]);
    await expect(page.locator('#room-cutaway-status')).toBeHidden();
    await page.locator('#room-cutaway').check();
    await page.locator('#full-walls').check();
    let restored = await page.evaluate(() => window.__htmlModel3dDebug());
    expect(restored.roomCutaway.active).toBe(false);
    expect(restored.roomCutaway.parts).toEqual([]);
    await page.locator('#full-walls').uncheck();
    if (viewport.width < 860) await page.locator('#mobile-panel-toggle').click();
    focused = await page.evaluate(() => window.__htmlModel3dDebug());
    checkBodies(focused);
    const canvas = await page.locator('#canvas').boundingBox();
    await page.mouse.move(canvas.x + canvas.width * .15, canvas.y + canvas.height * .8);
    await page.mouse.down();
    await page.mouse.move(canvas.x + canvas.width * .75, canvas.y + canvas.height * .8, { steps: 8 });
    await page.mouse.up();
    const rotated = await page.evaluate(() => window.__htmlModel3dDebug());
    checkBodies(rotated);
    expect(rotated.roomCutaway.parts).not.toEqual(focused.roomCutaway.parts);
    expect(rotated.furniture.shapes).toEqual(focused.furniture.shapes);
    await page.reload();
    checkBodies(await page.evaluate(() => window.__htmlModel3dDebug()));
    await page.locator('#room-overview').click();
    restored = await page.evaluate(() => window.__htmlModel3dDebug());
    expect(restored.roomCutaway.active).toBe(false);
    expect(restored.roomCutaway.parts).toEqual([]);
    expect(restored.visibleRooms).toEqual(before.visibleRooms);
    await assertNoFrameworkOverlay(page);
    expectNoUnexpectedConsole(messages);
    await context.close();
  });
}

test('mobile C-to-A hash navigation retains the complete shared floor and collapsed-panel closeup', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  const source = fs.readFileSync(path.join(REPO_ROOT, 'structured/candidates/furniture-plans/layout.js'), 'utf8');
  const shared = JSON.parse(source.replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const floor = shared.buildings.find(b => b.id === 'A').floors.find(f => f.id === 'floor-2');
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front');
  await page.locator('#mobile-panel-toggle').click();
  await expect(page.locator('#mobile-panel-toggle')).toHaveAttribute('aria-expanded', 'false');
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Amaster-bath&view=front&focus=room');
  await expect(page.locator('#mobile-panel-toggle')).toHaveAttribute('aria-expanded', 'false');
  await expect.poll(() => page.evaluate(() => {
    const stage = document.getElementById('stage'), canvas = document.getElementById('canvas');
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const debug = window.__htmlModel3dDebug();
    return debug.state.building === 'A' && debug.state.floor === 'floor-2' &&
      debug.state.room === 'A:floor-2:master-bath' && debug.roomCloseup &&
      debug.panelCollapsed && stage.clientHeight >= innerHeight - 84 &&
      Math.abs(canvas.width - stage.clientWidth * ratio) <= 1 && Math.abs(canvas.height - stage.clientHeight * ratio) <= 1 &&
      debug.focusedScreenBounds.length === 8 && debug.focusedScreenBounds.every(([x, y]) => Math.abs(x) < 1 && Math.abs(y) < 1);
  })).toBe(true);
  const debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.state).toEqual({ building: 'A', floor: 'floor-2', room: 'A:floor-2:master-bath', view: 'front' });
  expect(debug.visibleRooms.slice().sort()).toEqual(floor.rooms.map(r => r.id).sort());
  const wardrobes = ['A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right'];
  expect(debug.furniture.pendingItems.slice().sort()).toEqual(wardrobes);
  for (const id of wardrobes) expect(debug.furniture.shapes.filter(i => i.id === id))
    .toEqual([expect.objectContaining({ visible: false, width: 1800, depth: 600, height: 2200 })]);
  expect(debug.roomCutaway.active).toBe(true);
  expect(debug.roomCutaway.fixtureSightlines).toHaveLength(3);
  expect(debug.roomCutaway.fixtureSightlines.every(i => i.unobstructedSamples >= 3)).toBe(true);
  await assertNoFrameworkOverlay(page);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('original HTML model3d viewer loads and its primary controls respond', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=interior&building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=front', { waitUntil: 'load' });

  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect(page.getByRole('heading', { name: '原設計 HTML · 三棟 3D 對照' })).toBeVisible();
  await expect(page.locator('canvas#canvas')).toBeVisible();
  await expect(page.getByRole('img', { name: /原始 HTML 草圖/ })).toBeVisible();
  await expect(page.locator('#subtitle')).not.toBeEmpty();
  await expect(page.locator('#compare')).toContainText('只在 HTML：側院');
  await expect(page.locator('#orientation')).toContainText('道路／前方');
  await page.locator('summary').filter({ hasText: '來源、限制與原 HTML 連結' }).click();
  await expect(page.locator('a[href="../parametric/walkthrough.html"]')).toBeVisible();
  await expect(page.locator('#furniture')).toBeChecked();
  await expect(page.locator('#furniture-status')).toContainText('61 個空間、129 件');
  await expect(page.locator('#furniture-status')).toContainText('連結實物清單 1 件（待實測 1 件）');
  await expect(page.locator('#furniture-status')).toContainText('目前幾何下');
  await expect(page.locator('#furniture-start')).toContainText('家具無碰撞不代表');
  await expect(page.locator('a[href="../predesign/consistency-review.html"]')).toBeVisible();
  const furnitureState = await page.evaluate(() => window.__htmlModel3dDebug().furniture);
  expect(furnitureState.visible).toBe(true);
  expect(furnitureState.items).toBe(129);
  expect(furnitureState.issues.overflow).toBeGreaterThan(0);
  await assertNoFrameworkOverlay(page);

  await page.locator('#geom-source [data-geom="declared"]').click();
  await expect(page.locator('#geom-source [data-geom="declared"]')).toHaveClass(/on/);
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).furniture.visibleIssues).toBe(0);
  await page.locator('#presentation-mode [data-presentation="diagnostic"]').click();
  await page.locator('#color-mode [data-mode="provenance"]').click();
  await expect(page.locator('#color-mode [data-mode="provenance"]')).toHaveClass(/on/);
  await page.locator('#view-plan').click();
  await expect(page.locator('#view-plan')).toHaveClass(/on/);
  await expect(page.locator('#compass')).toContainText('俯視');
  await expect(page.locator('#compass')).toContainText('上方是道路');
  await page.locator('#openings').check();
  await expect(page.locator('#openings')).toBeChecked();
  await page.locator('#furniture').uncheck();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).furniture.visible).toBe(false);
  expectNoUnexpectedConsole(messages);
});

test('interior default isolates A living room and names recognizable full-size furniture', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=interior&building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=front', { waitUntil: 'load' });
  const debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.presentation).toBe('interior');
  expect(debug.state).toEqual({ building: 'A', floor: 'floor-1', room: 'A:floor-1:living', view: 'front' });
  expect(debug.visibleRooms).toEqual(['A:floor-1:living']);
  expect(debug.geomSource).toBe('declared');
  expect(debug.furniture.visibleItems).toBe(1);
  expect(debug.furniture.visibleIssues).toBe(0);
  for (const corner of debug.screenBounds) {
    expect(Math.abs(corner[0])).toBeLessThan(1);
    expect(Math.abs(corner[1])).toBeLessThan(1);
  }
  expect(debug.furniture.shapes.map(({ shape, parts }) => [shape, parts])).toEqual([
    ['sofa', 7], ['tv-console', 3], ['dining-set', 18],
  ]);
  expect(debug.furniture.shapes[0]).toMatchObject({ width: 2400, depth: 900, height: 850 });
  await expect(page.locator('#grid')).not.toBeChecked();
  await expect(page.locator('#ghost')).not.toBeChecked();
  await expect(page.locator('#openings')).toBeDisabled();
  await expect(page.locator('.furniture-label:visible')).toHaveCount(1);
  await expect(page.locator('#stage-title')).toContainText('非實測房型／正式牆位');
  await page.locator('#furniture-list [data-furniture-id="A:floor-1:living:furniture:sofa"]').click();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).selectedFurniture)
    .toBe('A:floor-1:living:furniture:sofa');
  await expect(page.locator('#info')).toContainText('三人沙發 · 2400 × 900 × 850 mm');
  // Selection is still possible for a pending item via the complete list.
  await expect(page.locator('#furniture-list')).toContainText('待調整');
  await page.locator('#furniture-names').uncheck();
  await expect(page.locator('.furniture-label:visible')).toHaveCount(0);
  await page.locator('#furniture-names').check();
  await expect(page.locator('.furniture-label:visible')).toHaveCount(1);
  await page.locator('#geom-source [data-geom="auto"]').click();
  const point = (await page.evaluate(() => window.__htmlModel3dDebug())).furniture.visibleScreenPositions
    .find((item) => item.id === 'A:floor-1:living:furniture:tv');
  const canvas = await page.locator('#canvas').boundingBox();
  await page.mouse.click(canvas.x + (point.hitX + 1) * canvas.width / 2, canvas.y + (1 - point.hitY) * canvas.height / 2);
  const picked = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(picked.selectedFurniture).toBe('A:floor-1:living:furniture:tv');
  expect(picked.geomSource).toBe('auto');
  await expect(page.locator('#geom-source [data-geom="auto"]')).toHaveClass(/on/);
  await assertNoFrameworkOverlay(page);
  expectNoUnexpectedConsole(messages);
});

test('every detailed furniture part stays inside the unchanged catalog envelope', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=interior&building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=front', { waitUntil: 'load' });
  await page.locator('#scope-buildings [data-building="overview"]').click();
  const { shapes } = (await page.evaluate(() => window.__htmlModel3dDebug())).furniture;
  expect(shapes).toHaveLength(129);
  const tolerance = 0.000001; // metres; floating-point rounding only
  for (const item of shapes) {
    const limit = [item.width / 2000, item.height / 1000, item.depth / 2000];
    for (const part of item.partBounds) {
      for (let axis = 0; axis < 3; axis += 1) {
        expect(part.min[axis], `${item.id} part min axis ${axis}`)
          .toBeGreaterThanOrEqual((axis === 1 ? 0 : -limit[axis]) - tolerance);
        expect(part.max[axis], `${item.id} part max axis ${axis}`)
          .toBeLessThanOrEqual(limit[axis] + tolerance);
      }
    }
  }
  // Rounded upholstery must retain its full external extent, not shrink to fit.
  const sofa = shapes.find((item) => item.id === 'A:floor-1:living:furniture:sofa');
  expect(sofa.partBounds[0].max[0] - sofa.partBounds[0].min[0]).toBeCloseTo(2.4, 5);
  const bed = shapes.find((item) => item.id === 'C:floor-3:master3f:furniture:bed');
  expect(bed).toMatchObject({ shape: 'bed', parts: 6, width: 1800, depth: 2000, height: 950 });
  expect(shapes.find((item) => item.shape === 'tank')).toMatchObject({ parts: 2 });
  expectNoUnexpectedConsole(messages);
});

test('unresolved upstairs furniture stays listed at its real size and conflict display is explicit', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Awalkin&view=front');
  const initial = await page.evaluate(() => window.__htmlModel3dDebug());
  const unresolved=initial.furniture.shapes.filter(i=>i.id.startsWith('A:floor-2:walkin:'));
  expect(unresolved).toHaveLength(2);
  expect(unresolved.every(i=>!i.visible && i.width===1800 && i.depth===600)).toBe(true);
  await expect(page.locator('#furniture-list .furniture-row.issue')).toHaveCount(2);
  await expect(page.locator('#furniture-list')).toContainText('1800');
  await expect(page.locator('#pending-furniture')).toContainText('未展示');
  await page.locator('#show-conflicts').check();
  const shown = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(shown.furniture.shapes.filter(i=>i.id.startsWith('A:floor-2:walkin:')).every(i=>i.visible && i.collision)).toBe(true);
  expect(shown.furniture.shapes.map(({ id, width, depth, height }) => ({ id, width, depth, height })))
    .toEqual(initial.furniture.shapes.map(({ id, width, depth, height }) => ({ id, width, depth, height })));
  await page.locator('#show-conflicts').uncheck();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).furniture.shapes
    .filter(i=>i.id.startsWith('A:floor-2:walkin:')).every(i=>!i.visible)).toBe(true);
  expectNoUnexpectedConsole(messages);
});

test('room geometry changes recompute pending furniture without changing its dimensions', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#building=C&floor=floor-3&room=C%3Afloor-3%3Amaster3f&view=front');
  const declared = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(declared.furniture.visibleItems).toBe(3);
  expect(declared.furniture.pendingItems).toHaveLength(0);
  await page.locator('#geom-source [data-geom="auto"]').click();
  const automatic = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(automatic.furniture.pendingItems.length).toBeGreaterThan(0);
  expect(automatic.furniture.visibleIssues).toBe(0);
  await expect(page.locator('#furniture-list')).toContainText('未展示');
  expect(automatic.furniture.shapes.map(({ width, depth, height }) => [width, depth, height]))
    .toEqual(declared.furniture.shapes.map(({ width, depth, height }) => [width, depth, height]));
  await page.locator('#geom-source [data-geom="declared"]').click();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).furniture.pendingItems).toHaveLength(0);
  await expect(page.locator('#pending-furniture')).toContainText('正式搬運／照護淨空仍待核對');
  expectNoUnexpectedConsole(messages);
});

test('interior floor scope uses HTML grid and does not leak furniture from hidden floors', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=interior&building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=front');
  await page.locator('#scope-buildings [data-building="C"]').click();
  let debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.geomSource).toBe('auto');
  expect(debug.state.room).toBe('');
  expect(debug.furniture.shapes.every((item) => item.id.startsWith('C:floor-1:'))).toBe(true);
  await expect(page.locator('#geom-source [data-geom="declared"]')).toBeDisabled();
  await page.locator('#scope-floors [data-floor="floor-3"]').click();
  debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.furniture.shapes.every((item) => item.id.startsWith('C:floor-3:'))).toBe(true);
  await page.locator('#scope-rooms [data-room="C:floor-3:master3f"]').click();
  await expect(page.locator('#geom-source [data-geom="declared"]')).toBeEnabled();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).visibleRooms).toEqual(['C:floor-3:master3f']);
  await page.locator('#floor-visibility input[type="checkbox"]').first().check();
  debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.geomSource).toBe('auto');
  expect(debug.state.room).toBe('');
  await expect(page.locator('#geom-source [data-geom="auto"]')).toHaveClass(/on/);
  await expect(page.locator('#geom-source [data-geom="declared"]')).toBeDisabled();
  expect(debug.furniture.shapes.every((item) => /^(A:floor-1:|C:floor-3:)/.test(item.id))).toBe(true);
  expectNoUnexpectedConsole(messages);
});

test('interior mobile room refits without clipping and keeps unresolved count when controls collapse', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Awalkin&view=front');
  await page.locator('#mobile-panel-toggle').click();
  await expect(page.locator('#pending-furniture')).toContainText('未展示');
  await expect(page.locator('#mobile-panel-toggle')).toHaveAttribute('aria-expanded', 'false');
  await page.goto('/structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&room=C%3Afloor-1%3Aelder&view=front');
  await page.locator('#mobile-panel-toggle').click();
  await expect.poll(async () => {
    const { screenBounds } = await page.evaluate(() => window.__htmlModel3dDebug());
    return screenBounds.every(([x, y]) => Math.abs(x) < 1 && Math.abs(y) < 1);
  }).toBe(true);
  await expect(page.locator('.furniture-label:visible')).toHaveCount(2);
  const labels = await page.locator('.furniture-label:visible').evaluateAll((elements) => elements.map((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right };
  }));
  for (const label of labels) {
    expect(label.left).toBeGreaterThanOrEqual(0);
    expect(label.right).toBeLessThanOrEqual(390);
  }
  expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(390);
  expectNoUnexpectedConsole(messages);
  await context.close();
});

test('furniture shortcuts select shared concept rooms with all standard-size furniture', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/structured/candidates/model3d.html', { waitUntil: 'load' });
  for (const [label, room, count] of [
    ['A 棟客廳', 'A:floor-1:living', 3],
    ['B 棟神明堂', 'B:floor-1:shrine', 5],
    ['B 棟武轎儲藏室', 'B:floor-1:storage', 5],
    ['C 棟孝親房', 'C:floor-1:elder', 3],
  ]) {
    await page.locator('#furniture-start').getByRole('link', { name: label, exact: true }).click();
    await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room)).toBe(room);
    const debug = await page.evaluate(() => window.__htmlModel3dDebug());
    expect(debug.state.view).toBe('plan');
    expect(debug.presentation).toBe('tour');
    expect(debug.furniture.shapes.filter(i=>i.id.startsWith(room+':furniture:')&&i.visible)).toHaveLength(count);
  }
  expectNoUnexpectedConsole(messages);
});

test('B palanquin uses the shared physical-item estimate and labels it pending measurement', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/BbuildingView.html#room-storage', { waitUntil: 'load' });
  const storagePlan = page.locator('.plan-cell[data-model-room-id="B:floor-1:storage"]');
  const sharedStorage = page.locator('.shared-furniture-plan details[data-model-room-id="B:floor-1:storage"]');
  await sharedStorage.locator('summary').click();
  await expect(sharedStorage.locator('li[data-furniture-id]')).toHaveCount(5);
  await expect(sharedStorage.locator('[data-physical-item-id="B.palanquin.primary"]')).toHaveAttribute('data-measurement-state','pending');
  await expect(storagePlan).toContainText('暫定淨開口150cm');
  await expect(storagePlan).toContainText('直進直出');

  await page.goto(
    '/structured/candidates/model3d.html#mode=tour&building=B&floor=floor-1&room=B%3Afloor-1%3Astorage&view=plan',
    { waitUntil: 'load' },
  );

  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room))
    .toBe('B:floor-1:storage');
  await expect(page.locator('#info')).toContainText('武轎（收納狀態）：1200 × 1700 × 1800 mm');
  await expect(page.locator('#info')).toContainText('一般尺寸暫估／待實測');
  await expect(page.locator('#info')).toContainText('法器／旗幟櫃');
  await expect(page.locator('#info')).toContainText('香燭金紙耐燃櫃');
  const debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.presentation).toBe('tour');
  expect(debug.furniture.shapes.filter(item => item.id.startsWith('B:floor-1:storage:furniture:') && item.visible)).toHaveLength(5);
  const room = debug.tour.rooms.find(r=>r.id==='B:floor-1:storage');
  expect(room.features.carry_path_mm).toEqual({center_x_mm:5200,width_mm:1600});
  expect(room.features.doors[0].width_mm).toBe(1500);
  expectNoUnexpectedConsole(messages);
});

test('A B C HTML furniture plans link to identical room geometry and actual 3D placements', async ({ page }) => {
  const messages = monitorConsole(page);
  for (const building of ['A', 'B', 'C']) {
    await page.goto(`/${building}buildingView.html`, { waitUntil: 'load' });
    await expect(page.locator('.shared-furniture-plan')).toHaveCount(4);
    await page.locator('.floor-tabs [aria-controls="floor-1"]').click();
    const floors = await page.evaluate(id => window.HOUSE_CONCEPT_LAYOUT.buildings
      .find(b => b.id === id).floors, building);
    const panel = page.locator('#floor-1 .shared-furniture-plan');
    await expect(panel.locator('img')).toBeVisible();
    await expect.poll(() => panel.locator('img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
    await panel.getByRole('link', { name: '在 3D 核對這一層', exact: true }).click();
    for(const currentFloor of floors){
      await page.locator('#scope-floors [data-floor="'+currentFloor.id+'"]').click();
      const debug = await page.evaluate(() => window.__htmlModel3dDebug());
      expect(debug.state.floor).toBe(currentFloor.id);
      expect(debug.presentation).toBe('tour');
      expect(debug.furniture.pendingItems.slice().sort()).toEqual(currentFloor.rooms.flatMap(r=>r.furniture)
        .filter(i=>i.placement.issues.length).map(i=>i.id).sort());
      for (const room of currentFloor.rooms) {
        const rendered = debug.tour.rooms.find(r => r.id === room.id);
        expect(rendered.geometry).toEqual(room.geometry);
        expect(rendered.features).toEqual(room.features);
        for (const item of room.furniture) {
          const actual = debug.furniture.shapes.find(i => i.id === item.id);
          expect(actual.visible).toBe(item.placement.issues.length===0);
          expect(actual.center[0]).toBeCloseTo(item.placement.center_x_mm, 2);
          expect(actual.center[1]).toBeCloseTo(item.placement.center_y_mm, 2);
          expect(actual.rotation).toBeCloseTo(item.placement.rotation_deg, 5);
          expect([actual.width, actual.depth, actual.height]).toEqual([item.width_mm, item.depth_mm, item.height_mm]);
        }
      }
      await assertNoFrameworkOverlay(page);
    }
  }
  expectNoUnexpectedConsole(messages);
});

test('original HTML room and 3D use a reversible deep link', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/AbuildingView.html#room-living', { waitUntil: 'load' });

  await expect(page.locator('.design-bridge')).toContainText('有界合理性提案 · A 棟');
  await expect(page.locator('#floor-1')).toHaveClass(/active/);
  await expect(page.locator('#room-living')).toHaveClass(/room-active/);
  await expect(page.locator('.design-bridge-floor-link')).toHaveCount(4);
  const roomLink = page.locator('#room-living .design-bridge-room-link');
  await expect(roomLink).toHaveAttribute('href', /model3d\.html#building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&mode=tour&view=plan/);

  await roomLink.click();
  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state)).toEqual({
    building: 'A', floor: 'floor-1', room: 'A:floor-1:living', view: 'plan',
  });
  await expect(page.locator('#scope-buildings [data-building="A"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#scope-floors [data-floor="floor-1"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#scope-rooms [data-room="A:floor-1:living"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#info')).toContainText('客餐廳');
  await expect(page.locator('#info')).toContainText('三人沙發');
  await expect(page.locator('#info')).toContainText('依房型推估');
  const shared=await page.evaluate(()=>window.__htmlModel3dDebug());
  expect(shared.presentation).toBe('tour');
  expect(shared.furniture.shapes.filter(i=>i.id.startsWith('A:floor-1:living:')&&i.visible)).toHaveLength(5);
  await expect(page.locator('#info')).toContainText('ABC v2 固定比較框');
  const backLink = page.locator('#info .info-link');
  await expect(backLink).toHaveAttribute('href', /AbuildingView\.html#proposal-room-living$/);

  await backLink.click();
  await expect(page).toHaveURL(/AbuildingView\.html#proposal-room-living$/);
  await expect(page.locator('#floor-1')).toHaveClass(/active/);
  await expect(page.locator('#proposal-room-living')).toHaveJSProperty('open', true);
  expectNoUnexpectedConsole(messages);
});

test('original HTML bridge and deep-linked model work over file protocol', async ({ page }) => {
  const messages = monitorConsole(page);
  const externalRequests = [];
  await page.route(/^https?:/, async (route) => {
    externalRequests.push(route.request().url());
    await route.abort();
  });
  const htmlUrl = `${pathToFileURL(path.join(REPO_ROOT, 'AbuildingView.html')).href}#room-living`;
  await page.goto(htmlUrl, { waitUntil: 'load' });

  await expect(page.locator('.design-bridge')).toBeVisible();
  await expect(page.locator('#room-living')).toHaveClass(/room-active/);
  await page.locator('#room-living .design-bridge-room-link').click();
  await expect(page).toHaveTitle('原設計 HTML · 三棟 3D 對照');
  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room))
    .toBe('A:floor-1:living');
  await page.locator('#view-front').click();
  expect((await page.evaluate(() => window.__htmlModel3dDebug())).presentation).toBe('tour');
  await expect(page.locator('.furniture-label:visible')).toHaveCount(5);
  expect(externalRequests).toEqual([]);
  expectNoUnexpectedConsole(messages);
});

test('A elder bedroom restoration keeps care furniture, bathroom and reversible HTML closeup', async ({ page }) => {
  const messages = monitorConsole(page);
  await page.goto('/AbuildingView.html#proposal-room-flex1', { waitUntil: 'load' });
  const elder = page.locator('#proposal-room-flex1');
  await expect(elder).toHaveJSProperty('open', true);
  await expect(elder).toHaveAttribute('data-requirement-id', 'A.floor-1.elder');
  await expect(elder).toContainText('雙人床');
  await expect(elder).toContainText('衣櫃');
  await expect(page.locator('[data-care-function-check]')).toContainText('主案不計車位');
  await elder.getByRole('link', { name: '在 3D 核對家具', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room)).toBe('A:floor-1:flex1');
  await expect(page.locator('#info')).toContainText('孝親房');
  await expect(page.locator('#info')).toContainText('A.floor-1.elder');
  await page.locator('#focus-room').click();
  const debug = await page.evaluate(() => window.__htmlModel3dDebug());
  expect(debug.roomCloseup).toBe(true);
  expect(debug.furniture.shapes.filter(i => i.id.startsWith('A:floor-1:flex1:') && i.visible)).toHaveLength(2);
  const bath = debug.tour.rooms.find(r => r.id === 'A:floor-1:bath1');
  expect(bath.features.doors.some(d => d.width_mm === 900 && d.operation === 'sliding')).toBe(true);
  const care = debug.layoutReview.checks.find(c => c.id === 'A-1F-care-functions');
  expect(care.site_legality).toBe('unknown');
  expect(care.professional_accessibility).toBe('unknown');
  expect(care.routes.elder_to_bath).toEqual(['A:floor-1:flex1', 'A:floor-1:rear-hall1', 'A:floor-1:bath1']);
  await page.locator('#info .info-link').click();
  await expect(page).toHaveURL(/AbuildingView\.html#proposal-room-flex1$/);
  await expect(page.locator('#proposal-room-flex1')).toHaveJSProperty('open', true);
  expectNoUnexpectedConsole(messages);
});

test('upstairs full-size bathrooms and hallway synchronize HTML and 3D while both A wardrobes remain pending', async ({ page }) => {
  const messages = monitorConsole(page);
  for (const [building, key, count] of [
    ['A', 'master-bath', 3], ['A', 'hall2', 1], ['B', 'bath2', 3], ['B', 'master-bath2', 3],
  ]) {
    await page.goto(`/${building}buildingView.html#proposal-room-${key}`, { waitUntil: 'load' });
    const roomPanel = page.locator(`#proposal-room-${key}`);
    await expect(page.locator('#floor-2')).toHaveClass(/active/);
    await expect(roomPanel).toHaveJSProperty('open', true);
    const floor = await page.evaluate(id => window.HOUSE_CONCEPT_LAYOUT.buildings
      .find(b => b.id === id).floors.find(f => f.id === 'floor-2'), building);
    const room = floor.rooms.find(r => r.key === key);
    await expect(roomPanel.locator('[data-furniture-id]')).toHaveCount(count);
    const note = key === 'hall2' ? '不能同時當通道' : '700mm';
    await expect(roomPanel).toContainText(note);
    if (['master-bath', 'master-bath2'].includes(key)) await expect(roomPanel).toContainText('門寬暫估800mm');
    await roomPanel.getByRole('link', { name: '在 3D 核對家具', exact: true }).click();
    await expect.poll(() => page.evaluate(() => window.__htmlModel3dDebug().state.room)).toBe(room.id);
    await page.locator('#view-front').click();
    await page.locator('#focus-room').click();
    const debug = await page.evaluate(() => window.__htmlModel3dDebug());
    expect(debug.roomCloseup).toBe(true);
    expect(debug.visibleRooms).toHaveLength(floor.rooms.length);
    expect(debug.layoutReview.status).toBe('proposal-owner-and-architect-review-pending');
    expect(debug.tour.rooms.find(r => r.id === room.id).geometry).toEqual(room.geometry);
    expect(debug.furniture.pendingItems.slice().sort()).toEqual(building === 'A' ? [
      'A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right',
    ] : []);
    const actual = debug.furniture.shapes.filter(i => i.id.startsWith(room.id + ':furniture:') && i.visible);
    expect(actual).toHaveLength(count);
    for (const item of room.furniture) {
      const rendered = actual.find(i => i.id === item.id);
      expect([rendered.width, rendered.depth, rendered.height]).toEqual([item.width_mm, item.depth_mm, item.height_mm]);
      expect(rendered.center[0]).toBeCloseTo(item.placement.center_x_mm, 2);
      expect(rendered.center[1]).toBeCloseTo(item.placement.center_y_mm, 2);
      expect(item.placement.issues).toEqual([]);
      expect(item.front_clearance_mm).toBe(key === 'hall2' ? 600 : 700);
      expect(item.shared_operation_with).toEqual([]);
    }
    if (key !== 'hall2') expect(actual.map(i => i.shape).sort()).toEqual(['shower', 'toilet', 'vanity']);
    const notes = await page.locator('#info [data-furniture-note-id]').evaluateAll(elements =>
      elements.map(e => ({ id: e.getAttribute('data-furniture-note-id'), text: e.textContent })));
    expect(notes).toEqual(room.furniture.filter(item => item.note).map(item => ({
      id: item.id, text: item.label + '：' + item.note,
    })));
    await expect(page.locator('#info')).toContainText(note);
    if (['master-bath', 'master-bath2'].includes(key)) await expect(page.locator('#info')).toContainText('門寬暫估800mm');
    await assertNoFrameworkOverlay(page);
    await page.locator('#info .info-link').click();
    await expect(page).toHaveURL(new RegExp(`${building}buildingView\\.html#proposal-room-${key}$`));
    await expect(page.locator(`#proposal-room-${key}`)).toHaveJSProperty('open', true);
  }
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

test('C1F space use and uninstalled frontage comparison match HTML and 3D on desktop/mobile', async ({ page }) => {
  const messages=monitorConsole(page);
  for(const size of [{width:1440,height:900},{width:390,height:844}]){
    await page.setViewportSize(size);
    await page.goto('/CbuildingView.html');
    await page.locator('.floor-tabs [aria-controls="floor-1"]').click();
    const panel=page.locator('#floor-1 .shared-furniture-plan');
    await expect(panel).toBeVisible();
    const expected=await page.evaluate(()=>window.HOUSE_CONCEPT_LAYOUT.buildings.find(b=>b.id==='C').floors[0]);
    const comparison=panel.locator('.frontage-study-review');
    await comparison.locator('summary').click();
    await expect(comparison).toContainText('騎樓／公共退縮適用時整案撤銷');
    await expect(panel).toHaveAttribute('data-frontage-study-visible','false');
    const toggle=comparison.locator('[data-frontage-study-toggle]');
    await toggle.check();
    await panel.locator('img').scrollIntoViewIfNeeded();
    await expect(panel.locator('img')).toHaveAttribute('src',/C_floor-1_frontage-study\.svg$/);
    await expect(panel).toHaveAttribute('data-frontage-study-visible','true');
    await toggle.uncheck();
    await expect(panel.locator('img')).toHaveAttribute('src',/C_floor-1\.svg$/);
    await panel.getByRole('link',{name:'在 3D 核對這一層',exact:true}).click();
    await page.waitForFunction(()=>window.__htmlModel3dDebug && window.__htmlModel3dDebug().state.building==='C');
    const base=await page.evaluate(()=>window.__htmlModel3dDebug());
    expect(base.visibleRooms.slice().sort()).toEqual(expected.rooms.map(r=>r.id).sort());
    expect(base.frontageStudy.visible).toEqual([]);
    const sofa=base.furniture.shapes.find(i=>i.id==='C:floor-1:living:furniture:sofa');
    const tv=base.furniture.shapes.find(i=>i.id==='C:floor-1:living:furniture:tv');
    expect(sofa).toMatchObject({width:1800,depth:900,height:850,visible:true});
    expect(sofa.placement.wall_anchor).toBe('rear');expect(tv.placement.wall_anchor).toBe('front');
    expect(sofa.placement.center_x_mm).toBe(tv.placement.center_x_mm);
    expect(base.furniture.shapes.find(i=>i.id==='C:floor-1:elder:furniture:wardrobe'))
      .toMatchObject({width:1200,depth:600,height:2200,visible:true});
    for(const room of expected.rooms){
      const actual=base.tour.rooms.find(r=>r.id===room.id);
      expect(actual.geometry).toEqual(room.geometry);expect(actual.features).toEqual(room.features);
    }
    await page.locator('#frontage-study').check();
    const compare=await page.evaluate(()=>window.__htmlModel3dDebug());
    expect(compare.frontageStudy.visible).toHaveLength(3);
    expect(compare.furniture.shapes).toEqual(base.furniture.shapes);
    const study=expected.rooms.find(r=>r.key==='garage').features.frontage_study;
    for(const zone of study.zones){
      const rendered=compare.frontageStudy.visible.find(z=>z.id===zone.id);
      expect(rendered.geometry).toEqual(zone.geometry);
      expect(rendered.status).toBe('conditional-not-installed');
    }
    await page.locator('#frontage-study').uncheck();
    await page.locator('#scope-rooms [data-room="C:floor-1:living"]').click();
    await page.locator('#focus-room').click();
    if(size.width===390)await page.locator('#mobile-panel-toggle').click();
    const focused=await page.evaluate(()=>window.__htmlModel3dDebug());
    expect(focused.roomCutaway.fixtureSightlines).toHaveLength(4);
    expect(focused.roomCutaway.fixtureSightlines.every(i=>i.unobstructedSamples>=3)).toBe(true);
    expect(focused.visibleRooms).toEqual(base.visibleRooms);
  }
  expectNoUnexpectedConsole(messages);
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
