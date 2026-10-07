// Maintained native-Windows Playwright CLI entrypoint. Node.js 20+ and Edge/Chrome
// must already be installed. Source files are read only; artifacts go to TEMP.
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const MARKER = 'house-windows-cli-qa';
const DEFAULT_PROJECT = path.resolve(__dirname, '..');
const LAYOUT_FILE = 'structured/candidates/furniture-plans/layout.js';
const SOURCE_FILES = [
  'AbuildingView.html', 'BbuildingView.html', 'CbuildingView.html',
  'assets/html_design_bridge.js', 'assets/html_design_bridge.css',
  'assets/vendor/three/three.min.js', 'structured/candidates/model3d.html',
  'inputs/concept-layout-review.json', 'inputs/furniture-layout.json', 'inputs/physical-items.json',
  'inputs/requirements.json', 'scripts/check_windows_playwright.cjs',
  'inputs/facade-concept.json', 'assets/references/facade-photo-v1.jpg', LAYOUT_FILE,
];

function parseArguments(argv) {
  const options = { project: DEFAULT_PROJECT, browser: 'msedge', preflight: false, help: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help') options.help = true;
    else if (arg === '--preflight') options.preflight = true;
    else if (/^--(?:project|browser)(?:=|$)/.test(arg)) {
      const separator = arg.indexOf('=');
      const key = arg.slice(2, separator < 0 ? undefined : separator);
      const value = separator < 0 ? argv[++i] : arg.slice(separator + 1);
      if (!value || value.startsWith('--')) throw new Error('Missing value for --' + key);
      options[key] = value;
    } else throw new Error('Unknown option: ' + arg);
  }
  if (!['msedge', 'chrome'].includes(options.browser)) throw new Error('Use --browser=msedge or --browser=chrome');
  options.project = path.resolve(options.project);
  return options;
}

function preflight(project) {
  const cli = path.join(project, 'node_modules', 'playwright', 'cli.js');
  const missing = [...SOURCE_FILES, 'node_modules/playwright/cli.js']
    .filter(file => !fs.existsSync(path.join(project, file)));
  if (missing.length) {
    throw new Error('Project is incomplete or the path is wrong: ' + project + '\nMissing: ' + missing.join(', ') +
      '\nUse --project "<latest project folder>". An old Desktop HTML-only folder is not the latest 3D project.' +
      '\nIf only node_modules is missing, install the pinned project dependencies separately with npm ci.');
  }
  const source = fs.readFileSync(path.join(project, LAYOUT_FILE), 'utf8');
  const match = source.match(/^\s*window\.HOUSE_CONCEPT_LAYOUT\s*=\s*([\s\S]+?)\s*;\s*$/);
  if (!match) throw new Error('Shared layout.js is not a supported JSON assignment. Regenerate the shared plans.');
  const layout = JSON.parse(match[1]);
  if (layout.schema !== 'house-concept-furniture-plan-v1' || layout.geometry_source !== 'tour_mm' ||
    !Array.isArray(layout.buildings) || layout.buildings.map(b => b.id).join(',') !== 'A,B,C') {
    throw new Error('Expected the current shared A/B/C furniture-plan manifest, not an old export.');
  }
  const plans = [];
  const counts = { floors: 0, rooms: 0, items: 0 };
  for (const building of layout.buildings) {
    if (!Array.isArray(building.floors) || building.floors.map(f => f.id).join(',') !== 'floor-1,floor-2,floor-3,floor-4') {
      throw new Error(building.id + ': expected all four shared floor plans');
    }
    for (const floor of building.floors) {
      if (floor.plan_file !== building.id + '_' + floor.id + '.svg' || !Array.isArray(floor.rooms)) {
        throw new Error('Invalid shared floor manifest: ' + building.id + ' ' + floor.id);
      }
      const plan = 'structured/candidates/furniture-plans/' + floor.plan_file;
      if (!fs.existsSync(path.join(project, plan))) throw new Error('Missing shared plan: ' + plan);
      plans.push(plan);
      const studies = floor.rooms.filter(room => room.features?.frontage_study);
      if (studies.length || floor.frontage_study_file) {
        if (building.id !== 'C' || floor.id !== 'floor-1' || studies.length !== 1 ||
          studies[0].key !== 'garage' || studies[0].furniture.length ||
          studies[0].features.frontage_study.status !== 'conditional-not-installed' ||
          studies[0].features.frontage_study.active_option !== 'keep-full-clear' ||
          studies[0].features.frontage_study.site_use_status !== 'unknown' ||
          floor.frontage_study_file !== 'C_floor-1_frontage-study.svg') {
          throw new Error('Invalid conditional frontage study; keep unknown land clear and regenerate shared plans');
        }
        const file = 'structured/candidates/furniture-plans/' + floor.frontage_study_file;
        if (!fs.existsSync(path.join(project, file))) throw new Error('Missing conditional frontage study: ' + file);
        plans.push(file);
      }
      counts.floors++;
      counts.rooms += floor.rooms.length;
      for (const room of floor.rooms) {
        if (!Array.isArray(room.furniture)) throw new Error('Missing furniture list: ' + room.id);
        counts.items += room.furniture.length;
      }
    }
  }
  const concept = JSON.parse(fs.readFileSync(path.join(project, 'inputs/facade-concept.json'), 'utf8'));
  const facade = layout.facade;
  if (!facade || facade.schema !== 'house-facade-layer-v1' || facade.geometry_source !== 'tour_mm' ||
    concept.schema !== 'house-facade-concept-v1' || facade.id !== concept.id ||
    facade.reference?.file !== 'assets/references/facade-photo-v1.jpg' ||
    !Array.isArray(facade.buildings) || facade.buildings.map(b => b.id).join(',') !== 'A,B,C') {
    throw new Error('Missing current shared facade proposal. Regenerate with scripts/export_model_3d.py.');
  }
  const referenceHash = crypto.createHash('sha256').update(fs.readFileSync(path.join(project, facade.reference.file))).digest('hex');
  if (facade.reference.sha256 !== referenceHash || concept.reference?.sha256 !== referenceHash) {
    throw new Error('Facade reference photo differs from the recorded source. Preserve provenance and regenerate.');
  }
  for (const building of facade.buildings) {
    if (building.elevation_file !== building.id + '_facade-front.svg') throw new Error('Invalid shared facade manifest: ' + building.id);
    const file = 'structured/candidates/furniture-plans/' + building.elevation_file;
    if (!fs.existsSync(path.join(project, file))) throw new Error('Missing shared facade: ' + file);
    plans.push(file);
  }
  return { cli, counts, sourceFiles: [...SOURCE_FILES, ...plans] };
}

function hashSources(project, files) {
  return Object.fromEntries(files.map(file => [file,
    crypto.createHash('sha256').update(fs.readFileSync(path.join(project, file))).digest('hex')]));
}

// This function is serialized for run-code's VM, which provides page but no Node
// globals or URL. Keep all Node I/O in runQa, not in this browser callback.
async function checkPages(page, baseUrl, outputDir, expectedCounts) {
  const checks = [];
  const messages = [];
  const screenshots = [];
  const counts = { floors: 0, rooms: 0, items: 0 };
  const sharedFloors = {};
  const assert = (condition, name) => {
    checks.push({ name, passed: Boolean(condition) });
    if (!condition) throw new Error(name);
  };
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(30000);
  page.on('pageerror', error => messages.push({ level: 'pageerror', text: error.message }));
  page.on('console', message => {
    if (['error', 'warning'].includes(message.type())) messages.push({ level: message.type(), text: message.text() });
  });
  const capture = async name => {
    const filename = outputDir + '/' + name;
    await page.screenshot({ path: filename, fullPage: false });
    screenshots.push(filename);
  };
  const setSlider = async (id, value) => {
    await page.locator('#' + id).evaluate((input, next) => {
      input.value = next;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }, String(value));
  };
  const pageHealth = async () => {
    assert((await page.locator('body').innerText()).trim().length > 100, 'page is not blank');
    assert(await page.locator('vite-error-overlay, nextjs-portal, #webpack-dev-server-client-overlay, [data-nextjs-dialog-overlay]').count() === 0,
      'no framework error overlay');
  };
  const selectHtmlFloor = async (building, floorId) => {
    // A/C open on an overview tab; all other floor panels are display:none.
    // Use the real control, not force-clicks or CSS overrides that hide UI bugs.
    await page.locator('.floor-tabs [role="tab"][aria-controls="' + floorId + '"]').click();
    await page.waitForFunction(id => {
      const tab = document.querySelector('.floor-tabs [role="tab"][aria-controls="' + id + '"]');
      const panel = document.getElementById(id);
      return tab && tab.getAttribute('aria-selected') === 'true' && panel &&
        panel.classList.contains('active') && panel.getClientRects().length > 0 &&
        getComputedStyle(panel).display !== 'none';
    }, floorId);
    assert(await page.locator('#' + floorId).isVisible(), building + ' HTML ' + floorId + ' tab shows its panel');
  };
  const selectRoomLabel = async roomId => {
    // A and C both have elder bedrooms; hidden labels also remain in the DOM.
    // Room identity must be unique and visible, not picked by shared text/order.
    const label = page.locator('.nav-label.room[data-room="' + roomId + '"]');
    assert(await label.count() === 1, roomId + ' has one navigation label');
    assert(await label.isVisible(), roomId + ' navigation label is visible');
    await label.click();
    await page.waitForFunction(id => window.__htmlModel3dDebug().state.room === id, roomId);
  };
  const collapseMobilePanel = async () => {
    // Same-document hash navigation preserves panel state. Set the desired
    // state instead of blindly toggling a panel that may already be collapsed.
    const toggle = page.locator('#mobile-panel-toggle');
    const expanded = await toggle.getAttribute('aria-expanded');
    assert(['true', 'false'].includes(expanded), 'mobile panel exposes its expanded state');
    if (expanded === 'true') await toggle.click();
    await page.waitForFunction(() => {
      const stage = document.getElementById('stage'), canvas = document.getElementById('canvas');
      const toggle = document.getElementById('mobile-panel-toggle');
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      return toggle.getAttribute('aria-expanded') === 'false' && window.__htmlModel3dDebug().panelCollapsed &&
        stage.clientHeight >= window.innerHeight - 84 &&
        Math.abs(canvas.width - stage.clientWidth * ratio) <= 1 &&
        Math.abs(canvas.height - stage.clientHeight * ratio) <= 1;
    });
    assert(await toggle.getAttribute('aria-expanded') === 'false', 'mobile panel collapsed and renderer resized');
  };
  const checkMobileBathroomContext = (debug, floor) => {
    const roomId = 'A:floor-2:master-bath';
    assert(floor && floor.id === 'floor-2' && debug.state.building === 'A' &&
      debug.state.floor === floor.id && debug.state.room === roomId,
    'mobile A bathroom selects the expected shared floor and room');
    const expectedRooms = floor.rooms.map(r => r.id).sort();
    const actualRooms = debug.visibleRooms.slice().sort();
    assert(JSON.stringify(actualRooms) === JSON.stringify(expectedRooms),
      'mobile A bathroom retains exact shared room IDs (expected ' + expectedRooms.length + ', got ' + actualRooms.length + ')');
    const expectedPending = ['A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right'];
    assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
      'mobile A bathroom retains both specific pending wardrobes');
    assert(expectedPending.every(id => {
      const items = debug.furniture.shapes.filter(i => i.id === id);
      return items.length === 1 && !items[0].visible && items[0].width === 1800 &&
        items[0].depth === 600 && items[0].height === 2200;
    }), 'mobile A bathroom keeps pending wardrobes hidden at their original dimensions');
    assert(debug.panelCollapsed && debug.focusedScreenBounds.length === 8 &&
      debug.focusedScreenBounds.every(point => Math.abs(point[0]) < 1 && Math.abs(point[1]) < 1),
    'mobile A bathroom closeup fits the resized stage with controls collapsed');
  };
  const expandMobilePanel = async () => {
    const toggle = page.locator('#mobile-panel-toggle');
    const expanded = await toggle.getAttribute('aria-expanded');
    assert(['true', 'false'].includes(expanded), 'mobile panel exposes state before expansion');
    if (expanded === 'false') await toggle.click();
    await page.waitForFunction(() => document.getElementById('mobile-panel-toggle').getAttribute('aria-expanded') === 'true');
  };
  const checkRoomCutaway = (debug, roomId, fixtureCount) => {
    const cut = debug.roomCutaway;
    assert(debug.roomCloseup && cut && cut.active && cut.heightMm === 550,
      roomId + ' camera-aware cutaway active, display height only');
    assert(cut.parts.length > 0 && cut.parts.every(p => ['wall', 'door', 'window', 'stairs'].includes(p.role)),
      roomId + ' cuts architecture only, not HVAC or furniture');
    assert(cut.fixtureSightlines.length === fixtureCount && cut.fixtureSightlines.every(i =>
      i.id.startsWith(roomId + ':furniture:') && i.samples === 5 && i.unobstructedSamples >= 3),
    roomId + ' real fixture-body samples clear architecture, not just visible labels');
    assert(cut.limitation.includes('not pixel visibility'), roomId + ' sightlines do not imply visual/professional acceptance');
  };
  const checkUpperFloor = (building, floor, debug) => {
    const room = key => floor.rooms.find(r => r.id === building + ':floor-2:' + key);
    const expectedPending = building === 'A' ? [
      'A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right',
    ] : [];
    assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
      building + ' upstairs pending list retains only the two original A wardrobes');
    assert(debug.layoutReview.status === 'proposal-owner-and-architect-review-pending',
      building + ' upstairs arrangement remains an unapproved proposal');
    const bathrooms = building === 'A' ? [['master-bath', 600, 450]] :
      [['bath2', 600, 450], ['master-bath2', 900, 550]];
    for (const [key, width, depth] of bathrooms) {
      const bath = room(key);
      assert(bath && bath.furniture.length === 3, building + ' ' + key + ' keeps all three fixtures');
      for (const [shape, w, d, h] of [['vanity', width, depth, 850], ['toilet', 450, 700, 800], ['shower', 900, 900, 2000]]) {
        const matches = bath.furniture.filter(i => i.shape === shape);
        const item = matches[0];
        assert(matches.length === 1 && item.width_mm === w && item.depth_mm === d && item.height_mm === h,
          bath.id + ' ' + shape + ' keeps normal catalogue dimensions');
        assert(!item.placement.issues.length && item.front_clearance_mm === 700 && !item.shared_operation_with.length,
          item.id + ' no smaller operating allowance or new sharing exception');
        const op = item.placement.operation_mm;
        const axis = ['front', 'rear'].includes(item.placement.wall_anchor) ? 'Y' : 'X';
        assert(op && op['max' + axis] - op['min' + axis] === 700, item.id + ' full 700mm operating strip');
        assert(debug.furniture.shapes.some(i => i.id === item.id && i.visible), item.id + ' is actually displayed');
      }
      if (key !== 'master-bath2') {
        const vanity = bath.furniture.find(i => i.shape === 'vanity').placement;
        const toilet = bath.furniture.find(i => i.shape === 'toilet').placement;
        assert(vanity.wall_anchor === 'front' && toilet.wall_anchor === 'front' &&
          toilet.aabb.minX - vanity.aabb.maxX >= 150, bath.id + ' toilet does not touch the basin');
      } else {
        assert(bath.geometry.h_mm === 1830, 'B ensuite receives 200mm without expanding the wet-zone band');
      }
      if (key !== 'bath2') {
        assert(bath.features.doors.some(d => d.operation === 'sliding'), bath.id + ' sliding-door proposal retained');
      }
    }
    if (building === 'A') {
      assert(room('master-bath').geometry.w_mm === 2400 && room('walkin').geometry.w_mm === 2000,
        'A 200mm bathroom/closet partition transfer is explicit');
      const hall = room('hall2');
      const cabinet = hall && hall.furniture.find(i => i.catalog_id === 'hall-cabinet');
      assert(cabinet && !cabinet.placement.issues.length && cabinet.width_mm === 2400 && cabinet.depth_mm === 400 &&
        cabinet.height_mm === 2200, 'A hallway keeps full-size cabinet clear of door approaches');
      const left = hall.geometry.x_mm + 80;
      assert(cabinet.placement.aabb.minX - left === 1040 && cabinet.placement.operation_mm.minX - left === 440 &&
        cabinet.note.includes('不能同時當通道'), 'A 1040mm closed / 440mm operating passage is not simultaneous access');
      const closet = room('walkin');
      assert(closet.furniture.length === 2 && closet.furniture.every(i => i.catalog_id === 'wardrobe-180' &&
        i.width_mm === 1800 && i.depth_mm === 600 && i.height_mm === 2200 && i.placement.status === 'pending-layout'),
      'A two full-size wardrobes remain pending, not deleted or silently substituted');
    } else {
      assert(room('bath2').geometry.h_mm === 2000 && room('master-bath2').geometry.y_mm === 15800,
        'B public/ensuite partition transfer preserves the rear wet-zone footprint');
    }
  };
  const checkCFirstFloor = (floor, debug) => {
    const room = key => floor.rooms.find(r => r.key === key);
    const dining = room('dining'), living = room('living'), kitchen = room('kitchen'), elder = room('elder');
    assert(dining && living && kitchen && elder && !room('front-service'),
      'C separates dining/lounge and reclaims only the old 1F AC alcove');
    assert(dining.geometry.w_mm === 4000 && dining.geometry.h_mm === 3200 &&
      living.geometry.w_mm === 6000 && living.geometry.h_mm === 2400 &&
      dining.geometry.w_mm*dining.geometry.h_mm + living.geometry.w_mm*living.geometry.h_mm === 27200000,
    'C 27.2m2 dining/lounge allocation is inside the same frame, not frontage enclosure');
    for (const [space, product, w, d, h] of [[living, 'sofa-2', 1800, 900, 850],
      [living, 'reading-chair', 900, 850, 850], [dining, 'dining-4', 1800, 1800, 750],
      [kitchen, 'counter-240-60', 2400, 600, 900], [elder, 'wardrobe-120', 1200, 600, 2200]]) {
      const item = space.furniture.find(i => i.catalog_id === product);
      assert(item && item.width_mm === w && item.depth_mm === d && item.height_mm === h && !item.placement.issues.length,
        space.id + ' keeps separate ordinary product ' + product + ' without scaling');
      assert(debug.furniture.shapes.some(i => i.id === item.id && i.visible), item.id + ' actually displayed');
    }
    const sofa = living.furniture.find(i => i.catalog_id === 'sofa-2').placement;
    const tv = living.furniture.find(i => i.catalog_id === 'wall-tv').placement;
    const table = living.furniture.find(i => i.catalog_id === 'coffee-table').placement;
    assert(sofa.wall_anchor === 'rear' && tv.wall_anchor === 'front' && sofa.center_x_mm === tv.center_x_mm &&
      sofa.center_x_mm === table.center_x_mm && sofa.aabb.minY - table.aabb.maxY === 400,
    'C lounge TV faces normal sofa with 400mm coffee-table gap');
    assert(living.features.reserved_mm.some(z => z.kind === 'care-turn' &&
      z.aabb.maxX-z.aabb.minX === 1500 && z.aabb.maxY-z.aabb.minY === 1500) &&
      dining.features.reserved_mm.some(z => z.kind === 'care-route' && z.aabb.maxX-z.aabb.minX === 1200),
    'C keeps dining care route and lounge turning reservation, not approval');
    const counter = kitchen.furniture.find(i => i.catalog_id === 'counter-240-60');
    assert(counter.front_clearance_mm === 900 && counter.shared_operation_with.join('|') === 'door-approach' &&
      counter.note.includes('非把原240×65cm代表型號縮薄'), 'C kitchen states distinct candidate and sequential use');
    const route = debug.layoutReview.hvac_routes.find(r => r.id === 'C-AC01');
    assert(route.outdoor_room === 'C:floor-2:balcony2f' && route.estimated_routed_length_mm === 14645 &&
      route.elevation_difference_mm === 1150 && route.compliance === 'unknown' && route.manual_source === null,
    'C relocated AC has routed quantity but no model/installer approval');
    const study = room('garage').features.frontage_study;
    assert(study.status === 'conditional-not-installed' && study.active_option === 'keep-full-clear' &&
      study.site_use_status === 'unknown' && !room('garage').furniture.length && !debug.frontageStudy.visible.length,
    'C unknown frontage is empty by default; garden/bench are conditional overlays only');
  };
  const checkFrontageStudy = (debug, floor) => {
    const source = floor.rooms.find(r => r.key === 'garage').features.frontage_study;
    const rendered = debug.frontageStudy.visible;
    assert(debug.state.building === 'C' && debug.state.floor === 'floor-1' && rendered.length === 3,
      'C conditional comparison has route, garden and bench wireframes');
    for (const zone of [{id: 'clear-route', geometry: source.route_mm, height_mm: 0}, ...source.zones]) {
      const actual = rendered.find(z => z.id === zone.id);
      assert(actual && actual.room === 'C:floor-1:garage' && actual.status === 'conditional-not-installed' &&
        JSON.stringify(actual.geometry) === JSON.stringify(zone.geometry) && actual.height_mm === zone.height_mm,
      zone.id + ' comparison uses the same HTML coordinates and uninstalled status');
      const box = actual.renderedBounds;
      assert(Math.abs((box.max[0]-box.min[0])*1000-zone.geometry.w_mm) < .02 &&
        Math.abs((box.max[2]-box.min[2])*1000-zone.geometry.h_mm) < .02 &&
        Math.abs((box.max[1]-box.min[1])*1000-zone.height_mm) < .02,
      zone.id + ' rendered wireframe matches the millimetre footprint');
    }
  };
  try {
    await page.context().route(/^https?:/, route => route.abort());
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const building of ['A', 'B', 'C']) {
      const htmlUrl = baseUrl + building + 'buildingView.html';
      await page.goto(htmlUrl, { waitUntil: 'load' });
      await page.waitForFunction(() => document.querySelectorAll('.shared-furniture-plan').length === 4);
      assert(page.url() === htmlUrl, building + ' HTML page identity');
      assert((await page.title()).length > 0, building + ' HTML title');
      await pageHealth();
      if (building === 'A') await capture('A-html-initial.png');
      const expected = await page.evaluate(id => window.HOUSE_CONCEPT_LAYOUT.buildings.find(b => b.id === id), building);
      assert(expected && expected.floors.length === 4, building + ' has all four shared plans');
      for (const floor of expected.floors) sharedFloors[building + ':' + floor.id] = floor;
      for (const floor of expected.floors) {
        await selectHtmlFloor(building, floor.id);
        const panel = page.locator('#' + floor.id + ' .shared-furniture-plan');
        // Lazy images must be scrolled into view before waiting for image load.
        await panel.locator('img').scrollIntoViewIfNeeded();
        await page.waitForFunction(id => {
          const image = document.querySelector('#' + id + ' .shared-furniture-plan img');
          return image && image.complete && image.naturalWidth > 0;
        }, floor.id);
        const entries = await panel.locator('[data-furniture-id]').evaluateAll(elements =>
          elements.map(e => ({ id: e.getAttribute('data-furniture-id'), text: e.textContent })));
        const furniture = floor.rooms.flatMap(room => room.furniture);
        assert(entries.length === furniture.length, building + ' ' + floor.id + ' HTML furniture count');
        for (const item of furniture) {
          const entry = entries.find(e => e.id === item.id);
          assert(entry && entry.text.includes(item.label) &&
            entry.text.includes(item.width_mm + ' × ' + item.depth_mm + ' × ' + item.height_mm + 'mm'),
          item.id + ' HTML name and full-size dimensions');
        }
        if (building === 'A' && floor.id === 'floor-1') {
          assert(await panel.locator('[data-care-function-check="conditional-proposal-function-screen-only"]').count() === 1,
            'A HTML distinguishes function screen from professional approval');
          const elder = panel.locator('[data-requirement-id="A.floor-1.elder"]');
          assert(await elder.count() === 1, 'A HTML retains explicit elder requirement');
          await elder.locator('summary').click();
          assert((await elder.innerText()).includes('雙人床') && (await elder.innerText()).includes('衣櫃'),
            'A HTML elder bedroom includes normal bed and wardrobe, not day-use flex');
          await panel.locator('img').scrollIntoViewIfNeeded();
          await capture('A-html-shared-plan.png');
        }
        if (['A', 'B'].includes(building) && floor.id === 'floor-2') {
          await capture(building + '-html-2F-shared-plan.png');
        }
        if (building === 'C' && floor.id === 'floor-1') {
          await capture('C-html-1F-shared-plan.png');
          const comparison = panel.locator('.frontage-study-review');
          await comparison.locator('summary').click();
          assert((await comparison.innerText()).includes('不是已配置家具') &&
            await comparison.getAttribute('data-frontage-study-status') === 'conditional-not-installed',
          'C HTML frontage comparison explains unknown rights and uninstalled status');
          const toggle = comparison.locator('[data-frontage-study-toggle]');
          await toggle.check();
          await page.waitForFunction(() => {
            const img = document.querySelector('#floor-1 .shared-furniture-plan img');
            return img.complete && img.naturalWidth > 0 && img.src.endsWith('C_floor-1_frontage-study.svg');
          });
          assert(await panel.getAttribute('data-frontage-study-visible') === 'true', 'C HTML shows conditional footprint comparison');
          await panel.locator('img').scrollIntoViewIfNeeded();
          await capture('C-html-1F-frontage-study.png');
          await toggle.uncheck();
          await page.waitForFunction(() => {
            const img = document.querySelector('#floor-1 .shared-furniture-plan img');
            return img.complete && img.naturalWidth > 0 && img.src.endsWith('C_floor-1.svg');
          });
          assert(await panel.getAttribute('data-frontage-study-visible') === 'false', 'C HTML restores full-clear frontage');
        }
      }
      // The last inspected HTML panel is RF, so return to 1F before its link.
      await selectHtmlFloor(building, 'floor-1');
      await page.locator('#floor-1 .shared-furniture-plan')
        .getByRole('link', { name: '在 3D 核對這一層', exact: true }).click();
      await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
      assert(await page.title() === '原設計 HTML · 三棟 3D 對照', building + ' 3D page title');
      assert(page.url().startsWith(baseUrl + 'structured/candidates/model3d.html#'), building + ' HTML-to-3D link');
      await pageHealth();
      for (const floor of expected.floors) {
        await page.locator('#scope-floors [data-floor="' + floor.id + '"]').click();
        await page.waitForFunction(id => window.__htmlModel3dDebug().state.floor === id, floor.id);
        const debug = await page.evaluate(() => window.__htmlModel3dDebug());
        assert(debug.presentation === 'tour' && debug.state.building === building,
          building + ' ' + floor.id + ' shared tour mode');
        const expectedPending = floor.rooms.flatMap(r => r.furniture).filter(i => i.placement.issues.length).map(i => i.id).sort();
        assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
          building + ' ' + floor.id + ' pending furniture matches explicit HTML list');
        assert(debug.visibleRooms.length === floor.rooms.length, building + ' ' + floor.id + ' room count');
        assert(floor.width_mm === 6000 && floor.depth_mm === 17630, building + ' fixed proposal frame');
        if (['A', 'B'].includes(building) && floor.id === 'floor-2') checkUpperFloor(building, floor, debug);
        if (building === 'C' && floor.id === 'floor-1') checkCFirstFloor(floor, debug);
        if (floor.id === 'floor-1') {
          const vehicles = debug.furniture.shapes.filter(i => i.visible && ['car', 'motorcycle'].includes(i.shape));
          assert(vehicles.length === 0, building + ' parking deferred, not silently credited');
          assert(expected.layout_review.parking.verified_spaces === null, building + ' parking not falsely verified');
          assert(expected.layout_review.parking.status === (building === 'B' ?
            'not-accommodated-in-worship-priority-proposal' : 'not-accommodated-in-care-priority-proposal'),
          building + ' explicit parking tradeoff');
          if (building === 'A') {
            const elder = floor.rooms.find(r => r.requirement_id === 'A.floor-1.elder');
            const bath = floor.rooms.find(r => r.requirement_id === 'A.floor-1.bath1');
            assert(elder && bath, 'A retains both care functions independently of HTML/3D equality');
            assert(elder.kind === 'bedroom' && elder.furniture.some(i => i.shape === 'bed' && i.width_mm >= 1000 && i.depth_mm >= 1800) &&
              elder.furniture.some(i => i.catalog_id.startsWith('wardrobe-') && i.width_mm >= 1200),
            'A elder is a furnished sleeping room, not a renamed desk or sofa bed');
            assert(['toilet', 'vanity', 'shower'].every(shape => bath.furniture.some(i => i.shape === shape && !i.placement.issues.length)),
              'A 1F retains usable toilet, basin and shower proposals');
            assert(bath.furniture.some(i => i.shape === 'shower' && i.step_free && i.width_mm >= 1200 && i.depth_mm >= 1200),
              'A shower has full-size step-free proposal');
            for (const room of [elder, bath]) {
              assert(room.features.reserved_mm.some(z => z.kind === 'care-turn' &&
                z.aabb.maxX - z.aabb.minX >= 1500 && z.aabb.maxY - z.aabb.minY >= 1500),
              room.id + ' retains 150cm turning reservation');
              assert(room.features.doors.some(d => d.width_mm >= 900 && d.operation === 'sliding'),
                room.id + ' retains sliding-door proposal');
            }
            const care = debug.layoutReview.checks.find(c => c.id === 'A-1F-care-functions');
            assert(care && care.site_legality === 'unknown' && care.professional_accessibility === 'unknown',
              'A function coverage does not invent parcel or accessibility approval');
            assert(care.routes.elder_to_bath.join('|') === 'A:floor-1:flex1|A:floor-1:rear-hall1|A:floor-1:bath1',
              'A night-time bathroom route uses public dry area, not kitchen or MDF');
          }
        }
        for (const room of floor.rooms) {
          const actualRoom = debug.tour.rooms.find(r => r.id === room.id);
          assert(Boolean(actualRoom), room.id + ' exists in 3D');
          assert(actualRoom.outdoor === room.outdoor, room.id + ' indoor/outdoor use matches HTML');
          if (room.outdoor) {
            assert(room.furniture.every(item => !['bed', 'sofa', 'l-sofa', 'cabinet', 'tv-console', 'wall-tv'].includes(item.shape) &&
              item.category !== 'network'), room.id + ' no indoor furniture incorrectly placed outdoors');
          }
          assert(JSON.stringify(actualRoom.features) === JSON.stringify(room.features), room.id + ' full architecture/AC metadata matches HTML');
          if (room.features.stair_geometry) {
            const stair = actualRoom.features.stair_geometry;
            assert(stair.type === 'two-flight-u-proposal' && stair.fits_reserved_box && stair.risers === 18 &&
              !actualRoom.features.stair_geometry_verified && actualRoom.architectureParts > (stair.connects_to_next_storey === false ? 0 : 18),
            room.id + ' rendered U stairs remain unverified');
          }
          for (const unit of actualRoom.features.hvac_units || []) {
            assert(unit.route.model === null && unit.route.manual_source === null && unit.route.compliance === 'unknown',
              unit.id + ' installer/model approval remains unknown');
          }
          for (const key of ['x_mm', 'y_mm', 'w_mm', 'h_mm']) {
            assert(actualRoom.geometry[key] === room.geometry[key], room.id + ' ' + key + ' matches HTML');
          }
          for (const open of room.features.open_connections) {
            assert(actualRoom.features.open_connections.some(o => o.neighbor === open.neighbor), room.id + ' shared stair hall');
            assert(!actualRoom.features.doors.some(d => d.neighbor === open.neighbor), room.id + ' no invented equipment-room door');
          }
          for (const item of room.furniture) {
            const actual = debug.furniture.shapes.find(i => i.id === item.id);
            const pending = item.placement.issues.length > 0;
            assert(Boolean(actual) && actual.visible === !pending, item.id + ' visibility reflects honest pending status');
            assert(actual.shape === item.shape, item.id + ' recognizable furniture type matches HTML');
            assert(actual.width === item.width_mm && actual.depth === item.depth_mm && actual.height === item.height_mm,
              item.id + ' full-size dimensions');
            assert(Math.abs(actual.center[0] - item.placement.center_x_mm) < 0.02 &&
              Math.abs(actual.center[1] - item.placement.center_y_mm) < 0.02 &&
              Math.abs(actual.rotation - item.placement.rotation_deg) < 0.001, item.id + ' placement matches HTML');
            assert((actual.overflow || actual.collision) === pending, item.id + ' conflict state matches HTML');
            counts.items++;
          }
          counts.rooms++;
        }
        counts.floors++;
        if (floor.id === 'floor-1') {
          await page.locator('#view-front').click();
          await page.locator('#architecture').uncheck();
          assert((await page.evaluate(() => window.__htmlModel3dDebug())).tour.rooms.every(r => !r.architectureVisible),
            building + ' architecture toggle off');
          await page.locator('#architecture').check();
          assert((await page.evaluate(() => window.__htmlModel3dDebug())).tour.rooms.filter(r => !r.outdoor).every(r => r.architectureVisible),
            building + ' architecture toggle on');
          await page.locator('#full-walls').check();
          await page.locator('#full-walls').uncheck();
          await capture(building + '-3D-1F.png');
          if (building === 'A') {
            for (const [key, name] of [['flex1', 'elder'], ['bath1', 'care-bath']]) {
              await page.locator('#scope-rooms [data-room="A:floor-1:' + key + '"]').click();
              await page.locator('#focus-room').click();
              const focused = await page.evaluate(() => window.__htmlModel3dDebug());
              assert(focused.roomCloseup && focused.state.room === 'A:floor-1:' + key && focused.visibleRooms.length === floor.rooms.length,
                'A ' + name + ' closeup retains entire floor geometry');
              assert((await page.locator('#info').innerText()).includes('150cm'), 'A ' + name + ' explains care turning reservation');
              await capture('A-3D-' + name + '-closeup.png');
              await page.locator('#room-overview').click();
            }
          } else if (building === 'C') {
            for (const key of ['dining', 'living', 'kitchen']) {
              const id = 'C:floor-1:' + key;
              const room = floor.rooms.find(r => r.id === id);
              await page.locator('#scope-rooms [data-room="' + id + '"]').click();
              await page.locator('#focus-room').click();
              const focused = await page.evaluate(() => window.__htmlModel3dDebug());
              checkRoomCutaway(focused, id, room.furniture.length);
              const displayed = await page.locator('#info [data-furniture-note-id]').evaluateAll(elements =>
                elements.map(e => ({id: e.getAttribute('data-furniture-note-id'), text: e.textContent})));
              assert(room.furniture.filter(i => i.note).every(i => displayed.some(n => n.id === i.id && n.text === i.label + '：' + i.note)),
                id + ' distinct product and operation caveats match HTML');
              await page.locator('#info').scrollIntoViewIfNeeded();
              await capture('C-3D-1F-' + key + '-closeup.png');
              await page.locator('#room-overview').click();
            }
            await page.locator('#scope-rooms [data-room="C:floor-1:garage"]').click();
            await page.locator('#focus-room').click();
            const base = await page.evaluate(() => window.__htmlModel3dDebug());
            await page.locator('#frontage-study').check();
            const compare = await page.evaluate(() => window.__htmlModel3dDebug());
            checkFrontageStudy(compare, floor);
            assert(JSON.stringify(compare.furniture.shapes) === JSON.stringify(base.furniture.shapes) &&
              JSON.stringify(compare.visibleRooms) === JSON.stringify(base.visibleRooms),
            'C frontage study changes display only, not indoor furniture, rooms or parking capacity');
            assert((await page.locator('#info').innerText()).includes('騎樓／公共退縮適用時整案撤銷'),
              'C 3D frontage info retains conditional restrictions');
            await capture('C-3D-1F-frontage-study.png');
            await page.locator('#frontage-study').uncheck();
            assert(!(await page.evaluate(() => window.__htmlModel3dDebug())).frontageStudy.visible.length,
              'C 3D frontage returns to full-clear base');
            await page.locator('#room-overview').click();
          }
        } else {
          await page.locator('#view-front').click();
          await capture(building + '-3D-' + floor.id + '.png');
          if (['A', 'B'].includes(building) && floor.id === 'floor-2') {
            const keys = building === 'A' ? ['master-bath', 'hall2'] : ['bath2', 'master-bath2'];
            for (const key of keys) {
              const id = building + ':floor-2:' + key;
              await page.locator('#scope-rooms [data-room="' + id + '"]').click();
              const roomOverview = await page.evaluate(() => window.__htmlModel3dDebug());
              await page.locator('#focus-room').click();
              const focused = await page.evaluate(() => window.__htmlModel3dDebug());
              assert(focused.roomCloseup && focused.state.room === id && focused.visibleRooms.length === floor.rooms.length,
                id + ' closeup preserves the whole floor');
              const fixtureCount = floor.rooms.find(r => r.id === id).furniture.length;
              checkRoomCutaway(focused, id, fixtureCount);
              assert(JSON.stringify(focused.furniture.shapes) === JSON.stringify(roomOverview.furniture.shapes) &&
                JSON.stringify(focused.tour.rooms) === JSON.stringify(roomOverview.tour.rooms),
              id + ' display cutaway preserves HTML geometry, placements and pending furniture');
              assert(await page.locator('#room-cutaway-status').isVisible(), id + ' display-only cutaway notice visible');
              assert(focused.furniture.shapes.filter(i => i.id.startsWith(id + ':furniture:') && i.visible).length === fixtureCount,
                id + ' closeup shows every proposed fixture');
              const expectedNotes = floor.rooms.find(r => r.id === id).furniture.filter(i => i.note);
              const displayedNotes = await page.locator('#info [data-furniture-note-id]').evaluateAll(elements =>
                elements.map(e => ({ id: e.getAttribute('data-furniture-note-id'), text: e.textContent })));
              assert(displayedNotes.length === expectedNotes.length, id + ' room info shows every shared furniture-use note');
              for (const item of expectedNotes) {
                const note = displayedNotes.find(n => n.id === item.id);
                assert(note && note.text === item.label + '：' + item.note, item.id + ' room-use limitation matches HTML source');
              }
              if (key === 'hall2') assert((await page.locator('#info').innerText()).includes('不能同時當通道'),
                'A hallway closeup explains sequential cabinet operation');
              if (['master-bath', 'master-bath2'].includes(key)) assert((await page.locator('#info').innerText()).includes('門寬暫估800mm'),
                id + ' door caption uses actual 800mm proposal, not hard-coded 900mm');
              await page.locator('#info').scrollIntoViewIfNeeded();
              await capture(building + '-3D-2F-' + key + '-closeup.png');
              if (id === 'A:floor-2:master-bath') {
                await page.locator('#full-walls').check();
                const fullWalls = await page.evaluate(() => window.__htmlModel3dDebug());
                assert(!fullWalls.roomCutaway.active && fullWalls.roomCutaway.parts.length === 0,
                  id + ' full-height switch restores all architecture materials');
                await capture('A-3D-2F-master-bath-full-walls.png');
                await page.locator('#full-walls').uncheck();
                const front = await page.evaluate(() => window.__htmlModel3dDebug());
                const canvas = await page.locator('#canvas').boundingBox();
                await page.mouse.move(canvas.x + canvas.width * .15, canvas.y + canvas.height * .8);
                await page.mouse.down();
                await page.mouse.move(canvas.x + canvas.width * .75, canvas.y + canvas.height * .8, { steps: 8 });
                await page.mouse.up();
                const rotated = await page.evaluate(() => window.__htmlModel3dDebug());
                checkRoomCutaway(rotated, id, fixtureCount);
                assert(JSON.stringify(rotated.roomCutaway.parts) !== JSON.stringify(front.roomCutaway.parts),
                  id + ' orbit recomputes obstruction rather than keeping a fixed cut wall');
                assert(JSON.stringify(rotated.furniture.shapes) === JSON.stringify(front.furniture.shapes),
                  id + ' orbit does not move or scale furniture');
                await capture('A-3D-2F-master-bath-rotated-cutaway.png');
                await page.locator('#view-front').click();
              }
              await page.locator('#room-overview').click();
              const restored = await page.evaluate(() => window.__htmlModel3dDebug());
              assert(!restored.roomCutaway.active && restored.roomCutaway.parts.length === 0,
                id + ' returning to whole floor restores uncut architecture');
            }
          }
        }
      }
    }
    for (const key of ['floors', 'rooms', 'items']) assert(counts[key] === expectedCounts[key], 'all expected ' + key + ' checked');
    await page.locator('#scope-floors [data-floor="floor-1"]').click();
    await page.locator('#view-front').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#scope-rooms [data-room="C:floor-1:garage"]').click();
    await page.locator('#focus-room').click();
    await page.locator('#frontage-study').check();
    await collapseMobilePanel();
    checkFrontageStudy(await page.evaluate(() => window.__htmlModel3dDebug()), sharedFloors['C:floor-1']);
    await capture('C-3D-mobile-frontage-study.png');
    await expandMobilePanel();
    await page.locator('#frontage-study').uncheck();
    await page.locator('#room-overview').click();
    await page.locator('#scope-rooms [data-room="C:floor-1:living"]').click();
    await page.locator('#focus-room').click();
    await collapseMobilePanel();
    const mobileLiving = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(mobileLiving, 'C:floor-1:living', 4);
    assert(mobileLiving.focusedScreenBounds.every(([x,y]) => Math.abs(x)<1 && Math.abs(y)<1),
      'C mobile lounge closeup fits real geometry');
    await capture('C-3D-mobile-living-closeup.png');
    await page.locator('#room-overview').click();
    await collapseMobilePanel();
    await selectRoomLabel('C:floor-1:elder');
    const elder = await page.evaluate(() => window.__htmlModel3dDebug().furniture.shapes.filter(i =>
      i.id.startsWith('C:floor-1:elder:furniture:') && i.visible));
    assert(await page.locator('.furniture-label:visible').count() === elder.length && elder.length > 0,
      'mobile elder room displayed furniture names');
    await page.waitForFunction(() => {
      const rectangles = [...document.querySelectorAll('.nav-label:not([hidden]), .furniture-label:not([hidden])')]
        .filter(e => e.getClientRects().length && getComputedStyle(e).display !== 'none')
        .map(e => e.getBoundingClientRect());
      return rectangles.every(r => r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight) &&
        rectangles.every((a, index) => rectangles.slice(index + 1).every(b =>
          Math.min(a.right, b.right) <= Math.max(a.left, b.left) || Math.min(a.bottom, b.bottom) <= Math.max(a.top, b.top)));
    });
    assert(true, 'mobile labels inside viewport without overlap');
    await pageHealth();
    await capture('C-3D-mobile-elder.png');
    const beforeCloseup = await page.evaluate(() => window.__htmlModel3dDebug());
    await page.locator('#focus-room').click();
    await page.waitForFunction(() => window.__htmlModel3dDebug().roomCloseup &&
      document.querySelector('#focus-room').getAttribute('aria-pressed') === 'true');
    assert(page.url().includes('focus=room'), 'mobile room closeup is shareable in URL');
    const closeup = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(closeup, 'C:floor-1:elder', elder.length);
    assert(JSON.stringify(closeup.visibleRooms) === JSON.stringify(beforeCloseup.visibleRooms),
      'room closeup preserves the complete floor instead of inventing a detached room');
    assert(closeup.focusedScreenBounds.length === 8 && closeup.focusedScreenBounds.every(point =>
      Math.abs(point[0]) < 1 && Math.abs(point[1]) < 1), 'mobile closeup frames the selected room');
    await page.waitForFunction(() => {
      const labels = [...document.querySelectorAll('.nav-label:not([hidden])')];
      return labels.length > 0 && labels.every(label => label.getAttribute('data-room') === 'C:floor-1:elder');
    });
    assert(await page.locator('.furniture-label:visible').count() === elder.length, 'closeup keeps selected furniture names');
    await page.waitForFunction(() => {
      const labels = [...document.querySelectorAll('.nav-label:not([hidden]), .furniture-label:not([hidden])')];
      const rectangles = labels.map(label => label.getBoundingClientRect());
      const actions = document.querySelector('#room-view-actions').getBoundingClientRect();
      return rectangles.every(rect => rect.left >= 0 && rect.right <= innerWidth && rect.top >= actions.bottom && rect.bottom <= innerHeight) &&
        rectangles.every((a, index) => rectangles.slice(index + 1).every(b =>
          Math.min(a.right, b.right) <= Math.max(a.left, b.left) || Math.min(a.bottom, b.bottom) <= Math.max(a.top, b.top)));
    });
    assert(true, 'closeup labels do not overlap each other or room-view controls');
    await capture('C-3D-mobile-elder-closeup.png');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function' && window.__htmlModel3dDebug().roomCloseup);
    assert(await page.locator('#focus-room').getAttribute('aria-pressed') === 'true', 'room closeup restores after reload');
    checkRoomCutaway(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:elder', elder.length);
    // Reload resets the mobile control panel; restore its collapsed state to
    // prove that the stage-level return button works without the sidebar.
    await collapseMobilePanel();
    await page.locator('#room-overview').click();
    const overview = await page.evaluate(() => window.__htmlModel3dDebug());
    assert(overview.state.room === '' && !overview.roomCloseup && !page.url().includes('focus=room'),
      'mobile room closeup returns to complete floor without expanding controls');
    assert(!overview.roomCutaway.active && overview.roomCutaway.parts.length === 0, 'mobile return restores architecture materials');
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Amaster-bath&view=front&focus=room', { waitUntil: 'load' });
    await page.waitForFunction(() => {
      const debug = window.__htmlModel3dDebug();
      return debug.state.building === 'A' && debug.state.floor === 'floor-2' &&
        debug.state.room === 'A:floor-2:master-bath' && debug.roomCloseup;
    });
    await collapseMobilePanel();
    const mobileBath = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(mobileBath, 'A:floor-2:master-bath', 3);
    checkMobileBathroomContext(mobileBath, sharedFloors['A:floor-2']);
    await pageHealth();
    await capture('A-3D-mobile-2F-master-bath-closeup.png');
    // Facade is a separate layer, not a new room/furniture export. Check the
    // real HTML -> exterior -> interior flow after all legacy QA above.
    await page.setViewportSize({ width: 1440, height: 900 });
    let facadeData;
    const checkExterior = (debug, building, record) => {
      const selected = building ? [record] : facadeData.buildings;
      assert(debug.facade.active && debug.state.view === 'exterior' && debug.presentation === 'tour' &&
        debug.state.building === building && debug.state.floor === '' && debug.state.room === '',
      (building || 'ABC') + ' exterior ignores indoor floor/room scope');
      assert(debug.facade.source === 'inputs/facade-concept.json' && debug.facade.id === facadeData.id &&
        debug.facade.compliance === 'unknown' && debug.facade.status === 'proposal-owner-and-architect-review-pending',
      'facade has shared provenance and no false professional approval');
      assert(JSON.stringify(debug.facade.componentIds.slice().sort()) === JSON.stringify(selected.flatMap(b =>
        b.components.filter(c => c.rendered).map(c => c.id)).sort()), '3D displays exactly the shared approved-for-illustration components');
      assert(JSON.stringify(debug.facade.pending.map(p => p.id).sort()) === JSON.stringify(selected.flatMap(b => b.pending.map(p => p.id)).sort()),
        'facade retains every pending conflict and unchecked screen/door option');
      assert(debug.facade.allFloors.length === selected.length * 4 &&
        debug.facade.allFloors.every(id => selected.some(b => id.startsWith(b.id + ':'))), 'exterior joins all selected storeys without exploding');
      assert(!debug.furniture.visible && debug.furniture.visibleItems === 0 && debug.furniture.items === expectedCounts.items && !debug.roomCutaway.active,
        'exterior hides furniture display only and clears room cutaway');
      assert(debug.facade.screenBounds.length === 8 && debug.facade.screenBounds.every(p => Math.abs(p[0]) < 1 && Math.abs(p[1]) < 1),
        'complete exterior fits the actual stage viewport');
      assert(debug.tour.rooms.every(r => !r.architectureVisible), 'exterior shows only union-boundary walls, no internal wall clutter');
      for (const b of selected) for (const floor of ['floor-1', 'floor-2', 'floor-3', 'floor-4']) {
        const shared = sharedFloors[b.id + ':' + floor];
        for (const room of shared.rooms) {
          const actual = debug.tour.rooms.find(r => r.id === room.id);
          assert(actual && JSON.stringify(actual.geometry) === JSON.stringify(room.geometry), room.id + ' facade preserves shared room geometry');
        }
      }
      const units = selected.flatMap(b => ['floor-1', 'floor-2', 'floor-3', 'floor-4'].flatMap(fid =>
        sharedFloors[b.id + ':' + fid].rooms.flatMap(r => (r.features.hvac_units || []).filter(u => u.type === 'outdoor').map(u =>
          ({ id: u.id, room: r.id, floor: fid, position_mm: [u.x_mm, u.y_mm, b.floors.find(f => f.id === fid).base_mm + u.mount_height_mm] })))));
      assert(JSON.stringify(debug.facade.equipment.slice().sort((a,b) => a.id.localeCompare(b.id))) ===
        JSON.stringify(units.sort((a,b) => a.id.localeCompare(b.id))), 'exterior retains exact outdoor-unit locations and pairs');
    };
    for (const building of ['A', 'B', 'C']) {
      await page.goto(baseUrl + building + 'buildingView.html#facade-proposal', { waitUntil: 'load' });
      await page.waitForFunction(() => document.querySelector('.shared-facade-proposal img')?.complete &&
        document.querySelector('.shared-facade-proposal img').naturalWidth > 0);
      await pageHealth();
      facadeData = await page.evaluate(() => window.HOUSE_CONCEPT_LAYOUT.facade);
      const record = facadeData.buildings.find(b => b.id === building);
      const panel = page.locator('.shared-facade-proposal');
      assert(await panel.getAttribute('data-facade-id') === facadeData.id &&
        await panel.getAttribute('data-geometry-source') === 'tour_mm', building + ' HTML shares facade source');
      assert(await panel.locator('[data-facade-pending-id]').count() === record.pending.length, building + ' HTML retains every pending facade item');
      assert(await panel.locator('[data-facade-check-id]').count() === facadeData.pending_checks.length,
        building + ' HTML contains site, care, wind, drainage and HVAC review checklist');
      if (building === 'A') await capture('A-html-facade-proposal.png');
      await panel.locator('.facade-exterior-link').click();
      await page.waitForFunction(() => window.__htmlModel3dDebug && window.__htmlModel3dDebug().facade.active);
      assert(page.url().includes('view=exterior') && !page.url().includes('floor='), building + ' HTML links to complete exterior, not just 1F');
      const debug = await page.evaluate(() => window.__htmlModel3dDebug());
      checkExterior(debug, building, record);
      await capture(building + '-3D-exterior-front.png');
      await page.locator('#exterior-oblique').click();
      const oblique = await page.evaluate(() => window.__htmlModel3dDebug());
      checkExterior(oblique, building, record);
      assert(oblique.facade.angle === 'oblique' && page.url().includes('angle=oblique'), 'exterior oblique angle is shareable');
      await capture(building + '-3D-exterior-oblique.png');
    }
    await page.locator('#scope-buildings [data-building="overview"]').click();
    checkExterior(await page.evaluate(() => window.__htmlModel3dDebug()), '', null);
    await capture('ABC-3D-exterior-oblique.png');
    await page.reload({ waitUntil: 'load' });
    await page.waitForFunction(() => window.__htmlModel3dDebug && window.__htmlModel3dDebug().facade.active);
    const reloadedExterior = await page.evaluate(() => window.__htmlModel3dDebug());
    checkExterior(reloadedExterior, '', null);
    assert(reloadedExterior.facade.angle === 'oblique', 'shared exterior restores all buildings and angle after reload');
    await page.locator('#scope-buildings [data-building="B"]').click();
    checkExterior(await page.evaluate(() => window.__htmlModel3dDebug()), 'B', facadeData.buildings.find(b => b.id === 'B'));
    await page.locator('#scope-floors [data-floor="floor-1"]').click();
    let returned = await page.evaluate(() => window.__htmlModel3dDebug());
    assert(!returned.facade.active && returned.state.building === 'B' && returned.state.floor === 'floor-1' &&
      returned.visibleRooms.includes('B:floor-1:shrine') && returned.visibleRooms.includes('B:floor-1:storage'),
    'floor navigation leaves exterior and restores B shrine/palanquin room scope');
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&room=A%3Afloor-2%3Amaster-bath&view=front&focus=room', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__htmlModel3dDebug && window.__htmlModel3dDebug().roomCloseup);
    await page.locator('#architecture').uncheck();
    await page.locator('#navigation').uncheck();
    await setSlider('explode', 600);await setSlider('cut', 900);
    const indoorBefore = await page.evaluate(() => window.__htmlModel3dDebug());
    await page.locator('#view-exterior').click();
    checkExterior(await page.evaluate(() => window.__htmlModel3dDebug()), 'A', facadeData.buildings.find(b => b.id === 'A'));
    await page.locator('#exterior-return').click();
    returned = await page.evaluate(() => window.__htmlModel3dDebug());
    assert(JSON.stringify(returned.state) === JSON.stringify(indoorBefore.state) && returned.roomCloseup &&
      returned.geomSource === indoorBefore.geomSource &&
      JSON.stringify(returned.facade.controls) === JSON.stringify(indoorBefore.facade.controls),
    'return restores indoor scope, room closeup, geometry source, clipping, explode and visibility preferences');
    assert(JSON.stringify(returned.furniture.pendingItems) === JSON.stringify(indoorBefore.furniture.pendingItems) &&
      returned.furniture.items === expectedCounts.items, 'return preserves both pending A wardrobes and exact furniture count');
    await page.locator('#architecture').check();await page.locator('#navigation').check();
    await setSlider('explode', 0);await setSlider('cut', 1000);
    await page.setViewportSize({ width: 390, height: 844 });
    await collapseMobilePanel();
    await page.locator('#view-exterior').click();
    const mobileExterior = await page.evaluate(() => window.__htmlModel3dDebug());
    checkExterior(mobileExterior, 'A', facadeData.buildings.find(b => b.id === 'A'));
    assert(mobileExterior.panelCollapsed && await page.locator('#exterior-return').isVisible(), 'mobile exterior return works without the sidebar');
    await capture('A-3D-mobile-exterior.png');
    await page.locator('#exterior-return').click();
    const mobileReturned = await page.evaluate(() => window.__htmlModel3dDebug());
    checkMobileBathroomContext(mobileReturned, sharedFloors['A:floor-2']);
    checkRoomCutaway(mobileReturned, 'A:floor-2:master-bath', 3);
    // A same-document room link must also remove exterior-only settings.
    await page.locator('#view-exterior').click();
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&room=C%3Afloor-1%3Aelder&view=front&focus=room');
    await page.waitForFunction(() => window.__htmlModel3dDebug().state.room === 'C:floor-1:elder');
    const hashReturn = await page.evaluate(() => window.__htmlModel3dDebug());
    assert(!hashReturn.facade.active && hashReturn.roomCloseup && hashReturn.facade.controls.navigation.checked &&
      !hashReturn.facade.controls['full-walls'].checked && hashReturn.visibleRooms.includes('C:floor-1:elder'),
    'same-document exterior-to-room link restores interior settings, not just URL scope');
    await pageHealth();
    const unexpected = messages.filter(message => !(message.level === 'warning' &&
      (message.text.includes('GPU stall due to ReadPixels') ||
        message.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(unexpected.length === 0, 'no unexpected console errors, warnings or page errors');
    return { marker: 'house-windows-cli-qa', status: 'passed', counts, checks, messages, screenshots,
      limitation: 'Automated browser checks only; screenshots still need visual review. Not professional design or regulatory approval.' };
  } catch (error) {
    await capture('failure.png').catch(() => {});
    return { marker: 'house-windows-cli-qa', status: 'failed', error: String(error), counts, checks, messages, screenshots };
  }
}

function makeBrowserScript(baseUrl, output, counts) {
  return `async page => (${checkPages.toString()})(page, ${JSON.stringify(baseUrl)}, ${JSON.stringify(output)}, ${JSON.stringify(counts)})`;
}

function findReport(value) {
  if (value && typeof value === 'object') {
    if (value.marker === MARKER) return value;
    for (const nested of Object.values(value)) {
      const found = findReport(nested);
      if (found) return found;
    }
  } else if (typeof value === 'string') {
    try { return findReport(JSON.parse(value)); } catch { /* Not complete JSON result data. */ }
  }
  return null;
}

function validateReport(result, counts) {
  if (!result || result.marker !== MARKER || !['passed', 'failed'].includes(result.status)) {
    throw new Error('No valid structured QA result; see checks.log. Verification is incomplete.');
  }
  if (result.status === 'passed' && (!Array.isArray(result.checks) || result.checks.length === 0 ||
    result.checks.some(c => c.passed !== true) || !result.counts ||
    Object.keys(counts).some(key => result.counts[key] !== counts[key]) ||
    !Array.isArray(result.screenshots) || result.screenshots.length < 6)) {
    throw new Error('Incomplete passing result; see checks.log. Verification is incomplete.');
  }
  return result;
}

function runQa(options, prepared, output, execute = spawnSync) {
  const session = 'house-qa-' + crypto.randomBytes(5).toString('hex');
  const config = path.join(output, 'cli.config.json');
  const script = path.join(output, 'check-pages.js');
  const baseUrl = pathToFileURL(options.project + path.sep).href;
  const sourceHashes = hashSources(options.project, prepared.sourceFiles);
  fs.writeFileSync(config, JSON.stringify({ browser: { browserName: 'chromium',
    launchOptions: { channel: options.browser, headless: true },
    contextOptions: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 } },
    allowUnrestrictedFileAccess: true, outputDir: output }, null, 2));
  fs.writeFileSync(script, makeBrowserScript(baseUrl, output, prepared.counts));
  const invoke = (name, argv, requiredSuccess = true) => {
    const result = execute(process.execPath, [prepared.cli, 'cli', '-s=' + session, '--json', ...argv],
      { cwd: output, encoding: 'utf8', timeout: 240000, maxBuffer: 8 * 1024 * 1024,
        env: { ...process.env, PWTEST_DAEMON_SESSION_DIR: path.join(output, 'daemon'), NO_UPDATE_NOTIFIER: '1' } });
    fs.writeFileSync(path.join(output, name + '.log'), (result.stdout || '') + '\n' + (result.stderr || '') +
      (result.error ? '\n' + String(result.error) : ''));
    if (requiredSuccess && (result.error || result.status !== 0)) throw new Error(name + ' failed; see ' + name + '.log');
    return result;
  };
  let report = { marker: MARKER, status: 'incomplete' };
  try {
    invoke('open', ['open', baseUrl + 'AbuildingView.html', '--config=' + config]);
    const response = invoke('checks', ['run-code', '--filename=' + script]).stdout;
    report = validateReport(findReport(JSON.parse(response)), prepared.counts);
    const afterHashes = hashSources(options.project, prepared.sourceFiles);
    if (JSON.stringify(sourceHashes) !== JSON.stringify(afterHashes)) {
      report.status = 'incomplete';
      report.error = 'Source files changed during QA. Rerun against one unchanged version.';
    }
  } catch (error) {
    report.status = 'incomplete';
    report.error = String(error);
  } finally {
    report.project = options.project;
    report.sourceHashes = sourceHashes;
    report.browser = options.browser;
    report.session = session;
    try {
      const closed = invoke('close', ['close'], false);
      const status = JSON.parse(closed.stdout || '{}').status;
      report.sessionClosed = !closed.error && closed.status === 0 && ['closed', 'not-open'].includes(status);
    } catch { report.sessionClosed = false; }
    if (!report.sessionClosed) report.cleanupWarning = 'Session cleanup not confirmed; see close.log. Only this QA session was targeted.';
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
  }
  return report;
}

function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    console.log('Windows: node "<project>\\scripts\\check_windows_playwright.cjs" [--preflight] [--project "<folder>"] [--browser=chrome]');
    console.log('Default project is the script\'s parent folder, not /tmp or a fixed WSL distribution.');
    console.log('Requires Windows Node.js 20+ and installed Edge/Chrome. No automatic installs, source edits or elevation.');
    console.log('Browser artifacts go to one new Windows TEMP folder. --preflight is read only and starts no browser.');
    return;
  }
  if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Node.js 20+ is required. No automatic installation is performed.');
  if (!options.preflight && process.platform !== 'win32') throw new Error('Run browser QA from native Windows PowerShell/Terminal, not WSL. Use --preflight for read-only file checks here.');
  console.log('Latest project: ' + options.project);
  const prepared = preflight(options.project);
  console.log('Preflight passed: ' + prepared.counts.floors + ' floors, ' + prepared.counts.rooms + ' rooms, ' + prepared.counts.items + ' items.');
  if (options.preflight) {
    console.log('File checks only; no browser launched and no rendered QA passed.');
    return;
  }
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'house-design-cli-'));
  console.log('QA output folder: ' + output);
  const report = runQa(options, prepared, output);
  console.log('Automated browser checks: ' + report.status);
  console.log('Result: ' + path.join(output, 'result.json'));
  if (report.error) console.error(report.error);
  if (report.cleanupWarning) console.warn(report.cleanupWarning);
  console.log('Screenshots still require visual review; this is not professional approval.');
  if (report.status !== 'passed') process.exitCode = 1;
}

if (require.main === module) {
  try { main(); } catch (error) { console.error(String(error)); process.exitCode = 1; }
}
module.exports = { parseArguments, preflight, hashSources, checkPages, makeBrowserScript, findReport, validateReport, runQa };
