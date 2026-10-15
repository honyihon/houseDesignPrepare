const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const template = fs.readFileSync(path.join(root, 'scripts/templates/model3d.html'), 'utf8');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
  .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\n$/, ''));
const functions = [
  template.match(/  function geomOf\([\s\S]*?(?=  function featuresOf\()/)[0],
  template.match(/  function placementOf\([\s\S]*?(?=  var PLACEMENT_ISSUES)/)[0],
  template.match(/  function placeFurniture\([\s\S]*?(?=  function furnitureBoxesOverlap\()/)[0],
];
const run = vm.runInNewContext(`var presentation='tour',geomSource='auto',viewState={room:''},MM=.001;
  function wz(y){return -y*MM;}
  ${functions.join('\n')}
  placeFurniture;`);

test('actual presentation filter never mixes extra proposal cells into legacy geometry modes',()=>{
  const definition=template.match(/  function cellInPresentation\([\s\S]*?(?=  function setScope\()/)[0];
  for(const presentation of ['tour','interior','diagnostic']){
    const filter=vm.runInNewContext(`${definition};cellInPresentation`,{presentation});
    assert.equal(filter({tour_active:true,proposal_only:true}),presentation==='tour');
    assert.equal(filter({tour_active:false,proposal_only:false}),presentation!=='tour');
    assert.equal(filter({tour_active:true,proposal_only:false}),true);
  }
});

test('3D sliding-door caption reads proposed widths instead of always stating 900mm', () => {
  const definition = template.match(/      var slidingDoors[\s\S]*?(?=      if\(\(features.reserved_mm)/)?.[0];
  assert.ok(definition, 'caption must use the current room features');
  for (const [doors, expected] of [
    [[{ operation: 'sliding', width_mm: 800 }], '800mm'],
    [[{ operation: 'sliding', width_mm: 900 }], '900mm'],
    [[{ operation: 'sliding', width_mm: 800 }, { operation: 'sliding', width_mm: 900 }], '800／900mm'],
    [[{ operation: 'unconfirmed', width_mm: 900 }], null],
    [undefined, null],
  ]) {
    const rows = [];
    vm.runInNewContext(definition, { features: { doors }, row: (name, text) => rows.push({ name, text }) });
    assert.equal(rows.length, expected ? 1 : 0);
    if (expected) {
      assert.equal(rows[0].name, '滑門提案');
      assert.ok(rows[0].text.includes('門寬暫估' + expected));
      assert.ok(rows[0].text.includes('未核'));
    }
  }
});

function renderRoomInfo(building, floor, room, selectedFurniture = '') {
  // Execute the complete production showInfo, not a copy of its note logic.
  // Scene/DOM primitives below are a unit harness, not browser-rendered QA.
  const definitions = template.match(/  function escapeHtml\([\s\S]*?(?=  \/\/ ---------- controls)/)?.[0];
  assert.ok(definitions);
  const info = {};
  const cell = { ...room, tour_mm: room.geometry, auto_mm: room.geometry, provenance: 'auto',
    is_outdoor: room.outdoor, badges: [], area_sqm: room.geometry.w_mm * room.geometry.h_mm / 1e6 };
  const mesh = { scale: {}, getWorldPosition() {}, userData: { cell,
    floor: { ...floor, height_mm: 3000, auto_depth_mm: floor.depth_mm, tour_depth_mm: floor.depth_mm },
    building: { id: building.id, source_file: building.id + 'buildingView.html' } } };
  const furnitureById = Object.fromEntries(room.furniture.map(item => [item.id, {
    item, cell, placement: item.placement, issueReasons: item.placement.issues,
    overflow: item.placement.issues.includes('overflow'),
    collision: item.placement.issues.some(issue => issue !== 'overflow'),
  }]));
  const showInfo = vm.runInNewContext(definitions + '\nshowInfo', {
    presentation: 'tour', geomSource: 'auto', selectedFurniture, furnitureById, overlappingKeys: {},
    DATA: { standards: { outdoor_slab_mm: 120 } }, PROV_LABEL: { auto: '推估' },
    FURNITURE_BASIS_LABEL: { 'room-use-inference': '依房型推估' },
    selection: { material: { color: { setHex() {} } }, position: {},
      scale: { copy() { return this; }, multiplyScalar() { return this; } } },
    document: { getElementById: id => { assert.equal(id, 'info'); return info; } },
    geomOf: c => c.tour_mm, featuresOf: c => c.features, issueText: entry => entry.issueReasons.join('、'),
  });
  showInfo(mesh);
  return info.innerHTML;
}

test('room info retains every shared furniture-use note without selecting a furniture item', () => {
  const escape = text => String(text).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
  for (const building of manifest.buildings) for (const floor of building.floors) for (const room of floor.rooms) {
    const html = renderRoomInfo(building, floor, room);
    const notes = room.furniture.filter(item => item.note);
    assert.equal((html.match(/data-furniture-note-id=/g) || []).length, notes.length, room.id + ' note count');
    if (room.furniture[0]?.room_note) assert.ok(html.includes(escape(room.furniture[0].room_note)), room.id + ' room limitation');
    for (const item of notes) {
      assert.ok(html.includes('data-furniture-note-id="' + escape(item.id) + '"'), item.id + ' identifiable note');
      assert.ok(html.includes(escape(item.note)), item.id + ' shared note is in the room info');
    }
    if (room.id === 'A:floor-2:hall2') {
      assert.ok(html.includes('880mm') && html.includes('280mm') && html.includes('待移') && html.includes('1280mm'),
        'pending hallway cabinet and continuous passage are explained before any cabinet click');
    }
  }
});

test('furniture selection retains all room-use notes and escapes note content as text', () => {
  const building = manifest.buildings.find(b => b.id === 'A');
  const floor = building.floors.find(f => f.id === 'floor-2');
  const room = structuredClone(floor.rooms.find(r => r.key === 'master-bath'));
  room.furniture[0].note = '備註 <img src=x onerror="bad()"> & "尺寸"';
  room.furniture[0].id = 'note-"quoted"';
  for (const selected of ['', room.furniture[0].id, room.furniture[1].id]) {
    const html = renderRoomInfo(building, floor, room, selected);
    assert.ok(html.includes('data-furniture-note-id="note-&quot;quoted&quot;"'));
    assert.ok(html.includes('&lt;img src=x onerror=&quot;bad()&quot;&gt; &amp; &quot;尺寸&quot;'));
    assert.ok(!html.includes('<img'));
    assert.ok(html.includes(room.furniture[1].note) && html.includes(room.furniture[2].note),
      'other fixtures keep their limitations even after selecting one item');
  }
});

test('actual 3D positioning code uses the same centers, rotation and mounting height as all HTML plans', () => {
  let count=0;
  for(const b of manifest.buildings) for(const f of b.floors) for(const r of f.rooms) for(const item of r.furniture){
    const p=item.placement;
    const entry={item,cell:{tour_mm:r.geometry,furniture_placements:{tour_mm:{[item.id]:p}}},floor:{base_mm:3000},
      group:{position:{set(x,y,z){this.x=x;this.y=y;this.z=z;}},rotation:{y:0}}};
    run(entry);
    assert.ok(Math.abs(entry.group.position.x-p.center_x_mm/1000)<1e-10);
    assert.ok(Math.abs(entry.group.position.y-(3000+p.mount_height_mm)/1000)<1e-10);
    assert.ok(Math.abs(entry.group.position.z+p.center_y_mm/1000)<1e-10);
    assert.ok(Math.abs(-entry.group.rotation.y*180/Math.PI-p.rotation_deg)<1e-10);
    for(const key of ['minX','maxX','minY','maxY']) assert.ok(Math.abs(entry.aabb[key]-p.aabb[key])<.02);
    assert.equal(entry.overflow,p.issues.includes('overflow'));
    assert.equal(entry.collision,p.issues.some(i=>i!=='overflow'));
    count++;
  }
  assert.equal(count,manifest.buildings.flatMap(b=>b.floors).flatMap(f=>f.rooms).flatMap(r=>r.furniture).length);
});

test('actual detailed parts stay within every real-size furniture envelope, including dining chairs',()=>{
  const source=template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0];
  const parts=vm.runInNewContext(`${source};furnitureParts`);
  for(const b of manifest.buildings) for(const f of b.floors) for(const r of f.rooms) for(const item of r.furniture){
    for(const part of parts(item)){
      assert.ok(Math.abs(part.x)+part.w/2<=.5+1e-8,`${item.id}: width`);
      assert.ok(Math.abs(part.z)+part.d/2<=.5+1e-8,`${item.id}: depth`);
      assert.ok(part.bottom>=0 && part.bottom+part.h<=1+1e-8,`${item.id}: height`);
    }
    if(item.shape==='dining-set'){
      const spec=parts(item);
      assert.equal(spec[0].w*item.width_mm,item.table_width_mm);
      assert.equal(spec[0].d*item.depth_mm,item.table_depth_mm);
    }
  }
});

test('actual 3D countertop details use shared local dimensions, not the generic decorative hob position', () => {
  const source = template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0];
  const parts = vm.runInNewContext(`${source};furnitureParts`);
  const counter = manifest.buildings[0].floors[0].rooms.find(r => r.key === 'kitchen').furniture.find(i => i.shape === 'counter');
  const details = parts(counter).filter(p => p.worktopPart);
  assert.equal(details.length, 2);
  for (const p of details) {
    const local = counter.worktop_parts.find(i => i.id === p.worktopPart);
    assert.equal(p.x * counter.width_mm, local.center_x_mm);
    assert.equal(p.z * counter.depth_mm, local.center_z_mm);
    assert.equal(p.w * counter.width_mm, local.width_mm);
    assert.equal(p.d * counter.depth_mm, local.depth_mm);
    // The SVG uses -z locally; the 3D uses world z and plan y=-world z.
    const radians = counter.placement.rotation_deg * Math.PI / 180;
    const x = counter.placement.center_x_mm + local.center_x_mm * Math.cos(radians) - local.center_z_mm * Math.sin(radians);
    const y = counter.placement.center_y_mm - local.center_x_mm * Math.sin(radians) - local.center_z_mm * Math.cos(radians);
    const mm = counter.placement.worktop_parts_mm.find(i => i.id === local.id);
    assert.ok(Math.abs(x - mm.center_x_mm) < .01 && Math.abs(y - mm.center_y_mm) < .01);
  }
});

test('compact four-seat candidate has full physical table, chairs and legs rather than scaled parts', () => {
  const source = template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0];
  const parts = vm.runInNewContext(`${source};furnitureParts`);
  const item = manifest.buildings[0].floors[0].rooms.find(r => r.key === 'living').furniture.find(i => i.catalog_id === 'dining-4-sides');
  const model = parts(item), seats = model.filter(p => Math.abs(p.h*item.height_mm-45)<1e-8);
  const backs = model.filter(p => Math.abs(p.h*item.height_mm-400)<1e-8);
  const legs = model.filter(p => Math.abs(p.w*item.width_mm-30)<1e-8 && Math.abs(p.d*item.depth_mm-30)<1e-8);
  assert.equal(item.height_mm,850,'external chair-back height, not just table height');
  assert.equal((model[0].bottom+model[0].h)*item.height_mm,750,'ordinary tabletop height');
  assert.equal(seats.length,4);assert.equal(backs.length,4);assert.equal(legs.length,16);
  assert.equal(new Set(seats.map(p=>p.x)).size,2);assert.equal(new Set(seats.map(p=>p.z)).size,2);
  for(const p of [...seats,...backs]) assert.equal(p.w*item.width_mm,450,'full-width seat/back');
  for(const p of seats){assert.equal(p.d*item.depth_mm,450);assert.equal((p.bottom+p.h)*item.height_mm,450);}
  for(const p of backs) assert.equal((p.bottom+p.h)*item.height_mm,850);
});

test('actual stair renderer uses shared A landings and full-height stacked flights without a fifth storey', () => {
  const THREE = require(path.join(root, 'assets/vendor/three/three.min.js'));
  const definitions = [
    template.match(/  function geomOf\([\s\S]*?(?=  function placementOf\()/)[0],
    template.match(/  function layoutCell\([\s\S]*?(?=  \/\/ ---------- build)/)[0],
    template.match(/  function wallPoint\([\s\S]*?(?=  function positionNavigationLabels\()/)[0],
  ].join('\n');
  const build = vm.runInNewContext(`var presentation='tour',geomSource='auto',viewState={room:''},MM=.001;
    var architectureCutawayParts=[];
    function wz(y){return -y*MM;} function addNavigationLabel(){}
    function architectureBox(group,x,y,z,w,h,d,colour){
      const part={x,y,z,w,h,d,colour,userData:{},material:{transparent:false,opacity:1,depthWrite:true}};
      group.children.push(part);return part;
    } ${definitions};buildArchitecture;`,{THREE,document:{getElementById:()=>({checked:true})},
      DATA:{standards:{door_height_mm:2100,window_sill_height_mm:900,window_height_mm:1200}}});
  for(const b of manifest.buildings) for(const f of b.floors){
    const r=f.rooms.find(r=>r.features.stairs),group={children:[],clear(){this.children=[];}};
    build({visible:true,userData:{shell:group,floor:f,cell:{id:r.id,name:r.name,tour_mm:r.geometry,
      tour_features:r.features,is_outdoor:r.outdoor,window_mm:0}}});
    const parts=group.children.filter(p=>p.colour===0xa4aead),g=r.features.stair_geometry;
    const base=f.base_mm/1000,fp=r.features.stair_footprint_mm;
    assert.equal(parts.length,g.connects_to_next_storey?g.risers+1:1,r.id+' actual step/platform count');
    const landing=parts[0],offset=g.departure_offset_mm;
    assert.ok(Math.abs(landing.z+fp.y_mm/1000+offset/1000-.5)<1e-8,'front floor-level platform position');
    assert.ok(Math.abs(landing.y+landing.h/2-base)<1e-8,'departure landing exactly at floor base');
    if(!g.connects_to_next_storey)continue;
    assert.ok(Math.abs(parts[1].y+parts[1].h/2-base-f.height_mm/1000)<1e-8,'top landing connects the next base');
    const middle=parts[2];assert.equal(Math.round(middle.d*1000),g.middle_landing_mm);
    assert.ok(Math.abs(middle.y+middle.h/2-base-f.height_mm/2000)<1e-8,'middle landing half height');
    assert.ok(Math.abs(middle.z+fp.y_mm/1000+(offset+g.run_mm+g.middle_landing_mm/2)/1000)<1e-8);
    for(const step of parts.slice(3)){
      assert.equal(Math.round(step.w*1000),g.flight_width_mm);
      assert.equal(Math.round(step.d*1000),g.tread_mm);
    }
    if(b.id==='A'){
      const shared=r.features.shared_landing_mm;
      assert.equal(Math.round(-landing.z*1000-landing.d*500),shared.y_mm);
      assert.equal(Math.round(landing.d*1000),shared.h_mm);
    }
  }
});

test('drying racks and outdoor seats are open structures, while network racks remain cabinets', () => {
  const source = template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0];
  const parts = vm.runInNewContext(`${source};furnitureParts`);
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'inputs/furniture-layout.json'), 'utf8')).catalog;
  const body = part => part.w >= 0.8 && part.d >= 0.8 && part.h >= 0.8;
  for (const id of ['clothes-rack', 'outdoor-bench']) {
    const model = parts({ ...catalog[id], catalog_id: id });
    assert.ok(model.length >= 10, `${id}: distinct rails/slats/legs`);
    assert.equal(model.some(body), false, `${id}: no opaque cabinet or sofa body`);
  }
  assert.equal(parts({ ...catalog['rack-12u'], catalog_id: 'rack-12u' }).some(body), true);
});

test('A care shower is an open step-free area, not a glass enclosure or raised tray', () => {
  const source = template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0];
  const parts = vm.runInNewContext(`${source};furnitureParts`);
  const room = manifest.buildings.find(b => b.id === 'A').floors[0].rooms.find(r => r.requirement_id === 'A.floor-1.bath1');
  const shower = room.furniture.find(i => i.shape === 'shower');
  assert.equal(shower.step_free, true);
  const model = parts(shower);
  assert.ok(model[0].h * shower.height_mm <= 2);
  assert.ok(!model.some(p => p.h > 0.5 && (p.w > 0.5 || p.d > 0.5)), 'no glass walls across the care shower');
});

test('actual camera closeup fits the shared room at mobile and desktop sizes without hiding its floor', () => {
  const THREE = require(path.join(root, 'assets/vendor/three/three.min.js'));
  const definitions = [
    template.match(/  function scopedMeshes\([\s\S]*?(?=  function focusScope\()/)[0],
    template.match(/  function focusScope\([\s\S]*?(?=  function frameLighting\()/)[0],
    template.match(/  function updateCamera\([\s\S]*?(?=  function applyViewPreset\()/)[0],
  ].join('\n');
  const floor = manifest.buildings.find(b => b.id === 'C').floors[0];
  for (const [width, height] of [[390, 790], [1080, 900]]) {
    const rootGroup = new THREE.Group(), pickables = [], furnitureEntries = [];
    for (const room of floor.rooms) {
      const g = room.geometry;
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(g.w_mm / 1000, 0.12, g.h_mm / 1000));
      mesh.position.set((g.x_mm + g.w_mm / 2) / 1000, -0.06, -(g.y_mm + g.h_mm / 2) / 1000);
      const shell = new THREE.Mesh(new THREE.BoxGeometry(g.w_mm / 1000, 3, g.h_mm / 1000));
      shell.position.set(mesh.position.x, 1.5, mesh.position.z);
      mesh.userData = { cell: { id: room.id }, building: { id: 'C' }, floor: { id: floor.id }, shell };
      rootGroup.add(mesh, shell);
      pickables.push(mesh);
      for (const item of room.furniture) {
        if (item.placement.issues.length) continue;
        const group = new THREE.Mesh(new THREE.BoxGeometry(item.width_mm / 1000, item.height_mm / 1000, item.depth_mm / 1000));
        group.position.set(item.placement.center_x_mm / 1000,
          (item.placement.mount_height_mm + item.height_mm / 2) / 1000, -item.placement.center_y_mm / 1000);
        group.rotation.y = -item.placement.rotation_deg * Math.PI / 180;
        rootGroup.add(group);
        furnitureEntries.push({ cell: { id: room.id }, building: { id: 'C' }, floor: { id: floor.id }, group });
      }
    }
    rootGroup.updateMatrixWorld(true);
    const frame = vm.runInNewContext(`
      var presentation='tour', roomCameraFocused=false;
      var viewState={building:'C',floor:'floor-1',room:'C:floor-1:elder'};
      var target=new THREE.Vector3(), spherical={radius:40,theta:0,phi:0.65};
      var camera=new THREE.PerspectiveCamera(45,stage.clientWidth/stage.clientHeight,0.1,2000);
      function furnitureIsVisible(){return true;}
      function frameLighting(){}
      function updateRoomCutaway(){}
      function facadeIsActive(){return viewState.view==='exterior';}
      ${definitions}
      (focused,kind)=>{
        roomCameraFocused=focused;
        focusScope(kind); updateCamera();
        var box=scopedViewBox();
        return {radius:spherical.radius,size:box.getSize(new THREE.Vector3()).toArray(),
          corners:boxCorners(box).map(p=>p.project(camera).toArray()),
          visible:pickables.filter(m=>m.visible).map(m=>m.userData.cell.id)};
      };`, { THREE, pickables, furnitureEntries, stage: { clientWidth: width, clientHeight: height },
        document: { getElementById: () => null } });
    const overview = frame(false, 'front');
    const closeup = frame(true, 'front');
    assert.ok(closeup.radius < overview.radius * 0.6, 'room is meaningfully larger on screen');
    assert.deepEqual(closeup.visible, overview.visible, 'other rooms were not removed');
    assert.ok(Math.abs(closeup.size[0] - 3.6) < 1e-6 && Math.abs(closeup.size[2] - 3.83) < 1e-6);
    for (const kind of ['front', 'plan']) {
      const result = frame(true, kind);
      for (const [x, y] of result.corners) assert.ok(Math.abs(x) < 1 && Math.abs(y) < 1, `${width}px ${kind}: corner fits`);
    }
  }
});

test('closeup URL state is limited to a selected shared-proposal room', () => {
  const definition = template.match(/  function mdfStudyActive\([\s\S]*?(?=  function buildMdfStudy\()/)[0] +
    template.match(/  function writeHash\([\s\S]*?(?=  function updateOrientation\()/)[0];
  for (const [presentation, room, focused, expected] of [
    ['tour', 'C:floor-1:elder', true, true], ['tour', 'C:floor-1:elder', false, false],
    ['tour', '', true, false], ['interior', 'C:floor-1:elder', true, false],
  ]) {
    let hash;
    vm.runInNewContext(`${definition};writeHash();`, {
      presentation, roomCameraFocused: focused, viewState: { building: 'C', floor: 'floor-1', room, view: 'front' },
      URLSearchParams, history: { replaceState(_state, _title, value) { hash = value; } },
      facadeIsActive: () => false,
      DATA: {},
    });
    assert.equal(new URLSearchParams(hash.slice(1)).get('focus') === 'room', expected);
  }
});

test('actual wall builder leaves shared stair-hall boundaries open without walls or door frames', () => {
  const THREE = require(path.join(root, 'assets/vendor/three/three.min.js'));
  const definitions = [
    template.match(/  function geomOf\([\s\S]*?(?=  function placementOf\()/)[0],
    template.match(/  function layoutCell\([\s\S]*?(?=  \/\/ ---------- build)/)[0],
    template.match(/  function wallPoint\([\s\S]*?(?=  function positionNavigationLabels\()/)[0],
  ].join('\n');
  for (const full of [false, true]) {
    const build = vm.runInNewContext(`
      var presentation='tour',geomSource='auto',viewState={room:''},MM=.001;
      function wz(y){return -y*MM;}
      function addNavigationLabel(){}
      function architectureBox(group,x,y,z,w,h,d,colour){
        if(w>0 && h>0 && d>0) group.children.push({x,y,z,w,h,d,colour});
      }
      ${definitions}
      buildArchitecture;`, {
      THREE, clipPlane: new THREE.Plane(new THREE.Vector3(0, -1, 0), 1000),
      document: { getElementById: id => ({ checked: id === 'full-walls' ? full : true }) },
      DATA: { standards: { door_height_mm: 2100, window_sill_height_mm: 900, window_height_mm: 1200 } },
    });
    let count = 0;
    for (const b of manifest.buildings) for (const f of b.floors) for (const r of f.rooms) {
      if (!r.features.open_connections.length) continue;
      const group = { children: [], clear() { this.children = []; }, add(part) { this.children.push(part); } };
      build({ visible: true, userData: { shell: group, floor: { base_mm: 0, height_mm: 3000 },
        cell: { id: r.id, name: r.name, tour_mm: r.geometry, tour_features: r.features,
          is_outdoor: r.outdoor, window_mm: r.features.window_mm } } });
      const g = r.geometry;
      for (const opening of r.features.open_connections) {
        const alongX = ['front', 'rear'].includes(opening.face);
        const x = (g.x_mm + (alongX ? g.w_mm * opening.ratio : opening.face === 'right' ? g.w_mm : 0)) / 1000;
        const z = -(g.y_mm + (alongX ? opening.face === 'rear' ? g.h_mm : 0 : g.h_mm * opening.ratio)) / 1000;
        const half = opening.width_mm / 2000 - 0.16; // ignore perpendicular wall corners
        const gap = { minX: x - (alongX ? half : 0.015), maxX: x + (alongX ? half : 0.015),
          minZ: z - (alongX ? 0.015 : half), maxZ: z + (alongX ? 0.015 : half) };
        for (const part of group.children.filter(p => [0xeae9e1, 0x3e8d74, 0x3b7894].includes(p.colour))) {
          const intersects = part.x - part.w / 2 < gap.maxX && part.x + part.w / 2 > gap.minX
            && part.z - part.d / 2 < gap.maxZ && part.z + part.d / 2 > gap.minZ;
          assert.equal(intersects, false, `${r.id} ${opening.face}: invented shared-boundary wall/frame`);
        }
        count++;
      }
    }
    assert.equal(count, manifest.buildings.flatMap(b=>b.floors).flatMap(f=>f.rooms)
      .reduce((sum,r)=>sum+r.features.open_connections.length,0));
  }
});
