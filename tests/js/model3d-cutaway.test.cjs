const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const THREE = require(path.join(root, 'assets/vendor/three/three.min.js'));
const template = fs.readFileSync(path.join(root, 'scripts/templates/model3d.html'), 'utf8');
const shared = JSON.parse(fs.readFileSync(path.join(root, 'structured/candidates/furniture-plans/layout.js'), 'utf8')
  .replace(/^window.HOUSE_CONCEPT_LAYOUT = /, '').replace(/;\s*$/, ''));
const definitions = [
  template.match(/  function solidMaterial\([\s\S]*?(?=  function lineMaterial\()/)[0],
  template.match(/  function geomOf\([\s\S]*?(?=  function placementOf\()/)[0],
  template.match(/  function layoutCell\([\s\S]*?(?=  \/\/ ---------- build)/)[0],
  template.match(/  function architectureBox\([\s\S]*?(?=  function addNavigationLabel\()/)[0],
  template.match(/  function wallPoint\([\s\S]*?(?=  function positionNavigationLabels\()/)[0],
  template.match(/  function scopedMeshes\([\s\S]*?(?=  function focusScope\()/)[0],
  template.match(/  function focusScope\([\s\S]*?(?=  function frameLighting\()/)[0],
  template.match(/  function updateCamera\([\s\S]*?(?=  function applyViewPreset\()/)[0],
].join('\n');
const furnitureParts = vm.runInNewContext(
  template.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0] + '\nfurnitureParts');

function sceneHarness(buildingId, floorId = 'floor-2', width = 1080, height = 900) {
  // Real Three.js geometry, production wall builder, camera and clipping logic.
  // This exercises sightlines without WebGL; it is not screenshot acceptance.
  const floor = shared.buildings.find(b => b.id === buildingId).floors.find(f => f.id === floorId);
  const rootGroup = new THREE.Group(), pickables = [], furnitureEntries = [], meshById = {};
  for (const room of floor.rooms) {
    const g = room.geometry, mesh = new THREE.Mesh(new THREE.BoxGeometry(g.w_mm / 1000, .12, g.h_mm / 1000));
    mesh.position.set((g.x_mm + g.w_mm / 2) / 1000, 2.94, -(g.y_mm + g.h_mm / 2) / 1000);
    const shell = new THREE.Group();
    mesh.userData = { cell: { id: room.id, name: room.name, is_outdoor: room.outdoor,
      tour_mm: g, tour_features: room.features, window_mm: room.features.window_mm },
    floor: { id: floor.id, base_mm: 3000, height_mm: 3000 }, building: { id: buildingId }, shell };
    rootGroup.add(mesh, shell);
    pickables.push(mesh);
    meshById[room.id] = mesh;
    for (const item of room.furniture) {
      const p = item.placement, group = new THREE.Group();
      group.position.set(p.center_x_mm / 1000, (3000 + p.mount_height_mm) / 1000, -p.center_y_mm / 1000);
      group.rotation.y = -p.rotation_deg * Math.PI / 180;
      group.visible = !p.issues.length;
      for (const part of furnitureParts(item)) {
        const geom = part.primitive === 'round' ? new THREE.SphereGeometry(.5, 12, 8) : new THREE.BoxGeometry(1, 1, 1);
        const body = new THREE.Mesh(geom);
        body.scale.set(part.w * item.width_mm / 1000, part.h * item.height_mm / 1000, part.d * item.depth_mm / 1000);
        body.position.set(part.x * item.width_mm / 1000, (part.bottom + part.h / 2) * item.height_mm / 1000,
          part.z * item.depth_mm / 1000);
        group.add(body);
      }
      rootGroup.add(group);
      furnitureEntries.push({ cell: { id: room.id }, item, floor: { id: floor.id }, building: { id: buildingId }, group });
    }
  }
  const controls = { architecture: { checked: true }, 'full-walls': { checked: false },
    'room-cutaway': { checked: true }, 'frontage-study': { checked: false }, 'room-cutaway-status': { hidden: true, textContent: '' } };
  const api = vm.runInNewContext(`
    var presentation='tour',geomSource='auto',roomCameraFocused=false,MM=.001;
    var viewState={building:buildingId,floor:floorId,room:''};
    var target=new THREE.Vector3(), spherical={radius:40,theta:.6,phi:.65};
    var camera=new THREE.PerspectiveCamera(45,stage.clientWidth/stage.clientHeight,.1,2000);
    var boxGeom=new THREE.BoxGeometry(1,1,1), materials={}, roomCutawayMaterials={};
    var clipPlane=new THREE.Plane(new THREE.Vector3(0,-1,0),1000);
    var roomCutawayPlane=new THREE.Plane(new THREE.Vector3(0,-1,0),1000);
    var architectureCutawayParts=[],roomCutawayActive=false;
    function wz(y){return -y*MM;}
    function addNavigationLabel(){}
    function furnitureIsVisible(){return true;}
    function frameLighting(){}
    function facadeIsActive(){return viewState.view==='exterior';}
    ${definitions}
    function rebuild(){architectureCutawayParts=[];pickables.forEach(buildArchitecture);root.updateMatrixWorld(true);}
    function inspect(){
      return JSON.parse(JSON.stringify({active:roomCutawayActive,statusHidden:controls['room-cutaway-status'].hidden,
        cutHeight:roomCutawayPlane.constant,cacheSize:Object.keys(roomCutawayMaterials).length,
        parts:architectureCutawayParts.map(e=>({room:e.mesh.userData.cell.id,role:e.role,face:e.face,
          clipped:e.clipped,original:e.part.material===e.material,position:e.part.position.toArray(),
          scale:e.part.scale.toArray(),uuid:e.part.uuid,planes:e.part.material.clippingPlanes.map(p=>p.constant)})),
        visible:pickables.filter(m=>m.visible).map(m=>m.userData.cell.id),
        furniture:furnitureEntries.map(e=>({id:e.item.id,position:e.group.position.toArray(),rotation:e.group.rotation.y,
          visible:e.group.visible,width:e.item.width_mm,depth:e.item.depth_mm,height:e.item.height_mm})),
        sightlines:fixtureSightlineEvidence()}));
    }
    rebuild();
    ({frame(room,focused=true,kind='front'){
        viewState.room=room;roomCameraFocused=focused;
        root.scale.x=kind==='plan'?-1:1;root.position.x=kind==='plan'?3:-3;root.updateMatrixWorld(true);
        focusScope(kind);updateCamera();return inspect();
      },rotate(theta,phi=.65){spherical.theta=theta;spherical.phi=phi;updateCamera();return inspect();},
      toggle(id,checked){controls[id].checked=checked;if(id==='full-walls'||id==='architecture')rebuild();
        updateCamera();return inspect();},
      presentation(value){presentation=value;updateCamera();return inspect();},
      explode(y){root.position.y=y;root.updateMatrixWorld(true);updateCamera();return inspect();},inspect});`, {
    THREE, root: rootGroup, pickables, furnitureEntries, meshById, buildingId, floorId, controls,
    stage: { clientWidth: width, clientHeight: height },
    document: { getElementById: id => { assert.ok(controls[id], id); return controls[id]; } },
    DATA: { standards: { door_height_mm: 2100, window_sill_height_mm: 900, window_height_mm: 1200 } },
  });
  return { api, floor };
}

const stableGeometry = state => ({ parts: state.parts.map(({ room, role, face, position, scale, uuid }) =>
  ({ room, role, face, position, scale, uuid })), visible: state.visible, furniture: state.furniture });

test('A 2F bathroom cutaway clears real fixture-body sightlines, including the adjacent high wall', () => {
  for (const [width, height] of [[1080, 900], [390, 790]]) {
    const { api, floor } = sceneHarness('A', 'floor-2', width, height);
    api.toggle('room-cutaway', false);
    const before = api.frame('A:floor-2:master-bath');
    assert.ok(before.sightlines.some(i => i.unobstructedSamples < i.samples), 'reproduce actual architecture occlusion');
    const after = api.toggle('room-cutaway', true);
    assert.equal(after.active, true);
    assert.equal(after.statusHidden, false);
    assert.equal(after.cutHeight, 3.55);
    assert.equal(after.sightlines.length, 3);
    assert.ok(after.sightlines.every(i => i.unobstructedSamples === i.samples), 'all basin/toilet/shower body probes clear');
    assert.ok(after.parts.some(p => p.clipped && p.room !== 'A:floor-2:master-bath'), 'neighbor wall also cut, not a detached room');
    assert.deepEqual(stableGeometry(after), stableGeometry(before), 'clipping never changes the plan or furniture');
    assert.equal(after.visible.length, floor.rooms.length);
    assert.equal(after.furniture.filter(i => !i.visible).length, 2, 'both original-size wardrobes stay pending');
  }
});

test('B public bathroom cuts obstructing stair treads but preserves the actual stair geometry and floor', () => {
  const { api } = sceneHarness('B');
  const before = api.frame('B:floor-2:bath2', false);
  const after = api.frame('B:floor-2:bath2');
  assert.ok(after.parts.some(p => p.role === 'stairs' && p.clipped), 'stair obstruction handled too');
  assert.ok(after.sightlines.every(i => i.unobstructedSamples === i.samples));
  assert.deepEqual(stableGeometry(after), stableGeometry(before));
  const returned = api.frame('B:floor-2:bath2', false);
  assert.equal(returned.active, false);
  assert.ok(returned.parts.every(p => p.original && !p.clipped));
});

test('cutaway follows camera rotation and mirrored HTML plan view without leaking shared materials', () => {
  const { api } = sceneHarness('A');
  const front = api.frame('A:floor-2:master-bath');
  assert.ok(front.parts.some(p => p.room === 'A:floor-2:master-bath' && p.face === 'front' && p.clipped));
  const rear = api.rotate(Math.PI + .6);
  assert.ok(rear.parts.some(p => p.room === 'A:floor-2:master-bath' && p.face === 'rear' && p.clipped));
  assert.ok(rear.parts.filter(p => p.room === 'A:floor-2:master-bath' && p.face === 'front').every(p => !p.clipped));
  assert.deepEqual(stableGeometry(rear), stableGeometry(front));
  for (let n = 0; n < 30; n++) {
    const rotated = api.rotate(n / 5);
    assert.ok(rotated.sightlines.every(i => i.unobstructedSamples >= 3), 'body sightlines survive orbit, not just labels');
  }
  const cacheSize = api.inspect().cacheSize;
  for (let n = 0; n < 30; n++) api.rotate(n / 5);
  assert.equal(api.inspect().cacheSize, cacheSize, 'reuse material clones across pointer events');
  const plan = api.frame('A:floor-2:master-bath', true, 'plan');
  assert.ok(plan.sightlines.every(i => i.unobstructedSamples === i.samples));
  const disabled = api.toggle('room-cutaway', false);
  assert.ok(disabled.parts.every(p => p.original && !p.clipped), 'no global/source material was modified');
});

test('full-wall, architecture, room and presentation controls restore uncut geometry', () => {
  const { api } = sceneHarness('B');
  api.frame('B:floor-2:master-bath2');
  for (const [id, value, restore] of [['full-walls', true, false], ['architecture', false, true], ['room-cutaway', false, true]]) {
    const state = api.toggle(id, value);
    assert.equal(state.active, false, id);
    assert.equal(state.statusHidden, true, id);
    assert.ok(state.parts.every(p => p.original && !p.clipped), id);
    assert.equal(api.toggle(id, restore).active, true);
  }
  assert.equal(api.presentation('diagnostic').active, false);
  assert.equal(api.presentation('interior').active, false);
  assert.equal(api.presentation('tour').active, true);
  const returned = api.frame('', false);
  assert.equal(returned.active, false);
  assert.ok(returned.parts.every(p => p.original));
});

test('cut plane follows the exploded selected floor, not a hard-coded ground elevation', () => {
  const { api } = sceneHarness('A');
  api.frame('A:floor-2:master-bath');
  const exploded = api.explode(2.4);
  assert.ok(Math.abs(exploded.cutHeight - 5.95) < 1e-10);
  assert.ok(exploded.sightlines.every(i => i.unobstructedSamples === i.samples));
});

test('mobile C elder closeup keeps bed, TV and wardrobe at real size and the full floor', () => {
  const { api, floor } = sceneHarness('C', 'floor-1', 390, 790);
  const state = api.frame('C:floor-1:elder');
  assert.equal(state.active, true);
  assert.equal(state.visible.length, floor.rooms.length);
  assert.equal(state.sightlines.length, 3);
  assert.ok(state.sightlines.every(i => i.unobstructedSamples === i.samples));
});

test('new C1F dining/lounge/kitchen closeups retain body sightlines at desktop and mobile aspect ratios', () => {
  for (const [width,height] of [[1080,900],[390,790]]) {
    for (const [key,count] of [['dining',1],['living',4],['kitchen',2]]) {
      const {api,floor}=sceneHarness('C','floor-1',width,height);
      const state=api.frame('C:floor-1:'+key);
      assert.equal(state.active,true,key);
      assert.equal(state.visible.length,floor.rooms.length,key);
      assert.equal(state.sightlines.length,count,key);
      assert.ok(state.sightlines.every(i => i.unobstructedSamples >= 3),key);
    }
  }
});

test('upstairs hall and ensuite keep body sightlines and do not clip HVAC symbols', () => {
  for (const [building, room] of [['A', 'hall2'], ['B', 'master-bath2']]) {
    const { api } = sceneHarness(building);
    const state = api.frame(`${building}:floor-2:${room}`);
    assert.equal(state.active, true);
    assert.ok(state.sightlines.every(i => i.unobstructedSamples >= 3));
    assert.ok(state.parts.every(p => ['wall', 'door', 'window', 'stairs'].includes(p.role)));
  }
});
