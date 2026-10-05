const { test, expect } = require('@playwright/test');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const os = require('node:os');
const { monitorConsole, expectNoUnexpectedConsole, assertNoFrameworkOverlay } = require('./helpers.cjs');
const root = path.resolve(__dirname, '../..');

for (const building of ['A', 'B', 'C']) {
  for (const width of [390, 820, 1440]) {
    test(`${building} original HTML room detail stays separate from plan ${width}px`, async ({ page }) => {
      const messages = monitorConsole(page);
      await page.setViewportSize({ width, height: 900 });
      const room = building === 'A' ? 'living' : building === 'B' ? 'storage' : 'elder-bath';
      const url = `${pathToFileURL(path.join(root, building + 'buildingView.html')).href}#room-${room}`;
      await page.goto(url);
      await expect(page).toHaveURL(url);
      await expect(page).toHaveTitle(new RegExp(building + '棟'));
      await expect(page.locator('.design-bridge .design-review-note')).toContainText('使用範圍與待確認事項');
      await assertNoFrameworkOverlay(page);
      for (let floor = 1; floor <= 4; floor++) {
        await page.locator(`.tab[data-floor="${floor}"]`).click();
        await expect(page.locator(`#floor-${floor}`)).toHaveClass(/active/);
      }
      await page.locator('.tab[data-floor="1"]').click();
      const detail = page.locator('#room-' + room);
      await detail.scrollIntoViewIfNeeded();
      if (width <= 1050) {
        await expect(page.locator('#floor-1 .visual-plan')).toHaveCSS('position', 'static');
        const boxes = await page.evaluate((id) => {
          const plan = document.querySelector('#floor-1 .visual-plan').getBoundingClientRect();
          const room = document.querySelector('#room-' + id).getBoundingClientRect();
          return { planBottom: plan.bottom, roomTop: room.top, scrollWidth: document.documentElement.scrollWidth, width: innerWidth };
        }, room);
        expect(boxes.planBottom).toBeLessThanOrEqual(boxes.roomTop);
        expect(boxes.scrollWidth).toBeLessThanOrEqual(boxes.width);
      } else {
        await expect(page.locator('#floor-1 .visual-plan')).toHaveCSS('position', 'sticky');
      }
      if (building === 'A') await expect(detail).toContainText('此次不自動合併或搬動房間');
      if (building === 'B') await expect(detail).toContainText('搬運情境尚未驗證');
      if (building === 'C') {
        await expect(detail).toContainText('不預設向內開');
        await expect(detail).toContainText('外部緊急解鎖');
      }
      await page.screenshot({ path: path.join(os.tmpdir(), `house-html-fixed-${building}-${width}.png`) });
      const href = await detail.locator('.design-bridge-room-link').getAttribute('href');
      expect(new URL(href).hash).toContain('building=' + building);
      expect(new URL(href).hash).toContain('room=' + building + '%3Afloor-1%3A' + room);
      await page.emulateMedia({ media: 'print' });
      await expect(page.locator('#floor-1 .visual-plan')).toHaveCSS('position', 'static');
      expectNoUnexpectedConsole(messages);
    });
  }
}
