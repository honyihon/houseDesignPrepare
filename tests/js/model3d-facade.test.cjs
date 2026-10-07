'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const THREE=require(path.join(root,'assets/vendor/three/three.min.js'));
const fragment=fs.readFileSync(path.join(root,'scripts/templates/model3d_facade.js'),'utf8');
const template=fs.readFileSync(path.join(root,'scripts/templates/model3d.html'),'utf8');
const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
  .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
function section(source,name,next){return source.match(new RegExp('  function '+name+'\\([\\s\\S]*?(?=  function '+next+'\\()'))[0];}
const json=value=>JSON.parse(JSON.stringify(value));

test('actual facade meshes use each shared box without modifying its plan/elevation coordinates',()=>{
  const build=vm.runInNewContext('var MM=.001;function wz(y){return -y*MM;}'+section(fragment,'facadeBox','initFacadeLayer')+';facadeBox',
    {THREE,boxGeom:new THREE.BoxGeometry(1,1,1)});
  for(const b of shared.facade.buildings)for(const c of b.components.filter(c=>c.rendered)){
    const source=json(c.box_mm),group=new THREE.Group(),mesh=build(group,c.box_mm,new THREE.MeshBasicMaterial());
    group.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(mesh);
    const expected=[source.x_mm/1000,source.z_mm/1000,-(source.y_mm+source.d_mm)/1000,
      (source.x_mm+source.w_mm)/1000,(source.z_mm+source.h_mm)/1000,-source.y_mm/1000];
    const actual=[...box.min.toArray(),...box.max.toArray()];
    actual.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-6,c.id+' axis '+i));
    assert.deepEqual(c.box_mm,source);
  }
});

test('production exterior camera fits single/all buildings, front/oblique and desktop/mobile without WebGL',()=>{
  // Projection proof only, not a browser screenshot or visual acceptance.
  const definition=section(fragment,'facadeViewBox','facadeDebug');
  const corners=section(template,'boxCorners','frameLighting');
  for(const count of [1,3])for(const [width,height] of [[1080,900],[390,790]])for(const angle of ['front','oblique']){
    const scene=new THREE.Group(),facadeGroups=[];
    for(let i=0;i<count;i++){
      const group=new THREE.Group();group.position.x=i*8;scene.add(group);
      for(const c of shared.facade.buildings[i].components.filter(c=>c.rendered)){
        const b=c.box_mm,mesh=new THREE.Mesh(new THREE.BoxGeometry(b.w_mm/1000,b.h_mm/1000,b.d_mm/1000));
        mesh.position.set((b.x_mm+b.w_mm/2)/1000,(b.z_mm+b.h_mm/2)/1000,-(b.y_mm+b.d_mm/2)/1000);group.add(mesh);
      }
      facadeGroups.push({group});
    }
    scene.updateMatrixWorld(true);
    const project=vm.runInNewContext(`var camera=new THREE.PerspectiveCamera(45,stage.clientWidth/stage.clientHeight,.1,2000);
      var target=new THREE.Vector3(),spherical={radius:40,phi:1,theta:0};
      function frameLighting(){}
      function updateCamera(){camera.position.set(target.x+spherical.radius*Math.sin(spherical.phi)*Math.sin(spherical.theta),
        target.y+spherical.radius*Math.cos(spherical.phi),target.z+spherical.radius*Math.sin(spherical.phi)*Math.cos(spherical.theta));
        camera.lookAt(target);camera.updateMatrixWorld();}
      ${corners}${definition}fitExteriorCamera();({corners:boxCorners(facadeViewBox()).map(c=>c.project(camera).toArray()),phi:spherical.phi});`,
    {THREE,facadeGroups,pickables:[],exteriorAngle:angle,stage:{clientWidth:width,clientHeight:height},
      document:{getElementById:id=>id==='facade-actions'?{offsetTop:124,offsetHeight:36}:{offsetHeight:60}}});
    for(const [x,y,z] of project.corners){assert.ok(Math.abs(x)<.86 && Math.abs(y)<1 && Math.abs(z)<1,`${count} ${width}px ${angle}: model fits`);}
    assert.ok(angle==='front'?project.phi>1.5:project.phi<1.5);
  }
});

function stateHarness(){
  const controls=Object.fromEntries(['architecture','full-walls','navigation','room-cutaway','cut','explode','ghost'].map(id=>
    [id,{checked:['architecture','navigation','room-cutaway'].includes(id),value:id==='cut'?'900':id==='explode'?'600':'on'}]));
  const buildings=shared.buildings.map(b=>({id:b.id,floors:b.floors.map(f=>({id:f.id,cells:f.rooms.map(r=>({id:r.id,tour_active:true}))}))}));
  const floorGroups=buildings.flatMap(b=>b.floors.map(f=>({building:b,floor:f,group:{visible:b.id==='A'&&f.id==='floor-2'},checkbox:{checked:b.id==='A'&&f.id==='floor-2'}})));
  const meshById=Object.fromEntries(buildings.flatMap(b=>b.floors.flatMap(f=>f.cells.map(c=>[c.id,{userData:{building:b,floor:f,cell:c}}]))));
  const stateFunctions=[section(fragment,'facadeIsActive','facadeMaterial'),section(fragment,'captureIndoorState','facadeViewBox'),
    section(template,'buildingRecord','writeHash'),section(template,'writeHash','updateOrientation'),section(template,'cellInPresentation','selectMesh')].join('\n');
  const api=vm.runInNewContext(`var viewState={building:'A',floor:'floor-2',room:'A:floor-2:master-bath',view:'front'};
    var presentation='tour',geomSource='auto',roomCameraFocused=true,selectedFurniture='item';
    var exteriorAngle='front',indoorSnapshot=null,hashInitialized=true;
    var facadeControlIds=['architecture','full-walls','navigation','room-cutaway','cut','explode','ghost'];
    var facadeGroups=buildings.map(b=>({group:{visible:false},building:b.id}));
    var hash='';
    function syncPresentation(){}function syncGeometryButtons(){}function syncRoomViewActions(){}
    function applyCut(){}function applyLayout(){}function renderScopeControls(){}function showInfo(){}
    function applyViewPreset(kind){viewState.view=kind;}
    ${stateFunctions}
    function inspect(){return JSON.parse(JSON.stringify({state:viewState,presentation,geomSource,roomCameraFocused,selectedFurniture,
      controls,floors:floorGroups.map(e=>e.group.visible),hash:history.value||'',snapshot:!!indoorSnapshot,angle:exteriorAngle}));}
    ({inspect,enter(b,angle){enterExterior(b,angle,true);return inspect();},leave(){leaveExterior(true);return inspect();},
      scope(b,f,r=''){setScope(b,f,r,true,true);return inspect();},restore(value){location.hash=value;restoreHash();return inspect();}});`,
    {controls,buildings,floorGroups,meshById,DATA:{buildings,facade:shared.facade},URLSearchParams,location:{hash:''},
      document:{getElementById:id=>controls[id]},history:{replaceState(_s,_t,value){/* assign VM variable through the provided hook below */ this.value=value;}}});
  return Object.fromEntries(Object.keys(api).map(key=>[key,(...args)=>json(api[key](...args))]));
}

test('production exterior state saves/restores exact indoor controls, room focus and selected scope',()=>{
  const api=stateHarness(),before=api.inspect();
  const exterior=api.enter('B','oblique');
  assert.deepEqual(exterior.state,{building:'B',floor:'',room:'',view:'exterior'});
  assert.equal(exterior.controls.cut.value,'1000');assert.equal(exterior.controls.explode.value,'0');
  assert.equal(exterior.controls.navigation.checked,false);assert.equal(exterior.roomCameraFocused,false);
  assert.equal(exterior.floors.filter(Boolean).length,4);assert.equal(exterior.angle,'oblique');
  assert.equal(new URLSearchParams(exterior.hash.slice(1)).get('view'),'exterior');
  assert.equal(new URLSearchParams(exterior.hash.slice(1)).get('floor'),null);
  api.enter('C','front'); // Must not overwrite the earlier indoor snapshot.
  const returned=api.leave();
  for(const key of ['state','presentation','geomSource','roomCameraFocused','selectedFurniture','controls','floors'])assert.deepEqual(returned[key],before[key],key);
  assert.equal(returned.snapshot,false);
});

test('actual hash restore ignores stale exterior room/floor and removes forced settings on an indoor hash',()=>{
  const api=stateHarness();
  const exterior=api.restore('#mode=diagnostic&building=B&floor=floor-1&room=A:floor-2:master-bath&view=exterior&focus=room&angle=oblique');
  assert.deepEqual(exterior.state,{building:'B',floor:'',room:'',view:'exterior'});
  assert.equal(exterior.presentation,'tour');assert.equal(exterior.roomCameraFocused,false);
  const indoor=api.restore('#mode=tour&building=C&floor=floor-1&room=C:floor-1:elder&view=plan&focus=room');
  assert.deepEqual(indoor.state,{building:'C',floor:'floor-1',room:'C:floor-1:elder',view:'plan'});
  assert.equal(indoor.controls.navigation.checked,true);assert.equal(indoor.controls['full-walls'].checked,false);
  assert.equal(indoor.controls.cut.value,'900');assert.equal(indoor.controls.explode.value,'600');assert.equal(indoor.roomCameraFocused,true);
  assert.equal(indoor.snapshot,false);
});

test('floor navigation exits exterior; invalid IDs remain safe and three-building view keeps all 12 floors',()=>{
  const api=stateHarness();api.enter('B','front');
  const b=api.scope('B','floor-1');assert.equal(b.state.view,'front');assert.equal(b.state.floor,'floor-1');
  assert.equal(b.floors.filter(Boolean).length,1);
  const all=api.restore('#view=exterior&building=NOT_A_BUILDING&floor=not-a-floor&room=missing&angle=bad');
  assert.deepEqual(all.state,{building:'',floor:'',room:'',view:'exterior'});
  assert.equal(all.floors.filter(Boolean).length,12);assert.equal(all.angle,'front');
});
