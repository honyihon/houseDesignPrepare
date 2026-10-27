'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_c_care_bath_playwright.cjs'),route=require('../../scripts/check_c_care_route_playwright.cjs'),entry=require('../../scripts/check_c_care_entry_playwright.cjs');
const ROOT=path.resolve(__dirname,'../..'),study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath/review.json'),'utf8'));
const counts={options:2,states:5,floors:20,rooms:195,items:250};
const actualAccessories=rows=>rows.map(c=>({...c,actualBoundsMm:qa.accessoryBounds(c)}));
const actualLeaves=rows=>rows.map(c=>{const [x,y,w,d]=c.rect_mm;return {...c,actualBoundsMm:{minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:c.height_mm}};});
const actualRoutes=rows=>rows.map(c=>({...c,actualPointsMm:structuredClone(c.points_mm)}));
test('bath package and all immutable parents preflight; all five mobile cases are actual private-bath closeups',()=>{
  const p=qa.preflight(ROOT);assert.deepEqual(p.counts,counts);assert.deepEqual(p.mainCounts,{floors:12,rooms:112,items:128});
  assert.equal(p.study.rendered_qa,'not-run');assert.equal(p.study.bath_display_revision,2);assert.equal(p.closeupCases.length,5);
  assert(p.closeupCases.every(c=>c.room==='C:floor-1:elder-bath'&&c.items.length===3&&c.items.every(i=>i.short===32&&i.long===64)));
});
const specs=qa.accessorySpecs(study.options[1].states[0]);
test('actual accessory bounds and states require complete eight-part geometry evidence; inspector is closure-free for owner CLI',()=>{
  assert.equal(qa.inspectAccessories(actualAccessories(specs),specs).length,8);assert.deepEqual(qa.inspectAccessories([],[]),[]);
  assert.equal(vm.runInNewContext('('+qa.inspectAccessories.toString()+')(actual,expected)',{actual:actualAccessories(specs),expected:specs}).length,8);
});
for(const kind of ['missing','duplicate','metadata-only','tiny-seat','short-arm','state','height','nonfinite','room'])test('accessory evidence rejects '+kind,()=>{
  const a=actualAccessories(specs);if(kind==='missing')a.pop();if(kind==='duplicate')a[1]=a[0];if(kind==='metadata-only')delete a[0].actualBoundsMm;
  if(kind==='tiny-seat')a[0].actualBoundsMm.maxX=a[0].actualBoundsMm.minX+100;if(kind==='short-arm')a[1].actualBoundsMm.maxHeight-=400;
  if(kind==='state')a[0].state='deployed';if(kind==='height')a[0].actualBoundsMm.maxHeight=200;if(kind==='nonfinite')a[0].actualBoundsMm.minY=NaN;
  if(kind==='room')a[0].room='C:floor-2:living2f';assert.throws(()=>qa.inspectAccessories(a,specs));
});
test('serialized owner workflow and all viewer scripts compile; no source gate or return link points to the old study',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/test',study,counts,qa.mobileCases(study));assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const s of ['inspectAccessories','Actual bath accessory list','Actual paired aperture/room parity','Actual unscaled retained furniture','equipment-return','overview',"ready('c-bath-refined','transfer')","ready('c-bath-control','baseline')"])
    assert(code.includes(s),s);
  assert(!code.includes('c-care-route.html'));assert(code.includes('house-c-care-bath-qa'));
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-3d.html'),'utf8');
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
  for(const s of ['careBath:careBathEvidence()','careRoute:careRouteEvidence()','careEntry:careEntryEvidence()','DATA.source.c_care_bath','care_bath_open_shower','care_bath_wall_hung','bath-equipment-list'])assert(text.includes(s));
  assert(!text.includes('DATA.source.c_care_route'));assert(!text.includes('DATA.source.current_design_basis'));
});
test('eight accessory meshes have actual correct full-size bounds in each pose, isolated tiny geometry only, never a Scene/WebGL runtime',()=>{
  const THREE=require('../../assets/vendor/three/three.min.js'),overlay=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-overlay.js'),'utf8');
  for(const s of study.options[1].states){
    const expected=qa.accessorySpecs(s),group=new THREE.Group(),features={care_bath_components:expected};
    vm.runInNewContext(overlay,{THREE,features,group,base:0,MM:.001,wz:y=>-y*.001,clipPlane:new THREE.Plane(new THREE.Vector3(0,-1,0),3.6)});
    group.updateMatrixWorld(true);
    const actual=group.children.map(p=>{const b=new THREE.Box3().setFromObject(p);return {...p.userData.careBath,room:'C:floor-1:elder-bath',actualBoundsMm:{minX:b.min.x*1000,maxX:b.max.x*1000,minY:-b.max.z*1000,maxY:-b.min.z*1000,minHeight:b.min.y*1000,maxHeight:b.max.y*1000}};});
    assert.equal(qa.inspectAccessories(actual,expected).length,8);
    group.traverse(p=>{p.geometry?.dispose();p.material?.dispose();});
  }
});
function passing(){
  const cases=qa.mobileCases(study),safeArea={left:12,right:378,top:220,bottom:680,usable:true};
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
  return {marker:'house-c-care-bath-qa',revision:2,displayRevision:2,bathDisplayRevision:2,status:'passed',counts,checks:[{name:'actual geometry',passed:true}],screenshots:Array.from({length:12},(_,n)=>n+'.png'),
    mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>{const overview=phase==='overview';return {phase,option:c.option,use:c.use,building:'C',floor:'floor-1',room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
      viewport:c.viewport,stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2',bathDisplayRevision:2,bodyProjectionBasis:'actual-mesh-bounds-not-nominal-empty-envelope'},
      draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
      overlays:['stage-title','room-view-actions','compass'].map(id=>({id,left:14,right:376,top:60,bottom:210})).concat(['orientation','study-stage-note'].map(id=>({id,left:14,right:376,top:690,bottom:730}))),
      roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)}))};})),
    leafEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,leaves:actualLeaves(entry.leafSpecs(s))}))),
    routeEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,outlines:actualRoutes(route.routeSpecs(s))}))),
    accessoryEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,components:actualAccessories(qa.accessorySpecs(s))})))};
}
test('completed bath QA requires all raw mobile phases, actual accessories, leaves and region geometry, not old passed',()=>{
  const r=passing(),p={study,counts,closeupCases:qa.mobileCases(study)};assert.equal(qa.validateReport(r,p).status,'passed');
  for(const kind of ['missing-accessory','duplicate-accessory','fake-seat','missing-phase','missing-leaf','missing-route','old-marker','old-display','old-fit']){
    const a=passing();if(kind==='missing-accessory')a.accessoryEvidence.pop();if(kind==='duplicate-accessory')a.accessoryEvidence[1]=a.accessoryEvidence[0];
    if(kind==='fake-seat')a.accessoryEvidence[1].components[0].actualBoundsMm.maxHeight=1;if(kind==='missing-phase')a.mobileEvidence.pop();
    if(kind==='missing-leaf')a.leafEvidence.pop();if(kind==='missing-route')a.routeEvidence.pop();if(kind==='old-marker')a.marker='house-c-care-route-qa';
    if(kind==='old-display')delete a.bathDisplayRevision;if(kind==='old-fit')delete a.mobileEvidence[0].fit.bathDisplayRevision;
    assert.throws(()=>qa.validateReport(a,p));
  }
});
test('owner run is one session only, no install/retry and incomplete on denial',()=>{
  for(const good of [true,false]){
    const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-bath-unit-')),calls=[];
    const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify(good?{result:passing()}:{isError:true}):args[4]==='close'?' {"status":"closed"}':'{}'};};
    const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study,counts,closeupCases:qa.mobileCases(study)},output,execute);
    assert.equal(r.status,good?'passed':'incomplete');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
    assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
  }
});
test('real thin basin and 2mm shower mesh regressions fit without changing 32/64px budgets or any geometry',()=>{
  const THREE=require('../../assets/vendor/three/three.min.js'),source=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-3d.html'),'utf8');
  const helpers=source.match(/  function cameraFrameForBox\([\s\S]*?(?=  function focusScope\()/)[0]+source.match(/  function boxCorners\([\s\S]*?(?=  function frameLighting\()/)[0];
  // Extract the exact fixture part builder and unmodified mesh construction,
  // but never initialize the page, Scene, WebGLRenderer or a complete floor.
  const fixtures=source.match(/  function furnitureParts\([\s\S]*?(?=  function furnitureColour\()/)[0]+source.match(/  function addFurniturePart\([\s\S]*?(?=  function addFurniture\()/)[0];
  const boxGeom=new THREE.BoxGeometry(1,1,1),roundGeom=new THREE.SphereGeometry(.5,20,12),cylinderGeom=new THREE.CylinderGeometry(.5,.5,1,24),wheelGeom=cylinderGeom.clone().rotateZ(Math.PI/2),edgeGeom=new THREE.EdgesGeometry(boxGeom);
  const material=new THREE.MeshBasicMaterial(),line=new THREE.LineBasicMaterial();
  const context={THREE,MM:.001,boxGeom,roundGeom,cylinderGeom,wheelGeom,softGeom:boxGeom,edgeGeom,furniturePickables:[],furnitureColour:()=>0xffffff,furnitureMaterial:()=>material,lineMaterial:()=>line};
  const m=vm.runInNewContext(helpers+fs.readFileSync(path.join(ROOT,'scripts/templates/current-design-camera.js'),'utf8')+fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-camera.js'),'utf8')+fixtures+';({cameraFrameForBox,basisChooseRoomFrame,bathChooseRoomFrame,basisBodyPixelBudget,frameBodyRect,boxCorners,visualParts,addFurniturePart});',context);
  try{for(const c of qa.mobileCases(study)){
    const s=study.options.find(o=>o.id===c.option).states.find(s=>s.id===c.use),r=s.plans.floors[0].rooms.find(r=>r.key==='elder-bath'),g=r.geometry;
    const box=new THREE.Box3(new THREE.Vector3(g.x_mm*.001-.08,-.12,-(g.y_mm+g.h_mm)*.001-.08),new THREE.Vector3((g.x_mm+g.w_mm)*.001+.08,3.6,-g.y_mm*.001+.08));
    const groups=[],bodies=r.furniture.map(item=>{
      const entry={item,group:new THREE.Group(),parts:[]};m.visualParts(item).forEach(p=>m.addFurniturePart(entry,p));
      entry.group.position.set(item.placement.center_x_mm*.001,item.mount_height_mm*.001,-item.placement.center_y_mm*.001);entry.group.rotation.y=-item.placement.rotation_deg*Math.PI/180;entry.group.updateMatrixWorld(true);groups.push(entry.group);
      return {id:item.id,budget:m.basisBodyPixelBudget(item),box:new THREE.Box3().setFromObject(entry.group)};
    });
    if(c.option==='c-bath-refined'){
      assert(Math.abs(bodies.find(b=>b.id.endsWith(':vanity')).box.getSize(new THREE.Vector3()).y-.17)<1e-6,'actual thin body, not 850mm nominal empty envelope');
      assert(Math.abs(bodies.find(b=>b.id.endsWith(':accessible-shower')).box.getSize(new THREE.Vector3()).y-.002)<1e-6,'actual open shower floor, not 2m nominal enclosure');
    }
    const before=JSON.stringify({box,bodies,groups:groups.map(g=>g.matrixWorld.toArray())});
    // First rect reproduces the failure's measured overlay budget; second
    // conservatively models the compact title/footer without hiding warnings.
    for(const area of [{left:12,right:378,top:231.78125,bottom:688.609375,usable:true},{left:12,right:378,top:210,bottom:716,usable:true}]){
      const baseline=m.cameraFrameForBox(box,area,390,790,.6,.65,45),old=m.basisChooseRoomFrame(box,area,390,790,45,bodies,baseline),f=m.bathChooseRoomFrame(box,area,390,790,45,bodies,baseline);
      assert(f.score>=1.02,c.option+'/'+c.use+' actual fixture visibility margin '+f.score);
      if(c.option==='c-bath-refined'&&area.top>230)assert(old.score<1,'old limited-angle camera really reproduces the thin-basin failure');
      const camera=new THREE.PerspectiveCamera(45,390/790,.01,1000);camera.position.copy(f.frame.target).addScaledVector(f.frame.direction,f.frame.radius);camera.lookAt(f.frame.target);camera.updateMatrixWorld();
      const project=b=>m.boxCorners(b).map(p=>p.project(camera).toArray());
      const raw=passing().mobileEvidence.find(e=>e.option===c.option&&e.use===c.use&&e.phase==='initial');
      raw.safeArea=area;raw.fit.area=area;raw.draw.area=area;raw.roomCorners=project(box);raw.items=bodies.map(b=>({id:b.id,corners:project(b.box)}));
      raw.overlays=raw.overlays.map(o=>({...o,top:o.top>600?area.bottom+10:60,bottom:o.top>600?area.bottom+30:area.top-10}));
      const inspected=require('../../scripts/check_current_design_playwright.cjs').inspectMobileView(raw,c);
      assert(inspected.bodyRects.every(b=>b.shortSidePx>=32&&b.longSidePx>=64),'same independent owner-run pixel requirements');
    }
    assert.equal(JSON.stringify({box,bodies,groups:groups.map(g=>g.matrixWorld.toArray())}),before,'camera does not scale, move or hide real room or fixtures');
  }}finally{for(const g of [boxGeom,roundGeom,cylinderGeom,wheelGeom,edgeGeom])g.dispose();material.dispose();line.dispose();}
});
test('failed mobile evidence survives the validation exception with real option, phase and projected corners',async()=>{
  const source=qa.pageCheckSource(),helper=source.match(/  const recordMobile=async\([\s\S]*?(?=  const warning=async)/)[0];
  const raw=passing().mobileEvidence[3],evidence=[],spec=qa.mobileCases(study)[1];raw.items[0].corners[0][0]=10;
  const fn=vm.runInNewContext(helper+';recordMobile;',{mobileEvidence:evidence,readMobile:async()=>raw,inspectMobileView:()=>{throw Error('actual body too small');}});
  await assert.rejects(()=>fn('initial',spec),/actual body too small/);assert.equal(evidence.length,1);assert.equal(evidence[0],raw);
  assert(qa.pageCheckSource().includes('await recordMobile(\'equipment-return\',spec)'));
});
test('compact mobile room title retains full name in tooltip and all adoption/approval warnings',()=>{
  const source=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-camera.js'),'utf8'),title={textContent:'',title:'',children:[],appendChild(e){this.children.push(e);}},name='孝親套衛比較（無固定玻璃／濕地分時轉位）';
  const context={document:{getElementById:()=>title,createElement:()=>({textContent:''})},stage:{clientWidth:390},presentation:'tour'};
  const sync=vm.runInNewContext(source+';bathSyncRoomTitle;',context);sync({userData:{cell:{key:'elder-bath'}}},name);
  assert.equal(title.title,name);assert.equal(title.textContent,'C 棟 · 1F · 孝親套衛比較');assert(title.children[0].textContent.includes('未採用／專業未核'));
  assert(!/\.visible\s*=|scale\.set|position\.set|setInterval|setTimeout/.test(source));
});
