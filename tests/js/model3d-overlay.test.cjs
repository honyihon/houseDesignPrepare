const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(path.resolve(__dirname, '../../scripts/templates/model3d.html'), 'utf8');
const source = template.match(/  function findOverlayPosition\([\s\S]*?(?=  function overlayLabelArea\()/)[0];
const place = vm.runInNewContext(`${source}; findOverlayPosition`);

function checkRect(rect, area, previous) {
  assert.ok(rect, 'label should fit in the available area');
  assert.ok(rect.x - rect.w / 2 >= area.left);
  assert.ok(rect.x + rect.w / 2 <= area.right);
  assert.ok(rect.y - rect.h / 2 >= area.top);
  assert.ok(rect.y + rect.h / 2 <= area.bottom);
  for (const other of previous) {
    assert.ok(Math.abs(rect.x - other.x) >= (rect.w + other.w) / 2 + 3
      || Math.abs(rect.y - other.y) >= (rect.h + other.h) / 2 + 3, 'labels must not overlap');
  }
}

test('mobile furniture names clamped above the title still remain separate', () => {
  const area = { left: 8, right: 382, top: 166, bottom: 708 };
  const occupied = [];
  for (const [w, h] of [[88, 30], [104, 30], [156, 30]]) {
    const rect = place(w, h, 180, 100, area, occupied);
    checkRect(rect, area, occupied);
    occupied.push(rect);
  }
  // Navigation checks those same furniture rectangles, not a different
  // top/bottom coordinate convention or positions before clamping.
  for (let index = 0; index < 16; index += 1) {
    const rect = place(index % 3 ? 80 : 140, 25, 210, 410, area, occupied);
    checkRect(rect, area, occupied);
    occupied.push(rect);
  }
});

test('desktop labels at a common anchor avoid furniture and each other', () => {
  const area = { left: 8, right: 1072, top: 108, bottom: 832 };
  const occupied = [];
  for (let index = 0; index < 24; index += 1) {
    const rect = place(100 + (index % 4) * 24, 26 + (index % 2) * 12, 540, 480, area, occupied);
    checkRect(rect, area, occupied);
    occupied.push(rect);
  }
});

test('impossible or full label areas hide text instead of clipping or stacking', () => {
  const area = { left: 8, right: 382, top: 166, bottom: 210 };
  assert.equal(place(390, 30, 180, 200, area, []), null);
  assert.equal(place(100, 60, 180, 200, area, []), null);
  assert.equal(place(100, 30, 180, 200, area, [{ x: 195, y: 188, w: 374, h: 44 }]), null);
});
