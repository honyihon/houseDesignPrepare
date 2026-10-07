const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {
  parseArguments, preflight, hashSources, makeBrowserScript, findReport, validateReport, runQa,
} = require('../../scripts/check_windows_playwright.cjs');

const root = path.resolve(__dirname, '../..');
const marker = 'house-windows-cli-qa';

// Infrastructure/contract tests only. Fake CLI replies below are deliberately
// isolated from real browser QA and must not be presented as rendered evidence.
function fixture(t) {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), 'house-cli-test-'));
  t.after(() => fs.rmSync(project, { recursive: true, force: true }));
  const write = (relative, content = 'fixture') => {
    const target = path.join(project, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
  };
  for (const file of ['AbuildingView.html', 'BbuildingView.html', 'CbuildingView.html',
    'assets/html_design_bridge.js', 'assets/html_design_bridge.css', 'assets/vendor/three/three.min.js',
    'structured/candidates/model3d.html', 'inputs/concept-layout-review.json', 'inputs/furniture-layout.json',
    'inputs/physical-items.json', 'inputs/requirements.json', 'scripts/check_windows_playwright.cjs',
    'assets/references/facade-photo-v1.jpg',
    'node_modules/playwright/cli.js']) write(file);
  const referenceHash = require('node:crypto').createHash('sha256').update('fixture').digest('hex');
  write('inputs/facade-concept.json', JSON.stringify({schema: 'house-facade-concept-v1', id: 'fixture-facade',reference:{sha256:referenceHash}}));
  const layout = { schema: 'house-concept-furniture-plan-v1', geometry_source: 'tour_mm',
    buildings: ['A', 'B', 'C'].map(id => ({ id, floors: [1, 2, 3, 4].map(number => {
      const floor = 'floor-' + number;
      const plan = id + '_' + floor + '.svg';
      write('structured/candidates/furniture-plans/' + plan, '<svg/>');
      return { id: floor, plan_file: plan, rooms: [{ id: id + ':' + floor + ':fixture', furniture: [{ id: 'fixture-item' }] }] };
    }) })) };
  layout.facade = {schema: 'house-facade-layer-v1', id: 'fixture-facade', geometry_source: 'tour_mm',
    reference: {file: 'assets/references/facade-photo-v1.jpg',sha256:referenceHash}, buildings: ['A','B','C'].map(id => {
      const elevation_file = id + '_facade-front.svg';
      write('structured/candidates/furniture-plans/' + elevation_file, '<svg/>');
      return {id,elevation_file};
    })};
  write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(layout) + ';\n');
  const output = path.join(project, 'qa-output');
  fs.mkdirSync(output);
  return { project, output, write, layout };
}

function passingReport(counts) {
  return { marker, status: 'passed', counts, checks: [{ name: 'fixture', passed: true }],
    screenshots: ['1.png', '2.png', '3.png', '4.png', '5.png', '6.png'] };
}

function fakeCli(report, onChecks = () => {}) {
  const calls = [];
  const execute = (executable, args, options) => {
    calls.push({ executable, args, options });
    if (args.includes('run-code')) {
      onChecks();
      return { status: 0, stdout: JSON.stringify({ result: JSON.stringify(report) }), stderr: '' };
    }
    return { status: 0, stdout: JSON.stringify({ status: args.includes('close') ? 'closed' : 'open' }), stderr: '' };
  };
  return { execute, calls };
}

test('default project follows the durable script location, with optional paths and no fixed distro', () => {
  assert.equal(parseArguments([]).project, root);
  assert.equal(parseArguments(['--preflight']).preflight, true);
  assert.equal(parseArguments(['--project', '/tmp/project with spaces', '--browser=chrome']).project,
    path.resolve('/tmp/project with spaces'));
  assert.equal(parseArguments(['--browser', 'chrome']).browser, 'chrome');
  for (const args of [['--project'], ['--project='], ['--browser', '--preflight'], ['--browser=firefox'], ['--install']]) {
    assert.throws(() => parseArguments(args));
  }
});

test('preflight verifies current shared outputs and all SVGs without executing their JS', t => {
  const f = fixture(t);
  const prepared = preflight(f.project);
  assert.deepEqual(prepared.counts, { floors: 12, rooms: 12, items: 12 });
  assert.equal(prepared.sourceFiles.length, 30);
  assert.match(prepared.cli, /node_modules[/\\]playwright[/\\]cli\.js$/);
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = process.exit(0);');
  assert.throws(() => preflight(f.project), SyntaxError);
});

test('old HTML-only Desktop copies fail preflight instead of being silently accepted', t => {
  const f = fixture(t);
  fs.unlinkSync(path.join(f.project, 'structured/candidates/model3d.html'));
  assert.throws(() => preflight(f.project), /Project is incomplete.*[\s\S]*model3d\.html/);
});

test('preflight rejects missing floors and plan paths outside the expected manifest', t => {
  const f = fixture(t);
  f.layout.buildings[0].floors[0].plan_file = '../../../../private.json';
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(f.layout) + ';');
  assert.throws(() => preflight(f.project), /Invalid shared floor manifest/);
  f.layout.buildings[0].floors.pop();
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(f.layout) + ';');
  assert.throws(() => preflight(f.project), /expected all four/);
});

test('current project read-only preflight checks all bounded rooms/items without changing source files', () => {
  const prepared = preflight(root);
  const before = hashSources(root, prepared.sourceFiles);
  assert.deepEqual(prepared.counts, { floors: 12, rooms: 105, items: 129 });
  assert.equal(prepared.sourceFiles.length, 31, 'hash conditional comparison SVG as well as the 12 base plans');
  assert.deepEqual(preflight(root), prepared);
  assert.deepEqual(hashSources(root, prepared.sourceFiles), before);
});

test('preflight rejects stale or unsafe facade manifests instead of accepting historical QA', t => {
  const f = fixture(t);
  f.layout.facade.buildings[0].elevation_file = '../../../bad.svg';
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(f.layout) + ';');
  assert.throws(() => preflight(f.project), /Invalid shared facade manifest/);
  delete f.layout.facade;
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(f.layout) + ';');
  assert.throws(() => preflight(f.project), /Missing current shared facade proposal/);
});

test('conditional frontage preflight requires the exact safe file and unknown/uninstalled status', t => {
  const f=fixture(t),floor=f.layout.buildings[2].floors[0],room=floor.rooms[0];
  room.key='garage';room.furniture=[];
  room.features={frontage_study:{status:'conditional-not-installed',active_option:'keep-full-clear',site_use_status:'unknown'}};
  floor.frontage_study_file='C_floor-1_frontage-study.svg';
  const save=()=>f.write('structured/candidates/furniture-plans/layout.js','window.HOUSE_CONCEPT_LAYOUT = '+JSON.stringify(f.layout)+';');
  save();
  assert.throws(()=>preflight(f.project),/Missing conditional frontage study/);
  f.write('structured/candidates/furniture-plans/'+floor.frontage_study_file,'<svg/>');
  assert.equal(preflight(f.project).sourceFiles.length,31);
  floor.frontage_study_file='../../private.svg';save();
  assert.throws(()=>preflight(f.project),/Invalid conditional frontage study/);
  floor.frontage_study_file='C_floor-1_frontage-study.svg';
  for(const [key,value] of [['status','installed'],['active_option','garden'],['site_use_status','verified']]){
    const original=room.features.frontage_study[key];
    room.features.frontage_study[key]=value;save();
    assert.throws(()=>preflight(f.project),/Invalid conditional frontage study/);
    room.features.frontage_study[key]=original;
  }
  room.furniture=[{id:'fake-installed-bench'}];save();
  assert.throws(()=>preflight(f.project),/Invalid conditional frontage study/);
});

test('C1F serialized QA catches simultaneous wrong HTML/3D layout claims independently', async t => {
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const source=checkPages.toString().match(/  const checkCFirstFloor = \(floor, debug\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source);
  const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  const base=shared.buildings[2].floors[0];
  const check=vm.runInNewContext(source+'\ncheckCFirstFloor',{assert:(condition,message)=>assert.ok(condition,message)});
  const make=()=>{
    const floor=JSON.parse(JSON.stringify(base));
    return {floor,debug:{layoutReview:JSON.parse(JSON.stringify(shared.layout_review)),frontageStudy:{visible:[]},
      furniture:{shapes:floor.rooms.flatMap(r=>r.furniture).map(i=>({id:i.id,visible:true}))}}};
  };
  for(const [name,mutate,error] of [
    ['current design',()=>{},null],
    ['dining disappeared',s=>s.floor.rooms=s.floor.rooms.filter(r=>r.key!=='dining'),/separates dining/],
    ['reclaim public frontage',s=>s.floor.rooms.find(r=>r.key==='living').geometry.h_mm=6000,/27.2m2/],
    ['silently resize old sofa',s=>s.floor.rooms.find(r=>r.key==='living').furniture.find(i=>i.catalog_id==='sofa-2').width_mm=1500,/ordinary product/],
    ['TV not facing sofa',s=>s.floor.rooms.find(r=>r.key==='living').furniture.find(i=>i.catalog_id==='wall-tv').placement.wall_anchor='left',/faces normal sofa/],
    ['turning reserve removed',s=>s.floor.rooms.find(r=>r.key==='living').features.reserved_mm=[],/care route/],
    ['shrink working strip',s=>s.floor.rooms.find(r=>r.key==='kitchen').furniture.find(i=>i.catalog_id==='counter-240-60').front_clearance_mm=600,/sequential use/],
    ['fake model approval',s=>s.debug.layoutReview.hvac_routes.find(r=>r.id==='C-AC01').compliance='passed',/no model/],
    ['unknown land marked usable',s=>s.floor.rooms.find(r=>r.key==='garage').features.frontage_study.site_use_status='verified',/unknown frontage/],
  ])await t.test(name,()=>{
    const state=make();mutate(state);
    if(error)assert.throws(()=>check(state.floor,state.debug),error);else check(state.floor,state.debug);
  });
});

test('run-code function compiles and reports failure without Node globals in its VM', async () => {
  const captures = [];
  const fakePage = { setDefaultTimeout() {}, setDefaultNavigationTimeout() {}, on() {},
    context: () => ({ route: async () => {} }), setViewportSize: async () => {},
    goto: async () => { throw new Error('intentional no-browser fixture'); },
    screenshot: async options => { captures.push(options.path); } };
  const script = new vm.Script('(' + makeBrowserScript('file://wsl.localhost/Ubuntu/project/', 'C:\\QA folder',
    { floors: 12, rooms: 92, items: 157 }) + ')');
  const callback = script.runInNewContext({});
  const result = await callback(fakePage);
  assert.equal(result.marker, marker);
  assert.equal(result.status, 'failed');
  assert.match(result.error, /intentional no-browser fixture/);
  assert.equal(captures.length, 1);
});

test('HTML QA activates each hidden floor before scrolling and restores 1F before its 3D link', async () => {
  // Tab/lazy-image contract simulation, not rendered browser evidence. Start on
  // A's real default overview tab and reject access to every inactive panel.
  const source = fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8');
  const layout = JSON.parse(source.replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const building = layout.buildings.find(b => b.id === 'A');
  let active = 'floor-0';
  const clicks = [];
  const scrolled = [];
  const loaded = new Set();
  const base = 'file:///project/';
  const floorIdOf = selector => selector.match(/floor-[1-4]/)?.[0];
  const document = {
    querySelectorAll(selector) {
      assert.equal(selector, '.shared-furniture-plan');
      return building.floors;
    },
    getElementById(id) {
      return { id, classList: { contains: name => name === 'active' && active === id },
        getClientRects: () => active === id ? [{}] : [] };
    },
    querySelector(selector) {
      const id = floorIdOf(selector);
      if (selector.startsWith('.floor-tabs ')) {
        return { getAttribute: name => { assert.equal(name, 'aria-selected'); return active === id ? 'true' : 'false'; } };
      }
      assert.ok(selector.endsWith('.shared-furniture-plan img'));
      return { complete: loaded.has(id), naturalWidth: loaded.has(id) ? 600 : 0 };
    },
  };
  const evaluate = (fn, arg) => vm.runInNewContext('(' + fn.toString() + ')(arg)', {
    arg, document, window: { HOUSE_CONCEPT_LAYOUT: layout },
    getComputedStyle: panel => ({ display: active === panel.id ? 'block' : 'none' }),
  });
  const locator = selector => {
    if (selector === 'body') return { innerText: async () => 'Meaningful HTML body content. '.repeat(10) };
    if (selector.startsWith('vite-error-overlay')) return { count: async () => 0 };
    const id = floorIdOf(selector);
    if (selector.startsWith('.floor-tabs ')) {
      assert.match(selector, /\[role="tab"\]\[aria-controls="floor-[1-4]"\]/);
      return { click: async () => { active = id; clicks.push(id); } };
    }
    assert.match(selector, /^#floor-[1-4](?: \.shared-furniture-plan)?$/);
    return {
      isVisible: async () => active === id,
      locator(child) {
        if (child === 'img') return { scrollIntoViewIfNeeded: async () => {
          assert.equal(active, id, 'hidden floor must never be scrolled');
          scrolled.push(id);
          loaded.add(id);
        } };
        if (child.startsWith('[data-care-function-check=')) return { count: async () => 1 };
        if (child === '[data-requirement-id="A.floor-1.elder"]') return {
          count: async () => 1,
          locator: sub => { assert.equal(sub, 'summary'); return { click: async () => { assert.equal(active, 'floor-1'); } }; },
          innerText: async () => '雙人床 衣櫃',
        };
        assert.equal(child, '[data-furniture-id]');
        return { evaluateAll: async fn => fn(building.floors.find(f => f.id === id).rooms.flatMap(r => r.furniture)
          .map(item => ({ getAttribute: name => { assert.equal(name, 'data-furniture-id'); return item.id; },
            textContent: item.label + ' ' + item.width_mm + ' × ' + item.depth_mm + ' × ' + item.height_mm + 'mm' }))) };
      },
      getByRole(role, options) {
        assert.equal(role, 'link');
        assert.equal(options.name, '在 3D 核對這一層');
        return { click: async () => {
          assert.equal(active, id, '1F link must not be clicked while RF is active');
          throw new Error('intentional end of HTML contract fixture');
        } };
      },
    };
  };
  const fakePage = {
    setDefaultTimeout() {}, setDefaultNavigationTimeout() {}, on() {},
    context: () => ({ route: async () => {} }), setViewportSize: async () => {},
    goto: async url => { assert.equal(url, base + 'AbuildingView.html'); },
    url: () => base + 'AbuildingView.html', title: async () => 'A building',
    locator, evaluate, screenshot: async () => {},
    waitForFunction: async (fn, arg) => { assert.ok(evaluate(fn, arg), 'expected UI condition was not satisfied'); },
  };
  const script = new vm.Script('(' + makeBrowserScript(base, 'C:\\QA', { floors: 12, rooms: 92, items: 157 }) + ')');
  const result = await script.runInNewContext({})(fakePage);
  assert.equal(result.status, 'failed'); // Intentionally stop before any 3D QA.
  assert.match(result.error, /intentional end of HTML contract fixture/);
  assert.deepEqual(clicks, ['floor-1', 'floor-2', 'floor-3', 'floor-4', 'floor-1']);
  assert.deepEqual(scrolled, ['floor-1', 'floor-1', 'floor-2', 'floor-3', 'floor-4']);
  assert.equal(result.checks.filter(c => c.name.includes('tab shows its panel')).length, 5);
  assert.ok(result.checks.every(c => c.passed));
});

test('serialized room selection disambiguates A/C elder labels and rejects missing, duplicate or hidden targets', async t => {
  // Execute the actual run-code helper in a Node-free VM. This verifies the
  // selector contract, not browser rendering, visibility or clickability.
  const script = makeBrowserScript('file:///project/', 'C:\\QA', { floors: 12, rooms: 105, items: 129 });
  const source = script.match(/  const selectRoomLabel = async roomId => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source, 'room-label helper must survive serialization');
  assert.ok(script.includes("await selectRoomLabel('C:floor-1:elder');"), 'mobile QA must use the tested helper');
  const a = { id: 'A:floor-1:flex1', text: '孝親房（床＋衣櫃＋照護轉位）', visible: false };
  const c = { id: 'C:floor-1:elder', text: '後段孝親房（轉位待演練）', visible: true };
  for (const [name, labels, error] of [
    ['same-name hidden A and visible C', [a, c], null],
    ['missing C', [a], /has one navigation label/],
    ['duplicate C', [a, c, c], /has one navigation label/],
    ['hidden C', [a, { ...c, visible: false }], /navigation label is visible/],
  ]) {
    await t.test(name, async () => {
      const clicks = [];
      let selected = '';
      const page = {
        locator(selector) {
          const match = selector.match(/^\.nav-label\.room\[data-room="([^"]+)"\]$/);
          assert.ok(match, 'selector must use the exact room ID, never shared text or DOM order');
          const matches = labels.filter(label => label.id === match[1]);
          return { count: async () => matches.length, isVisible: async () => matches.length === 1 && matches[0].visible,
            click: async () => {
              assert.equal(matches.length, 1);
              assert.equal(matches[0].visible, true);
              clicks.push(matches[0].id);
              selected = matches[0].id;
            } };
        },
        waitForFunction: async (fn, id) => {
          assert.ok(vm.runInNewContext('(' + fn.toString() + ')(id)', {
            id, window: { __htmlModel3dDebug: () => ({ state: { room: selected } }) },
          }), 'selection must update the room state');
        },
      };
      const select = vm.runInNewContext(source + '\nselectRoomLabel', {
        page, assert: (condition, message) => assert.ok(condition, message),
      });
      if (error) {
        await assert.rejects(select(c.id), error);
        assert.deepEqual(clicks, []);
      } else {
        await select(c.id);
        assert.deepEqual(clicks, [c.id]);
      }
    });
  }
});

test('serialized upstairs QA independently rejects missing fixtures, reduced allowances and hidden closet tradeoffs', async t => {
  // Exercise the real helper in run-code's Node-free VM. This is a data/CLI
  // regression, not a browser-rendered acceptance result.
  const script = makeBrowserScript('file:///project/', 'C:\\QA', { floors: 12, rooms: 105, items: 129 });
  const source = script.match(/  const checkUpperFloor = \(building, floor, debug\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source, 'upstairs checks must survive serialization');
  assert.ok(script.includes('checkUpperFloor(building, floor, debug);'));
  for (const id of ['A', 'B']) {
    for (const key of id === 'A' ? ['master-bath', 'hall2'] : ['bath2', 'master-bath2']) {
      assert.ok(script.includes("['" + (id === 'A' ? 'master-bath' : 'bath2') + "', '" +
        (id === 'A' ? 'hall2' : 'master-bath2') + "']"), key + ' has a closeup capture target');
    }
  }
  const shared = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const makeCase = id => {
    const floor = structuredClone(shared.buildings.find(b => b.id === id).floors.find(f => f.id === 'floor-2'));
    const items = floor.rooms.flatMap(r => r.furniture);
    const debug = { layoutReview: { status: 'proposal-owner-and-architect-review-pending' }, furniture: {
      pendingItems: items.filter(i => i.placement.issues.length).map(i => i.id),
      shapes: items.map(i => ({ id: i.id, visible: !i.placement.issues.length })),
    } };
    return { id, floor, debug };
  };
  const check = vm.runInNewContext(source + '\ncheckUpperFloor', {
    assert: (condition, message) => assert.ok(condition, message),
  });
  for (const [name, id, mutate, error] of [
    ['current A', 'A', () => {}, null],
    ['current B', 'B', () => {}, null],
    ['public basin omitted to fit ensuite', 'B', c => c.floor.rooms.find(r => r.key === 'bath2').furniture.shift(), /three fixtures/],
    ['undersized basin', 'A', c => c.floor.rooms.find(r => r.key === 'master-bath').furniture[0].width_mm = 500, /catalogue dimensions/],
    ['reduced front allowance', 'B', c => c.floor.rooms.find(r => r.key === 'master-bath2').furniture[0].front_clearance_mm = 100, /operating allowance/],
    ['sharing exception hides collision', 'A', c => c.floor.rooms.find(r => r.key === 'master-bath').furniture[0].shared_operation_with.push('door-approach'), /sharing exception/],
    ['toilet touching basin', 'A', c => c.floor.rooms.find(r => r.key === 'master-bath').furniture[1].placement.aabb.minX = 715.2, /touch the basin/],
    ['fixture not displayed', 'B', c => c.debug.furniture.shapes.find(i => i.id === 'B:floor-2:master-bath2:furniture:vanity').visible = false, /actually displayed/],
    ['wardrobes falsely credited', 'A', c => c.debug.furniture.pendingItems = [], /pending list/],
    ['wardrobe silently downsized', 'A', c => c.floor.rooms.find(r => r.key === 'walkin').furniture[0].width_mm = 1200, /full-size wardrobes/],
    ['operation caveat removed', 'A', c => c.floor.rooms.find(r => r.key === 'hall2').furniture[0].note = '', /not simultaneous access/],
    ['false professional acceptance', 'B', c => c.debug.layoutReview.status = 'approved', /unapproved proposal/],
  ]) {
    await t.test(name, () => {
      const c = makeCase(id);
      mutate(c);
      if (error) assert.throws(() => check(c.id, c.floor, c.debug), error);
      else check(c.id, c.floor, c.debug);
    });
  }
});

test('serialized cutaway QA requires body sightlines, preserved dimensions and reversible architecture controls', async t => {
  const script = makeBrowserScript('file:///project/', 'C:\\QA', { floors: 12, rooms: 105, items: 129 });
  const source = script.match(/  const checkRoomCutaway = \(debug, roomId, fixtureCount\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source);
  for (const expected of ['checkRoomCutaway(focused, id, fixtureCount)', 'full-height switch restores',
    'orbit recomputes obstruction', 'returning to whole floor restores', 'A-3D-mobile-2F-master-bath-closeup.png',
    'A-3D-2F-master-bath-full-walls.png', 'A-3D-2F-master-bath-rotated-cutaway.png',
    'preserves HTML geometry, placements and pending furniture']) assert.ok(script.includes(expected), expected);
  const roomId = 'A:floor-2:master-bath';
  const state = () => ({ roomCloseup: true, roomCutaway: { active: true, heightMm: 550,
    parts: [{ room: roomId, role: 'wall', face: 'front' }],
    fixtureSightlines: ['vanity', 'toilet', 'shower'].map(id => ({ id: roomId + ':furniture:' + id, samples: 5, unobstructedSamples: 5 })),
    limitation: 'not pixel visibility or professional approval' } });
  const check = vm.runInNewContext(source + '\ncheckRoomCutaway', {
    assert: (condition, message) => assert.ok(condition, message),
  });
  for (const [name, mutate, error] of [
    ['valid body evidence', () => {}, null],
    ['closeup off', s => s.roomCloseup = false, /cutaway active/],
    ['auto cutaway off', s => s.roomCutaway.active = false, /cutaway active/],
    ['geometry height mistaken for cut height', s => s.roomCutaway.heightMm = 3000, /cutaway active/],
    ['HVAC cut instead of wall', s => s.roomCutaway.parts[0].role = 'hvac', /architecture only/],
    ['fixture omitted', s => s.roomCutaway.fixtureSightlines.pop(), /fixture-body samples/],
    ['labels visible but body blocked', s => s.roomCutaway.fixtureSightlines[0].unobstructedSamples = 0, /fixture-body samples/],
    ['unrelated room evidence', s => s.roomCutaway.fixtureSightlines[0].id = 'B:floor-2:bath2:furniture:toilet', /fixture-body samples/],
    ['visual acceptance falsely implied', s => s.roomCutaway.limitation = 'passed', /do not imply/],
  ]) await t.test(name, () => {
    const value = state();
    mutate(value);
    if (error) assert.throws(() => check(value, roomId, 3), error);
    else check(value, roomId, 3);
  });
});

test('mobile bathroom context uses all shared room IDs instead of a hard-coded room count', async t => {
  // Execute the serialized production assertion with real shared-floor data.
  // This is a CLI regression, not a rendered-browser acceptance result.
  const script = makeBrowserScript('file:///project/', 'C:\\QA', { floors: 12, rooms: 105, items: 129 });
  const definition = script.match(/  const checkMobileBathroomContext = \(debug, floor\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);
  assert.ok(script.includes("checkMobileBathroomContext(mobileBath, sharedFloors['A:floor-2'])"));
  assert.ok(!script.includes('mobileBath.visibleRooms.length === 9'));
  const shared = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const floor = shared.buildings.find(b => b.id === 'A').floors.find(f => f.id === 'floor-2');
  assert.equal(floor.rooms.length, 10, 'reproduce the floor that the former assertion incorrectly counted as nine');
  const fixture = () => ({ state: { building: 'A', floor: 'floor-2', room: 'A:floor-2:master-bath' },
    visibleRooms: floor.rooms.map(r => r.id), panelCollapsed: true,
    focusedScreenBounds: Array.from({ length: 8 }, () => [.5, .5, 0]),
    furniture: { pendingItems: floor.rooms.flatMap(r => r.furniture).filter(i => i.placement.issues.length).map(i => i.id),
      shapes: floor.rooms.flatMap(r => r.furniture).map(i => ({ id: i.id, visible: !i.placement.issues.length,
        width: i.width_mm, depth: i.depth_mm, height: i.height_mm })) } });
  const check = vm.runInNewContext(definition + '\ncheckMobileBathroomContext', {
    assert: (condition, message) => assert.ok(condition, message),
  });
  for (const [name, mutate, error] of [
    ['current ten-room floor', () => {}, null],
    ['room order differs', d => d.visibleRooms.reverse(), null],
    ['missing room', d => d.visibleRooms.pop(), /exact shared room IDs.*expected 10, got 9/],
    ['wrong room despite matching count', d => d.visibleRooms[0] = 'B:floor-2:master', /exact shared room IDs/],
    ['duplicate room despite matching count', d => d.visibleRooms[0] = d.visibleRooms[1], /exact shared room IDs/],
    ['extra room', d => d.visibleRooms.push('A:floor-1:flex1'), /exact shared room IDs/],
    ['wrong selected room', d => d.state.room = 'C:floor-1:elder', /shared floor and room/],
    ['wrong selected floor', d => d.state.floor = 'floor-1', /shared floor and room/],
    ['missing wardrobe', d => d.furniture.pendingItems.pop(), /specific pending wardrobes/],
    ['wrong wardrobe IDs with the same count', d => d.furniture.pendingItems[0] = 'other-wardrobe', /specific pending wardrobes/],
    ['pending wardrobe not retained in model', d => d.furniture.shapes = d.furniture.shapes.filter(i => i.id !== d.furniture.pendingItems[0]), /original dimensions/],
    ['pending wardrobe falsely displayed', d => d.furniture.shapes.find(i => i.id === d.furniture.pendingItems[0]).visible = true, /original dimensions/],
    ['wardrobe silently downsized', d => d.furniture.shapes.find(i => i.id === d.furniture.pendingItems[0]).width = 1200, /original dimensions/],
    ['panel inadvertently expanded', d => d.panelCollapsed = false, /controls collapsed/],
    ['room outside mobile frame', d => d.focusedScreenBounds[0][0] = 1.1, /fits the resized stage/],
    ['no camera-frame evidence', d => d.focusedScreenBounds = [], /fits the resized stage/],
  ]) await t.test(name, () => {
    const debug = fixture();
    mutate(debug);
    if (error) assert.throws(() => check(debug, floor), error);
    else check(debug, floor);
  });
});

test('serialized mobile panel setup is idempotent across hash navigation and waits for renderer resize', async t => {
  const script = makeBrowserScript('file:///project/', 'C:\\QA', { floors: 12, rooms: 105, items: 129 });
  const definition = script.match(/  const collapseMobilePanel = async \(\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);
  assert.equal((script.match(/await collapseMobilePanel\(\)/g) || []).length, 6, 'all six mobile setup points, including C frontage/lounge and exterior, use explicit state');
  assert.ok(!script.includes("await page.locator('#mobile-panel-toggle').click()"));
  for (const initial of ['true', 'false']) await t.test('initial aria-expanded=' + initial, async () => {
    let expanded = initial, clicks = 0, waits = 0;
    const stage = { clientWidth: 390, clientHeight: 790 };
    const canvas = { width: 780, height: 1580 };
    const toggle = { getAttribute: async () => expanded, click: async () => {
      clicks++;
      expanded = expanded === 'true' ? 'false' : 'true';
      canvas.height = 944; // renderer still uses the old expanded-panel height
    } };
    const document = { getElementById: id => ({ stage, canvas,
      'mobile-panel-toggle': { getAttribute: () => expanded } })[id] };
    const window = { devicePixelRatio: 2, innerHeight: 844, __htmlModel3dDebug: () => ({ panelCollapsed: expanded === 'false' }) };
    const setup = vm.runInNewContext(definition + '\ncollapseMobilePanel', {
      assert: (condition, message) => assert.ok(condition, message), document, window,
      page: { locator: selector => { assert.equal(selector, '#mobile-panel-toggle'); return toggle; },
        waitForFunction: async predicate => {
          waits++;
          if (initial === 'true' && waits === 1) {
            assert.equal(predicate(), false, 'wait for delayed renderer resize, not merely the collapsed class');
            canvas.height = stage.clientHeight * window.devicePixelRatio;
          }
          assert.equal(predicate(), true, 'collapsed panel and renderer dimensions are ready');
        } },
    });
    await setup();
    await setup();
    assert.equal(expanded, 'false');
    assert.equal(clicks, initial === 'true' ? 1 : 0, 'never expand an already-collapsed panel');
    assert.equal(waits, 2);
  });
});

test('nested CLI JSON results parse, but code echoes and ordinary logs cannot imply success', () => {
  const report = passingReport({ floors: 12, rooms: 92, items: 157 });
  assert.equal(findReport(JSON.parse(JSON.stringify({ result: JSON.stringify(report) }))).status, 'passed');
  assert.equal(findReport({ result: JSON.stringify({ ...report, status: 'failed' }) }).status, 'failed');
  assert.equal(findReport({ content: [{ text: 'async page => { return ' + JSON.stringify(report) + '; }' }] }), null);
  assert.equal(findReport({ code: 'exit 0', status: 'open' }), null);
});

test('partial counts, failed checks, missing screenshots and absent structured data cannot pass', () => {
  const counts = { floors: 12, rooms: 92, items: 157 };
  const valid = passingReport(counts);
  assert.equal(validateReport(valid, counts), valid);
  for (const invalid of [null, { status: 'passed' }, { ...valid, checks: [] },
    { ...valid, checks: [{ passed: false }] }, { ...valid, counts: { ...counts, rooms: 1 } },
    { ...valid, screenshots: [] }]) assert.throws(() => validateReport(invalid, counts));
});

test('QA commands use one isolated named session and output folder, never shell/global cleanup', t => {
  const f = fixture(t);
  const prepared = preflight(f.project);
  const fake = fakeCli(passingReport(prepared.counts));
  const report = runQa({ project: f.project, browser: 'msedge' }, prepared, f.output, fake.execute);
  assert.equal(report.status, 'passed');
  assert.equal(report.sessionClosed, true);
  assert.equal(fake.calls.length, 3);
  const sessions = fake.calls.map(call => call.args.find(arg => arg.startsWith('-s=')));
  assert.equal(new Set(sessions).size, 1);
  assert.ok(sessions[0].startsWith('-s=house-qa-'));
  for (const call of fake.calls) {
    assert.equal(call.options.cwd, f.output);
    assert.equal(call.options.env.PWTEST_DAEMON_SESSION_DIR, path.join(f.output, 'daemon'));
    assert.equal(call.options.shell, undefined);
    assert.ok(!call.args.includes('close-all') && !call.args.includes('kill-all'));
  }
  assert.deepEqual(report.sourceHashes, hashSources(f.project, prepared.sourceFiles));
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.output, 'cli.config.json'))).browser.launchOptions.channel, 'msedge');
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.output, 'result.json'))).status, 'passed');
});

test('source changes during QA invalidate a previously passing result', t => {
  const f = fixture(t);
  const prepared = preflight(f.project);
  const fake = fakeCli(passingReport(prepared.counts), () => f.write('AbuildingView.html', 'changed during fake QA'));
  const report = runQa({ project: f.project, browser: 'chrome' }, prepared, f.output, fake.execute);
  assert.equal(report.status, 'incomplete');
  assert.match(report.error, /Source files changed/);
});

test('launch failure still records an incomplete report and closes only its own session', t => {
  const f = fixture(t);
  const prepared = preflight(f.project);
  const commands = [];
  const execute = (executable, args) => {
    commands.push(args);
    return args.includes('close') ? { status: 0, stdout: '{"status":"not-open"}' }
      : { status: 1, stderr: 'fixture: installed Edge unavailable' };
  };
  const report = runQa({ project: f.project, browser: 'msedge' }, prepared, f.output, execute);
  assert.equal(report.status, 'incomplete');
  assert.equal(report.sessionClosed, true);
  assert.match(report.error, /open failed/);
  assert.equal(commands.length, 2);
  assert.match(fs.readFileSync(path.join(f.output, 'open.log'), 'utf8'), /Edge unavailable/);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.output, 'result.json'))).status, 'incomplete');
});

test('successful process exit with no result marker remains incomplete', t => {
  const f = fixture(t);
  const prepared = preflight(f.project);
  const fake = fakeCli({ status: 'ok' });
  const report = runQa({ project: f.project, browser: 'msedge' }, prepared, f.output, fake.execute);
  assert.equal(report.status, 'incomplete');
  assert.equal(report.sessionClosed, true);
  assert.match(report.error, /No valid structured QA result/);
});
