const { expect } = require('@playwright/test');

const WALKTHROUGH_PATH = '/structured/parametric/walkthrough.html';

function monitorConsole(page) {
  const messages = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      messages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', (error) => messages.push(`pageerror: ${error.message}`));
  return messages;
}

function expectNoUnexpectedConsole(messages) {
  const unexpected = messages.filter((message) =>
    !message.includes('GPU stall due to ReadPixels') &&
    !message.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')
  );
  expect(unexpected, unexpected.join('\n')).toEqual([]);
}

async function assertNoFrameworkOverlay(page) {
  const overlays = page.locator(
    'vite-error-overlay, nextjs-portal, #webpack-dev-server-client-overlay, [data-nextjs-dialog-overlay]'
  );
  await expect(overlays).toHaveCount(0);
}

async function loadWalkthrough(page, url = WALKTHROUGH_PATH) {
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => typeof window.__walkDebug === 'function');
  await expect(page.locator('canvas#canvas')).toBeVisible();
  await page.waitForTimeout(300);
}

async function walkDebug(page) {
  return page.evaluate(() => window.__walkDebug());
}

async function setRange(locator, value) {
  await locator.evaluate((element, nextValue) => {
    element.value = String(nextValue);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

module.exports = {
  WALKTHROUGH_PATH,
  assertNoFrameworkOverlay,
  expectNoUnexpectedConsole,
  loadWalkthrough,
  monitorConsole,
  setRange,
  walkDebug,
};
