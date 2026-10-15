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
  'assets/html_design_bridge.js', 'assets/html_design_bridge.css', 'assets/plan_viewer.js',
  'assets/vendor/three/three.min.js', 'structured/candidates/model3d.html',
  'inputs/concept-layout-review.json', 'inputs/furniture-layout.json', 'inputs/physical-items.json',
  'inputs/requirements.json', 'scripts/check_windows_playwright.cjs',
  'inputs/facade-concept.json', 'assets/references/facade-photo-v1.jpg', LAYOUT_FILE,
];
const C1F_FILES = ['inputs/c1f-bath-daylight-options.json', 'structured/candidates/c1f-options.html',
  'structured/candidates/c1f-options-3d.html', 'structured/candidates/c1f-options/layout.js',
  ...['baseline', 'bath-front', 'front-living'].map(id => 'structured/candidates/c1f-options/' + id + '.svg')];

function preflightMdf(project, layout) {
  const s = layout.layout_review?.mdf_study;
  if (!s) {
    if (['abc-rationality-v3-a32-arcade','abc-rationality-v4-b-ritual-c-open-living','abc-rationality-v5-minimal-fengshui','abc-rationality-v6-space-efficiency'].includes(layout.layout_review?.id)) throw new Error('Current A main is missing the MDF study');
    return []; // Generic CLI fixtures and historical layouts are not the A main.
  }
  const source = 'inputs/a-mdf-under-stair.json';
  const files = [source, 'scripts/lib/model3d_mdf.py',
    'structured/candidates/furniture-plans/A_floor-1_mdf-study.svg',
    'structured/candidates/furniture-plans/A_floor-1_mdf-section.svg'];
  for (const file of files) if (!fs.existsSync(path.join(project, file))) throw new Error('Missing MDF study file: ' + file);
  const raw = JSON.parse(fs.readFileSync(path.join(project, source), 'utf8'));
  const unknown = ['structural_section','finished_headroom','fire_and_escape','ventilation_and_heat',
    'water_and_condensation','power_and_earthing','equipment_and_replacement'];
  const same = require('node:util').isDeepStrictEqual;
  const floor = layout.buildings.find(b => b.id === 'A')?.floors.find(f => f.id === 'floor-1');
  const backup = floor?.rooms.find(r => r.key === 'mdf'), rack = backup?.furniture.find(i => i.catalog_id === 'rack-18u');
  if (s.schema !== 'house-mdf-under-stair-study-v1' || s.status !== 'conditional-not-installed' ||
      s.active_design !== 'side-backup' || s.preferred_option !== 'under-stair' || s.evidence !== null ||
      Object.keys(s.professional_status || {}).length !== unknown.length || unknown.some(k => s.professional_status[k] !== 'unknown') ||
      !same(s.clearances_mm, {front:800,rear:600,left:300,right:300,top:200}) ||
      s.candidate.installed !== false || s.candidate.section_verified !== false || s.candidate.counts_as_furniture !== false ||
      !s.candidate.issues.includes('side-maintenance-exceeds-return-flight') ||
      s.candidate.flight_width_mm !== 900 || s.reuse.installed !== false || s.reuse.released_area_sqm !== null ||
      s.reuse.counts_as_furniture !== false || s.backup.released_area_sqm !== null ||
      s.plan_file !== 'A_floor-1_mdf-study.svg' || s.section_file !== 'A_floor-1_mdf-section.svg' ||
      !rack || !same(s.backup.geometry, backup.geometry) || !same(s.backup.placement, rack.placement) ||
      !same([s.rack.width_mm,s.rack.depth_mm,s.rack.height_mm],[600,600,1000]) ||
      !same(s.clearances_mm, raw.clearances_mm) || !same(s.professional_status, raw.professional_status) ||
      raw.active_design !== s.active_design || raw.status !== s.status || raw.evidence !== null ||
      raw.return_flight_offset_mm !== s.return_flight_offset_mm || !same(raw.reuse.storage_rect_mm,s.reuse.storage_rect_mm)) {
    throw new Error('MDF study is stale, changed-size, falsely approved or releases its backup');
  }
  return files;
}

function preflightC1f(project, layout) {
  const missing = C1F_FILES.filter(file => !fs.existsSync(path.join(project, file)));
  if (missing.length) throw new Error('Missing C1F comparison artifacts: ' + missing.join(', ') + '\nRun python scripts/export_c1f_options.py');
  const raw = fs.readFileSync(path.join(project, 'structured/candidates/c1f-options/layout.js'), 'utf8');
  const match = raw.match(/^\s*window\.HOUSE_C1F_OPTIONS\s*=\s*([\s\S]+?)\s*;\s*$/);
  if (!match) throw new Error('Invalid C1F comparison JSON assignment');
  const study = JSON.parse(match[1]);
  if (study.schema !== 'house-c1f-options-v1' || study.status !== 'comparison-only-not-adopted' ||
      study.active_design !== 'baseline' || !Array.isArray(study.options) ||
      study.options.map(o => o.id).join(',') !== 'baseline,bath-front,front-living') {
    throw new Error('C1F study must stay a comparison with baseline active');
  }
  for (const option of study.options) {
    if (option.floor?.plan_file !== option.id + '.svg' || !Array.isArray(option.floor.rooms) ||
      option.public_bath_verified !== null || option.daylight_verified !== null || option.plumbing_verified !== null) {
      throw new Error('Invalid or falsely approved C1F comparison: ' + option.id);
    }
  }
  const baseline = { ...study.options[0].floor, plan_file: 'C_floor-1.svg' };
  if (study.baseline_reference === 'inputs/references/abc-before-space-efficiency-20261014.json') {
    const reference=JSON.parse(fs.readFileSync(path.join(project,study.baseline_reference),'utf8')).buildings.C.floors['floor-1'].rooms;
    if(Object.keys(reference).length!==baseline.rooms.length||baseline.rooms.some(r=>!reference[r.key]||reference[r.key].name!==r.name||
      !require('node:util').isDeepStrictEqual(reference[r.key].rect,[r.geometry.x_mm,r.geometry.y_mm,r.geometry.w_mm,r.geometry.h_mm]))) throw new Error('Stale C1F frozen baseline');
  } else if (!require('node:util').isDeepStrictEqual(baseline, layout.buildings[2].floors[0])) {
    throw new Error('C1F comparison baseline is stale or differs from the active C floor');
  }
  const sourceHashes = study.source_hashes;
  if (!sourceHashes || !Object.keys(sourceHashes).length) throw new Error('Missing C1F source hashes');
  for (const [file, hash] of Object.entries(sourceHashes)) {
    if (!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(file) || file.split('/').includes('..') ||
        !/^[a-f0-9]{64}$/.test(hash) || !fs.existsSync(path.join(project, file))) {
      throw new Error('Invalid C1F source hash path: ' + file);
    }
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(project, file))).digest('hex');
    if (actual !== hash) throw new Error('Stale C1F comparison source: ' + file + '\nRun python scripts/export_c1f_options.py');
  }
  return [...C1F_FILES, ...Object.keys(sourceHashes)];
}

function preflightArcade(project, layout) {
  const files = ['inputs/abc-arcade-capacity.json', 'structured/candidates/arcade-capacity.html',
    'structured/candidates/arcade-capacity-3d.html', 'structured/candidates/arcade-capacity/layout.js'];
  for (const file of files) {
    if (!fs.existsSync(path.join(project, file))) throw new Error('Missing arcade capacity artifact: ' + file + '\nRun python scripts/export_arcade_capacity.py');
  }
  const raw = fs.readFileSync(path.join(project, files[3]), 'utf8');
  const match = raw.match(/^\s*window\.HOUSE_ARCADE_CAPACITY\s*=\s*([\s\S]+?)\s*;\s*$/);
  if (!match) throw new Error('Invalid arcade capacity JSON assignment');
  const study = JSON.parse(match[1]);
  const professionalKeys = ['parcel_dimensions', 'arcade_applicability', 'building_area', 'coverage_and_far',
    'arcade_clear_height', 'structure_and_fire', 'accessibility', 'daylight_and_ventilation',
    'hvac_installation', 'feng_shui_and_altar_orientation'];
  if (study.schema !== 'house-abc-arcade-capacity-v1' || study.status !== 'comparison-only-not-adopted' ||
      study.active_design !== 'main-a32-arcade-v1' || study.default_comparison !== 'arcade32' ||
      study.reference_review !== 'inputs/references/abc-before-a-arcade.json' ||
      study.options?.map(o => o.id).join(',') !== 'baseline,arcade32,room-first' ||
      !study.professional_status || Object.keys(study.professional_status).length !== professionalKeys.length ||
      professionalKeys.some(key => study.professional_status[key] !== 'unknown')) {
    throw new Error('Arcade study must remain an unapproved historical comparison, current A main separate');
  }
  const reference = JSON.parse(fs.readFileSync(path.join(project, study.reference_review), 'utf8'));
  files.push(study.reference_review);
  for (const option of study.options) {
    if (option.plans?.buildings?.map(b => b.id).join(',') !== 'A,B,C') throw new Error('Incomplete arcade ABC plans');
    for (const [index, building] of option.plans.buildings.entries()) {
      const capacity = option.capacity?.[building.id];
      if (!capacity || capacity.legal_building_area_sqm !== null || capacity.arcade_net_height_verified !== null ||
          capacity.verified_parking_spaces !== null || capacity.displayed_cars !== 0 ||
          capacity.coverage_sensitivity?.some(r => r.legal_result !== 'unknown')) {
        throw new Error('Falsely approved arcade capacity: ' + option.id + ' ' + building.id);
      }
      if (building.floors.map(f => f.id).join(',') !== 'floor-1,floor-2,floor-3,floor-4') throw new Error('Incomplete arcade floors');
      for (const [floorIndex, floor] of building.floors.entries()) {
        const name = option.id + '_' + building.id + '_' + floor.id + '.svg';
        if (floor.plan_file !== name || !Array.isArray(floor.rooms)) throw new Error('Invalid arcade plan path');
        const file = 'structured/candidates/arcade-capacity/' + name;
        if (!fs.existsSync(path.join(project, file))) throw new Error('Missing arcade plan: ' + file);
        files.push(file);
        if (option.id === 'baseline') {
          const expected = reference.buildings?.[building.id]?.floors?.[floor.id]?.rooms;
          if (!expected || Object.keys(expected).length !== floor.rooms.length || floor.rooms.some(room => {
            const spec = expected[room.key], g = room.geometry;
            return !spec || spec.name !== room.name || !g ||
              !require('node:util').isDeepStrictEqual(spec.rect, [g.x_mm,g.y_mm,g.w_mm,g.h_mm]);
          })) throw new Error('Arcade baseline is stale or differs from its frozen historical reference');
        }
      }
    }
  }
  if (!study.source_hashes || !Object.keys(study.source_hashes).length) throw new Error('Missing arcade source hashes');
  for (const [file, hash] of Object.entries(study.source_hashes)) {
    if (!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(file) || file.split('/').includes('..') ||
        !/^[a-f0-9]{64}$/.test(hash) || !fs.existsSync(path.join(project, file))) throw new Error('Invalid arcade source hash: ' + file);
    if (crypto.createHash('sha256').update(fs.readFileSync(path.join(project, file))).digest('hex') !== hash) {
      throw new Error('Stale arcade capacity source: ' + file + '\nRun python scripts/export_arcade_capacity.py');
    }
  }
  return [...files, ...Object.keys(study.source_hashes)];
}

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

function preflightFengshui(project, layout) {
  const spec = layout.layout_review?.fengshui_minimal;
  if (!spec) {
    if (['abc-rationality-v5-minimal-fengshui','abc-rationality-v6-space-efficiency'].includes(layout.layout_review?.id)) throw new Error('Missing minimal fengshui contract');
    return [];
  }
  if (spec.id !== 'abc-minimal-fengshui-v1' || spec.status !== 'partial-proposal-not-approved' ||
      spec.religious_acceptance !== 'unknown' || spec.structural_acceptance !== 'unknown' ||
      spec.document !== 'Docs/fengshui-minimal-v1.md' || spec.pending_decisions?.length !== 4 ||
      spec.pending_decisions.map(p => p.id).slice().sort().join(',') !==
        'A-door-and-kitchen-scope,B-upper-use,B1-backing,C1-care-suite' ||
      spec.pending_decisions.some(p => p.status !== 'not-adopted')) {
    throw new Error('Invalid or falsely approved minimal fengshui proposal');
  }
  const files = [spec.document, 'scripts/lib/model3d_fengshui.py'];
  for (const file of files) if (!fs.existsSync(path.join(project, file))) throw new Error('Missing fengshui source: ' + file);
  return files;
}

function preflightBcOptions(project, layout) {
  const source = 'inputs/bc-constraints-options.json';
  if (!fs.existsSync(path.join(project, source))) return []; // Historical projects / generic fixtures.
  const files = [source, 'Docs/bc-constraints-review-v1.md', 'scripts/export_bc_options.py',
    'scripts/templates/bc-options.html', 'scripts/templates/bc-options-controls.html',
    'scripts/templates/bc-options-bootstrap.js', 'structured/candidates/bc-options.html',
    'structured/candidates/bc-options-3d.html', 'structured/candidates/bc-options/layout.js'];
  for (const file of files) if (!fs.existsSync(path.join(project, file))) throw new Error('Missing BC comparison artifact: ' + file);
  const match = fs.readFileSync(path.join(project, files.at(-1)), 'utf8')
    .match(/^\s*window\.HOUSE_BC_OPTIONS\s*=\s*([\s\S]+?)\s*;\s*$/);
  if (!match) throw new Error('Invalid BC comparison JSON assignment');
  const study = JSON.parse(match[1]), raw = JSON.parse(fs.readFileSync(path.join(project, source), 'utf8'));
  const same = require('node:util').isDeepStrictEqual;
  const ids = ['b-baseline','b-strict','c-baseline','c-side-bed','c-wet-stack'];
  const keys = ['religious_acceptance','structure_and_fire','site_and_area','accessibility',
    'daylight_and_ventilation','plumbing_and_hvac','transport_rehearsal'];
  if (study.schema !== 'house-bc-constraints-options-v1' || study.status !== 'comparison-only-not-adopted' ||
      study.active_design !== 'baseline' || study.default_option !== 'b-strict' ||
      study.options?.map(o => o.id).join(',') !== ids.join(',') ||
      !same(study.confirmed_b_rules, raw.confirmed_b_rules) ||
      ['altar_door_faces_street','no_stair_or_hall_behind_altar','no_sleep_above_whole_shrine'].some(k => study.confirmed_b_rules[k] !== true)) {
    throw new Error('BC comparison loses confirmed rules or adopts an option');
  }
  const overlap = (a,b) => a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
  const box = g => ({minX:g.x_mm,maxX:g.x_mm+g.w_mm,minY:g.y_mm,maxY:g.y_mm+g.h_mm});
  for (const option of study.options) {
    if (option.status !== study.status || option.building !== option.id[0].toUpperCase() ||
        Object.keys(option.professional_status || {}).length !== keys.length ||
        keys.some(k => option.professional_status[k] !== 'unknown') ||
        option.plans?.id !== option.building || option.plans.floors.map(f => f.id).join(',') !== 'floor-1,floor-2,floor-3,floor-4') {
      throw new Error('Invalid or falsely approved BC comparison: ' + option.id);
    }
    for (const floor of option.plans.floors) {
      const name = option.id + '_' + floor.id + '.svg';
      if (floor.plan_file !== name || floor.width_mm !== 6000 || floor.depth_mm !== 17630 ||
          floor.rooms.reduce((sum,r) => sum + r.geometry.w_mm*r.geometry.h_mm, 0) !== 6000*17630) throw new Error('Invalid BC bounded floor: ' + name);
      const file = 'structured/candidates/bc-options/' + name;
      if (!fs.existsSync(path.join(project, file))) throw new Error('Missing BC floor plan: ' + file);
      const svg = fs.readFileSync(path.join(project, file), 'utf8');
      if (!svg.includes('data-study-option="'+option.id+'"') || !svg.includes('data-study-status="comparison-only-not-adopted"')) throw new Error('Unidentified BC comparison SVG: ' + file);
      files.push(file);
    }
    if (option.id.endsWith('baseline')) {
      const baseline = structuredClone(option.plans);
      baseline.floors.forEach(f => { f.plan_file = option.building + '_' + f.id + '.svg'; });
      if(study.baseline_reference==='inputs/references/abc-before-space-efficiency-20261014.json'){
        const reference=JSON.parse(fs.readFileSync(path.join(project,study.baseline_reference),'utf8')).buildings[option.building];
        if(baseline.floors.some(f=>Object.keys(reference.floors[f.id].rooms).length!==f.rooms.length||f.rooms.some(r=>{
          const original=reference.floors[f.id].rooms[r.key],g=r.geometry;return !original||original.name!==r.name||!same(original.rect,[g.x_mm,g.y_mm,g.w_mm,g.h_mm]);
        })))throw new Error('Stale BC frozen baseline: '+option.id);
      }else if (!same(baseline, layout.buildings.find(b => b.id === option.building))) throw new Error('Stale BC main baseline: ' + option.id);
    }
    const all = option.plans.floors.flatMap(f => f.rooms), room = key => all.find(r => r.id === option.building + ':' + key);
    const frontage = room('floor-1:garage');
    if (!frontage.outdoor || frontage.furniture.length || !same(frontage.geometry,{x_mm:0,y_mm:0,w_mm:6000,h_mm:3900})) throw new Error('BC comparison occupies the frontage');
    const issues = all.flatMap(r => r.furniture.filter(i => i.placement.issues.length).map(i => ({room_id:r.id,item_id:i.id,issues:i.placement.issues})));
    if (!same(issues,option.unresolved_furniture) ||
        issues.some(i => option.id !== 'c-wet-stack' || i.item_id !== 'C:floor-2:guestroom2f:furniture:wardrobe')) throw new Error('BC comparison hides unresolved furniture');
    if (option.id === 'b-strict') {
      const shrine = room('floor-1:shrine'), altar = shrine.furniture.find(i => i.shape === 'altar'),
        backing = room('floor-1:altar-backing'), rear = { ...altar.placement.aabb,minY:shrine.geometry.y_mm+shrine.geometry.h_mm,maxY:17630 };
      const prohibited = all.filter(r => r.id.includes(':floor-1:') && (r.kind === 'stair' || /hall|corridor|entry/.test(r.key)) && overlap(rear,box(r.geometry)));
      const sleepers = all.filter(r => !r.id.includes(':floor-1:') && (r.kind === 'bedroom' || r.furniture.some(i => ['bed','sofa-bed'].includes(i.shape))) && overlap(box(shrine.geometry),box(r.geometry)));
      const door = shrine.features.doors.find(d => d.purpose === 'ritual-entry');
      if (prohibited.length || sleepers.length || backing.geometry.y_mm !== rear.minY ||
          backing.geometry.w_mm < 2000 || backing.geometry.h_mm < 1500 || backing.furniture.length !== 1 ||
          backing.furniture[0].catalog_id !== 'ritual-cabinet' || !door || door.face !== 'front' ||
          door.neighbor !== 'B:floor-1:garage' || door.width_mm !== 1800 ||
          Math.abs(shrine.geometry.x_mm+shrine.geometry.w_mm*door.ratio-altar.placement.center_x_mm) > 1 ||
          !same(option.geometry_review.public_stair_path,['public-entry','rear-hall','stair1'])) throw new Error('BC strict B actual-room constraints fail');
      const demands = [['floor-1:shrine','altar',1800,600],['floor-1:storage','ceremonial-storage',1200,1700],
        ['floor-2:master2','bed',1520,1880],['floor-2:master2','wardrobe',1800,600],['floor-3:guest3','bed',1050,1880]];
      for (const [rid,local,w,d] of demands) {
        const item = room(rid)?.furniture.find(i => i.id.endsWith(':furniture:'+local));
        if (!item || item.width_mm < w || item.depth_mm < d) throw new Error('BC loses ordinary-sized B product: ' + local);
      }
      if (option.geometry_review.transport?.transport_acceptance !== 'unknown' ||
          option.geometry_review.program_screen.owner_tradeoffs_accepted !== null ||
          option.geometry_review.program_screen.areas.filter(a => a.state === 'brief-area-shortfall').length !== 2) throw new Error('BC B hides capacity or transport limitations');
    }
    if (['c-side-bed','c-wet-stack'].includes(option.id)) {
      const elder=room('floor-1:elder'),bath=room('floor-1:elder-bath'),bed=elder.furniture.find(i=>i.shape==='bed');
      const wet=all.filter(r=>!r.id.includes(':floor-1:') && ['bath','kitchen'].includes(r.kind));
      if (!same(elder.geometry,{x_mm:0,y_mm:13800,w_mm:3600,h_mm:3830}) ||
          !same(bath.geometry,{x_mm:3600,y_mm:13800,w_mm:2400,h_mm:3000}) || elder.features.window_mm !== 2300 ||
          !bed || bed.width_mm !== 1520 || bed.depth_mm !== 1880 || bed.placement.wall_anchor !== 'left' ||
          wet.some(r=>overlap(bed.placement.aabb,box(r.geometry))) ||
          (option.id==='c-wet-stack' && wet.some(r=>overlap(box(elder.geometry),box(r.geometry))))) throw new Error('BC C comparison shrinks care suite or misstates wet projection');
      if (option.id==='c-side-bed') {
        const above=wet.filter(r=>r.geometry.x_mm<bed.placement.aabb.maxX && r.geometry.x_mm+r.geometry.w_mm>bed.placement.aabb.minX);
        const gap=Math.min(...above.map(r=>bed.placement.aabb.minY-r.geometry.y_mm-r.geometry.h_mm));
        if (gap<200 || gap!==option.geometry_review.wet_room_to_bed_nominal_gap_mm) throw new Error('BC C small option loses extra wet-wall separation');
      }
    }
  }
  if (!study.source_hashes || !study.source_hashes[source]) throw new Error('Missing BC comparison source hashes');
  for (const [file,hash] of Object.entries(study.source_hashes)) {
    if (!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(file) || file.split('/').includes('..') ||
        !/^[a-f0-9]{64}$/.test(hash) || !fs.existsSync(path.join(project,file))) throw new Error('Invalid BC source hash: ' + file);
    if (crypto.createHash('sha256').update(fs.readFileSync(path.join(project,file))).digest('hex') !== hash) throw new Error('Stale BC comparison source: ' + file + '\nRun python scripts/export_bc_options.py');
  }
  return [...files,...Object.keys(study.source_hashes)];
}

function preflightSpaceAllocation(project, layout) {
  if (layout.layout_review?.id !== 'abc-rationality-v6-space-efficiency') return [];
  const audit = layout.layout_review.space_efficiency_review;
  if (!audit || audit.professional_acceptance !== 'unknown' || audit.status !== 'diagnostics-not-approval' ||
      audit.heuristic_is_law !== false || audit.floors?.length !== 12 || audit.b_priority?.preferred !== 'b32-rear' ||
      audit.b_priority?.fallback !== 'b32-front' || audit.b_priority.status !== 'comparison-only-not-adopted') throw new Error('Missing unverified space-allocation review');
  for (const b of layout.buildings) for (const f of b.floors) {
    const stats = audit.floors.find(a=>a.building===b.id && a.floor===f.id);
    const area=r=>r.geometry.w_mm*r.geometry.h_mm/1e6;
    const circulation=f.rooms.filter(r=>!r.outdoor && r.features.space_role==='circulation' && r.kind!=='stair').reduce((n,r)=>n+area(r),0);
    const bedrooms=f.rooms.filter(r=>!r.outdoor && r.kind==='bedroom').reduce((n,r)=>n+area(r),0);
    if (!stats || stats.professional_acceptance !== 'unknown' || Math.abs(stats.circulation_nominal_sqm-circulation)>.001 ||
        Math.abs(stats.bedroom_nominal_sqm-bedrooms)>.001 || f.rooms.some(r=>!r.features.allocation_review ||
        Math.abs(r.features.allocation_review.nominal_area_sqm-area(r))>.001)) throw new Error('Space allocation differs from actual tour coordinates');
  }
  const room=id=>layout.buildings.flatMap(b=>b.floors.flatMap(f=>f.rooms)).find(r=>r.id===id);
  if (room('A:floor-2:master').geometry.w_mm!==6000 || room('A:floor-2:master').geometry.h_mm!==3280 ||
      room('A:floor-2:bedroom2').geometry.w_mm!==2800 || room('A:floor-2:master-bath').kind!=='bath' ||
      room('B:floor-2:master-bath2').kind!=='bath' ||
      room('C:floor-3:fitness3f').features.doors.some(d=>d.neighbor==='C:floor-3:master3f') ||
      !room('C:floor-3:fitness3f').features.doors.some(d=>d.neighbor==='C:floor-3:front-hall')) throw new Error('Space-efficiency fix regressed or uses a private through-route');
  const files=['Docs/abc-space-efficiency-v1.md','scripts/lib/model3d_space_efficiency.py',audit.baseline_file];
  if (layout.layout_review.space_efficiency.revision===2) {
    const followup=audit.a_followup,source=layout.layout_review.space_efficiency.a_followup;
    const expectedMoves=[
      ['A:floor-2:walkin:furniture:wardrobe-right','A:floor-2:master:furniture:wardrobe-right'],
      ['A:floor-2:hall2:furniture:hall-cabinet','A:floor-2:master:furniture:hall-cabinet'],
      ['A:floor-3:multi:furniture:desk','A:floor-3:rear-common:furniture:desk'],
    ];
    const all=layout.buildings.flatMap(b=>b.floors.flatMap(f=>f.rooms.flatMap(r=>r.furniture)));
    if (!followup || audit.revision!==2 || followup.status!=='geometry-only-professional-review-pending' ||
        followup.professional_acceptance!=='unknown' || followup.owner_storage_choice!=='distributed-capacity-preserved' ||
        source?.status!=='proposal-not-professionally-approved' || followup.wardrobe_capacity_mm!==5400 ||
        followup.shallow_storage_width_mm!==2400 || all.length!==128 ||
        expectedMoves.some(([from,to])=>all.some(i=>i.id===from)||!all.some(i=>i.id===to&&i.relocated_from===from&&!i.placement.issues.length))) throw new Error('Storage followup hides, duplicates or falsely approves original furniture');
    const master=room('A:floor-2:master'),closet=room('A:floor-2:walkin'),reading=room('A:floor-3:rear-common');
    if (room('A:floor-2:hall2').furniture.length || closet.furniture.length!==1 ||
        [...master.furniture, ...closet.furniture].filter(i=>i.catalog_id==='wardrobe-180').length!==3 ||
        [...master.furniture, ...closet.furniture].some(i=>i.placement.issues.length) ||
        reading.features.space_role!=='work-zone' || reading.furniture.length!==2 ||
        reading.furniture.some(i=>i.placement.issues.length) || room('A:floor-3:front-hall').geometry.w_mm!==1360) throw new Error('Storage followup still obstructs public access or only renames the dry zone');
    for (const i of [...master.furniture,...closet.furniture,...reading.furniture]) {
      const size={'wardrobe-180':[1800,600,2200],'hall-cabinet':[2400,400,2200],'desk-120':[1200,600,750],
        'shelf-180':[1800,400,2100],'double-bed':[1800,2000,950]}[i.catalog_id];
      if (!size || JSON.stringify(size)!==JSON.stringify([i.width_mm,i.depth_mm,i.height_mm])) throw new Error('Storage followup shrinks products');
    }
    if (source.baseline_file!=='inputs/references/abc-before-a-storage-20261014.json' ||
        crypto.createHash('sha256').update(fs.readFileSync(path.join(project,source.baseline_file))).digest('hex')!==source.baseline_sha256) throw new Error('Storage followup baseline changed');
    files.push('Docs/a-storage-dry-zone-v2.md',source.baseline_file);
  }
  return files;
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
  return { cli, counts, sourceFiles: [...new Set([...SOURCE_FILES, ...plans, ...preflightMdf(project, layout), ...preflightC1f(project, layout), ...preflightArcade(project, layout), ...preflightFengshui(project, layout), ...preflightBcOptions(project, layout), ...preflightSpaceAllocation(project, layout)])] };
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
  function checkMinimalFengshui(building, floor, debug) {
    const spec = debug.layoutReview.fengshui_minimal;
    if (!spec) {
      assert(!['abc-rationality-v5-minimal-fengshui','abc-rationality-v6-space-efficiency'].includes(debug.layoutReview.id), 'current scene retains its fengshui decision contract');
      return;
    }
    assert(spec.status === 'partial-proposal-not-approved' && spec.religious_acceptance === 'unknown' &&
      spec.structural_acceptance === 'unknown' && spec.pending_decisions.length === 4 &&
      spec.pending_decisions.every(p => p.status === 'not-adopted'), 'fengshui keeps unadopted decisions unknown');
    const overlap = (a,b) => a.minX < b.maxX-1 && a.maxX > b.minX+1 && a.minY < b.maxY-1 && a.maxY > b.minY+1;
    const shape = id => debug.furniture.shapes.find(i => i.id === id);
    if (building === 'A' && floor.id === 'floor-1') {
      const counter = shape('A:floor-1:kitchen:furniture:counter');
      const item = floor.rooms.find(r => r.key === 'kitchen').furniture.find(i => i.id === counter?.id);
      assert(counter && counter.visible && counter.width === 2400 && counter.depth === 600 &&
        counter.worktopParts?.length === 2, 'A retains full-size counter and both rendered worktop parts');
      for (const part of counter.worktopParts) {
        const expected = item.placement.worktop_parts_mm.find(p => p.id === part.id);
        assert(expected && ['minX','maxX','minY','maxY'].every(k => Math.abs(part.aabb[k]-expected.aabb[k]) < .05),
          'A rendered ' + part.id + ' matches the SVG/shared worktop transform');
      }
      const hob = counter.worktopParts.find(p => p.id === 'hob');
      const sink = counter.worktopParts.find(p => p.id === 'sink');
      assert(hob && sink && hob.aabb.maxY+600 <= sink.aabb.minY+1, 'A forward hob and rear sink retain 60cm preparation');
      const check = debug.layoutReview.checks.find(c => c.id === 'A-hob-wet-projection');
      assert(check?.scope === 'hob-only-not-whole-kitchen' && check.plumbing_acceptance === 'unknown',
        'A hob screen does not approve plumbing or the whole kitchen');
      for (const id of check.wet_room_ids) {
        const room = sharedFloors['A:' + id.split(':')[1]].rooms.find(r => r.id === id), g = room.geometry;
        assert(!overlap(hob.aabb,{minX:g.x_mm,maxX:g.x_mm+g.w_mm,minY:g.y_mm,maxY:g.y_mm+g.h_mm}),
          'A rendered hob avoids ' + id + ' projection');
      }
    }
    if (building === 'B' && ['floor-2','floor-3'].includes(floor.id)) {
      const altar = sharedFloors['B:floor-1'].rooms.find(r => r.key === 'shrine').furniture.find(i => i.shape === 'altar');
      const key = floor.id === 'floor-2' ? 'living2' : 'guest3';
      const room = floor.rooms.find(r => r.key === key);
      for (const item of room.furniture) {
        const actual = shape(item.id);
        assert(actual && actual.visible && !actual.overflow && !actual.collision &&
          actual.width === item.width_mm && actual.depth === item.depth_mm && actual.height === item.height_mm &&
          !overlap(actual.placement.aabb,altar.placement.aabb), item.id + ' avoids the altar body without shrinking');
      }
      assert(room.features.fengshui_review.religious_acceptance === 'unknown', 'B upper use is not religious approval');
    }
    if (building === 'C' && floor.id === 'floor-3') {
      const bed = shape('C:floor-3:master3f:furniture:bed');
      assert(bed && bed.visible && bed.width === 1800 && bed.depth === 2000 && bed.rotation === 270 &&
        bed.placement.wall_anchor === 'left', 'C3 original-size bed has the side-wall headboard');
    }
    if (floor.id === 'floor-1' && ['B','C'].includes(building)) {
      const room = floor.rooms.find(r => r.key === (building === 'B' ? 'shrine' : 'elder'));
      assert(room.features.fengshui_review.status === 'decision-pending-not-adopted',
        building + ' 1F remains a decision, not an adopted alternative');
    }
  }
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
  const collectCStudySvg = () => {
    const svg = document.documentElement;
    return {
      kind: svg.localName, namespace: svg.namespaceURI,
      option: svg.getAttribute('data-study-option'), status: svg.getAttribute('data-study-status'),
      rooms: Array.from(svg.querySelectorAll('g[data-room-id]'), g => ({
        id: g.getAttribute('data-room-id'),
        geometry: ['data-x-mm','data-y-mm','data-w-mm','data-h-mm'].map(k =>
          g.hasAttribute(k) ? Number(g.getAttribute(k)) : null),
      })),
      // Room geometry and readable links live in separate layers. Do not look
      // for an anchor inside the wall/furniture group, which can also be empty.
      labels: Array.from(svg.querySelectorAll('[data-plan-labels="room-names"] a[data-label-room-id]'), a => ({
        id: a.getAttribute('data-label-room-id'), url: a.getAttribute('href'),
      })),
    };
  };
  const checkCStudySvg = (option, svg) => {
    assert(svg.kind === 'svg' && svg.namespace === 'http://www.w3.org/2000/svg' && svg.option === option.id &&
      svg.status === 'comparison-only-not-adopted', option.id + ' SVG document loads as the unadopted selected study');
    const rooms = option.floor.rooms;
    assert(svg.rooms.length === rooms.length && rooms.every(r => {
      const matches = svg.rooms.filter(g => g.id === r.id);
      return matches.length === 1 && JSON.stringify(matches[0].geometry) ===
        JSON.stringify([r.geometry.x_mm,r.geometry.y_mm,r.geometry.w_mm,r.geometry.h_mm]);
    }), option.id + ' SVG uses exact room coordinates');
    assert(svg.labels.length === rooms.length && rooms.every(r => {
      const matches = svg.labels.filter(a => a.id === r.id);
      return matches.length === 1 && matches[0].url === '../c1f-options-3d.html?scheme=' + option.id +
        '#mode=tour&building=C&floor=floor-1&room=' + encodeURIComponent(r.id) + '&view=plan';
    }), option.id + ' SVG top-layer room labels retain unique same-scheme room links');
  };
  const collectAHvacLabelBounds = () => {
    const root = document.documentElement;
    const box = node => {
      const b = node.getBBox();
      return { x: b.x, y: b.y, w: b.width, h: b.height,
        visible: node.getClientRects().length > 0 && getComputedStyle(node).visibility === 'visible' &&
          getComputedStyle(node).display !== 'none' && Number(getComputedStyle(node).opacity) > 0 };
    };
    return { kind: root.localName, building: root.getAttribute('data-building'), floor: root.getAttribute('data-floor'),
      labels: Array.from(root.querySelectorAll('a[data-label-room-id="A:floor-2:front-service"]'), node => ({
        name: node.getAttribute('data-full-name'), box: box(node),
      })),
      bodies: Array.from(root.querySelectorAll('g[data-room-id="A:floor-2:front-service"] rect[data-hvac-id]'), node => ({
        id: node.getAttribute('data-hvac-id'), type: node.getAttribute('data-hvac-type'), box: box(node),
      })),
      codes: Array.from(root.querySelectorAll('g[data-room-id="A:floor-2:front-service"] text[data-hvac-label-id]'), node => ({
        id: node.getAttribute('data-hvac-label-id'), type: node.getAttribute('data-hvac-label-type'),
        text: node.textContent, box: box(node),
      })),
    };
  };
  const checkAHvacLabelBounds = (floor, evidence) => {
    const room = floor.rooms.find(r => r.id === 'A:floor-2:front-service');
    assert(room && evidence.kind === 'svg' && evidence.building === 'A' && evidence.floor === 'floor-2' &&
      evidence.labels.length === 1 && evidence.labels[0].name === room.name,
    'A2 native SVG retains its unique full-name front balcony label');
    const label = evidence.labels[0].box;
    const valid = b => b && b.visible && ['x','y','w','h'].every(k => Number.isFinite(b[k])) && b.w > 0 && b.h > 0;
    assert(valid(label), 'A2 balcony room name has real visible browser font bounds');
    const units = room.features.hvac_units;
    assert(units.length === 2 && units.every(u => u.type === 'outdoor') &&
      evidence.bodies.length === units.length && evidence.codes.length === units.length,
    'A2 balcony retains both outdoor unit symbols and both complete codes');
    for (const unit of units) {
      const bodies = evidence.bodies.filter(n => n.id === unit.id && n.type === unit.type);
      const codes = evidence.codes.filter(n => n.id === unit.id && n.type === unit.type && n.text === unit.id + '外');
      assert(bodies.length === 1 && codes.length === 1 && valid(bodies[0].box) && valid(codes[0].box),
        unit.id + ' unique symbol and code remain visible, not hidden to avoid overlap');
      const w = ['left','right'].includes(unit.face) ? unit.depth_mm : unit.width_mm;
      const h = ['left','right'].includes(unit.face) ? unit.width_mm : unit.depth_mm;
      assert(Object.entries({x:unit.x_mm-w/2,y:unit.y_mm-h/2,w,h}).every(([k,v])=>Math.abs(bodies[0].box[k]-v)<.1),
        unit.id + ' SVG device body retains the exact shared 3D position and size');
      // SVG getBBox excludes the room-name's 45mm white outline by default.
      // Reserve that paint as well; values are diagram units, not clearances.
      const padded = {x:label.x-22.5,y:label.y-22.5,w:label.w+45,h:label.h+45};
      for (const [name,b] of [['symbol',bodies[0].box],['code',codes[0].box]]) {
        assert(padded.x+padded.w<=b.x || padded.x>=b.x+b.w || padded.y+padded.h<=b.y || padded.y>=b.y+b.h,
          'A2 actual rendered balcony name clears ' + unit.id + ' ' + name);
      }
    }
  };
  function checkBcOption(option, floor, debug) {
    const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
    assert(debug.presentation === 'tour' && debug.state.building === option.building && debug.state.floor === floor.id &&
      debug.layoutReview.status === 'comparison-only-not-adopted' && debug.bcOption?.id === option.id &&
      debug.bcOption.status === option.status, option.id + ' scene retains its independent unadopted identity');
    assert(same(debug.visibleRooms.slice().sort(),floor.rooms.map(r=>r.id).sort()), option.id + ' ' + floor.id + ' retains all rooms');
    assert(debug.furniture.items === option.plans.floors.reduce((s,f)=>s+f.rooms.reduce((n,r)=>n+r.furniture.length,0),0),
      option.id + ' inventory is single-building, not stale ABC totals');
    const pending = floor.rooms.flatMap(r=>r.furniture.filter(i=>i.placement.issues.length).map(i=>i.id));
    assert(same(debug.furniture.pendingItems.slice().sort(),pending.sort()) && debug.furniture.visibleIssues === 0,
      option.id + ' pending furniture remains explicit, not rendered as a successful fit');
    for (const room of floor.rooms) {
      const actual = debug.tour.rooms.find(r=>r.id===room.id);
      assert(actual && same(actual.geometry,room.geometry) && same(actual.features,room.features),
        option.id + ' ' + room.key + ' HTML/SVG and real scene share geometry, doors, windows and clearances');
      for (const item of room.furniture) {
        const shape = debug.furniture.shapes.find(i=>i.id===item.id), p=item.placement;
        assert(shape && shape.width===item.width_mm && shape.depth===item.depth_mm && shape.height===item.height_mm &&
          same(shape.placement,p) && shape.visible===!p.issues.length, option.id+' full-size placement '+item.id);
        assert(shape && Math.abs(shape.center[0]-p.center_x_mm)<.1 && Math.abs(shape.center[1]-p.center_y_mm)<.1 &&
          Math.abs(shape.rotation-p.rotation_deg)<.1, option.id+' actual mesh transform '+item.id);
      }
    }
    assert(debug.bcOption.geometry_review.religious_acceptance==='unknown' &&
      debug.bcOption.geometry_review.program_screen.owner_tradeoffs_accepted===null,
      option.id+' geometry check does not invent religious or owner approval');
  }
  // isVisible() alone also accepts an unclipped DOM box below the viewport.
  // Collect actual browser layout/style, then apply the same pure contract in
  // negative fixtures. Fixtures are not screenshots or rendered CSS evidence.
  const collectBcPresentation = () => {
    const inspect = selector => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const box = node.getBoundingClientRect(), style = getComputedStyle(node);
      let opacity = 1;
      for (let parent = node; parent; parent = parent.parentElement) opacity *= Number(getComputedStyle(parent).opacity);
      return { text: node.textContent.trim(), rect: { left: box.left, top: box.top, right: box.right,
        bottom: box.bottom, width: box.width, height: box.height }, hasBox: node.getClientRects().length > 0,
        display: style.display, visibility: style.visibility, position: style.position, opacity,
        zIndex: Number(style.zIndex) || 0, color: style.color, background: style.backgroundColor,
        clientWidth: node.clientWidth, scrollWidth: node.scrollWidth,
        clientHeight: node.clientHeight, scrollHeight: node.scrollHeight,
        role: node.getAttribute('role'), live: node.getAttribute('aria-live'),
        href: node.getAttribute('href'), disabled: Boolean(node.disabled),
        label: node.labels ? Array.from(node.labels).map(n => n.textContent.trim()).join(' ') : '' };
    };
    const retired = ['#tour-actions', '#furniture-start', '#presentation-mode', '#geom-source', '#geometry-hint',
      '#mdf-study-description', '#mdf-section-link', 'label:has(#mdf-study)', 'label:has(#frontage-study)',
      'label:has(#frontage-study)+.hint', 'h2:has(+#presentation-mode)', 'h2:has(+#geom-source)',
      '#facade-actions', '#compare', 'label:has(#ghost)', 'h2:has(+label #ghost)'];
    // Native CSS rejects nested :has(). One invalid selector also invalidates
    // its entire comma-separated stylesheet rule; do not skip such failures.
    for (const selector of retired) {
      if (!CSS.supports('selector(' + selector + ')')) throw new Error('Invalid or unsupported BC presentation selector: ' + selector);
    }
    return { viewport: { left: 0, top: 0, right: innerWidth, bottom: innerHeight, width: innerWidth, height: innerHeight },
      bcClass: document.body.classList.contains('bc-study'), kind: document.body.getAttribute('data-study-kind'),
      option: document.body.getAttribute('data-study-option'), title: document.title,
      scheme: document.getElementById('study-scheme')?.value,
      stage: inspect('#stage'), badge: inspect('#study-stage-note'), orientation: inspect('#orientation'),
      panel: inspect('#panel'), card: inspect('#bc-study-controls'), warning: inspect('.bc-study-warning'),
      retired: Object.fromEntries(retired.map(selector => [selector, inspect(selector)?.display ?? null])),
      controls: ['#study-scheme', '#study-plan-link', '.bc-study-links a[href="model3d.html"]',
        '#bc-study-controls summary'].map(inspect) };
  };
  function checkBcPresentation(evidence, option, controls = false) {
    const name = option.id + ' comparison presentation';
    const validRect = r => r && ['left','top','right','bottom','width','height'].every(k => Number.isFinite(r[k])) &&
      r.width > 0 && r.height > 0 && Math.abs(r.right-r.left-r.width) < 1 && Math.abs(r.bottom-r.top-r.height) < 1;
    const inside = (a,b) => validRect(a) && validRect(b) && a.left >= b.left-1 && a.top >= b.top-1 &&
      a.right <= b.right+1 && a.bottom <= b.bottom+1;
    const painted = n => n && n.hasBox && n.display !== 'none' && n.visibility === 'visible' && n.opacity >= .95;
    const color = value => {
      if (!/^rgba?\(/.test(value || '')) return null;
      const c = value.match(/[\d.]+/g).map(Number);
      return c.length >= 3 ? { rgb: c.slice(0,3), alpha: c[3] ?? 1 } : null;
    };
    const luminance = c => c.rgb.map(v => { const n = v/255; return n <= .04045 ? n/12.92 : ((n+.055)/1.055)**2.4; })
      .reduce((sum,n,i) => sum+n*[.2126,.7152,.0722][i],0);
    assert(evidence.bcClass && evidence.kind === 'bc-constraints' && evidence.option === option.id &&
      evidence.scheme === option.id && evidence.title.includes(option.label) && evidence.title.includes('未採用'),
      name + ' retains the current comparison identity, not ABC main');
    const badge = evidence.badge;
    assert(painted(badge) && badge.position === 'absolute' && badge.zIndex >= 1 && evidence.stage?.position === 'relative' &&
      badge.text.includes(option.label) && badge.text.includes('未採用／未核') && badge.role === 'status' && badge.live === 'polite',
      name + ' has a painted, positioned and accessible unadopted warning');
    assert(inside(badge.rect,evidence.viewport) && inside(badge.rect,evidence.stage.rect),
      name + ' warning is fully inside both the viewport and 3D stage');
    assert(badge.scrollWidth <= badge.clientWidth+1 && badge.scrollHeight <= badge.clientHeight+1,
      name + ' warning text is not clipped');
    const foreground = color(badge.color), background = color(badge.background);
    assert(foreground && background && foreground.alpha >= .95 && background.alpha >= .95 &&
      (Math.max(luminance(foreground),luminance(background))+.05)/(Math.min(luminance(foreground),luminance(background))+.05) >= 4.5,
      name + ' warning has an opaque background and readable text contrast');
    const direction = evidence.orientation;
    assert(painted(direction) && inside(direction.rect,evidence.viewport) && inside(direction.rect,evidence.stage.rect) &&
      (badge.rect.right <= direction.rect.left-3 || badge.rect.left >= direction.rect.right+3 ||
        badge.rect.bottom <= direction.rect.top-3 || badge.rect.top >= direction.rect.bottom+3),
      name + ' warning does not overlap the visible direction footer');
    const retired = ['#tour-actions', '#furniture-start', '#presentation-mode', '#geom-source', '#geometry-hint',
      '#mdf-study-description', '#mdf-section-link', 'label:has(#mdf-study)', 'label:has(#frontage-study)',
      'label:has(#frontage-study)+.hint', 'h2:has(+#presentation-mode)', 'h2:has(+#geom-source)',
      '#facade-actions', '#compare', 'label:has(#ghost)', 'h2:has(+label #ghost)'];
    assert(retired.every(selector => evidence.retired?.[selector] === 'none'),
      name + ' hides unrelated ABC shortcuts, MDF, facade and historical geometry controls');
    if (controls) {
      assert(painted(evidence.card) && painted(evidence.warning) && evidence.warning.text.includes('未採用／未核') &&
        evidence.card.scrollWidth <= evidence.card.clientWidth+1 && evidence.panel.scrollWidth <= evidence.panel.clientWidth+1,
        name + ' expanded sidebar keeps the warning without horizontal overflow');
      assert(evidence.controls.length === 4 && evidence.controls.every(n => painted(n) && !n.disabled &&
        validRect(n.rect) && n.rect.height >= 44 && n.rect.width >= 44 &&
        n.rect.left >= evidence.panel.rect.left-1 && n.rect.right <= evidence.panel.rect.right+1),
        name + ' scheme, return links and tradeoffs are usable 44px targets within the panel');
      assert(evidence.controls[0].label.includes('方案') && evidence.controls[1].href === 'bc-options.html#'+option.id &&
        evidence.controls[2].href === 'model3d.html', name + ' labels and return destinations match this comparison');
    }
  }
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
  const checkPlanReader = async (panel, screenshot) => {
    const reader=panel.locator('[data-plan-viewer]'),frame=reader.locator('[data-plan-viewport]');
    await frame.scrollIntoViewIfNeeded();
    await page.waitForFunction(selector=>{
      const r=document.querySelector(selector),img=r?.querySelector('[data-plan-content]');
      return r?.dataset.planMode==='readable' && img?.complete && img.naturalWidth>0;
    }, '#'+await panel.getAttribute('data-floor-id')+' [data-plan-viewer]');
    const inspect=()=>reader.evaluate(r=>{
      const img=r.querySelector('[data-plan-content]'),v=r.querySelector('[data-plan-viewport]');
      const image=img.getBoundingClientRect();
      return {mode:r.dataset.planMode,width:image.width,height:image.height,vw:v.clientWidth,vh:v.clientHeight,
        left:v.scrollLeft,top:v.scrollTop,source:img.src,controls:[...r.querySelectorAll('button')].map(b=>b.getBoundingClientRect().height),
        sourceRatio:Number(r.dataset.sourceHeight)/Number(r.dataset.sourceWidth),
        overflow:document.documentElement.scrollWidth>window.innerWidth+2};
    });
    let state=await inspect();
    assert(Math.abs(state.width-660)<1 && Math.abs(state.height/state.width-state.sourceRatio)<.01 &&
      state.controls.length===4 && state.controls.every(h=>h>=44) && !state.overflow,
      'main HTML reader is independently readable with original aspect, touch controls and no page overflow');
    await reader.locator('[data-plan-action="in"]').click();state=await inspect();
    assert(state.width>660 && state.mode==='zoom','main HTML vector zoom increases actual drawing size');
    await reader.locator('[data-plan-action="overview"]').click();state=await inspect();
    assert(state.width<=state.vw+1 && state.height<=state.vh+1 && state.mode==='overview',
      'main HTML overview fits both axes without changing plan source');
    await reader.locator('[data-plan-action="readable"]').click();state=await inspect();
    assert(Math.abs(state.width-660)<1 && state.top===0 && state.left===0,'main HTML readable reset restores drawing and scroll origin');
    await frame.focus();await page.keyboard.press('End');state=await inspect();
    assert(state.top>0 && state.source.includes('/furniture-plans/'),'main HTML keyboard scroll reaches the original vector');
    await reader.locator('[data-plan-action="readable"]').click();
    await frame.scrollIntoViewIfNeeded();await capture(screenshot);
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
    const resolved = floor.rooms.find(r=>r.key==='master')?.features.storage_resolution;
    const expectedPending = resolved ? [] : ['A:floor-2:hall2:furniture:hall-cabinet',
      'A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right'];
    assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
      'mobile A bathroom retains both pending wardrobes and the displaced hallway cabinet');
    if (resolved) {
      const storage=[['A:floor-2:master:furniture:wardrobe',1800,600],['A:floor-2:master:furniture:wardrobe-right',1800,600],
        ['A:floor-2:master:furniture:hall-cabinet',2400,400],['A:floor-2:walkin:furniture:wardrobe-left',1800,600]];
      assert(storage.every(([id,w,d])=>debug.furniture.shapes.filter(i=>i.id===id&&i.visible&&i.width===w&&i.depth===d&&i.height===2200).length===1),
        'mobile A bathroom retains all relocated storage visible at original dimensions');
    }
    assert(expectedPending.every(id => {
      const items = debug.furniture.shapes.filter(i => i.id === id);
      const wardrobe = id.includes(':walkin:');
      return items.length === 1 && !items[0].visible && items[0].width === (wardrobe ? 1800 : 2400) &&
        items[0].depth === (wardrobe ? 600 : 400) && items[0].height === 2200;
    }), 'mobile A bathroom keeps pending wardrobes and displaced cabinet hidden at their original dimensions');
    assert(debug.panelCollapsed && debug.focusedScreenBounds.length === 8 &&
      debug.focusedScreenBounds.every(point => Math.abs(point[0]) < 1 && Math.abs(point[1]) < 1),
    'mobile A bathroom closeup fits the resized stage with controls collapsed');
  };
  const expandMobilePanel = async () => {
    const toggle = page.locator('#mobile-panel-toggle');
    const expanded = await toggle.getAttribute('aria-expanded');
    assert(['true', 'false'].includes(expanded), 'mobile panel exposes state before expansion');
    if (expanded === 'false') await toggle.click();
    await page.waitForFunction(() => {
      const stage = document.getElementById('stage'), canvas = document.getElementById('canvas');
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      return document.getElementById('mobile-panel-toggle').getAttribute('aria-expanded') === 'true' &&
        !window.__htmlModel3dDebug().panelCollapsed &&
        Math.abs(canvas.width - stage.clientWidth * ratio) <= 1 &&
        Math.abs(canvas.height - stage.clientHeight * ratio) <= 1;
    });
    assert(await toggle.getAttribute('aria-expanded') === 'true', 'mobile panel expanded and renderer resized');
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
  const checkMdfStudy = (debug, floor) => {
    const view = debug.mdfStudy, s = view && view.data;
    assert(view && view.active && s && s.status === 'conditional-not-installed' && s.active_design === 'side-backup' &&
      s.preferred_option === 'under-stair' && s.candidate.installed === false && s.candidate.counts_as_furniture === false &&
      s.candidate.section_verified === false && s.reuse.installed === false && s.reuse.released_area_sqm === null &&
      s.backup.released_area_sqm === null, 'MDF study retains backup and cannot count installation or freed space');
    assert(Object.values(s.professional_status).every(v => v === 'unknown') && s.evidence === null,
      'MDF study never invents structural, fire, ventilation or replacement approval');
    assert(JSON.stringify([s.rack.width_mm,s.rack.depth_mm,s.rack.height_mm]) === '[600,600,1000]' &&
      s.clearances_mm.front === 800 && s.clearances_mm.rear === 600 && s.clearances_mm.left === 300 && s.clearances_mm.right === 300 &&
      s.candidate.flight_width_mm === 900 && s.candidate.service_mm.maxX-s.candidate.service_mm.minX === 1200 &&
      s.candidate.service_mm.maxY-s.candidate.service_mm.minY === 2000 &&
      s.candidate.issues.includes('side-maintenance-exceeds-return-flight'), 'MDF study preserves full rack and original maintenance conflict');
    const backup = floor.rooms.find(r => r.key === 'mdf'), rack = backup.furniture.find(i => i.id === s.rack.original_item_id);
    assert(rack && JSON.stringify(s.backup.geometry) === JSON.stringify(backup.geometry) &&
      JSON.stringify(s.backup.placement) === JSON.stringify(rack.placement) && rack.placement.side_operation_mm.length === 2,
    'MDF backup equals HTML room and includes both 300mm maintenance sides');
    assert(view.visible.length === 8 && view.visible.every(v => v.status === 'conditional-not-installed' && !v.counts_as_furniture),
      'MDF has exactly eight non-installed study envelopes, not extra products');
    for (const v of view.visible) {
      const bounds = v.renderedBounds;
      assert(Math.abs((bounds.max[0]-bounds.min[0])*1000-(v.box.maxX-v.box.minX)) < .02 &&
        Math.abs((bounds.max[2]-bounds.min[2])*1000-(v.box.maxY-v.box.minY)) < .02 &&
        Math.abs((bounds.max[1]-bounds.min[1])*1000-v.height_mm) < .02, v.id + ' MDF real scene envelope has unchanged source dimensions');
    }
    assert(debug.furniture.items === expectedCounts.items && debug.visibleRooms.length === floor.rooms.length,
      'MDF study retains original item count and all A1F rooms');
  };
  const checkCameraFraming = (debug, roomId = '') => {
    const frame = debug.cameraFraming, area = frame && frame.safeArea;
    assert(frame && frame.ready && area && area.usable && frame.width > 0 && frame.height > 0,
      'camera framing has a rendered frame and a measured usable viewport');
    const rectangle = points => {
      assert(points.length === 8 && points.every(p => p.length === 3 && p.every(Number.isFinite) && p[2] >= -1 && p[2] <= 1),
        'framing uses eight finite projected body corners inside camera depth');
      const xs = points.map(p => (p[0] + 1) * frame.width / 2), ys = points.map(p => (1 - p[1]) * frame.height / 2);
      return { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
    };
    const inside = box => box.left >= area.left - 1 && box.right <= area.right + 1 &&
      box.top >= area.top - 1 && box.bottom <= area.bottom + 1;
    const box = rectangle(debug.focusedScreenBounds), usableW = area.right - area.left, usableH = area.bottom - area.top;
    assert(inside(box), 'focused model fits the measured control/title/caveat-safe rectangle');
    assert(Math.max((box.right - box.left) / usableW, (box.bottom - box.top) / usableH) >= .6,
      'focused model fills at least 60% of one usable viewport dimension, not a tiny fit');
    const headers = ['hud', 'stage-title', 'room-view-actions', 'facade-actions', 'compass'];
    assert(frame.overlays.every(r => headers.includes(r.id) ? r.bottom + 9 <= area.top : r.top - 9 >= area.bottom),
      'camera safe area is backed by actual overlay rectangles, including the unadopted badge');
    if (roomId) {
      assert(debug.roomCloseup && debug.state.room === roomId, 'readability checks the selected closeup, not the whole floor');
      const expected = debug.furniture.shapes.filter(i => i.visible && i.id.startsWith(roomId + ':furniture:')).map(i => i.id).sort();
      assert(JSON.stringify(frame.selectedItems.map(i => i.id).sort()) === JSON.stringify(expected),
        'readability covers every displayed selected-room product body');
      if (!expected.length) {
        const retained = debug.furniture.shapes.filter(i => i.id.startsWith(roomId + ':furniture:'));
        assert(debug.furniture.visible && debug.tour.rooms.some(r => r.id === roomId) &&
          retained.every(i => (i.overflow || i.collision) && debug.furniture.pendingItems.includes(i.id)),
        'empty-room framing retains its room and pending originals; hidden valid furniture is not evidence');
      }
      for (const item of frame.selectedItems) {
        const body = rectangle(item.corners);
        assert(inside(body) && body.right - body.left >= 16 && body.bottom - body.top >= 16,
          item.id + ' has at least a 16×16 CSS-pixel projected body within the safe area');
      }
    } else if (frame.width / frame.height >= 1.8) {
      assert(box.right - box.left >= usableW * .4, 'landscape whole floor uses at least 40% of the available width');
    }
    assert(frame.limitation.includes('not pixel visibility'), 'projected-size checks never claim pixel or professional acceptance');
  };
  const checkMobileComparisonControls = async () => {
    const measurement = await page.evaluate(() => {
      const toolbar = document.querySelector('.toolbar'), controls = [...toolbar.querySelectorAll('select, button, a.action')];
      return { width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1,
        controls: controls.map(element => {
          const r = element.getBoundingClientRect(), range = document.createRange();range.selectNodeContents(element);
          const lines = element.tagName === 'A' ? [...new Set([...range.getClientRects()].map(line => Math.round(line.top)))] : [];
          return { id: element.id, left: r.left, right: r.right, width: r.width, height: r.height, lines: lines.length };
        }) };
    });
    assert(!measurement.overflow && measurement.controls.length >= 4 && measurement.controls.every(r =>
      r.left >= 0 && r.right <= measurement.width + 1 && r.width >= 44 && r.height >= 44),
    'mobile comparison controls stay inside the viewport with 44px touch targets');
    const link = measurement.controls.find(r => r.id === 'open-3d');
    assert(link && link.width >= 100 && link.lines === 1, 'mobile 本案3D link stays at least 100px wide on one readable line');
  };
  const checkAMainArcade = (floor, debug) => {
    const room = key => floor.rooms.find(r => r.key === key);
    const arcade = room('arcade'), passage = room('care-passage'), elder = room('flex1');
    const care = debug.layoutReview.checks.find(c => c.id === 'A-1F-care-functions');
    const basis = debug.layoutReview.checks.find(c => c.id === 'A-32ping-arcade-functions');
    assert(arcade && arcade.outdoor && arcade.geometry.x_mm === 0 && arcade.geometry.y_mm === 0 &&
      arcade.geometry.w_mm === 6000 && arcade.geometry.h_mm === 3900 && !arcade.furniture.length &&
      !arcade.features.hvac_units.length && arcade.name.includes('騎樓'),
    'A main explicitly draws a clear 3.9m arcade inside the parcel');
    assert(floor.width_mm === 6000 && floor.depth_mm === 17630 && floor.base_mm === 0 && floor.height_mm === 4000 &&
      floor.rooms.filter(r => r !== arcade).every(r => r.geometry.y_mm >= 3900),
    'A frontage is inside the fixed 32-ping frame, not added onto a private front room');
    assert(basis && basis.status === 'bounded-arcade-and-function-screen-only' && basis.arcade_applicability === 'unknown' &&
      basis.verified_headroom_mm === null && basis.legal_building_area_sqm === null &&
      basis.professional_acceptance === 'unknown' && basis.verified_parking_spaces === null,
    'A arcade function screen cannot invent legal, headroom, parking or professional approval');
    assert(passage && passage.geometry.w_mm - 160 >= 1200 && care &&
      Object.values(care.routes).every(route => !route.some(id => ['A:floor-1:mdf','A:floor-1:stair-door'].includes(id))),
    'A retains 1200mm assumed clear care passage without stairs or MDF through-routes');
    assert(elder && elder.geometry.w_mm === 3600 && elder.geometry.h_mm === 3770 &&
      elder.furniture.some(i => i.catalog_id === 'queen-bed' && i.width_mm === 1520 && i.depth_mm === 1880) &&
      elder.furniture.some(i => i.catalog_id === 'wardrobe-120' && i.width_mm === 1200 && i.depth_mm === 600),
    'A elder room and full-size original bed and wardrobe are not reduced to fit an arcade');
    const living = room('living'), area = (living.geometry.w_mm-160)*(living.geometry.h_mm-160)/1e6;
    assert(Math.abs(area-18.003)<.001 && basis.note.includes('施工餘裕很小'),
      'A tight living-area margin stays explicit, not called comfortable or verified');
    const dining = living.furniture.find(i => i.catalog_id === 'dining-4-sides');
    assert(dining && dining.width_mm === 1200 && dining.depth_mm === 1800 && dining.height_mm === 850 &&
      dining.table_width_mm === 1200 && dining.table_depth_mm === 800 && !dining.placement.issues.length,
    'A uses a normal four-seat long-side candidate, not shrunken table or chairs');
  };
  const checkUpperFloor = (building, floor, debug) => {
    const room = key => floor.rooms.find(r => r.id === building + ':floor-2:' + key);
    const resolved = building === 'A' && room('master')?.features.storage_resolution;
    const expectedPending = building === 'A' && !resolved ? [
      'A:floor-2:hall2:furniture:hall-cabinet',
      'A:floor-2:walkin:furniture:wardrobe-left', 'A:floor-2:walkin:furniture:wardrobe-right',
    ] : [];
    assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
      building + ' upstairs pending list retains original A wardrobes and displaced hall cabinet');
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
      assert(room('master-bath').geometry.w_mm === 2400 && room('walkin').geometry.w_mm === 2400,
        'A upstairs bathroom keeps width while the shared landing changes closet geometry');
      const hall = room('hall2');
      const cabinet = (resolved ? room('master') : hall).furniture.find(i => i.catalog_id === 'hall-cabinet');
      const closet = room('walkin');
      if (resolved) {
        assert(hall.furniture.length===0 && hall.geometry.w_mm-160===1280 &&
          cabinet.width_mm===2400 && cabinet.depth_mm===400 && cabinet.height_mm===2200 && !cabinet.placement.issues.length &&
          debug.furniture.shapes.some(i=>i.id===cabinet.id&&i.visible), 'A relocated full-size shallow cabinet is visible and leaves public access clear');
        const wardrobes=[...room('master').furniture,...closet.furniture].filter(i=>i.catalog_id==='wardrobe-180');
        assert(wardrobes.length===3 && closet.furniture.length===1 && wardrobes.every(i=>i.width_mm===1800&&i.depth_mm===600&&i.height_mm===2200&&
          !i.placement.issues.length&&debug.furniture.shapes.some(s=>s.id===i.id&&s.visible)), 'A all three full-size wardrobes are genuinely placed, not deleted or shrunk');
        assert(closet.furniture[0].shared_operation_mode==='sequential-only-not-verified' &&
          JSON.stringify(closet.furniture[0].shared_operation_with)==='["door-approach"]', 'A closet entry/operation overlap stays private and explicitly sequential');
      } else {
      assert(cabinet && cabinet.placement.issues.includes('circulation') && cabinet.width_mm === 2400 && cabinet.depth_mm === 400 &&
        cabinet.height_mm === 2200, 'A full-size hallway cabinet is pending, not squeezed into public access');
      assert(hall.geometry.w_mm - 160 === 1280 && cabinet.note.includes('不能同時當通道') &&
        debug.furniture.shapes.some(i => i.id === cabinet.id && !i.visible),
      'A keeps 1280mm assumed public passage and hides only the explicitly pending cabinet');
      assert(closet.furniture.length === 2 && closet.furniture.every(i => i.catalog_id === 'wardrobe-180' &&
        i.width_mm === 1800 && i.depth_mm === 600 && i.height_mm === 2200 && i.placement.status === 'pending-layout'),
      'A two full-size wardrobes remain pending, not deleted or silently substituted');
      }
    } else {
      assert(room('bath2').geometry.h_mm === 2000 && room('master-bath2').geometry.y_mm === 15800,
        'B public/ensuite partition transfer preserves the rear wet-zone footprint');
    }
  };
  const checkCFirstFloor = (floor, debug) => {
    const room = key => floor.rooms.find(r => r.key === key);
    const dining = room('dining'), living = room('living'), kitchen = room('kitchen'), elder = room('elder');
    assert(dining && living && kitchen && elder && !room('front-service'),
      'C retains dining/lounge functional zones without enclosing the frontage');
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
    assert(sofa.wall_anchor === '' && sofa.rotation_deg === 90 && tv.wall_anchor === 'left' && sofa.center_y_mm === tv.center_y_mm &&
      sofa.center_y_mm === table.center_y_mm && sofa.aabb.minX - table.aabb.maxX === 400,
    'C lounge TV on retained left wall faces normal sofa with 400mm coffee-table gap');
    const open = debug.layoutReview.checks.find(c => c.id === 'C-open-living-dining');
    assert(open && open.allocation_area_sqm === 33.6 && open.living_dining_area_sqm === 27.2 && open.added_floor_area_sqm === 0 &&
      open.structural_acceptance === 'unknown' && open.fire_acceptance === 'unknown' && open.daylight_acceptance === 'unknown',
    'C open-plan area does not invent new space or professional approval');
    for (const [a,b,width] of [['entrance','dining',3200],['entrance','living',2000],['dining','living',4000]]) {
      for (const [x,y] of [[a,b],[b,a]]) {
        const zone=room(x), neighbor=room(y);
        assert(zone.features.space_group === 'C1-open-living-dining' && neighbor.features.space_group === zone.features.space_group &&
          zone.features.open_connections.some(o => o.neighbor === neighbor.id && o.width_mm === width) &&
          !zone.features.doors.some(o => o.neighbor === neighbor.id), 'C full shared boundary has no partition/door: '+x+'/'+y);
      }
    }
    assert(living.features.reserved_mm.some(z => z.kind === 'care-turn' &&
      z.aabb.maxX-z.aabb.minX === 1500 && z.aabb.maxY-z.aabb.minY === 1500) &&
      dining.features.reserved_mm.some(z => z.kind === 'care-route' && z.aabb.maxX-z.aabb.minX === 1200),
    'C keeps dining care route and lounge turning reservation, not approval');
    const counter = kitchen.furniture.find(i => i.catalog_id === 'counter-240-60');
    assert(counter.front_clearance_mm === 900 && counter.shared_operation_with.join('|') === 'door-approach' &&
      counter.note.includes('非把原240×65cm代表型號縮薄'), 'C kitchen states distinct candidate and sequential use');
    const route = debug.layoutReview.hvac_routes.find(r => r.id === 'C-AC01');
    assert(route.outdoor_room === 'C:floor-2:balcony2f' && route.estimated_routed_length_mm === 14325 &&
      route.elevation_difference_mm === 1150 && route.compliance === 'unknown' && route.manual_source === null,
    'C AC moves to a retained wall with routed quantity but no model/installer approval');
    const study = room('garage').features.frontage_study;
    assert(study.status === 'conditional-not-installed' && study.active_option === 'keep-full-clear' &&
      study.site_use_status === 'unknown' && !room('garage').furniture.length && !debug.frontageStudy.visible.length,
    'C unknown frontage is empty by default; garden/bench are conditional overlays only');
  };
  const checkBFirstFloor = (floor, debug) => {
    const room = key => floor.rooms.find(r => r.key === key), shrine=room('shrine');
    const altar=shrine.furniture.find(i => i.shape === 'altar').placement;
    const front=shrine.features.doors.find(d => d.purpose === 'ritual-entry');
    assert(front && front.face === 'front' && front.neighbor === 'B:floor-1:garage' && front.width_mm === 1800 &&
      Math.abs(shrine.geometry.x_mm + shrine.geometry.w_mm*front.ratio - altar.center_x_mm) < 1,
    'B owner-required front ritual door shares the altar axis');
    const review=debug.layoutReview.checks.find(c => c.id === 'B-ritual-and-transport-flow');
    assert(review && review.ritual.owner_requires_axial_front_door && review.ritual.religious_acceptance === 'unknown' &&
      review.transport.transport_acceptance === 'unknown' && review.transport.segments.map(s=>s.room_id.split(':').at(-1)).join(',') === 'garage,entry,corridor1,storage',
    'B worship and straight storage-body route stay separate without religious or transport approval');
    const body=room('storage').furniture.find(i=>i.shape==='palanquin');
    assert(body && review.transport.gates.every(g=>g.nominal_width_mm===1500 && g.body_side_margin_mm===(1500-body.width_mm)/2) &&
      review.transport.bottleneck_assumed_width_mm===1440 &&
      ['width_mm','depth_mm','height_mm'].every(k=>review.transport.storage_dimensions[k]===body[k]),
    'B inventory-linked body margins and assumed corridor do not prove poles, handlers or rehearsal');
    assert(debug.transportRoutes.length===4, 'B renderer retains all four annotated transport segments');
    for(const segment of debug.transportRoutes){
      const source=review.transport.segments.find(s=>s.room_id===segment.room);
      const points=source.centerline_mm.flatMap(p=>[p[0]/1000,.04,-p[1]/1000]);
      assert(segment.status==='storage-body-sweep-only-not-transport-approval' &&
        JSON.stringify(segment.segment)===JSON.stringify(source) && segment.renderedPoints.length===points.length &&
        segment.renderedPoints.every((v,i)=>Math.abs(v-points[i])<.00001), segment.room+' actual route vertices match the shared plan');
    }
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
  const checkCOption = (option, debug) => {
    const floor = option.floor, room = key => floor.rooms.find(r => r.key === key);
    assert(debug.presentation === 'tour' && debug.state.building === 'C' && debug.state.floor === 'floor-1' &&
      debug.layoutReview.status === 'comparison-only-not-adopted', option.id + ' is an isolated unadopted C1F study');
    assert(floor.width_mm === 6000 && floor.depth_mm === 17630 &&
      floor.rooms.length === (option.id === 'baseline' ? 11 : 12) &&
      new Set(floor.rooms.map(r => r.id)).size === floor.rooms.length &&
      JSON.stringify(debug.visibleRooms.slice().sort()) === JSON.stringify(floor.rooms.map(r => r.id).sort()),
    option.id + ' retains the exact bounded floor and room IDs');
    assert(JSON.stringify(debug.furniture.shapes.map(i => i.id).sort()) ===
      JSON.stringify(floor.rooms.flatMap(r => r.furniture.map(i => i.id)).sort()),
    option.id + ' retains the exact study furniture IDs');
    for (const expected of floor.rooms) {
      const actual = debug.tour.rooms.find(r => r.id === expected.id);
      assert(actual && JSON.stringify(actual.geometry) === JSON.stringify(expected.geometry) &&
        JSON.stringify(actual.features) === JSON.stringify(expected.features), expected.id + ' study geometry/openings/reserves match');
      for (const item of expected.furniture) {
        const shape = debug.furniture.shapes.find(i => i.id === item.id), p = item.placement;
        assert(shape && shape.visible && shape.width === item.width_mm && shape.depth === item.depth_mm &&
          shape.height === item.height_mm && !p.issues.length &&
          Math.abs(shape.center[0] - p.center_x_mm) < .01 && Math.abs(shape.center[1] - p.center_y_mm) < .01 &&
          Math.abs(shape.rotation - p.rotation_deg) < .01, item.id + ' study displays the full-size exact placement');
      }
      assert(!expected.features.window_face || ['front', 'rear'].includes(expected.features.window_face),
        expected.id + ' does not invent a legal side window');
    }
    for (const [key, box] of [
      ['garage', [0,0,6000,3900]], ['kitchen', [0,9500,2400,2600]], ['stair1f', [2400,9500,3600,4300]],
      ['sideyard', [0,12100,1200,1700]], ['sliding-door', [1200,12100,1200,1700]],
      ['elder', [0,13800,3600,3830]], ['elder-bath', [3600,13800,2400,3000]], ['service', [3600,16800,2400,830]],
    ]) {
      const kept = room(key);
      assert(kept && JSON.stringify(['x_mm','y_mm','w_mm','h_mm'].map(k => kept.geometry[k])) === JSON.stringify(box),
        option.id + ' preserves ' + key + ' coordinates, not a parking/clearance approval');
    }
    assert(!debug.furniture.pendingItems.length && !room('garage').furniture.length && room('garage').outdoor,
      option.id + ' keeps unknown frontage empty and no hidden unresolved furniture');
    for (const [catalog, w, d] of [['queen-bed',1520,1880],['wardrobe-120',1200,600]]) {
      assert(room('elder').furniture.some(i => i.catalog_id === catalog && i.width_mm === w && i.depth_mm === d),
        option.id + ' retains elder bed/storage ' + catalog);
    }
    const turning = room(option.id === 'front-living' ? 'entrance' : 'living');
    assert(turning.features.reserved_mm.some(z => z.kind === 'care-turn' && z.aabb.maxX-z.aabb.minX === 1500 &&
      z.aabb.maxY-z.aabb.minY === 1500), option.id + ' keeps a public-area turning reservation, not accessible approval');
    assert(option.public_bath_verified === null && option.daylight_verified === null && option.plumbing_verified === null,
      option.id + ' retains unknown professional conditions');
    const expectedRoute = option.id === 'bath-front' ? ['dining','entrance','public-bath'] :
      option.id === 'front-living' ? ['entrance','public-bath'] : ['entrance','living','stair1f','elder','elder-bath'];
    assert(option.route.status === 'door-graph-only-not-clearance-proof' &&
      JSON.stringify(option.route.room_keys) === JSON.stringify(expectedRoute) &&
      room(expectedRoute[0]).features.doors.some(d => d.neighbor === null) &&
      expectedRoute.slice(1).every((key, i) => {
        const f = room(expectedRoute[i]).features;
        return [...f.doors, ...f.open_connections].some(d => d.neighbor === 'C:floor-1:' + key);
      }), option.id + ' visitor route uses actual connected openings, not just route text');
    if (option.id !== 'baseline') {
      const wc = room('public-bath'), door = wc.features.doors;
      assert(wc.kind === 'bath' && wc.geometry.w_mm === 2000 && wc.geometry.h_mm === (option.id === 'bath-front' ? 2200 : 2800) &&
        wc.furniture.length === 2 && wc.furniture.some(i => i.catalog_id === 'toilet' && i.width_mm === 450 && i.depth_mm === 700) &&
        wc.furniture.some(i => i.catalog_id === 'vanity-60' && i.width_mm === 600 && i.depth_mm === 450) &&
        door.length === 1 && door[0].neighbor === 'C:floor-1:entrance' && door[0].operation === 'sliding' &&
        door[0].width_mm === 800 && door[0].face === (option.id === 'bath-front' ? 'rear' : 'front') &&
        option.route.avoids_elder_bedroom && !option.route.room_keys.some(k => ['elder','elder-bath'].includes(k)),
      option.id + ' provides only ordinary public fixtures and a bedroom-independent door graph');
      assert(!room('entrance').furniture.length && option.tradeoffs.some(t => t.includes('鞋櫃')),
        option.id + ' discloses original shoe-storage loss instead of shrinking a cabinet');
    }
    if (option.id === 'front-living') {
      assert(room('living').geometry.y_mm === 3900 && room('living').features.window_face === 'front' &&
        room('living').features.window_mm === 1200 && !room('dining').features.window_face && !room('public-bath').features.window_face,
      'front living has only a candidate window; interior dining/WC remain without exterior windows');
    } else {
      assert(!room('living').features.window_face && room('dining').features.window_face === 'front' &&
        room('dining').features.window_mm === 2400 && (option.id === 'baseline' ? !room('public-bath') :
          room('public-bath').features.window_face === 'front' && room('public-bath').features.window_mm === 600),
      option.id + ' retains candidate front windows without inventing independent living daylight');
    }
    const ac = debug.layoutReview.hvac_routes.find(r => r.id === 'C-AC01');
    assert(ac && ac.outdoor_room === 'C:floor-2:balcony2f' && ac.compliance === 'unknown' && ac.manual_source === null &&
      ac.elevation_difference_mm === 1150 && ac.estimated_routed_length_mm ===
        (option.id === 'front-living' ? 10845 : option.id === 'baseline' ? 14325 : 14645) &&
      Object.entries(option.hvac).every(([key, value]) => ac[key] === value),
    option.id + ' recomputes AC quantity without claiming installation approval');
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
        await panel.locator('.shared-plan-open img').scrollIntoViewIfNeeded();
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
          await panel.locator('.shared-plan-viewport').scrollIntoViewIfNeeded();
          await capture('A-html-shared-plan.png');
          const mdf = panel.locator('.mdf-study-review');
          await mdf.locator('summary').click();
          assert(await mdf.getAttribute('data-mdf-study-status') === 'conditional-not-installed' &&
            (await mdf.innerText()).includes('1200×2000mm') && (await mdf.innerText()).includes('機櫃仍只計1台'),
          'A HTML MDF study explains original clearances and no double-counted rack');
          await mdf.locator('[data-mdf-study-toggle]').check();
          await page.waitForFunction(() => {
            const img = document.querySelector('#floor-1 .shared-plan-open img');
            return img.complete && img.naturalWidth > 0 && img.src.endsWith('A_floor-1_mdf-study.svg');
          });
          assert(await panel.getAttribute('data-mdf-study-visible') === 'true', 'A HTML enables non-installed MDF plan overlay');
          await panel.locator('.shared-plan-viewport').scrollIntoViewIfNeeded();
          await capture('A-html-mdf-study.png');
          await mdf.locator('img').scrollIntoViewIfNeeded();
          await page.waitForFunction(() => document.querySelector('.mdf-study-review > img').complete &&
            document.querySelector('.mdf-study-review > img').naturalWidth > 0);
          await capture('A-html-mdf-section.png');
          await mdf.locator('[data-mdf-study-toggle]').uncheck();
          assert(await panel.getAttribute('data-mdf-study-visible') === 'false', 'A HTML returns to current MDF backup, not adoption');
          await mdf.locator('summary').click();
        }
        if (['A', 'B'].includes(building) && floor.id === 'floor-2') {
          await checkPlanReader(panel,building+'-html-2F-readable.png');
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
          await panel.locator('.shared-plan-viewport').scrollIntoViewIfNeeded();
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
        checkMinimalFengshui(building, floor, debug);
        if(debug.layoutReview.id==='abc-rationality-v6-space-efficiency'){
          const allocation=debug.layoutReview.space_efficiency_review.floors.find(a=>a.building===building&&a.floor===floor.id);
          assert(allocation && allocation.professional_acceptance==='unknown', 'space allocation retains per-floor unknown approval');
          if(building==='A'&&floor.id==='floor-2'){
            const master=floor.rooms.find(r=>r.key==='master'),bed2=floor.rooms.find(r=>r.key==='bedroom2');
            assert(master.geometry.w_mm===6000 && master.geometry.h_mm===3280 && bed2.geometry.w_mm===2800 &&
              allocation.circulation_nominal_sqm===(debug.layoutReview.space_efficiency_review.a_followup?20.52:25.08) && allocation.baseline.circulation_nominal_sqm===34.2,
            'A actual rooms recover corridor area without shrinking stairs');
            assert(master.furniture.some(i=>i.catalog_id==='wardrobe-180'&&!i.placement.issues.length), 'A restored 180cm wardrobe is actually accommodated');
            await capture('A-floor-2-space-efficiency.png');
          }
          if(building==='C'&&floor.id==='floor-3'){
            const fitness=floor.rooms.find(r=>r.key==='fitness3f');
            assert(fitness.features.doors.some(d=>d.neighbor==='C:floor-3:front-hall') &&
              !fitness.features.doors.some(d=>d.neighbor==='C:floor-3:master3f'), 'C fitness has a public entrance, not a master-bedroom passage');
            await capture('C-floor-3-space-efficiency.png');
          }
        }
        assert(debug.presentation === 'tour' && debug.state.building === building,
          building + ' ' + floor.id + ' shared tour mode');
        const expectedPending = floor.rooms.flatMap(r => r.furniture).filter(i => i.placement.issues.length).map(i => i.id).sort();
        assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(expectedPending),
          building + ' ' + floor.id + ' pending furniture matches explicit HTML list');
        assert(debug.visibleRooms.length === floor.rooms.length, building + ' ' + floor.id + ' room count');
        assert(floor.width_mm === 6000 && floor.depth_mm === 17630, building + ' fixed proposal frame');
        if (['A', 'B'].includes(building) && floor.id === 'floor-2') checkUpperFloor(building, floor, debug);
        if (building === 'C' && floor.id === 'floor-1') checkCFirstFloor(floor, debug);
        if (building === 'B' && floor.id === 'floor-1') checkBFirstFloor(floor, debug);
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
            assert(care.routes.elder_to_bath.join('|') === 'A:floor-1:flex1|A:floor-1:rear-hall1|A:floor-1:care-passage|A:floor-1:bath1',
              'A night-time bathroom route uses public dry area, not kitchen or MDF');
            checkAMainArcade(floor, debug);
          }
        }
        for (const room of floor.rooms) {
          const actualRoom = debug.tour.rooms.find(r => r.id === room.id);
          assert(Boolean(actualRoom), room.id + ' exists in 3D');
          assert(actualRoom.outdoor === room.outdoor, room.id + ' indoor/outdoor use matches HTML');
          assert(actualRoom.base_mm === floor.base_mm && actualRoom.height_mm === floor.height_mm,
            room.id + ' storey base and height match the shared HTML plan');
          if (room.outdoor) {
            assert(room.furniture.every(item => !['bed', 'sofa', 'l-sofa', 'cabinet', 'tv-console', 'wall-tv'].includes(item.shape) &&
              item.category !== 'network'), room.id + ' no indoor furniture incorrectly placed outdoors');
          }
          assert(JSON.stringify(actualRoom.features) === JSON.stringify(room.features), room.id + ' full architecture/AC metadata matches HTML');
          if (room.features.stair_geometry) {
            const stair = actualRoom.features.stair_geometry;
            assert(stair.type === 'two-flight-u-proposal' && stair.fits_reserved_box &&
              stair.risers === (building === 'A' && floor.id === 'floor-1' ? 24 : 18) &&
              !actualRoom.features.stair_geometry_verified && actualRoom.architectureParts > (stair.connects_to_next_storey === false ? 0 : 18),
            room.id + ' rendered U stairs remain unverified');
            if (building === 'A') {
              const landing = actualRoom.features.shared_landing_mm;
              assert(floor.base_mm === ({'floor-1':0,'floor-2':4000,'floor-3':7000,'floor-4':10000})[floor.id] &&
                floor.height_mm === (floor.id === 'floor-1' ? 4000 : 3000) && stair.flight_width_mm === 900 &&
                stair.tread_mm === 260 && stair.departure_offset_mm === 0 && stair.shared_front_landing &&
                landing.x_mm === 80 && landing.y_mm === 4950 && landing.w_mm === 2000 && landing.h_mm === 1000 &&
                !actualRoom.features.doors.length && actualRoom.features.open_connections.length === 1 &&
                actualRoom.features.open_connections[0].face === 'front',
              room.id + ' keeps the current stacked shared platform, not a door into elevated flights');
            }
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
            for (const [key, name] of [['arcade', 'arcade'], ['flex1', 'elder'], ['bath1', 'care-bath']]) {
              await page.locator('#scope-rooms [data-room="A:floor-1:' + key + '"]').click();
              await page.locator('#focus-room').click();
              const focused = await page.evaluate(() => window.__htmlModel3dDebug());
              assert(focused.roomCloseup && focused.state.room === 'A:floor-1:' + key && focused.visibleRooms.length === floor.rooms.length,
                'A ' + name + ' closeup retains entire floor geometry');
              if (key === 'arcade') {
                checkCameraFraming(focused, 'A:floor-1:arcade');
                assert((await page.locator('#info').innerText()).includes('騎樓3.9m') &&
                  !focused.furniture.shapes.some(i => i.visible && i.id.startsWith('A:floor-1:arcade:')),
                'A arcade closeup visibly labels the reserved frontage, not a parking or furniture room');
              } else assert((await page.locator('#info').innerText()).includes('150cm'),
                'A ' + name + ' explains care turning reservation');
              await capture('A-3D-' + name + '-closeup.png');
              await page.locator('#room-overview').click();
            }
            await page.locator('#scope-rooms [data-room="A:floor-1:stair-door"]').click();
            await page.locator('#focus-room').click();
            const beforeMdf = await page.evaluate(() => window.__htmlModel3dDebug());
            await page.locator('#mdf-study').check();
            const mdf = await page.evaluate(() => window.__htmlModel3dDebug());
            checkMdfStudy(mdf, floor);
            checkCameraFraming(mdf, 'A:floor-1:stair-door');
            assert(JSON.stringify(mdf.furniture.shapes) === JSON.stringify(beforeMdf.furniture.shapes) &&
              JSON.stringify(mdf.tour.rooms) === JSON.stringify(beforeMdf.tour.rooms),
            'A MDF study changes no installed rack, stair, opening, furniture or care-room geometry');
            assert(page.url().includes('mdf=study') && await page.locator('#mdf-study-note').isVisible(),
              'A MDF study shares through hash and visibly warns that maintenance is unresolved');
            await capture('A-3D-mdf-study.png');
            await page.reload({ waitUntil: 'load' });
            await page.waitForFunction(() => window.__htmlModel3dDebug()?.mdfStudy.active);
            checkMdfStudy(await page.evaluate(() => window.__htmlModel3dDebug()), floor);
            await page.locator('#mdf-study').uncheck();
            assert(!(await page.evaluate(() => window.__htmlModel3dDebug())).mdfStudy.visible.length,
              'A MDF study switches off without adopting or deleting the backup');
            await page.locator('#room-overview').click();
          } else if (building === 'B') {
            for (const key of ['shrine','entry','storage']) {
              const id='B:floor-1:'+key;
              await page.locator('#scope-rooms [data-room="'+id+'"]').click();
              await page.locator('#focus-room').click();
              const focused=await page.evaluate(()=>window.__htmlModel3dDebug());
              checkBFirstFloor(floor,focused);
              assert((await page.locator('#info').innerText()).includes(key==='shrine'?'屋主家規':'裝桿'),
                'B '+key+' visibly explains owner ritual preference or unverified pole transport');
              if (key==='shrine') assert(await page.locator('.nav-label.entry').filter({hasText:'中軸祭祀門'}).count()===1,
                'B shrine visibly labels its owner-required front ritual door');
              await capture('B-3D-'+key+'-flow-closeup.png');
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
              checkCameraFraming(focused, id);
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
              const fixtureCount = floor.rooms.find(r => r.id === id).furniture.filter(i => !i.placement.issues.length).length;
              checkRoomCutaway(focused, id, fixtureCount);
              checkCameraFraming(focused, id);
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
              if (key === 'hall2') assert((await page.locator('#info').innerText()).includes(floor.rooms.find(r=>r.key==='hall2').features.storage_resolution?'容量不減':'不能同時當通道'),
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
        const fengshuiRoom = ({'A:floor-1':'kitchen','B:floor-2':'living2','B:floor-3':'guest3','C:floor-3':'master3f'})[building+':'+floor.id];
        if (fengshuiRoom && debug.layoutReview.fengshui_minimal) {
          const id = building + ':' + floor.id + ':' + fengshuiRoom;
          await page.locator('#scope-rooms [data-room="' + id + '"]').click();
          await page.locator('#focus-room').click();
          const focused = await page.evaluate(() => window.__htmlModel3dDebug());
          checkCameraFraming(focused, id);
          assert(focused.roomCloseup && focused.visibleRooms.length === floor.rooms.length,
            id + ' fengshui closeup preserves all floor rooms');
          assert((await page.locator('#info').innerText()).includes('風水最小修改／待決'),
            id + ' closeup shows the partial/pending fengshui limitation');
          await page.locator('#info').scrollIntoViewIfNeeded();
          await capture(building + '-3D-' + floor.id + '-' + fengshuiRoom + '-fengshui-closeup.png');
          await page.locator('#room-overview').click();
        }
      }
    }
    for (const key of ['floors', 'rooms', 'items']) assert(counts[key] === expectedCounts[key], 'all expected ' + key + ' checked');
    await page.locator('#scope-floors [data-floor="floor-1"]').click();
    await page.locator('#view-front').click();
    // Native SVG inspection avoids UNC file object/image DOM restrictions.
    // Validate actual font bounds, not the generator's estimated rectangles.
    await page.goto(baseUrl + 'structured/candidates/furniture-plans/A_floor-2.svg');
    await page.evaluate(() => document.fonts.ready.then(() => true));
    checkAHvacLabelBounds(sharedFloors['A:floor-2'], await page.evaluate(collectAHvacLabelBounds));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(baseUrl+'AbuildingView.html',{waitUntil:'load'});
    await selectHtmlFloor('A','floor-2');
    await checkPlanReader(page.locator('#floor-2 .shared-furniture-plan'),'A-html-mobile-2F-readable.png');
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=A&floor=floor-1&room=A%3Afloor-1%3Astair-door&view=front&focus=room&mdf=study', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__htmlModel3dDebug()?.mdfStudy.active);
    await collapseMobilePanel();
    const mobileMdf = await page.evaluate(() => window.__htmlModel3dDebug());
    checkMdfStudy(mobileMdf, sharedFloors['A:floor-1']);
    checkCameraFraming(mobileMdf, 'A:floor-1:stair-door');
    assert(await page.locator('#mdf-study-note').isVisible(), 'A mobile MDF caveat remains visible with sidebar collapsed');
    await capture('A-3D-mobile-mdf-study.png');
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front', { waitUntil: 'load' });
    await page.waitForFunction(() => {
      const debug = window.__htmlModel3dDebug?.();
      return debug?.state.building === 'C' && debug.state.floor === 'floor-1' && !debug.mdfStudy.active;
    });
    // This is hash navigation on the same viewer, not a fresh document. The
    // preceding MDF closeup deliberately collapsed the mobile sidebar.
    await expandMobilePanel();
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
    checkCameraFraming(mobileLiving, 'C:floor-1:living');
    assert(mobileLiving.cameraFraming.routes.some(r => r.id === 'C-AC01' && r.visible && !r.cameraFit && r.points.length >= 6),
      'C lounge keeps its actual remote HVAC route rendered without inflating the closeup');
    assert(mobileLiving.focusedScreenBounds.every(([x,y]) => Math.abs(x)<1 && Math.abs(y)<1),
      'C mobile lounge closeup fits real geometry');
    await capture('C-3D-mobile-living-closeup.png');
    await page.setViewportSize({ width: 844, height: 390 });
    await collapseMobilePanel();
    const landscapeLiving = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(landscapeLiving, 'C:floor-1:living', 4);
    checkCameraFraming(landscapeLiving, 'C:floor-1:living');
    await capture('C-3D-landscape-living-closeup.png');
    await page.setViewportSize({ width: 390, height: 844 });await collapseMobilePanel();
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
    checkCameraFraming(closeup, 'C:floor-1:elder');
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
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=A&floor=floor-1&room=A%3Afloor-1%3Aliving&view=front&focus=room', { waitUntil: 'load' });
    await page.waitForFunction(() => window.__htmlModel3dDebug().roomCloseup &&
      window.__htmlModel3dDebug().state.room === 'A:floor-1:living');
    await collapseMobilePanel();
    const mobileALiving = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(mobileALiving, 'A:floor-1:living', 4);
    checkCameraFraming(mobileALiving, 'A:floor-1:living');
    await capture('A-3D-mobile-living-closeup.png');
    await page.setViewportSize({ width: 844, height: 390 });
    await collapseMobilePanel();
    const landscapeALiving = await page.evaluate(() => window.__htmlModel3dDebug());
    checkRoomCutaway(landscapeALiving, 'A:floor-1:living', 4);
    checkCameraFraming(landscapeALiving, 'A:floor-1:living');
    assert(landscapeALiving.cameraFraming.autoFit.theta === .85,
      'A landscape closeup looks toward the side-mounted TV instead of enlarging its body');
    assert(JSON.stringify(landscapeALiving.furniture.shapes) === JSON.stringify(mobileALiving.furniture.shapes) &&
      JSON.stringify(landscapeALiving.visibleRooms) === JSON.stringify(mobileALiving.visibleRooms),
    'A landscape readability changes the camera only, retaining every room and full-size product');
    await capture('A-3D-landscape-living-closeup.png');
    await page.setViewportSize({ width: 390, height: 844 });
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
    checkCameraFraming(mobileBath, 'A:floor-2:master-bath');
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

    // C1F comparisons use one browser/page and the same scene renderer. They
    // never increment the main ABC counts or mutate the main design manifest.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(baseUrl + 'CbuildingView.html');
    await selectHtmlFloor('C', 'floor-1');
    const studyLink = page.locator('#floor-1 .c1f-options-link');
    assert(await studyLink.count() === 1, 'C1F main HTML exposes one explicitly unadopted comparison link');
    await studyLink.click();
    await page.waitForFunction(() => typeof window.__c1fOptionsDebug === 'function');
    const study = await page.evaluate(() => window.HOUSE_C1F_OPTIONS);
    assert(study.status === 'comparison-only-not-adopted' && study.active_design === 'baseline' &&
      study.options.map(o => o.id).join(',') === 'baseline,bath-front,front-living', 'study leaves baseline active');
    for (const option of study.options) {
      await page.goto(baseUrl + 'structured/candidates/c1f-options.html#scheme=baseline');
      await page.waitForFunction(() => typeof window.__c1fOptionsDebug === 'function');
      await page.locator('#scheme').selectOption(option.id);
      const selected = await page.evaluate(() => window.__c1fOptionsDebug());
      assert(selected.id === option.id && selected.activeDesign === 'baseline' &&
        selected.status === 'comparison-only-not-adopted', option.id + ' comparison selector changes only the study');
      assert((await page.locator('#plan').getAttribute('data')) === 'c1f-options/' + option.id + '.svg' &&
        (await page.locator('#open-3d').getAttribute('href')).includes('?scheme=' + option.id), option.id + ' plan/3D links retain scheme identity');
      assert(await page.locator('canvas').count() === 0, '2D comparison page starts no WebGL scene');
      await pageHealth();
      await capture('C-study-' + option.id + '-html.png');
      // Inspect the native SVG document: avoids relying on cross-origin
      // object.contentDocument privileges on Windows/UNC file URLs.
      await page.goto(baseUrl + 'structured/candidates/c1f-options/' + option.id + '.svg');
      checkCStudySvg(option, await page.evaluate(collectCStudySvg));
      await page.goBack();
      await page.waitForFunction(id => typeof window.__c1fOptionsDebug === 'function' &&
        window.__c1fOptionsDebug().id === id, option.id);
      await page.locator('#open-3d').click();
      await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
      assert((await page.locator('body').getAttribute('data-study-option')) === option.id &&
        await page.locator('canvas').count() === 1 && !(await page.locator('#renderer-fallback').isVisible()),
      option.id + ' opens one live 3D scene, not its fallback');
      checkCOption(option, await page.evaluate(() => window.__htmlModel3dDebug()));
      await capture('C-study-' + option.id + '-3D.png');
      if (option.public_bath_key) {
        await page.locator('#scope-rooms [data-room="C:floor-1:public-bath"]').click();
        await page.locator('#focus-room').click();
        checkRoomCutaway(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath', 2);
        checkCameraFraming(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath');
        await capture('C-study-' + option.id + '-public-bath-closeup.png');
        await page.locator('#room-overview').click();
      }
      await page.locator('#study-scheme').selectOption('baseline');
      await page.waitForURL(url => url.searchParams.get('scheme') === 'baseline');
      await page.waitForFunction(() => document.body.getAttribute('data-study-option') === 'baseline' &&
        typeof window.__htmlModel3dDebug === 'function');
      checkCOption(study.options[0], await page.evaluate(() => window.__htmlModel3dDebug()));
    }
    for (const query of ['', '?scheme=not-a-scheme']) {
      await page.goto(baseUrl + 'structured/candidates/c1f-options-3d.html' + query + '#mode=tour&building=C&floor=floor-1&view=front');
      await page.waitForURL(url => url.searchParams.get('scheme') === 'baseline');
      await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
      checkCOption(study.options[0], await page.evaluate(() => window.__htmlModel3dDebug()));
      assert(await page.locator('canvas').count() === 1, 'bare/invalid file entry redirects before creating a second scene');
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(baseUrl + 'structured/candidates/c1f-options.html#scheme=front-living');
    await page.waitForFunction(() => typeof window.__c1fOptionsDebug === 'function');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      'mobile comparison keeps controls, plan and table inside the viewport');
    for (const width of [360, 390, 430]) {
      await page.setViewportSize({ width, height: 844 });await checkMobileComparisonControls();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await capture('C-study-mobile-front-living-html.png');
    await page.reload();
    assert((await page.locator('#scheme').inputValue()) === 'front-living', 'mobile reload preserves selected study');
    await page.locator('#reset').click();
    assert((await page.locator('#scheme').inputValue()) === 'baseline', 'mobile reset returns to baseline');
    await page.locator('#scheme').selectOption('front-living');
    await page.locator('#open-3d').click();
    await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
    await collapseMobilePanel();
    checkCOption(study.options[2], await page.evaluate(() => window.__htmlModel3dDebug()));
    assert(await page.locator('#study-stage-note').isVisible(), 'mobile collapsed panel still marks study as unadopted');
    await capture('C-study-mobile-front-living-3D.png');
    await expandMobilePanel();
    await page.locator('#scope-rooms [data-room="C:floor-1:public-bath"]').click();
    await page.locator('#focus-room').click();
    await collapseMobilePanel();
    checkRoomCutaway(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath', 2);
    checkCameraFraming(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath');
    await capture('C-study-mobile-public-bath-closeup.png');
    await page.setViewportSize({ width: 844, height: 390 });
    await collapseMobilePanel();
    checkRoomCutaway(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath', 2);
    checkCameraFraming(await page.evaluate(() => window.__htmlModel3dDebug()), 'C:floor-1:public-bath');
    await capture('C-study-landscape-public-bath-closeup.png');
    // Independent parcel/arcade capacity comparison: selection never adopts a
    // layout. All four levels share the modified core/elevation dataset.
    const checkCapacityOption = (option, building, floor, debug) => {
      const id = building.id, capacity = option.capacity[id];
      assert(debug.presentation === 'tour' && debug.state.building === id && debug.state.floor === floor.id,
        option.id + ' ' + id + ' ' + floor.id + ' is the selected capacity scene');
      assert(JSON.stringify(debug.visibleRooms.slice().sort()) === JSON.stringify(floor.rooms.map(r => r.id).sort()),
        'capacity scene retains exact room IDs, including care rooms');
      const pending = floor.rooms.flatMap(r => r.furniture).filter(i => i.placement.issues.length).map(i => i.id).sort();
      assert(JSON.stringify(debug.furniture.pendingItems.slice().sort()) === JSON.stringify(pending),
        'capacity unresolved furniture remains pending at ordinary dimensions');
      assert(capacity.legal_building_area_sqm === null && capacity.arcade_net_height_verified === null &&
        capacity.verified_parking_spaces === null && capacity.displayed_cars === 0 &&
        capacity.coverage_sensitivity.every(r => r.legal_result === 'unknown'), 'capacity has no false regulatory or parking approval');
      for (const room of floor.rooms) {
        const actual = debug.tour.rooms.find(r => r.id === room.id);
        assert(actual && JSON.stringify(actual.geometry) === JSON.stringify(room.geometry), room.id + ' exact capacity geometry');
        if (room.features.stair_geometry) {
          const stair = actual.features.stair_geometry;
          assert(JSON.stringify(stair) === JSON.stringify(room.features.stair_geometry) && stair.fits_reserved_box &&
            JSON.stringify(actual.features.stair_footprint_mm) === JSON.stringify(room.features.stair_footprint_mm),
          room.id + ' uses shared well, real riser count and sufficient reserved depth');
          if (option.id !== 'baseline') assert(stair.risers === (floor.id === 'floor-1' ? 24 : 18) &&
            actual.features.stair_footprint_mm.h_mm === 4970 && stair.middle_landing_mm + stair.run_mm + stair.landing_mm === 4970,
          '4m first-storey stair and upper arrival are coherently recalculated');
        }
        for (const item of room.furniture) {
          const actualItem = debug.furniture.shapes.find(i => i.id === item.id);
          assert(actualItem && actualItem.width === item.width_mm && actualItem.depth === item.depth_mm &&
            actualItem.height === item.height_mm && actualItem.visible === !item.placement.issues.length,
          item.id + ' preserves product dimensions and honest pending visibility');
        }
      }
      assert(!debug.furniture.shapes.some(i => i.visible && ['car','motorcycle'].includes(i.shape)), 'arcade not credited as private parking');
      if (floor.id === 'floor-1' && option.id !== 'baseline') {
        assert(floor.width_mm === 6000 && floor.depth_mm === (option.id === 'arcade32' ? 17630 : id === 'A' ? 22430 : 18530),
          'capacity cannot enlarge a nominal 32-ping parcel or borrow a neighbouring parcel');
        const frontage = floor.rooms.find(r => ['garage','arcade'].includes(r.key));
        assert(frontage && frontage.outdoor && !frontage.furniture.length && frontage.geometry.y_mm === 0 &&
          frontage.geometry.h_mm === 3900 && !frontage.features.frontage_study, 'capacity frontage stays fully clear without private-garden assumptions');
        for (const key of id === 'A' ? ['flex1','bath1'] : id === 'C' ? ['elder','elder-bath'] : []) {
          const room = floor.rooms.find(r => r.key === key);
          assert(room && room.furniture.length >= 2 && room.furniture.every(i => !i.placement.issues.length),
            id + ' elder sleeping/bathing cannot silently disappear to manufacture a fit');
          if (['flex1','elder'].includes(key)) assert(room.furniture.some(i => i.shape === 'bed' && i.width_mm === 1520 && i.depth_mm === 1880) &&
            room.furniture.some(i => i.catalog_id === 'wardrobe-120' && i.width_mm === 1200 && i.depth_mm === 600), 'care room has real normal bed/wardrobe, not matching tiny renderers');
          else assert(['shower','toilet','vanity'].every(shape => room.furniture.some(i => i.shape === shape)), 'ground care bathing retains all three actual equipment roles');
        }
        if (option.id === 'arcade32' && ['A','C'].includes(id)) assert(capacity.ground_program_status === 'conflicts-remain',
          id + ' restricted proposal is explicitly a conflict, not a chosen solution');
      }
      assert(debug.layoutReview.hvac_routes.every(r => r.compliance === 'unknown' && r.model === null), 'modified AC elevations remain unverified');
    };
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(baseUrl + 'structured/candidates/arcade-capacity.html');
    await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
    const capacityStudy = await page.evaluate(() => window.HOUSE_ARCADE_CAPACITY);
    assert(capacityStudy.active_design === 'main-a32-arcade-v1' && capacityStudy.status === 'comparison-only-not-adopted' &&
      capacityStudy.reference_review === 'inputs/references/abc-before-a-arcade.json' &&
      Object.values(capacityStudy.professional_status).every(s => s === 'unknown'), 'ABC capacity study does not adopt or approve a design');
    assert((await page.title()).includes('32地坪') && page.url().includes('arcade-capacity.html'), 'capacity page identity');
    for (const bid of ['A','B','C']) {
      await page.goto(baseUrl + bid + 'buildingView.html');
      const link = page.locator('.arcade-capacity-link');
      assert(await link.count() === 1 && (await link.innerText()).includes('未採用'), bid + ' HTML exposes one unadopted capacity entry');
      await link.click();await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
      assert((await page.evaluate(() => window.__arcadeCapacityDebug())).building === bid, 'HTML capacity link retains its own building');
    }
    for (const option of capacityStudy.options) {
      for (const building of option.plans.buildings) {
        await page.goto(baseUrl + 'structured/candidates/arcade-capacity.html#scheme=' + option.id + '&building=' + building.id + '&floor=floor-1');
        await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
        for (const floor of building.floors) {
          await page.locator('#floor').selectOption(floor.id);
          const selected = await page.evaluate(() => window.__arcadeCapacityDebug());
          assert(selected.id === option.id && selected.building === building.id && selected.floor === floor.id &&
            selected.activeDesign === 'main-a32-arcade-v1' && selected.capacity.legal_building_area_sqm === null,
          'capacity HTML selectors keep option/building/floor and unknown approvals');
          assert(await page.locator('canvas').count() === 0 &&
            (await page.locator('#plan').getAttribute('data')) === 'arcade-capacity/' + floor.plan_file,
          'capacity HTML uses native same-source SVG, no WebGL allocation');
        }
        await page.locator('#floor').selectOption('floor-1');
        await pageHealth();
        if (option.id === 'arcade32') await capture('capacity-' + building.id + '-32ping-html.png');
        await page.locator('#open-3d').click();
        await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
        assert((await page.locator('body').getAttribute('data-study-option')) === option.id &&
          await page.locator('canvas').count() === 1 && !(await page.locator('#renderer-fallback').isVisible()), 'capacity opens exactly one live 3D scene');
        for (const floor of building.floors) {
          await page.locator('#scope-floors [data-floor="' + floor.id + '"]').click();
          await page.waitForFunction(fid => window.__htmlModel3dDebug().state.floor === fid, floor.id);
          checkCapacityOption(option, building, floor, await page.evaluate(() => window.__htmlModel3dDebug()));
          if (floor.id === 'floor-1') {
            await pageHealth();
            await capture('capacity-' + option.id + '-' + building.id + '-3D.png');
          }
        }
        await page.locator('#study-plan-link').click();
        await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
        const returned = await page.evaluate(() => window.__arcadeCapacityDebug());
        assert(returned.id === option.id && returned.building === building.id && returned.floor === 'floor-4', 'return link retains exact capacity option/building/floor');
      }
    }
    // File URL bootstrap and failed-render fallback are real navigation,
    // never an untested history query rewrite or a different scheme's plan.
    for (const query of ['', '?scheme=invalid']) {
      await page.goto(baseUrl + 'structured/candidates/arcade-capacity-3d.html' + query + '#building=C&floor=floor-1');
      await page.waitForURL(url => url.searchParams.get('scheme') === 'arcade32');
      await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
      const option = capacityStudy.options[1], building = option.plans.buildings[2];
      checkCapacityOption(option, building, building.floors[0], await page.evaluate(() => window.__htmlModel3dDebug()));
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(baseUrl + 'structured/candidates/arcade-capacity.html#scheme=room-first&building=A&floor=floor-1');
    await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'mobile capacity table/controls stay inside viewport');
    for (const width of [360, 390, 430]) {
      await page.setViewportSize({ width, height: 844 });await checkMobileComparisonControls();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#scheme').selectOption('arcade32');await page.locator('#building').selectOption('C');
    await page.reload();
    assert((await page.locator('#scheme').inputValue()) === 'arcade32' && (await page.locator('#building').inputValue()) === 'C', 'mobile capacity reload preserves selection');
    await pageHealth();
    await capture('capacity-mobile-C-html.png');
    await page.locator('#open-3d').click();await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
    await collapseMobilePanel();
    checkCapacityOption(capacityStudy.options[1], capacityStudy.options[1].plans.buildings[2], capacityStudy.options[1].plans.buildings[2].floors[0],
      await page.evaluate(() => window.__htmlModel3dDebug()));
    assert(await page.locator('#study-stage-note').isVisible(), 'mobile capacity caveat survives collapsed controls');
    checkCameraFraming(await page.evaluate(() => window.__htmlModel3dDebug()));
    await pageHealth();
    await capture('capacity-mobile-C-3D.png');
    await page.setViewportSize({ width: 844, height: 390 });await collapseMobilePanel();
    checkCameraFraming(await page.evaluate(() => window.__htmlModel3dDebug()));
    await capture('capacity-landscape-C-3D.png');
    await expandMobilePanel();await page.locator('#study-scheme').selectOption('room-first');
    await page.waitForURL(url => url.searchParams.get('scheme') === 'room-first');
    await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
    checkCapacityOption(capacityStudy.options[2], capacityStudy.options[2].plans.buildings[2], capacityStudy.options[2].plans.buildings[2].floors[0],
      await page.evaluate(() => window.__htmlModel3dDebug()));
    await page.locator('#study-plan-link').click();await page.waitForFunction(() => typeof window.__arcadeCapacityDebug === 'function');
    await page.locator('#reset').click();
    assert((await page.locator('#scheme').inputValue()) === 'arcade32' && (await page.locator('#building').inputValue()) === 'A', 'capacity reset returns to default comparison, never adopts it');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=B&floor=floor-1&view=front');
    await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
    await expandMobilePanel();
    for (const key of ['shrine','storage']) {
      await expandMobilePanel();
      await page.locator('#scope-rooms [data-room="B:floor-1:'+key+'"]').click();
      await page.locator('#focus-room').click();
      await collapseMobilePanel();
      const focused=await page.evaluate(()=>window.__htmlModel3dDebug());
      checkBFirstFloor(sharedFloors['B:floor-1'],focused);
      checkCameraFraming(focused,'B:floor-1:'+key);
      assert(focused.visibleRooms.length===sharedFloors['B:floor-1'].rooms.length,
        'mobile B '+key+' retains the entire floor and inventory, not a hidden-room illusion');
      await pageHealth();
      await capture('B-3D-mobile-'+key+'-flow.png');
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(baseUrl + 'structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front');
    await page.waitForFunction(() => typeof window.__htmlModel3dDebug === 'function');
    checkCFirstFloor(sharedFloors['C:floor-1'], await page.evaluate(() => window.__htmlModel3dDebug()));
    assert(!(await page.locator('body').getAttribute('data-study-option')), 'return to main 3D never adopts a comparison');
    await pageHealth();
    // B strict family constraints and C care-suite alternatives are isolated
    // comparisons: same data -> SVG -> one actual scene, never main adoption.
    await page.goto(baseUrl+'structured/candidates/bc-options.html');
    await page.waitForFunction(()=>!!window.HOUSE_BC_OPTIONS);
    const bcStudy=await page.evaluate(()=>window.HOUSE_BC_OPTIONS);
    assert(bcStudy.status==='comparison-only-not-adopted' && bcStudy.active_design==='baseline' &&
      bcStudy.options.map(o=>o.id).join(',')==='b-baseline,b-strict,c-baseline,c-side-bed,c-wet-stack', 'BC HTML loads all five unadopted comparisons');
    assert((await page.title()).includes('未採用'), 'BC HTML page identity states not adopted');
    await pageHealth();
    for(const [bid,scheme] of [['B','b-strict'],['C','c-side-bed']]) {
      await page.goto(baseUrl+bid+'buildingView.html');
      const link=page.locator('.bc-constraints-link');
      assert(await link.count()===1, bid+' main HTML exposes its comparison without replacing the main plan');
      await link.click();await page.waitForFunction(()=>!!window.HOUSE_BC_OPTIONS);
      assert(page.url().endsWith('bc-options.html#'+scheme), bid+' HTML-to-comparison retains its recommended scheme');
    }
    for(const option of bcStudy.options) {
      const floor=option.plans.floors[0];
      await page.goto(baseUrl+'structured/candidates/bc-options.html#'+option.id);
      const section=page.locator('section[id="'+option.id+'"]');
      assert((await section.innerText()).includes('未採用'), option.id+' HTML displays adoption warning');
      for(const f of option.plans.floors) {
        await page.goto(baseUrl+'structured/candidates/bc-options/'+f.plan_file);
        assert(await page.locator('svg').getAttribute('data-study-option')===option.id &&
          await page.locator('svg').getAttribute('data-study-status')===option.status, option.id+' '+f.id+' real SVG identity');
        const svgRooms=await page.locator('g[data-room-id]').evaluateAll(nodes=>nodes.map(n=>({id:n.getAttribute('data-room-id'),
          geometry:Object.fromEntries(['x','y','w','h'].map(k=>[k+'_mm',Number(n.getAttribute('data-'+k+'-mm'))]))})));
        assert(JSON.stringify(svgRooms)===JSON.stringify(f.rooms.map(r=>({id:r.id,geometry:r.geometry}))), option.id+' '+f.id+' loaded SVG has exact room bounds');
      }
      await page.goto(baseUrl+'structured/candidates/bc-options.html#'+option.id);
      await page.locator('section[id="'+option.id+'"] a[href*="bc-options-3d.html"]').first().click();
      await page.waitForFunction(()=>typeof window.__htmlModel3dDebug==='function' && window.__htmlModel3dDebug().cameraFraming.ready);
      assert((await page.title()).includes('未採用') && await page.locator('#canvas').count()===1 &&
        await page.locator('body').getAttribute('data-study-option')===option.id, option.id+' HTML opens one identified comparison renderer');
      checkBcPresentation(await page.evaluate(collectBcPresentation),option,true);
      if (['b-strict','c-side-bed'].includes(option.id)) await capture('bc-'+option.id+'-controls-desktop.png');
      for(const f of option.plans.floors) {
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();
        await page.waitForFunction(id=>window.__htmlModel3dDebug().state.floor===id,f.id);
        checkBcOption(option,f,await page.evaluate(()=>window.__htmlModel3dDebug()));
        checkBcPresentation(await page.evaluate(collectBcPresentation),option,true);
        if((option.id==='b-strict' && ['floor-1','floor-2','floor-3'].includes(f.id)) ||
          (option.id==='c-wet-stack' && ['floor-2','floor-3'].includes(f.id))) await capture('bc-'+option.id+'-'+f.id+'-desktop.png');
      }
      if(option.id==='c-side-bed') {
        await page.locator('#scope-floors [data-floor="floor-1"]').click();
        await page.locator('#scope-rooms [data-room="C:floor-1:elder"]').click();
        await page.locator('#focus-room').click();
        checkBcOption(option,floor,await page.evaluate(()=>window.__htmlModel3dDebug()));
        checkBcPresentation(await page.evaluate(collectBcPresentation),option,true);
        await capture('bc-c-side-bed-elder-desktop.png');
      }
      await pageHealth();
      await page.locator('#study-plan-link').click();await page.waitForFunction(()=>!!window.HOUSE_BC_OPTIONS);
      assert(page.url().endsWith('bc-options.html#'+option.id), option.id+' return link keeps comparison, not adopted main room');
    }
    for(const query of ['', '?scheme=invalid']) {
      await page.goto(baseUrl+'structured/candidates/bc-options-3d.html'+query+'#building=C&floor=floor-1');
      await page.waitForFunction(()=>typeof window.__htmlModel3dDebug==='function' && window.__htmlModel3dDebug().bcOption?.id==='b-strict');
      assert(page.url().includes('?scheme=b-strict') && (await page.evaluate(()=>window.__htmlModel3dDebug().state.building))==='B',
        'BC missing/invalid query uses real file navigation and correct B scope');
      checkBcPresentation(await page.evaluate(collectBcPresentation),bcStudy.options.find(o=>o.id==='b-strict'),true);
    }
    await page.setViewportSize({width:390,height:844});
    await expandMobilePanel();
    await page.locator('#study-scheme').selectOption('c-side-bed');
    await page.waitForFunction(()=>typeof window.__htmlModel3dDebug==='function' && window.__htmlModel3dDebug().bcOption?.id==='c-side-bed');
    for(const [scheme,bid,key] of [['c-side-bed','C','elder'],['b-strict','B','shrine']]) {
      const option=bcStudy.options.find(o=>o.id===scheme);
      await expandMobilePanel();
      if(await page.locator('#study-scheme').inputValue()!==scheme) {
        await page.locator('#study-scheme').selectOption(scheme);
        await page.waitForFunction(id=>typeof window.__htmlModel3dDebug==='function' && window.__htmlModel3dDebug().bcOption?.id===id,scheme);
        await expandMobilePanel();
      }
      await page.locator('#study-scheme').scrollIntoViewIfNeeded();
      checkBcPresentation(await page.evaluate(collectBcPresentation),option,true);
      await capture('bc-'+scheme+'-controls-mobile.png');
      await page.locator('#scope-rooms [data-room="'+bid+':floor-1:'+key+'"]').click();
      await page.locator('#focus-room').click();await collapseMobilePanel();
      const debug=await page.evaluate(()=>window.__htmlModel3dDebug());
      checkBcOption(option,option.plans.floors[0],debug);
      checkCameraFraming(debug,bid+':floor-1:'+key);
      checkBcPresentation(await page.evaluate(collectBcPresentation),option);
      await pageHealth();await capture('bc-'+scheme+'-'+key+'-mobile.png');
      await page.reload({waitUntil:'load'});
      await page.waitForFunction(id=>typeof window.__htmlModel3dDebug==='function' && window.__htmlModel3dDebug().bcOption?.id===id,scheme);
      assert((await page.evaluate(()=>window.__htmlModel3dDebug().selected))===bid+':floor-1:'+key,
        'mobile '+scheme+' reload retains selected scheme and room');
      await collapseMobilePanel();
      checkBcPresentation(await page.evaluate(collectBcPresentation),option);
      checkBcOption(option,option.plans.floors[0],await page.evaluate(()=>window.__htmlModel3dDebug()));
      await page.setViewportSize({width:844,height:390});
      await page.waitForFunction(()=>{
        const stage=document.getElementById('stage'),canvas=document.getElementById('canvas');
        const ratio=Math.min(window.devicePixelRatio||1,2);
        return window.__htmlModel3dDebug().cameraFraming.ready &&
          Math.abs(canvas.width-stage.clientWidth*ratio)<=1 && Math.abs(canvas.height-stage.clientHeight*ratio)<=1;
      });
      const landscapeBc=await page.evaluate(()=>window.__htmlModel3dDebug());
      checkBcOption(option,option.plans.floors[0],landscapeBc);
      checkCameraFraming(landscapeBc,bid+':floor-1:'+key);
      checkBcPresentation(await page.evaluate(collectBcPresentation),option);
      await pageHealth();await capture('bc-'+scheme+'-'+key+'-landscape.png');
      await page.setViewportSize({width:390,height:844});
    }
    await page.setViewportSize({width:1440,height:900});
    await page.goto(baseUrl+'structured/candidates/model3d.html#mode=tour&building=B&floor=floor-1');
    await page.waitForFunction(()=>typeof window.__htmlModel3dDebug==='function');
    const mainAfterBc=await page.evaluate(()=>window.__htmlModel3dDebug());
    assert(mainAfterBc.bcOption===null && mainAfterBc.furniture.items===expectedCounts.items &&
      !(await page.locator('body').getAttribute('data-study-option')), 'BC selection never adopts into ABC main');
    assert(!(await page.locator('body').evaluate(node=>node.classList.contains('bc-study'))) &&
      await page.locator('#study-stage-note').count()===0 && await page.locator('#tour-actions').isVisible() &&
      await page.locator('#furniture-start').isVisible() && await page.locator('#presentation-mode').isVisible(),
      'returning to ABC main restores its original controls without comparison-only styles');
    const unexpected = messages.filter(message => !(message.level === 'warning' &&
      (message.text.includes('GPU stall due to ReadPixels') ||
        message.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(unexpected.length === 0, 'no unexpected console errors, warnings or page errors');
    return { marker: 'house-windows-cli-qa', status: 'passed', counts, checks, messages, screenshots,
      limitation: 'Automated browser checks only; screenshots still need visual review. Not professional design or regulatory approval.' };
  } catch (error) {
    const failureUrl = page.url();
    await capture('failure.png').catch(() => {});
    const report = { marker: 'house-windows-cli-qa', status: 'failed', error: String(error),
      failureUrl, counts, checks, messages, screenshots };
    // CLI serializes a body/frameset accessibility snapshot after run-code.
    // Native SVG has neither: that secondary timeout would erase the actual
    // failed check. Preserve its URL/screenshot, then use a cheap reporting page.
    // This is not a retry and can never change a failed result to passed.
    if (/\.svg(?:[?#]|$)/i.test(failureUrl)) {
      try {
        await page.goto('about:blank', { timeout: 5000 });
        report.reportingPage = 'about:blank';
      } catch (reportingError) {
        report.reportingWarning = String(reportingError);
      }
    }
    return report;
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
    const response = JSON.parse(invoke('checks', ['run-code', '--filename=' + script]).stdout);
    if (response?.isError) throw new Error('Playwright CLI error: ' + String(response.error || 'unknown error') +
      '\nVerification is incomplete; see checks.log.');
    report = validateReport(findReport(response), prepared.counts);
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
module.exports = { parseArguments, preflight, preflightC1f, preflightArcade, preflightMdf, preflightFengshui, preflightBcOptions, preflightSpaceAllocation, hashSources, checkPages, makeBrowserScript, findReport, validateReport, runQa };
