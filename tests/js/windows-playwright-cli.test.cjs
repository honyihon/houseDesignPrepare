const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {
  parseArguments, preflight, hashSources, makeBrowserScript, findReport, validateReport, runQa,
  preflightMdf, preflightFengshui, preflightBcOptions, preflightSpaceAllocation,
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
    'assets/html_design_bridge.js', 'assets/html_design_bridge.css', 'assets/plan_viewer.js', 'assets/vendor/three/three.min.js',
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
      return { id: floor, plan_file: plan, base_mm:(number-1)*3000, height_mm:3000,
        rooms: [{ id: id + ':' + floor + ':fixture', key:'fixture', name:'Fixture room',
          geometry:{x_mm:0,y_mm:0,w_mm:6000,h_mm:17630}, furniture: [{ id: 'fixture-item' }] }] };
    }) })) };
  layout.facade = {schema: 'house-facade-layer-v1', id: 'fixture-facade', geometry_source: 'tour_mm',
    reference: {file: 'assets/references/facade-photo-v1.jpg',sha256:referenceHash}, buildings: ['A','B','C'].map(id => {
      const elevation_file = id + '_facade-front.svg';
      write('structured/candidates/furniture-plans/' + elevation_file, '<svg/>');
      return {id,elevation_file};
    })};
  write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = ' + JSON.stringify(layout) + ';\n');
  for (const id of ['baseline','bath-front','front-living']) write('structured/candidates/c1f-options/'+id+'.svg','<svg/>');
  write('structured/candidates/c1f-options.html');write('structured/candidates/c1f-options-3d.html');
  write('inputs/c1f-bath-daylight-options.json');
  const study={schema:'house-c1f-options-v1',status:'comparison-only-not-adopted',active_design:'baseline',
    source_hashes:{'inputs/c1f-bath-daylight-options.json':referenceHash},options:['baseline','bath-front','front-living'].map(id=>({
      id,public_bath_verified:null,daylight_verified:null,plumbing_verified:null,
      floor:{...layout.buildings[2].floors[0],plan_file:id+'.svg'}
    }))};
  write('structured/candidates/c1f-options/layout.js','window.HOUSE_C1F_OPTIONS = '+JSON.stringify(study)+';\n');
  write('inputs/abc-arcade-capacity.json');
  write('structured/candidates/arcade-capacity.html');write('structured/candidates/arcade-capacity-3d.html');
  const referencePath='inputs/references/abc-before-a-arcade.json';
  const reference=JSON.stringify({buildings:Object.fromEntries(layout.buildings.map(b=>[b.id,{
    floors:Object.fromEntries(b.floors.map(f=>[f.id,{rooms:Object.fromEntries(f.rooms.map(r=>[r.key,{
      name:r.name,rect:[r.geometry.x_mm,r.geometry.y_mm,r.geometry.w_mm,r.geometry.h_mm]}]))}]))}]))});
  write(referencePath,reference);
  const arcade={schema:'house-abc-arcade-capacity-v1',status:'comparison-only-not-adopted',active_design:'main-a32-arcade-v1',
    reference_review:referencePath,default_comparison:'arcade32',
    professional_status:Object.fromEntries(['parcel_dimensions','arcade_applicability','building_area','coverage_and_far',
      'arcade_clear_height','structure_and_fire','accessibility','daylight_and_ventilation',
      'hvac_installation','feng_shui_and_altar_orientation'].map(key=>[key,'unknown'])),
    source_hashes:{'inputs/abc-arcade-capacity.json':referenceHash,
      [referencePath]:require('node:crypto').createHash('sha256').update(reference).digest('hex')},
    options:['baseline','arcade32','room-first'].map(id=>({id,plans:{buildings:layout.buildings.map(b=>({id:b.id,
      floors:b.floors.map(f=>{const plan=id+'_'+b.id+'_'+f.id+'.svg';write('structured/candidates/arcade-capacity/'+plan,'<svg/>');
        return {...f,plan_file:plan};})}))},capacity:Object.fromEntries(['A','B','C'].map(b=>[b,{
        legal_building_area_sqm:null,arcade_net_height_verified:null,verified_parking_spaces:null,displayed_cars:0,
        coverage_sensitivity:[{legal_result:'unknown'}]
      }]))}))};
  write('structured/candidates/arcade-capacity/layout.js','window.HOUSE_ARCADE_CAPACITY = '+JSON.stringify(arcade)+';\n');
  const output = path.join(project, 'qa-output');
  fs.mkdirSync(output);
  return { project, output, write, layout, study, arcade };
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
  assert.equal(prepared.sourceFiles.length, 79);
  assert.match(prepared.cli, /node_modules[/\\]playwright[/\\]cli\.js$/);
  f.write('structured/candidates/furniture-plans/layout.js', 'window.HOUSE_CONCEPT_LAYOUT = process.exit(0);');
  assert.throws(() => preflight(f.project), SyntaxError);
});

test('space-allocation review uses real geometry and keeps professional status and B32 priority unapproved', () => {
  const layout=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  assert.ok(preflightSpaceAllocation(root,layout).includes('Docs/abc-space-efficiency-v1.md'));
  const scenarios=[
    [s=>{s.layout_review.space_efficiency_review.professional_acceptance='passed';},/unverified/],
    [s=>{s.layout_review.space_efficiency_review.b_priority.status='adopted';},/unverified/],
    [s=>{s.layout_review.space_efficiency_review.floors[1].circulation_nominal_sqm+=1;},/actual tour coordinates/],
    [s=>{s.buildings[0].floors[1].rooms.find(r=>r.key==='master').geometry.w_mm+=100;},/actual tour coordinates/],
    [s=>{const suite=s.buildings[1].floors[1].rooms.find(r=>r.key==='master-bath2');suite.kind='bedroom';
      s.layout_review.space_efficiency_review.floors.find(a=>a.building==='B'&&a.floor==='floor-2').bedroom_nominal_sqm+=5.49;
    },/fix regressed/],
    [s=>{s.buildings[2].floors[2].rooms.find(r=>r.key==='fitness3f').features.doors
      .find(d=>d.neighbor==='C:floor-3:front-hall').neighbor='C:floor-3:master3f';},/private through-route/],
  ];
  for (const [mutate,expected] of scenarios) {
    const changed=structuredClone(layout);mutate(changed);
    assert.throws(()=>preflightSpaceAllocation(root,changed),expected);
  }
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
  assert.deepEqual(prepared.counts, { floors: 12, rooms: 112, items: 128 });
  assert.ok(prepared.sourceFiles.length >= 38, 'hash C1F study artifacts and their generator sources as well as main plans');
  assert.ok(prepared.sourceFiles.includes('structured/candidates/c1f-options-3d.html'));
  assert.ok(prepared.sourceFiles.includes('structured/candidates/arcade-capacity-3d.html'));
  assert.ok(prepared.sourceFiles.includes('Docs/fengshui-minimal-v1.md'));
  assert.ok(prepared.sourceFiles.includes('scripts/lib/model3d_fengshui.py'));
  assert.deepEqual(preflight(root), prepared);
  assert.deepEqual(hashSources(root, prepared.sourceFiles), before);
});

test('minimal fengshui preflight retains unknown decisions and hashes their real sources', t => {
  const shared = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const files = ['Docs/fengshui-minimal-v1.md', 'scripts/lib/model3d_fengshui.py'];
  assert.deepEqual(preflightFengshui(root, shared), files);
  for (const mutate of [
    d => delete d.layout_review.fengshui_minimal,
    d => d.layout_review.fengshui_minimal.status = 'approved',
    d => d.layout_review.fengshui_minimal.religious_acceptance = 'passed',
    d => d.layout_review.fengshui_minimal.structural_acceptance = 'passed',
    d => d.layout_review.fengshui_minimal.pending_decisions.pop(),
    d => d.layout_review.fengshui_minimal.pending_decisions[0].id = 'B-upper-use',
    d => d.layout_review.fengshui_minimal.pending_decisions[0].status = 'adopted',
    d => d.layout_review.fengshui_minimal.document = '../private.json',
  ]) {
    const data = structuredClone(shared);mutate(data);
    assert.throws(() => preflightFengshui(root, data), /fengshui/i);
  }
  assert.deepEqual(preflightFengshui(root, {layout_review:{id:'historical'}}), []);
  const f = fixture(t);
  assert.throws(() => preflightFengshui(f.project, shared), /Missing fengshui source/);
  for (const file of files) f.write(file);
  assert.deepEqual(preflightFengshui(f.project, shared), files);
});

test('serialized minimal fengshui QA catches false approval, real worktop divergence and shrunk furniture', async t => {
  // Contract doubles below are not a rendered browser pass or screenshot proof.
  const {checkPages} = require('../../scripts/check_windows_playwright.cjs');
  const definition = checkPages.toString().match(/  function checkMinimalFengshui\(building, floor, debug\) \{[\s\S]*?\n  }/)?.[0];
  assert.ok(definition);
  const shared = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
  const sharedFloors = Object.fromEntries(shared.buildings.flatMap(b => b.floors.map(f => [b.id + ':' + f.id, f])));
  const check = vm.runInNewContext(definition + '\ncheckMinimalFengshui', {
    sharedFloors, assert:(value,message) => assert.ok(value,message),
  });
  const make = (building, id) => {
    const floor = structuredClone(sharedFloors[building + ':' + id]);
    const shapes = floor.rooms.flatMap(r => r.furniture.map(i => ({
      id:i.id, visible:true, overflow:false, collision:false,
      width:i.width_mm, depth:i.depth_mm, height:i.height_mm,
      rotation:i.placement.rotation_deg, placement:structuredClone(i.placement),
      worktopParts:structuredClone(i.placement.worktop_parts_mm || []),
    })));
    return {floor, debug:{layoutReview:structuredClone(shared.layout_review), furniture:{shapes}}};
  };
  const shape = (s, tail) => s.debug.furniture.shapes.find(i => i.id.endsWith(tail));
  for (const [b,f] of [['A','floor-1'],['B','floor-1'],['B','floor-2'],['B','floor-3'],['C','floor-1'],['C','floor-3']]) {
    const s = make(b,f);check(b,s.floor,s.debug);
  }
  for (const [b,f,name,mutate,error] of [
    ['A','floor-1','contract removed',s => delete s.debug.layoutReview.fengshui_minimal,/decision contract/],
    ['A','floor-1','approval invented',s => s.debug.layoutReview.fengshui_minimal.religious_acceptance='passed',/decisions unknown/],
    ['A','floor-1','rendered hob removed',s => shape(s,':counter').worktopParts.pop(),/both rendered worktop parts/],
    ['A','floor-1','actual hob does not match shared data',s => shape(s,':counter').worktopParts[0].aabb.minY+=100,/shared worktop transform/],
    ['A','floor-1','whole kitchen approval invented',s => s.debug.layoutReview.checks.find(c=>c.id==='A-hob-wet-projection').scope='whole-kitchen-approved',/whole kitchen/],
    ['B','floor-2','sofa shrink',s => shape(s,':sofa').width=1800,/without shrinking/],
    ['B','floor-3','bed over altar',s => shape(s,':bed').placement.aabb=structuredClone(sharedFloors['B:floor-1'].rooms.find(r=>r.key==='shrine').furniture.find(i=>i.shape==='altar').placement.aabb),/without shrinking/],
    ['C','floor-3','bed shrink',s => shape(s,':bed').width=1500,/original-size bed/],
    ['C','floor-3','headboard turned back',s => shape(s,':bed').rotation=0,/side-wall headboard/],
    ['B','floor-1','backing silently adopted',s => s.floor.rooms.find(r=>r.key==='shrine').features.fengshui_review.status='adopted',/not an adopted alternative/],
    ['C','floor-1','care suite silently adopted',s => s.floor.rooms.find(r=>r.key==='elder').features.fengshui_review.status='adopted',/not an adopted alternative/],
  ]) await t.test(name, () => {
    const s=make(b,f);mutate(s);assert.throws(() => check(b,s.floor,s.debug),error);
  });
});

test('current MDF preflight rejects adoption, freed area, shrunken products or removed side clearance',()=>{
  const layout=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  assert.equal(preflightMdf(root,layout).length,4);
  for(const mutate of [
    s=>s.active_design='under-stair',s=>s.candidate.section_verified=true,s=>s.candidate.installed=true,
    s=>s.reuse.released_area_sqm=2.9,s=>s.professional_status.structural_section='passed',
    s=>s.rack.height_mm=600,s=>s.candidate.issues=[],
    s=>s.backup.placement.side_operation_mm=[],s=>s.plan_file='../../private.svg',
  ]){
    const changed=structuredClone(layout);mutate(changed.layout_review.mdf_study);
    assert.throws(()=>preflightMdf(root,changed),/MDF/);
  }
  const missing=structuredClone(layout);delete missing.layout_review.mdf_study;
  assert.throws(()=>preflightMdf(root,missing),/missing the MDF study/);
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

test('C1F preflight rejects stale baseline, adopted/approved claims and modified or unsafe source hashes',t=>{
  const f=fixture(t),{preflightC1f}=require('../../scripts/check_windows_playwright.cjs');
  const save=()=>f.write('structured/candidates/c1f-options/layout.js','window.HOUSE_C1F_OPTIONS = '+JSON.stringify(f.study)+';');
  assert.equal(preflightC1f(f.project,f.layout).length,8);
  f.study.active_design='bath-front';save();assert.throws(()=>preflightC1f(f.project,f.layout),/must stay a comparison/);
  f.study.active_design='baseline';f.study.options[1].daylight_verified=true;save();
  assert.throws(()=>preflightC1f(f.project,f.layout),/falsely approved/);
  f.study.options[1].daylight_verified=null;f.study.options[0].floor.rooms=[];save();
  assert.throws(()=>preflightC1f(f.project,f.layout),/baseline is stale/);
  f.study.options[0].floor.rooms=f.layout.buildings[2].floors[0].rooms;
  f.study.source_hashes={'../private.json':'0'.repeat(64)};save();assert.throws(()=>preflightC1f(f.project,f.layout),/Invalid C1F source/);
  f.study.source_hashes={'inputs/c1f-bath-daylight-options.json':'0'.repeat(64)};save();
  assert.throws(()=>preflightC1f(f.project,f.layout),/Stale C1F comparison source/);
});

test('conditional frontage preflight requires the exact safe file and unknown/uninstalled status', t => {
  const f=fixture(t),floor=f.layout.buildings[2].floors[0],room=floor.rooms[0];
  room.key='garage';room.furniture=[];
  room.features={frontage_study:{status:'conditional-not-installed',active_option:'keep-full-clear',site_use_status:'unknown'}};
  floor.frontage_study_file='C_floor-1_frontage-study.svg';
  const save=()=>{
    f.write('structured/candidates/furniture-plans/layout.js','window.HOUSE_CONCEPT_LAYOUT = '+JSON.stringify(f.layout)+';');
    f.study.options[0].floor={...floor,plan_file:'baseline.svg'};
    f.write('structured/candidates/c1f-options/layout.js','window.HOUSE_C1F_OPTIONS = '+JSON.stringify(f.study)+';');
  };
  save();
  assert.throws(()=>preflight(f.project),/Missing conditional frontage study/);
  f.write('structured/candidates/furniture-plans/'+floor.frontage_study_file,'<svg/>');
  assert.equal(preflight(f.project).sourceFiles.length,80);
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

test('arcade preflight rejects false adoption, approvals, stale baselines, missing plans and unsafe source paths',t=>{
  const f=fixture(t),{preflightArcade}=require('../../scripts/check_windows_playwright.cjs');
  const save=()=>f.write('structured/candidates/arcade-capacity/layout.js','window.HOUSE_ARCADE_CAPACITY = '+JSON.stringify(f.arcade)+';');
  assert.equal(preflightArcade(f.project,f.layout).length,43);
  const originalStatus=f.arcade.professional_status;
  for(const status of [{}, {...originalStatus,structure_and_fire:'verified'},
    Object.fromEntries(Object.entries(originalStatus).filter(([key])=>key!=='structure_and_fire'))]){
    f.arcade.professional_status=status;save();
    assert.throws(()=>preflightArcade(f.project,f.layout),/unapproved historical comparison/);
  }
  f.arcade.professional_status=originalStatus;
  f.arcade.active_design='arcade32';save();assert.throws(()=>preflightArcade(f.project,f.layout),/unapproved historical comparison/);
  f.arcade.active_design='main-a32-arcade-v1';f.arcade.options[1].capacity.A.legal_building_area_sqm=90;save();
  assert.throws(()=>preflightArcade(f.project,f.layout),/Falsely approved/);
  f.arcade.options[1].capacity.A.legal_building_area_sqm=null;f.arcade.options[0].plans.buildings[0].floors[0].rooms=[];save();
  assert.throws(()=>preflightArcade(f.project,f.layout),/baseline is stale/);
  f.arcade.options[0].plans.buildings[0].floors[0].rooms=f.layout.buildings[0].floors[0].rooms;
  f.arcade.source_hashes={'../private.json':'0'.repeat(64)};save();assert.throws(()=>preflightArcade(f.project,f.layout),/Invalid arcade source/);
  f.arcade.source_hashes={'inputs/abc-arcade-capacity.json':'0'.repeat(64)};save();assert.throws(()=>preflightArcade(f.project,f.layout),/Stale arcade capacity source/);
  f.arcade.source_hashes={};save();assert.throws(()=>preflightArcade(f.project,f.layout),/Missing arcade source/);
});

test('current A arcade serialized QA rejects matched drawings that erase functions or invent approvals', async t => {
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const source=checkPages.toString().match(/  const checkAMainArcade = \(floor, debug\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source);
  const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  const check=vm.runInNewContext(source+'\ncheckAMainArcade',{assert:(value,message)=>assert.ok(value,message)});
  const make=()=>({floor:structuredClone(shared.buildings[0].floors[0]),debug:{layoutReview:structuredClone(shared.layout_review)}});
  const room=(s,k)=>s.floor.rooms.find(r=>r.key===k);
  for(const [name,mutate,error] of [
    ['current main',()=>{},null],
    ['arcade removed',s=>s.floor.rooms=s.floor.rooms.filter(r=>r.key!=='arcade'),/clear 3.9m arcade/],
    ['frontage furnished',s=>room(s,'arcade').furniture=[{id:'bench'}],/clear 3.9m arcade/],
    ['frame artificially deepened',s=>s.floor.depth_mm=20000,/fixed 32-ping frame/],
    ['private room occupies frontage',s=>room(s,'living').geometry.y_mm=0,/fixed 32-ping frame/],
    ['old 3m nominal ground level',s=>s.floor.height_mm=3000,/fixed 32-ping frame/],
    ['narrow care passage',s=>room(s,'care-passage').geometry.w_mm=1200,/1200mm assumed/],
    ['MDF through route',s=>s.debug.layoutReview.checks.find(c=>c.id==='A-1F-care-functions').routes.elder_to_bath.push('A:floor-1:mdf'),/without stairs or MDF/],
    ['elder bedroom shrunk',s=>room(s,'flex1').geometry.w_mm=3000,/elder room/],
    ['bed reduced',s=>room(s,'flex1').furniture.find(i=>i.shape==='bed').width_mm=1000,/full-size original/],
    ['tiny table',s=>room(s,'living').furniture.find(i=>i.shape==='dining-set').table_width_mm=900,/normal four-seat/],
    ['margin caution removed',s=>s.debug.layoutReview.checks.find(c=>c.id==='A-32ping-arcade-functions').note='',/tight living-area/],
    ['professional approval invented',s=>s.debug.layoutReview.checks.find(c=>c.id==='A-32ping-arcade-functions').professional_acceptance='approved',/cannot invent/],
  ]) await t.test(name,()=>{const s=make();mutate(s);if(error)assert.throws(()=>check(s.floor,s.debug),error);else check(s.floor,s.debug);});
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
    ['dining disappeared',s=>s.floor.rooms=s.floor.rooms.filter(r=>r.key!=='dining'),/retains dining/],
    ['reclaim public frontage',s=>s.floor.rooms.find(r=>r.key==='living').geometry.h_mm=6000,/27.2m2/],
    ['silently resize old sofa',s=>s.floor.rooms.find(r=>r.key==='living').furniture.find(i=>i.catalog_id==='sofa-2').width_mm=1500,/ordinary product/],
    ['TV not facing sofa',s=>s.floor.rooms.find(r=>r.key==='living').furniture.find(i=>i.catalog_id==='wall-tv').placement.wall_anchor='front',/faces normal sofa/],
    ['turning reserve removed',s=>s.floor.rooms.find(r=>r.key==='living').features.reserved_mm=[],/care route/],
    ['shrink working strip',s=>s.floor.rooms.find(r=>r.key==='kitchen').furniture.find(i=>i.catalog_id==='counter-240-60').front_clearance_mm=600,/sequential use/],
    ['fake model approval',s=>s.debug.layoutReview.hvac_routes.find(r=>r.id==='C-AC01').compliance='passed',/no model/],
    ['partition restored',s=>s.floor.rooms.find(r=>r.key==='dining').features.open_connections[0].width_mm=1000,/no partition/],
    ['false open-plan approval',s=>s.debug.layoutReview.checks.find(c=>c.id==='C-open-living-dining').fire_acceptance='passed',/professional approval/],
    ['unknown land marked usable',s=>s.floor.rooms.find(r=>r.key==='garage').features.frontage_study.site_use_status='verified',/unknown frontage/],
  ])await t.test(name,()=>{
    const state=make();mutate(state);
    if(error)assert.throws(()=>check(state.floor,state.debug),error);else check(state.floor,state.debug);
  });
});

test('C1F SVG QA reads current separate geometry and top-label layers without legacy child anchors', async t => {
  // Shape fixtures from real SVG attributes, not a DOM/rendered browser pass.
  const {checkPages} = require('../../scripts/check_windows_playwright.cjs');
  const definition = name => {
    const source = checkPages.toString().match(new RegExp('  const ' + name + ' = [\\s\\S]*?\\n  };'))?.[0];
    assert.ok(source, name + ' must survive the Node-free run-code serialization');
    return source;
  };
  const study = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/c1f-options/layout.js'), 'utf8')
    .replace(/^window.HOUSE_C1F_OPTIONS = /, '').replace(/;\s*$/, ''));
  const attributes = tag => Object.fromEntries(Array.from(tag.matchAll(/([\w:-]+)="([^"]*)"/g),
    ([, key, value]) => [key, value.replace(/&amp;/g, '&')]));
  const node = values => ({ getAttribute: key => values[key] ?? null, hasAttribute: key => key in values,
    querySelector: () => null });
  const collect = option => {
    const xml = fs.readFileSync(path.join(root, 'structured/candidates/c1f-options', option.id + '.svg'), 'utf8');
    const groups = Array.from(xml.matchAll(/<g\b[^>]*\bdata-room-id="[^>]*>/g), ([tag]) => node(attributes(tag)));
    const labelLayer = xml.match(/<g data-plan-labels="room-names">([\s\S]*?)<\/g>/)?.[1];
    assert.ok(labelLayer, 'use the actual top-level room-name layer');
    const labels = Array.from(labelLayer.matchAll(/<a\b[^>]*\bdata-label-room-id="[^>]*>/g),
      ([tag]) => node(attributes(tag)));
    const rootValues = attributes(xml.match(/<svg\b[^>]*>/)[0]);
    const documentElement = { ...node(rootValues), localName: 'svg', namespaceURI: rootValues.xmlns,
      querySelectorAll: selector => {
        if (selector === 'g[data-room-id]') return groups;
        assert.equal(selector, '[data-plan-labels="room-names"] a[data-label-room-id]');
        return labels;
      } };
    const collected = vm.runInNewContext(definition('collectCStudySvg') + '\ncollectCStudySvg()', {
      document: { documentElement },
    });
    assert.throws(() => groups[0].querySelector('a').getAttribute('href'), /null/,
      'the legacy accessor fails on a geometry group without a child anchor');
    return JSON.parse(JSON.stringify(collected));
  };
  const check = vm.runInNewContext(definition('checkCStudySvg') + '\ncheckCStudySvg', {
    assert: (value, name) => assert.ok(value, name),
  });
  for (const option of study.options) await t.test(option.id + ' real SVG coordinates and links', () => {
    const loaded = collect(option);
    assert.equal(loaded.rooms.length, option.floor.rooms.length);
    assert.equal(loaded.labels.length, option.floor.rooms.length);
    check(option, loaded);
  });
  const option = study.options[0], base = collect(option);
  for (const [name, mutate, error] of [
    ['HTML shell instead of native SVG', s => s.kind = 'html', /SVG document/],
    ['wrong namespace', s => s.namespace = null, /SVG document/],
    ['wrong selected scheme', s => s.option = 'front-living', /SVG document/],
    ['false adoption', s => s.status = 'adopted', /SVG document/],
    ['missing geometry group', s => s.rooms.pop(), /exact room coordinates/],
    ['duplicate geometry ID with matching count', s => s.rooms[0].id = s.rooms[1].id, /exact room coordinates/],
    ['incorrect geometry', s => s.rooms[0].geometry[2] += 100, /exact room coordinates/],
    ['missing zero-position attribute', s => s.rooms[0].geometry[0] = null, /exact room coordinates/],
    ['missing top-layer label', s => s.labels.pop(), /top-layer room labels/],
    ['duplicate label ID with matching count', s => s.labels[0].id = s.labels[1].id, /top-layer room labels/],
    ['orphan label', s => s.labels[0].id = 'C:floor-1:invented', /top-layer room labels/],
    ['missing link href', s => s.labels[0].url = null, /top-layer room labels/],
    ['link to another scheme', s => s.labels[0].url = s.labels[0].url.replace('scheme=baseline', 'scheme=bath-front'), /top-layer room labels/],
    ['link to wrong room', s => s.labels[0].url = s.labels[1].url, /top-layer room labels/],
    ['link to old ABC main', s => s.labels[0].url = s.labels[0].url.replace('c1f-options-3d.html', 'model3d.html'), /top-layer room labels/],
    ['external link with matched query', s => s.labels[0].url = 'https://example.invalid/' + s.labels[0].url, /top-layer room labels/],
  ]) await t.test(name, () => {
    const loaded = structuredClone(base); mutate(loaded);
    assert.throws(() => check(option, loaded), error);
  });
});

test('A2 SVG label QA uses actual browser font bounds and cannot hide or move outdoor units', async t => {
  // Browser-boundary doubles only, not new rendered screenshot evidence.
  const {checkPages} = require('../../scripts/check_windows_playwright.cjs');
  const definition = name => {
    const source = checkPages.toString().match(new RegExp('  const ' + name + ' = [\\s\\S]*?\\n  };'))?.[0];
    assert.ok(source); return source;
  };
  const shared = JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  const floor = shared.buildings[0].floors[1], room = floor.rooms.find(r=>r.key==='front-service');
  const validBox = (x,y,w,h)=>({x,y,w,h,visible:true});
  const fixture = () => ({ kind:'svg',building:'A',floor:'floor-2',
    labels:[{name:room.name,box:validBox(2160,100,1680,230)}],
    bodies:room.features.hvac_units.map(u=>({id:u.id,type:u.type,
      box:validBox(u.x_mm-u.width_mm/2,u.y_mm-u.depth_mm/2,u.width_mm,u.depth_mm)})),
    codes:room.features.hvac_units.map(u=>({id:u.id,type:u.type,text:u.id+'外',
      box:validBox(u.x_mm+100,u.y_mm-5,713,180)})),
  });
  const check = vm.runInNewContext(definition('checkAHvacLabelBounds')+'\ncheckAHvacLabelBounds', {
    assert:(condition,name)=>assert.ok(condition,name),
  });
  for (const [name,mutate,error] of [
    ['current separated labels',()=>{},null],
    ['wrong document identity',e=>e.kind='html',/native SVG/],
    ['wrong building',e=>e.building='B',/native SVG/],
    ['missing room name',e=>e.labels=[],/native SVG/],
    ['duplicate room name',e=>e.labels.push(e.labels[0]),/native SVG/],
    ['full-name identity lost',e=>e.labels[0].name='front balcony',/native SVG/],
    ['hidden room name',e=>e.labels[0].box.visible=false,/visible browser font bounds/],
    ['no actual glyph geometry',e=>e.labels[0].box.w=0,/visible browser font bounds/],
    ['invalid glyph geometry',e=>e.labels[0].box.x=NaN,/visible browser font bounds/],
    ['old overlapping left name',e=>e.labels[0].box.x=140,/actual rendered balcony name/],
    ['code drifts into the name',e=>e.codes[0].box.x=2300,/actual rendered balcony name/],
    ['outline-only collision',e=>e.codes[0].box.x=3820,/actual rendered balcony name/],
    ['device symbol omitted',e=>e.bodies.pop(),/both outdoor unit/],
    ['device code omitted',e=>e.codes.pop(),/both outdoor unit/],
    ['device code hidden',e=>e.codes[0].box.visible=false,/remain visible/],
    ['device code truncated',e=>e.codes[0].text='A',/remain visible/],
    ['indoor code substituted',e=>e.codes[0].type='indoor',/remain visible/],
    ['same code duplicated',e=>e.codes[0]=e.codes[1],/remain visible/],
    ['device symbol shrunk',e=>e.bodies[0].box.w-=50,/exact shared 3D position and size/],
    ['device symbol moved',e=>e.bodies[0].box.x+=50,/exact shared 3D position and size/],
  ]) await t.test(name,()=>{
    const e=fixture();mutate(e);
    if(error)assert.throws(()=>check(floor,e),error);else check(floor,e);
  });
  const evidence=fixture();
  const node=(attrs,b)=>({getAttribute:k=>attrs[k]??null,getBBox:()=>({x:b.x,y:b.y,width:b.w,height:b.h}),
    getClientRects:()=>[b],textContent:attrs.text??''});
  const collector=vm.runInNewContext(definition('collectAHvacLabelBounds')+'\ncollectAHvacLabelBounds',{
    getComputedStyle:()=>({display:'inline',visibility:'visible',opacity:'1'}),
    document:{documentElement:{localName:'svg',getAttribute:k=>({'data-building':'A','data-floor':'floor-2'})[k],
      querySelectorAll:selector=>{
        if(selector==='a[data-label-room-id="A:floor-2:front-service"]')return evidence.labels.map(n=>node({'data-full-name':n.name},n.box));
        if(selector==='g[data-room-id="A:floor-2:front-service"] rect[data-hvac-id]')return evidence.bodies.map(n=>node({'data-hvac-id':n.id,'data-hvac-type':n.type},n.box));
        assert.equal(selector,'g[data-room-id="A:floor-2:front-service"] text[data-hvac-label-id]');
        return evidence.codes.map(n=>node({'data-hvac-label-id':n.id,'data-hvac-label-type':n.type,text:n.text},n.box));
      } }},
  });
  check(floor,collector());
  const script=makeBrowserScript('file:///project/','C:\\QA',{floors:12,rooms:112,items:128});
  assert.ok(script.includes("page.goto(baseUrl + 'structured/candidates/furniture-plans/A_floor-2.svg')"));
  assert.ok(script.includes('await page.evaluate(collectAHvacLabelBounds)'));
});

test('isolated C1F serialized QA rejects matched but physically misleading comparison data', async t => {
  // Contract fixtures only: matching fake debug data is intentionally not
  // evidence that a browser rendered a scene or that a route is accessible.
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const source=checkPages.toString().match(/  const checkCOption = \(option, debug\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(source);
  const data=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/c1f-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_C1F_OPTIONS = /,'').replace(/;\s*$/,''));
  const check=vm.runInNewContext(source+'\ncheckCOption',{assert:(condition,message)=>assert.ok(condition,message)});
  const make=id=>{
    const option=JSON.parse(JSON.stringify(data.options.find(o=>o.id===id)));
    const shapes=option.floor.rooms.flatMap(r=>r.furniture.map(i=>({id:i.id,visible:true,
      width:i.width_mm,depth:i.depth_mm,height:i.height_mm,
      center:[i.placement.center_x_mm,i.placement.center_y_mm],rotation:i.placement.rotation_deg})));
    return {option,debug:{presentation:'tour',state:{building:'C',floor:'floor-1'},
      layoutReview:{status:'comparison-only-not-adopted',hvac_routes:[{...option.hvac,manual_source:null}]},
      visibleRooms:option.floor.rooms.map(r=>r.id),tour:{rooms:option.floor.rooms},furniture:{shapes,pendingItems:[]}}};
  };
  const room=(s,key)=>s.option.floor.rooms.find(r=>r.key===key);
  const removeProduct=(s,key,catalog)=>{
    const r=room(s,key),item=r.furniture.find(i=>i.catalog_id===catalog);
    r.furniture=r.furniture.filter(i=>i.id!==item.id);
    s.debug.furniture.shapes=s.debug.furniture.shapes.filter(i=>i.id!==item.id);
  };
  const scenarios=[
    ['baseline','main baseline',()=>{},null],
    ['bath-front','front WC proposal',()=>{},null],
    ['front-living','front living proposal',()=>{},null],
    ['bath-front','bedroom removed',s=>{
      s.option.floor.rooms=s.option.floor.rooms.filter(r=>r.key!=='elder');
      s.debug.visibleRooms=s.option.floor.rooms.map(r=>r.id);
      s.debug.tour.rooms=s.option.floor.rooms;
    },/bounded floor/],
    ['front-living','elder bedroom shifted',s=>{room(s,'elder').geometry.y_mm+=100;},/preserves elder coordinates/],
    ['bath-front','elder bed removed in both pictures',s=>removeProduct(s,'elder','queen-bed'),/elder bed\/storage/],
    ['front-living','wardrobe removed in both pictures',s=>removeProduct(s,'elder','wardrobe-120'),/elder bed\/storage/],
    ['bath-front','unapproved bathroom claimed approved',s=>{s.option.public_bath_verified=true;},/unknown professional/],
    ['front-living','daylight claimed approved',s=>{s.option.daylight_verified=true;},/unknown professional/],
    ['bath-front','plumbing claimed approved',s=>{s.option.plumbing_verified=true;},/unknown professional/],
    ['bath-front','WC enters bedroom',s=>{room(s,'public-bath').features.doors[0].neighbor='C:floor-1:elder';},/bedroom-independent/],
    ['front-living','door narrowed in both pictures',s=>{room(s,'public-bath').features.doors[0].width_mm=500;},/bedroom-independent/],
    ['front-living','false connected route text',s=>{
      room(s,'entrance').features.doors=room(s,'entrance').features.doors.filter(d=>d.neighbor!=='C:floor-1:public-bath');
    },/actual connected openings/],
    ['bath-front','side-window invented in both pictures',s=>{room(s,'public-bath').features.window_face='right';},/legal side window/],
    ['bath-front','living direct daylight invented',s=>{room(s,'living').features.window_face='front';},/independent living daylight/],
    ['front-living','borrow-light dining claimed exterior-lit',s=>{room(s,'dining').features.window_face='front';},/interior dining\/WC/],
    ['front-living','turning reserve removed',s=>{room(s,'entrance').features.reserved_mm=[];},/turning reservation/],
    ['bath-front','shoe-storage loss concealed',s=>{s.option.tradeoffs=s.option.tradeoffs.filter(v=>!v.includes('鞋櫃'));},/shoe-storage loss/],
    ['front-living','AC old route reused in both claims',s=>{
      s.option.hvac.estimated_routed_length_mm=14645;s.debug.layoutReview.hvac_routes[0].estimated_routed_length_mm=14645;
    },/AC quantity/],
    ['bath-front','AC installer approval invented',s=>{s.debug.layoutReview.hvac_routes[0].compliance='passed';},/AC quantity/],
    ['front-living','fixture silently hidden',s=>{s.debug.furniture.shapes[0].visible=false;},/full-size exact placement/],
    ['bath-front','extra fixture only in 3D',s=>{s.debug.furniture.shapes.push({id:'invented'});},/exact study furniture IDs/],
  ];
  for(const [id,name,mutate,error] of scenarios)await t.test(id+' / '+name,()=>{
    const state=make(id);mutate(state);
    if(error)assert.throws(()=>check(state.option,state.debug),error);else check(state.option,state.debug);
  });
});

test('BC preflight rejects false adoption, stale evidence, hidden products and altered care suite', t => {
  const f=fixture(t),shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  assert.deepEqual(preflightBcOptions(f.project,shared),[],'generic fixtures do not invent BC data');
  const real=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/bc-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_BC_OPTIONS = /,'').replace(/;\s*$/,''));
  const source='inputs/bc-constraints-options.json',sourceText=fs.readFileSync(path.join(root,source),'utf8');
  for(const file of [source,real.baseline_reference,'Docs/bc-constraints-review-v1.md','scripts/export_bc_options.py',
    'scripts/templates/bc-options.html','scripts/templates/bc-options-controls.html','scripts/templates/bc-options-bootstrap.js',
    'structured/candidates/bc-options.html','structured/candidates/bc-options-3d.html',
    ...real.options.flatMap(o=>o.plans.floors.map(f=>'structured/candidates/bc-options/'+f.plan_file))]) {
    f.write(file,fs.readFileSync(path.join(root,file),'utf8'));
  }
  const write=study=>{
    study.source_hashes={[source]:require('node:crypto').createHash('sha256').update(sourceText).digest('hex')};
    f.write('structured/candidates/bc-options/layout.js','window.HOUSE_BC_OPTIONS = '+JSON.stringify(study)+';\n');
  };
  write(real);assert.ok(preflightBcOptions(f.project,shared).length>=29);
  const scenarios=[
    [s=>{s.active_design='b-strict';},/adopts/],
    [s=>{s.confirmed_b_rules.no_sleep_above_whole_shrine=false;},/rules/],
    [s=>{s.options[1].professional_status.accessibility='passed';},/falsely approved/],
    [s=>{delete s.options[1].professional_status.religious_acceptance;},/falsely approved/],
    [s=>{s.options[0].plans.floors[0].rooms[0].name+=' stale';},/Stale BC frozen baseline/],
    [s=>{s.options[1].unresolved_furniture.push({item_id:'invented'});},/hides unresolved/],
    [s=>{s.options[1].plans.floors[2].rooms.find(r=>r.key==='quiet-study').kind='bedroom';},/actual-room/],
    [s=>{s.options[1].plans.floors[0].rooms.find(r=>r.key==='shrine').furniture.find(i=>i.shape==='altar').width_mm=900;},/ordinary-sized/],
    [s=>{s.options[3].plans.floors[0].rooms.find(r=>r.key==='elder').features.window_mm=1200;},/shrinks care suite/],
    [s=>{const rooms=s.options[3].plans.floors[1].rooms;
      rooms.find(r=>r.key==='bath2f').geometry.h_mm=2200;
      const rear=rooms.find(r=>r.key==='rear-service');rear.geometry.y_mm=16000;rear.geometry.h_mm=1630;
    },/extra wet-wall separation/],
    [s=>{s.options[4].unresolved_furniture=[];},/hides unresolved/],
  ];
  for(const [mutate,expected] of scenarios) {
    const s=structuredClone(real);mutate(s);write(s);
    assert.throws(()=>preflightBcOptions(f.project,shared),expected);
  }
  write(real);f.write(source,sourceText+'\n');
  assert.throws(()=>preflightBcOptions(f.project,shared),/Stale BC comparison source/);
});

test('BC scene contract rejects missing rooms, hidden ordinary products and falsely passed pending furniture',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  function checkBcOption\(option, floor, debug\) \{[\s\S]*?\n  }/)?.[0];
  const check=vm.runInNewContext(definition+'\ncheckBcOption',{assert:(c,m)=>assert.ok(c,m)});
  const study=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/bc-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_BC_OPTIONS = /,'').replace(/;\s*$/,''));
  const make=id=>{
    const option=structuredClone(study.options.find(o=>o.id===id)),floor=option.plans.floors[id==='c-wet-stack'?1:0];
    return {option,floor,debug:{presentation:'tour',state:{building:option.building,floor:floor.id},
      layoutReview:{status:option.status},bcOption:{id:option.id,status:option.status,geometry_review:option.geometry_review},
      visibleRooms:floor.rooms.map(r=>r.id),tour:{rooms:floor.rooms},furniture:{
        items:option.plans.floors.reduce((s,f)=>s+f.rooms.reduce((n,r)=>n+r.furniture.length,0),0),visibleIssues:0,
        pendingItems:floor.rooms.flatMap(r=>r.furniture.filter(i=>i.placement.issues.length).map(i=>i.id)),
        shapes:floor.rooms.flatMap(r=>r.furniture.map(i=>({id:i.id,width:i.width_mm,depth:i.depth_mm,height:i.height_mm,
          placement:i.placement,center:[i.placement.center_x_mm,i.placement.center_y_mm],rotation:i.placement.rotation_deg,
          visible:!i.placement.issues.length})))}}};
  };
  for(const id of ['b-strict','c-side-bed','c-wet-stack']) {
    const {option,floor,debug}=make(id);check(option,floor,debug);
  }
  for(const [id,mutate,expected] of [
    ['b-strict',s=>{s.debug.visibleRooms.pop();},/retains all rooms/],
    ['c-side-bed',s=>{s.debug.furniture.shapes[0].visible=false;},/full-size placement/],
    ['b-strict',s=>{s.debug.furniture.shapes[0].center[0]+=10;},/mesh transform/],
    ['b-strict',s=>{s.debug.furniture.items=127;},/single-building/],
    ['c-wet-stack',s=>{s.debug.furniture.pendingItems=[];},/pending furniture/],
    ['c-wet-stack',s=>{s.debug.furniture.shapes.find(i=>!i.visible).visible=true;},/full-size placement/],
    ['c-side-bed',s=>{s.debug.bcOption.geometry_review.religious_acceptance='approved';},/invent/],
  ]) {
    const state=make(id);mutate(state);
    assert.throws(()=>check(state.option,state.floor,state.debug),expected);
  }
});

test('BC presentation contract rejects DOM-visible but offscreen warnings and unrelated main controls',async t=>{
  // Pure negative contract fixtures, not browser layout, CSS or visual proof.
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  function checkBcPresentation\(evidence, option, controls = false\) \{[\s\S]*?\n  }/)?.[0];
  assert.ok(definition,'the serialized production presentation checker is exercised');
  const check=vm.runInNewContext(definition+'\ncheckBcPresentation',{assert:(c,m)=>assert.ok(c,m)});
  const option={id:'b-strict',label:'B 全家規比較'};
  const rect=(left,top,width,height)=>({left,top,width,height,right:left+width,bottom:top+height});
  const node=(box,text='')=>({text,rect:box,hasBox:true,display:'block',visibility:'visible',position:'static',
    opacity:1,zIndex:0,clientWidth:box.width,scrollWidth:box.width,clientHeight:box.height,scrollHeight:box.height,disabled:false});
  const retired=['#tour-actions','#furniture-start','#presentation-mode','#geom-source','#geometry-hint',
    '#mdf-study-description','#mdf-section-link','label:has(#mdf-study)','label:has(#frontage-study)',
    'label:has(#frontage-study)+.hint','h2:has(+#presentation-mode)','h2:has(+#geom-source)',
    '#facade-actions','#compare','label:has(#ghost)','h2:has(+label #ghost)'];
  const fixture=()=>({bcClass:true,kind:'bc-constraints',option:option.id,scheme:option.id,title:option.label+' · 比較用 3D（未採用）',
    viewport:rect(0,0,1440,900),stage:{...node(rect(360,0,1080,900)),position:'relative'},
    badge:{...node(rect(374,800,480,30),option.label+' · 比較，未採用／未核'),position:'absolute',zIndex:4,
      color:'rgb(101, 67, 11)',background:'rgb(255, 245, 221)',role:'status',live:'polite'},
    orientation:node(rect(374,845,420,43)),panel:node(rect(0,0,360,900)),card:node(rect(16,16,328,260)),
    warning:node(rect(29,50,302,36),'本頁是比較方案，未採用／未核'),
    retired:Object.fromEntries(retired.map(selector=>[selector,'none'])),
    controls:[{...node(rect(29,100,302,44)),label:'方案'},
      {...node(rect(29,150,144,44)),href:'bc-options.html#b-strict'},
      {...node(rect(179,150,150,44)),href:'model3d.html'},node(rect(29,210,302,44))]});
  check(fixture(),option,true);
  for(const [name,viewport,stage,badge,direction] of [
    ['portrait',rect(0,0,390,844),rect(0,54,390,790),rect(14,690,362,44),rect(14,745,362,78)],
    ['landscape',rect(0,0,844,390),rect(0,54,844,336),rect(440,325,390,48),rect(14,319,390,60)],
  ]) await t.test(name+' collapsed footer layout',()=>{
    const e=fixture();e.viewport=viewport;e.stage.rect=stage;e.badge.rect=badge;e.orientation.rect=direction;
    e.card=null;e.warning=null;e.controls=[];check(e,option);
  });
  for(const [name,mutate,expected] of [
    ['original static below-canvas warning',e=>{e.badge.position='static';e.badge.rect=rect(374,910,480,30);},/positioned/],
    ['absolute but below viewport',e=>{e.badge.rect=rect(374,910,480,30);},/viewport and 3D stage/],
    ['inside viewport but outside stage',e=>{e.badge.rect=rect(12,800,300,30);},/viewport and 3D stage/],
    ['clipped right edge',e=>{e.badge.rect=rect(1000,800,480,30);},/viewport and 3D stage/],
    ['missing badge',e=>{e.badge=null;},/positioned/],
    ['invisible parent',e=>{e.badge.opacity=0;},/painted/],
    ['missing warning text',e=>{e.badge.text=option.label;},/unadopted warning/],
    ['stale scheme label',e=>{e.badge.text='C 孝親比較 · 未採用／未核';},/unadopted warning/],
    ['missing ARIA status',e=>{e.badge.role=null;},/accessible/],
    ['clipped warning text',e=>{e.badge.scrollHeight=e.badge.clientHeight+20;},/text is not clipped/],
    ['transparent background',e=>{e.badge.background='rgba(255, 245, 221, 0)';},/opaque background/],
    ['unreadable text contrast',e=>{e.badge.color='rgb(255, 245, 221)';},/readable text contrast/],
    ['overlapping direction footer',e=>{e.badge.rect=rect(374,840,480,30);},/does not overlap/],
    ['hidden direction footer',e=>{e.orientation.hasBox=false;},/visible direction footer/],
    ['wrong active scheme',e=>{e.scheme='c-side-bed';},/identity/],
    ['main shortcut remains',e=>{e.retired['#tour-actions']='flex';},/hides unrelated ABC/],
    ['MDF label remains',e=>{e.retired['label:has(#mdf-study)']='flex';},/hides unrelated ABC/],
    ['missing retired control evidence',e=>{e.retired={};},/hides unrelated ABC/],
    ['tiny scheme control',e=>{e.controls[0].rect=rect(29,100,302,22);},/44px targets/],
    ['disabled return link',e=>{e.controls[1].disabled=true;},/44px targets/],
    ['horizontal sidebar overflow',e=>{e.panel.scrollWidth=700;},/horizontal overflow/],
    ['unlabelled scheme control',e=>{e.controls[0].label='';},/labels and return destinations/],
    ['wrong comparison return',e=>{e.controls[1].href='model3d.html';},/return destinations/],
  ]) await t.test(name,()=>{
    const e=fixture();mutate(e);assert.throws(()=>check(e,option,true),expected);
  });
  const script=makeBrowserScript('file:///project/','C:\\QA',{floors:12,rooms:112,items:127});
  assert.ok(script.includes('page.evaluate(collectBcPresentation)'),'actual browser layout evidence is collected');
  assert.ok(script.includes("capture('bc-'+scheme+'-'+key+'-landscape.png')"),'both B and C landscape screenshots are captured');
  assert.ok(!script.includes("isVisible(), 'mobile '+scheme+' comparison status"),'the weak BC DOM-only assertion is removed');
});

test('BC presentation collector checks native selector support before querying or measuring the DOM',()=>{
  // Browser-CSS contract double only: the real CSS.supports call is Windows QA.
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  const collectBcPresentation = \(\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);
  const valid='h2:has(+label #ghost)',nested='h2:has(+label:has(#ghost))';
  assert.ok(definition.includes(valid));
  const run=(source,unsupported='')=>{
    const supported=[],queried=[];
    const collect=vm.runInNewContext(source+'\ncollectBcPresentation',{
      CSS:{supports:rule=>{
        supported.push(rule);
        // Standard CSS forbids :has() inside :has(); other parser behavior is
        // intentionally not simulated here or claimed as actual browser proof.
        return !/:has\([^)]*:has\(/.test(rule) && rule!=='selector('+unsupported+')';
      }},
      document:{title:'比較用 3D',body:{classList:{contains:()=>true},getAttribute:()=>null},
        getElementById:()=>({value:'b-strict'}),querySelector:selector=>{
          assert.equal(supported.length,16,'all retired selectors are checked before the first DOM read');
          queried.push(selector);return null;
        }},innerWidth:1440,innerHeight:900,
    });
    return {collect,supported,queried};
  };
  const good=run(definition),evidence=good.collect();
  assert.ok(good.supported.includes('selector('+valid+')'));
  assert.ok(good.queried.includes(valid));
  assert.equal(evidence.retired[valid],null,'a missing element is not falsely treated as hidden');
  for(const [source,unsupported,expected] of [
    [definition.replace(valid,nested),'',/Invalid or unsupported BC presentation selector: h2:has\(\+label:has\(#ghost\)\)/],
    [definition,'label:has(#ghost)',/Invalid or unsupported BC presentation selector: label:has\(#ghost\)/],
  ]) {
    const bad=run(source,unsupported);
    assert.throws(()=>bad.collect(),expected);
    assert.equal(bad.queried.length,0,'do not suppress selector errors or collect incomplete layout evidence');
  }
  const css=fs.readFileSync(path.join(root,'scripts/templates/bc-options-controls.html'),'utf8');
  assert.ok(css.includes('body.bc-study '+valid));
  assert.ok(!/:has\([^)]*:has\(/.test(css),'a nested :has() must not invalidate the whole hide rule');
});

test('run-code function compiles and reports failure without Node globals in its VM', async () => {
  const captures = [];
  const fakePage = { setDefaultTimeout() {}, setDefaultNavigationTimeout() {}, on() {},
    context: () => ({ route: async () => {} }), setViewportSize: async () => {},
    goto: async () => { throw new Error('intentional no-browser fixture'); },
    url: () => 'file:///project/AbuildingView.html',
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

test('serialized SVG failure keeps original evidence and permits CLI body snapshots without a retry', async t => {
  for (const [name, failureUrl, reportingFails] of [
    ['SVG failure', 'file:///project/c1f-options/baseline.svg', false],
    ['SVG query/hash failure', 'file:///project/c1f-options/baseline.svg?test=1#room', false],
    ['HTML failure needs no reporting navigation', 'file:///project/CbuildingView.html', false],
    ['reporting navigation fails', 'file:///project/c1f-options/baseline.svg', true],
  ]) await t.test(name, async () => {
    let current = failureUrl;
    const events = [];
    const fakePage = { setDefaultTimeout() {}, setDefaultNavigationTimeout() {}, on() {},
      context: () => ({ route: async () => {} }), setViewportSize: async () => {}, url: () => current,
      goto: async (url, options) => {
        events.push(['goto', url]);
        if (url !== 'about:blank') throw new Error('original SVG link failure');
        assert.equal(options.timeout, 5000, 'bound the reporting-only navigation');
        if (reportingFails) throw new Error('fixture reporting page unavailable');
        current = url;
      },
      screenshot: async options => { events.push(['screenshot', current, options.path]); },
    };
    const callback = vm.runInNewContext('(' + makeBrowserScript('file:///project/', 'C:\\QA',
      { floors: 12, rooms: 112, items: 128 }) + ')', {});
    const report = await callback(fakePage);
    assert.equal(report.status, 'failed');
    assert.match(report.error, /original SVG link failure/);
    assert.equal(report.failureUrl, failureUrl);
    assert.equal(events[1][0], 'screenshot');
    assert.equal(events[1][1], failureUrl, 'capture the failed document before leaving it');
    assert.equal(report.screenshots.length, 1);
    assert.equal(report.checks.length, 0, 'reporting does not invent passed checks');
    const isSvg = failureUrl.includes('.svg');
    assert.equal(events.length, isSvg ? 3 : 2, 'never rerun the failed interaction');
    if (isSvg && !reportingFails) {
      assert.equal(report.reportingPage, 'about:blank');
      assert.equal(current, 'about:blank');
    } else {
      assert.equal(report.reportingPage, undefined);
      assert.equal(current, failureUrl);
    }
    if (reportingFails) assert.match(report.reportingWarning, /reporting page unavailable/);
  });
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
  let mdfChecked=false,mdfOpen=false,mdfSectionLoaded=false;
  const readers=Object.fromEntries(building.floors.map(f=>[f.id,{width:660,mode:'readable',left:0,top:0}]));
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
      if(selector==='.mdf-study-review > img')return {complete:mdfSectionLoaded,naturalWidth:mdfSectionLoaded?1100:0};
      if (selector.endsWith('[data-plan-viewer]')) return {dataset:{planMode:readers[id].mode},querySelector:()=>({complete:loaded.has(id),naturalWidth:loaded.has(id)?6600:0})};
      assert.ok(selector.endsWith('.shared-furniture-plan img') || selector.endsWith('.shared-plan-open img'));
      return { complete: loaded.has(id), naturalWidth: loaded.has(id) ? 600 : 0,
        src:mdfChecked && id==='floor-1'?'file:///project/A_floor-1_mdf-study.svg':'file:///project/A_'+id+'.svg' };
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
      getAttribute:async name=>{if(name==='data-floor-id')return id;assert.equal(name,'data-mdf-study-visible');return String(mdfChecked);},
      locator(child) {
        if (child === 'img' || child === '.shared-plan-open img' || child === '.shared-plan-viewport') return { scrollIntoViewIfNeeded: async () => {
          assert.equal(active, id, 'hidden floor must never be scrolled');
          scrolled.push(id);
          loaded.add(id);
        } };
        if (child==='[data-plan-viewer]') {
          const state=readers[id],ratio=19030/6600;
          const viewport={clientWidth:1000,clientHeight:640,get scrollLeft(){return state.left;},get scrollTop(){return state.top;}};
          const r={dataset:{sourceHeight:'19030',sourceWidth:'6600',get planMode(){return state.mode;}},querySelector:css=>css==='[data-plan-content]'?
            {src:'file:///project/structured/candidates/furniture-plans/A_'+id+'.svg',getBoundingClientRect:()=>({width:state.width,height:state.width*ratio})}:viewport,
            querySelectorAll:()=>Array.from({length:4},()=>({getBoundingClientRect:()=>({height:44})}))};
          return {evaluate:fn=>vm.runInNewContext('('+fn.toString()+')(r)',{r,document:{documentElement:{scrollWidth:1440}},window:{innerWidth:1440}}),
            locator(css){
              if(css==='[data-plan-viewport]')return {scrollIntoViewIfNeeded:async()=>{assert.equal(active,id);loaded.add(id);scrolled.push(id);},focus:async()=>{assert.equal(active,id);}};
              const action=css.match(/data-plan-action="([^"]+)"/)?.[1];assert.ok(action);
              return {click:async()=>{assert.equal(active,id);state.width=action==='in'?state.width*1.35:action==='overview'?200:660;
                state.mode=action==='in'?'zoom':action;state.left=state.top=0;}};
            }};
        }
        if(child === '.mdf-study-review')return {
          getAttribute:async name=>{assert.equal(name,'data-mdf-study-status');return 'conditional-not-installed';},
          innerText:async()=> '1200×2000mm；機櫃仍只計1台',
          locator(sub){
            if(sub==='summary')return {click:async()=>{assert.equal(active,'floor-1');mdfOpen=!mdfOpen;}};
            if(sub==='[data-mdf-study-toggle]')return {
              check:async()=>{assert.ok(mdfOpen);mdfChecked=true;},uncheck:async()=>{assert.ok(mdfOpen);mdfChecked=false;}};
            assert.equal(sub,'img');return {scrollIntoViewIfNeeded:async()=>{assert.ok(mdfOpen);mdfSectionLoaded=true;scrolled.push('floor-1:mdf-section');}};
          }
        };
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
    keyboard:{press:async key=>{assert.equal(key,'End');readers[active].top=900;}},
    waitForFunction: async (fn, arg) => { assert.ok(evaluate(fn, arg), 'expected UI condition was not satisfied'); },
  };
  const script = new vm.Script('(' + makeBrowserScript(base, 'C:\\QA', { floors: 12, rooms: 92, items: 157 }) + ')');
  const result = await script.runInNewContext({})(fakePage);
  assert.equal(result.status, 'failed'); // Intentionally stop before any 3D QA.
  assert.match(result.error, /intentional end of HTML contract fixture/);
  assert.deepEqual(clicks, ['floor-1', 'floor-2', 'floor-3', 'floor-4', 'floor-1']);
  assert.deepEqual(scrolled, ['floor-1', 'floor-1', 'floor-1', 'floor-1:mdf-section', 'floor-2', 'floor-2', 'floor-2', 'floor-3', 'floor-4']);
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
    ['wardrobes lose resolved visibility', 'A', c => c.debug.furniture.shapes.find(i=>i.id==='A:floor-2:master:furniture:wardrobe-right').visible=false, /genuinely placed/],
    ['wardrobe silently downsized', 'A', c => c.floor.rooms.find(r => r.key === 'walkin').furniture[0].width_mm = 1200, /full-size wardrobes/],
    ['sequential closet caveat removed', 'A', c => c.floor.rooms.find(r => r.key === 'walkin').furniture[0].shared_operation_mode='', /explicitly sequential/],
    ['relocated hall cabinet hidden', 'A', c => c.debug.furniture.shapes.find(i => i.id.includes(':master:furniture:hall-cabinet')).visible = false, /relocated full-size/],
    ['hallway passage reserve narrowed', 'A', c => c.floor.rooms.find(r => r.key === 'hall2').geometry.w_mm = 1200, /relocated full-size/],
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

test('serialized framing rejects tiny fits, small or omitted bodies and unmeasured caveat overlap', async t => {
  const script=makeBrowserScript('file:///project/','C:\\QA',{floors:12,rooms:105,items:129});
  const definition=script.match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);
  for(const call of ["checkCameraFraming(mobileLiving, 'C:floor-1:living')",'checkCameraFraming(landscapeLiving',
    "checkCameraFraming(mobileBath, 'A:floor-2:master-bath')",'capacity-landscape-C-3D.png'])assert.ok(script.includes(call),call);
  const check=vm.runInNewContext(definition+'\ncheckCameraFraming',{assert:(value,message)=>assert.ok(value,message)});
  const id='C:floor-1:public-bath';
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[-.5,.5].map(z=>
    [x/844*2-1,1-y/336*2,z])));
  const fixture=()=>({roomCloseup:true,state:{room:id},focusedScreenBounds:corners(250,115,595,270),
    furniture:{shapes:[{id:id+':furniture:toilet',visible:true}]},cameraFraming:{ready:true,width:844,height:336,
      safeArea:{left:12,right:832,top:110,bottom:272,usable:true},
      overlays:[{id:'room-view-actions',bottom:100},{id:'study-stage-note',top:282}],
      selectedItems:[{id:id+':furniture:toilet',corners:corners(430,170,458,205)}],limitation:'not pixel visibility'}});
  for(const [name,mutate,error] of [
    ['measurable room and ordinary fixture',()=>{},null],
    ['initial frame not rendered',d=>d.cameraFraming.ready=false,/rendered frame/],
    ['control space unavailable',d=>d.cameraFraming.safeArea.usable=false,/usable viewport/],
    ['old tiny-but-inside fit',d=>d.focusedScreenBounds=corners(410,180,450,210),/tiny fit/],
    ['body shrunk below readable size',d=>d.cameraFraming.selectedItems[0].corners=corners(430,170,435,180),/16×16/],
    ['room covered by note',d=>d.focusedScreenBounds=corners(250,115,595,300),/safe rectangle/],
    ['fixture omitted',d=>d.cameraFraming.selectedItems=[],/every displayed/],
    ['different selected product',d=>d.cameraFraming.selectedItems[0].id='other-item',/every displayed/],
    ['note actually overlaps fit',d=>d.cameraFraming.overlays[1].top=250,/actual overlay/],
    ['wrong camera depth',d=>d.focusedScreenBounds[0][2]=2,/camera depth/],
    ['NaN projection',d=>d.focusedScreenBounds[0][0]=NaN,/finite projected/],
    ['whole floor instead of selected closeup',d=>d.roomCloseup=false,/selected closeup/],
    ['pixel approval overstated',d=>d.cameraFraming.limitation='approved',/never claim/],
  ])await t.test(name,()=>{const d=fixture();mutate(d);if(error)assert.throws(()=>check(d,id),error);else check(d,id);});
  const d=fixture();d.roomCloseup=false;d.state.room='';check(d);
  d.focusedScreenBounds=corners(400,115,580,270);
  assert.throws(()=>check(d),/40%/,'landscape width is checked even when the vertical fit is large enough');
  const pending=fixture();pending.furniture.visible=true;pending.furniture.shapes[0].visible=false;
  pending.furniture.shapes[0].collision=true;pending.furniture.pendingItems=[id+':furniture:toilet'];
  pending.tour={rooms:[{id}]};pending.cameraFraming.selectedItems=[];
  check(pending,id); // framing-only, never proof that a pending fixture was installed
  for(const [name,mutate] of [
    ['pending original omitted from list',d=>d.furniture.pendingItems=[]],
    ['valid body hidden to fake readability',d=>d.furniture.shapes[0].collision=false],
    ['all furniture disabled',d=>d.furniture.visible=false],
    ['selected room missing',d=>d.tour.rooms=[]],
  ]){
    const d=structuredClone(pending);mutate(d);
    assert.throws(()=>check(d,id),/retains its room and pending originals/,name);
  }
});

test('mobile comparison QA rejects vertical 3D text and small controls at 360–430px',async t=>{
  const script=makeBrowserScript('file:///project/','C:\\QA',{floors:12,rooms:105,items:129});
  const definition=script.match(/  const checkMobileComparisonControls = async \(\) => \{[\s\S]*?\n  };/)?.[0];assert.ok(definition);
  assert.ok(script.includes('for (const width of [360, 390, 430])'));
  // Fake DOM measurement only: real CSS/line wrapping remains Windows QA.
  for(const width of [360,390,430])for(const [name,mutate,error] of [
    ['two readable links',()=>{},null],['narrow 3D link',s=>s.controls[2].r.width=80,/100px/],
    ['wrapped 3D link',s=>s.controls[2].lines=[0,16],/readable line/],
    ['small touch target',s=>s.controls[0].r.height=20,/44px/],
    ['control outside screen',s=>s.controls[2].r.right=width+20,/inside the viewport/],
    ['horizontal overflow',s=>s.scrollWidth=width+10,/inside the viewport/],
  ])await t.test(width+' '+name,async()=>{
    const state={scrollWidth:width,controls:['scheme','reset','open-3d','main-design'].map((id,i)=>({id,tagName:i<2?'SELECT':'A',
      r:{left:12,right:width-12,width:width-24,height:44},lines:[0]}))};mutate(state);
    const document={documentElement:{scrollWidth:state.scrollWidth},querySelector:selector=>{
      assert.equal(selector,'.toolbar');return {querySelectorAll:()=>state.controls.map(c=>({...c,getBoundingClientRect:()=>c.r}))};},
      createRange:()=>{let element;return {selectNodeContents:value=>{element=value;},getClientRects:()=>element.lines.map(top=>({top}))};}};
    const page={evaluate:fn=>vm.runInNewContext('('+fn.toString()+')()',{document,innerWidth:width})};
    const check=vm.runInNewContext(definition+'\ncheckMobileComparisonControls',{page,assert:(value,message)=>assert.ok(value,message)});
    if(error)await assert.rejects(check(),error);else await check();
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
  assert.equal(floor.rooms.length, 11, 'new shared front landing is retained, not a hard-coded old room count');
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
    ['current eleven-room floor', () => {}, null],
    ['room order differs', d => d.visibleRooms.reverse(), null],
    ['missing room', d => d.visibleRooms.pop(), /exact shared room IDs.*expected 11, got 10/],
    ['wrong room despite matching count', d => d.visibleRooms[0] = 'B:floor-2:master', /exact shared room IDs/],
    ['duplicate room despite matching count', d => d.visibleRooms[0] = d.visibleRooms[1], /exact shared room IDs/],
    ['extra room', d => d.visibleRooms.push('A:floor-1:flex1'), /exact shared room IDs/],
    ['wrong selected room', d => d.state.room = 'C:floor-1:elder', /shared floor and room/],
    ['wrong selected floor', d => d.state.floor = 'floor-1', /shared floor and room/],
    ['missing wardrobe', d => d.furniture.shapes=d.furniture.shapes.filter(i=>i.id!=='A:floor-2:master:furniture:wardrobe-right'), /original dimensions/],
    ['wrong wardrobe IDs with the same count', d => d.furniture.pendingItems[0] = 'other-wardrobe', /pending wardrobes and the displaced/],
    ['relocated wardrobe not retained in model', d => d.furniture.shapes = d.furniture.shapes.filter(i => i.id !== 'A:floor-2:master:furniture:wardrobe'), /original dimensions/],
    ['resolved wardrobe hidden', d => d.furniture.shapes.find(i => i.id === 'A:floor-2:master:furniture:wardrobe').visible = false, /original dimensions/],
    ['wardrobe silently downsized', d => d.furniture.shapes.find(i => i.id === 'A:floor-2:walkin:furniture:wardrobe-left').width = 1200, /original dimensions/],
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
  assert.equal((script.match(/await collapseMobilePanel\(\)/g) || []).length, 19,
    'all nineteen mobile setup points, including BC reloads, B ritual/storage flow, MDF, A TV and capacity landscape, use explicit state');
  assert.ok(script.includes("capture('A-3D-mobile-living-closeup.png')") &&
    script.includes("capture('A-3D-landscape-living-closeup.png')"),
  'A living room is checked in both real mobile orientations, not only in scene-math tests');
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

test('serialized MDF-to-C mobile transition expands preserved hidden controls before real clicks',async t=>{
  // DOM/CLI contract only. Real Edge failure.png proved that same-document
  // navigation retained the collapsed sidebar; this is not rendered QA.
  const script=makeBrowserScript('file:///project/','C:\\QA',{floors:12,rooms:112,items:127});
  const definition=name=>{
    const value=script.match(new RegExp('  const '+name+' = async \\(\\) => \\{[\\s\\S]*?\\n  };'))?.[0];
    assert.ok(value,name);return value;
  };
  const transition=script.match(/    await page.goto\(baseUrl \+ 'structured\/candidates\/model3d.html#mode=tour&building=C&floor=floor-1&view=front'[\s\S]*?    await collapseMobilePanel\(\);/)?.[0];
  assert.ok(transition,'actual production MDF-to-C transition');
  assert.equal((transition.match(/await expandMobilePanel\(\)/g)||[]).length,1);
  async function run(initial,removeExpansion=false){
    let expanded=initial,building='A',floor='floor-1',mdfActive=true,room='',study=false,clicks=0,resizeWaits=0;
    const stage={clientWidth:390,clientHeight:initial==='false'?790:470};
    const canvas={width:780,height:stage.clientHeight*2},events=[];
    const debug=()=>({panelCollapsed:expanded==='false',state:{building,floor,room},mdfStudy:{active:mdfActive}});
    const toggle={getAttribute:async()=>expanded,click:async()=>{
      expanded=expanded==='false'?'true':'false';clicks++;
      stage.clientHeight=expanded==='false'?790:470; // canvas intentionally resizes later
    }};
    const document={getElementById:id=>({'mobile-panel-toggle':{getAttribute:()=>expanded},stage,canvas})[id]};
    const window={devicePixelRatio:2,innerHeight:844,__htmlModel3dDebug:debug};
    const page={
      goto:async url=>{
        assert.ok(url.includes('building=C&floor=floor-1&view=front'));
        building='C';floor='floor-1';mdfActive=false;events.push('C hash retained '+expanded);
      },
      waitForFunction:async predicate=>{
        if(!predicate()){
          assert.notEqual(canvas.height,stage.clientHeight*2,'wait only for the real delayed resize contract');
          resizeWaits++;canvas.height=stage.clientHeight*2;
        }
        assert.equal(predicate(),true,'requested panel state and renderer are ready');
      },
      locator:selector=>{
        if(selector==='#mobile-panel-toggle')return toggle;
        return {click:async()=>{
          assert.equal(expanded,'true','cannot click hidden mobile controls');
          if(selector==='#scope-rooms [data-room="C:floor-1:garage"]'){room='C:floor-1:garage';events.push('garage');}
          else {assert.equal(selector,'#focus-room');assert.equal(room,'C:floor-1:garage');events.push('focus');}
        },check:async()=>{assert.equal(selector,'#frontage-study');assert.equal(expanded,'true');study=true;events.push('study');}};
      }
    };
    const execute=vm.runInNewContext(definition('expandMobilePanel')+'\n'+definition('collapseMobilePanel')+
      '\n(async()=>{'+(removeExpansion?transition.replace('    await expandMobilePanel();\n',''):transition)+'})',
      {page,document,window,baseUrl:'file:///project/',assert:(ok,message)=>assert.ok(ok,message)});
    await execute();
    assert.equal(room,'C:floor-1:garage');assert.equal(study,true);assert.equal(expanded,'false');
    assert.deepEqual(events,['C hash retained '+initial,'garage','focus','study']);
    assert.equal(clicks,initial==='false'?2:1,'explicit state, never a blind extra toggle');
    assert.equal(resizeWaits,clicks,'each changed panel state waits for renderer resize');
  }
  for(const initial of ['false','true'])await t.test('initial aria-expanded='+initial,()=>run(initial));
  await t.test('original missing expansion cannot pass with collapsed controls',async()=>{
    await assert.rejects(()=>run('false',true),/cannot click hidden mobile controls/);
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

test('CLI timeout errors stay explicit and incomplete even if a result echo claims success', async t => {
  for (const echoedPass of [false, true]) await t.test('echoed pass=' + echoedPass, t => {
    const f = fixture(t), prepared = preflight(f.project);
    const fake = fakeCli(passingReport(prepared.counts));
    const execute = (executable, args, options) => {
      if (args.includes('run-code')) return { status: 0, stdout: JSON.stringify({
        isError: true, error: 'TimeoutError: Timeout 15000ms exceeded.',
        ...(echoedPass ? { result: JSON.stringify(passingReport(prepared.counts)) } : {}),
      }), stderr: '' };
      return fake.execute(executable, args, options);
    };
    const report = runQa({ project: f.project, browser: 'msedge' }, prepared, f.output, execute);
    assert.equal(report.status, 'incomplete');
    assert.match(report.error, /Playwright CLI error: TimeoutError: Timeout 15000ms exceeded/);
    assert.match(report.error, /Verification is incomplete/);
    assert.equal(report.sessionClosed, true);
    assert.match(fs.readFileSync(path.join(f.output, 'checks.log'), 'utf8'), /Timeout 15000ms/);
  });
});

test('structured SVG failures remain failed with original evidence and isolated session closure', t => {
  const f = fixture(t), prepared = preflight(f.project);
  const failed = { marker, status: 'failed', error: 'baseline SVG top-layer room labels retain unique same-scheme room links',
    failureUrl: 'file:///project/c1f-options/baseline.svg', reportingPage: 'about:blank',
    counts: prepared.counts, checks: [{ name: 'real SVG room links', passed: false }], screenshots: ['failure.png'] };
  const fake = fakeCli(failed);
  const report = runQa({ project: f.project, browser: 'msedge' }, prepared, f.output, fake.execute);
  assert.equal(report.status, 'failed');
  assert.equal(report.error, failed.error);
  assert.equal(report.failureUrl, failed.failureUrl);
  assert.equal(report.reportingPage, 'about:blank');
  assert.equal(report.checks[0].passed, false);
  assert.equal(report.sessionClosed, true);
  assert.equal(fake.calls.length, 3, 'one run-code attempt, no retry');
});
