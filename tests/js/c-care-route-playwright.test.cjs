'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_c_care_route_playwright.cjs'),entry=require('../../scripts/check_c_care_entry_playwright.cjs'),ROOT=path.resolve(__dirname,'../..');
const study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-route/review.json'),'utf8'));
const counts={options:2,states:5,floors:20,rooms:195,items:250};
const actualLeaves=leaves=>leaves.map(l=>{const [x,y,w,d]=l.rect_mm;return {...l,actualBoundsMm:{minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:l.height_mm}};});
const actualRoutes=routes=>routes.map(r=>({...r,actualPointsMm:structuredClone(r.points_mm)}));
test('independent two-option/five-state package is source-bound and previous verified packages still preflight',()=>{
  const p=qa.preflight(ROOT);assert.deepEqual(p.counts,counts);assert.equal(p.closeupCases.length,5);
  assert.deepEqual(p.mainCounts,{floors:12,rooms:112,items:128});assert.equal(p.study.rendered_qa,'not-run');
  assert.deepEqual(p.closeupCases.map(c=>c.room.split(':').at(-1)),['elder','dining','dining','elder','elder']);
});
test('actual street and sliding leaf meshes are full-height and independently open/closed',()=>{
  for(const s of study.options[1].states){const expected=entry.leafSpecs(s);assert.equal(expected.length,3);
    assert.equal(entry.inspectLeaves(actualLeaves(expected),expected).length,3);
    const street=expected.find(l=>l.id==='street');assert.equal(street.state,s.id==='street-closed'?'closed':'open');
  }
});
const expected=qa.routeSpecs(study.options[1].states[0]);
test('route/sweep evidence requires the actual polyline vertices, not just declared metadata',()=>{
  assert.equal(qa.inspectRoutes(actualRoutes(expected),expected).length,3);assert.deepEqual(qa.inspectRoutes([],[]),[]);
});
for(const kind of ['missing','duplicate','metadata-only','wrong-point','nonfinite','state','room','kind'])test('actual route evidence rejects '+kind,()=>{
  const a=actualRoutes(expected);if(kind==='missing')a.pop();if(kind==='duplicate')a[1]=a[0];if(kind==='metadata-only')delete a[0].actualPointsMm;
  if(kind==='wrong-point')a[0].actualPointsMm[0][0]+=5;if(kind==='nonfinite')a[0].actualPointsMm[0][0]=NaN;
  if(kind==='state')a[0].blocked=true;if(kind==='room')a[0].room='C:floor-2:living2f';if(kind==='kind')a[0].kind='approved';
  assert.throws(()=>qa.inspectRoutes(a,expected));
});
test('owner browser script compiles standalone, checks actual meshes/mobile interactions and uses only the new route package',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/route',study,counts,qa.mobileCases(study));
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const text of ['Actual paired aperture/room parity','Actual unscaled retained furniture','inspectRoutes','inspectLeaves','equipment-return','overview',"ready('c-route-control','baseline')"])
    assert(code.includes(text),text);
  assert(!code.includes('c-care-entry.html'));assert(code.includes('house-c-care-route-qa'));assert(code.includes('route-adoption-warning'));
});
test('viewer inline scripts compile and retain local fit, actual leaf and route geometry debug',()=>{
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-route-3d.html'),'utf8');
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
  for(const s of ['careRoute:careRouteEvidence()','careEntry:careEntryEvidence()','actualPointsMm:points','DATA.source.c_care_route','c-care-route.html#'])assert(text.includes(s));
  assert(!text.includes('DATA.source.c_care_entry'));assert(!text.includes('DATA.source.current_design_basis'));
});
function passing(){
  const cases=qa.mobileCases(study),safeArea={left:12,right:378,top:220,bottom:680,usable:true};
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
  return {marker:'house-c-care-route-qa',revision:2,displayRevision:2,status:'passed',counts,
    checks:[{name:'actual meshes',passed:true}],screenshots:Array.from({length:12},(_,n)=>n+'.png'),mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>{
      const overview=phase==='overview';return {phase,option:c.option,use:c.use,building:'C',floor:'floor-1',room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
        viewport:c.viewport,stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,
        fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2'},
        draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
        overlays:['stage-title','room-view-actions','compass'].map(id=>({id,left:14,right:376,top:60,bottom:210})).concat(['orientation','study-stage-note'].map(id=>({id,left:14,right:376,top:690,bottom:730}))),
        roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)}))};
    })),leafEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,leaves:actualLeaves(entry.leafSpecs(s))}))),
    routeEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,outlines:actualRoutes(qa.routeSpecs(s))})))};
}
test('completion requires every raw mobile phase, actual leaf bodies and actual routes per independent state',()=>{
  const r=passing(),p={study,counts,closeupCases:qa.mobileCases(study)};assert.equal(qa.validateReport(r,p).status,'passed');
  for(const kind of ['leaf','routes','duplicate','fake-point','mobile','old-marker']){
    const a=passing();if(kind==='leaf')a.leafEvidence.pop();if(kind==='routes')a.routeEvidence.pop();if(kind==='duplicate')a.routeEvidence[1]=a.routeEvidence[0];
    if(kind==='fake-point')a.routeEvidence[1].outlines[0].actualPointsMm[0][0]=0;if(kind==='mobile')a.mobileEvidence.pop();if(kind==='old-marker')a.marker='house-c-care-entry-qa';
    assert.throws(()=>qa.validateReport(a,p));
  }
});
test('owner run closes only its one session; denial is incomplete, never retried or installed',()=>{
  for(const good of [true,false]){
    const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-route-unit-')),calls=[];
    const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify(good?{result:passing()}:{isError:true}):args[4]==='close'?' {"status":"closed"}':'{}'};};
    const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study,counts,closeupCases:qa.mobileCases(study)},output,execute);
    assert.equal(r.status,good?'passed':'incomplete');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
    assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
  }
});
test('front dining and private bedroom mobile cases fit full-size bodies using pure camera math only',()=>{
  const THREE=require('../../assets/vendor/three/three.min.js'),source=fs.readFileSync(path.join(ROOT,'scripts/templates/model3d.html'),'utf8');
  const helpers=source.match(/  function cameraFrameForBox\([\s\S]*?(?=  function focusScope\()/)[0]+source.match(/  function boxCorners\([\s\S]*?(?=  function frameLighting\()/)[0];
  const local=fs.readFileSync(path.join(ROOT,'scripts/templates/current-design-camera.js'),'utf8');
  const m=vm.runInNewContext(helpers+local+';({cameraFrameForBox,basisChooseRoomFrame,basisBodyPixelBudget,frameBodyRect});',{THREE});
  for(const c of qa.mobileCases(study)){
    const o=study.options.find(o=>o.id===c.option),s=o.states.find(s=>s.id===c.use),r=s.plans.floors[0].rooms.find(r=>r.id===c.room),g=r.geometry;
    const box=new THREE.Box3(new THREE.Vector3(g.x_mm*.001-.08,-.12,-(g.y_mm+g.h_mm)*.001-.08),new THREE.Vector3((g.x_mm+g.w_mm)*.001+.08,3.6,-g.y_mm*.001+.08));
    const bodies=r.furniture.map(i=>({id:i.id,budget:m.basisBodyPixelBudget(i),box:new THREE.Box3(new THREE.Vector3(i.placement.aabb.minX*.001,i.placement.mount_height_mm*.001,-i.placement.aabb.maxY*.001),
      new THREE.Vector3(i.placement.aabb.maxX*.001,(i.placement.mount_height_mm+i.height_mm)*.001,-i.placement.aabb.minY*.001))}));
    const before=JSON.stringify({box,bodies}),a={left:12,right:378,top:275,bottom:650,usable:true};
    const fitted=m.basisChooseRoomFrame(box,a,390,790,45,bodies,m.cameraFrameForBox(box,a,390,790,.6,.65,45));assert.ok(fitted.score>=1,c.use+' camera budget');
    for(const b of bodies){const v=m.frameBodyRect(b.box,fitted.frame,390,790),spec=c.items.find(i=>i.id===b.id),w=v.right-v.left,h=v.bottom-v.top;
      assert(Math.min(w,h)>=spec.short&&Math.max(w,h)>=spec.long,c.use+' actual body-pixel target');}
    assert.equal(JSON.stringify({box,bodies}),before,'never scale source room/furniture');
  }
});
