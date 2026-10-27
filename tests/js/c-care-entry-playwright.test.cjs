'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_c_care_entry_playwright.cjs'),ROOT=path.resolve(__dirname,'../..');
const study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-entry/review.json'),'utf8'));
test('care package remains C-only and source-bound, primary five-option package still verifies',()=>{
  const p=qa.preflight(ROOT);assert.deepEqual(p.counts,{options:2,states:3,floors:12,rooms:117,items:150});assert.equal(p.closeupCases.length,3);
  assert.deepEqual(p.mainCounts,{floors:12,rooms:112,items:128});assert.equal(p.study.rendered_qa,'not-run');
});
const expected=qa.leafSpecs(study.options[1].states[0]);
const actualFor=leaves=>leaves.map(l=>{const [x,y,w,d]=l.rect_mm;return {...l,actualBoundsMm:{minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:l.height_mm}};});
const actual=()=>actualFor(expected);
test('actual full-height door meshes, not rectangle metadata alone, match every parked leaf',()=>{
  assert.equal(qa.inspectLeaves(actual(),expected).length,2);assert.deepEqual(qa.inspectLeaves([],[]),[]);
});
for(const bad of ['missing','duplicate','metadata-only','tiny','state','height','nonfinite','room'])test('door evidence rejects '+bad,()=>{
  const a=actual();if(bad==='missing')a.pop();if(bad==='duplicate')a[1]=a[0];if(bad==='metadata-only')delete a[0].actualBoundsMm;
  if(bad==='tiny')a[0].actualBoundsMm.maxX=a[0].actualBoundsMm.minX+600;if(bad==='state')a[0].state='closed';
  if(bad==='height')a[0].actualBoundsMm.maxHeight=100;if(bad==='nonfinite')a[0].actualBoundsMm.minX=NaN;if(bad==='room')a[0].room='C:floor-2:living2f';
  assert.throws(()=>qa.inspectLeaves(a,expected));
});
test('owner script is self-contained and checks actual apertures, leaves and unscaled products',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/check',study,{},qa.mobileCases(study));
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const name of ['Actual paired aperture/room parity','Actual unscaled retained furniture','inspectLeaves','equipment-return','overview','Visible first-viewport care non-adoption warning'])assert(code.includes(name));
});
test('every generated script compiles and all external links return to this comparison',()=>{
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-entry-3d.html'),'utf8');
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
  assert(text.includes('DATA.source.c_care_entry'));assert(!text.includes('DATA.source.current_design_basis'));
  assert(text.includes('careEntry:careEntryEvidence()'));assert(text.includes('new THREE.Matrix4().copy(m.parent.matrixWorld).invert()'));assert(!text.includes('htmlHref="current-design-basis.html#"'));
});
test('absent or old mobile evidence cannot be accepted as a passing care result',()=>{
  assert.throws(()=>qa.validateReport(null,{}));
  assert.throws(()=>qa.validateReport({marker:'house-c-care-entry-qa',revision:1,status:'passed'}, {counts:{},closeupCases:[]}));
});
function passing(){
  const cases=qa.mobileCases(study),safeArea={left:12,right:378,top:220,bottom:680,usable:true};
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
  return {marker:'house-c-care-entry-qa',revision:2,displayRevision:2,status:'passed',counts:{options:2,states:3,floors:12,rooms:117,items:150},
    checks:[{name:'actual meshes',passed:true}],screenshots:Array.from({length:8},(_,n)=>n+'.png'),mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>{
      const overview=phase==='overview';
      return {phase,option:c.option,use:c.use,building:'C',floor:'floor-1',room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
        viewport:c.viewport,stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,
        fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2'},
        draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
        overlays:['stage-title','room-view-actions','compass'].map(id=>({id,left:14,right:376,top:60,bottom:210})).concat(['orientation','study-stage-note'].map(id=>({id,left:14,right:376,top:690,bottom:730}))),
        roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)}))};
    })),leafEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,leaves:actualFor(qa.leafSpecs(s))})))};
}
test('completed care result requires all raw mobile phases and actual leaf bodies for each independent state',()=>{
  const report=passing(),prepared={study,counts:report.counts,closeupCases:qa.mobileCases(study)};
  assert.equal(qa.validateReport(report,prepared).status,'passed');
  for(const change of ['missing','duplicate','fake-body','missing-phase']){
    const r=passing();if(change==='missing')r.leafEvidence.pop();if(change==='duplicate')r.leafEvidence[1]=r.leafEvidence[0];
    if(change==='fake-body')r.leafEvidence[1].leaves[0].actualBoundsMm.maxHeight=1;if(change==='missing-phase')r.mobileEvidence.pop();
    assert.throws(()=>qa.validateReport(r,prepared));
  }
});
test('successful owner-run QA closes its one session and does not auto-install or retry',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-care-success-')),calls=[],report=passing();
  const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify({result:report}):args[4]==='close'?' {"status":"closed"}':'{}'};};
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study,counts:report.counts,closeupCases:qa.mobileCases(study)},output,execute);
  assert.equal(r.status,'passed');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
});
test('CLI denial is incomplete, uses one owned session and only closes that session',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-care-unit-')),calls=[];
  const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?' {"isError":true}':args[4]==='close'?' {"status":"closed"}':'{}'};};
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study:{},counts:{},closeupCases:[]},output,execute);
  assert.equal(r.status,'incomplete');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
  assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
});
test('new mobile elder views retain real-size furniture readability with the inherited pure camera fitter',()=>{
  // Camera/vector math only, never instantiate Scene or WebGLRenderer.
  const THREE=require('../../assets/vendor/three/three.min.js'),source=fs.readFileSync(path.join(ROOT,'scripts/templates/model3d.html'),'utf8');
  const helpers=source.match(/  function cameraFrameForBox\([\s\S]*?(?=  function focusScope\()/)[0]+source.match(/  function boxCorners\([\s\S]*?(?=  function frameLighting\()/)[0];
  const local=fs.readFileSync(path.join(ROOT,'scripts/templates/current-design-camera.js'),'utf8');
  const m=vm.runInNewContext(helpers+local+';({cameraFrameForBox,basisChooseRoomFrame,basisBodyPixelBudget,frameBodyRect});',{THREE});
  for(const o of study.options){
    const r=o.states[0].plans.floors[0].rooms.find(r=>r.key==='elder'),g=r.geometry;
    const box=new THREE.Box3(new THREE.Vector3(g.x_mm*.001-.08,-.12,-(g.y_mm+g.h_mm)*.001-.08),new THREE.Vector3((g.x_mm+g.w_mm)*.001+.08,3.6,-g.y_mm*.001+.08));
    const bodies=r.furniture.map(i=>({id:i.id,budget:m.basisBodyPixelBudget(i),box:new THREE.Box3(new THREE.Vector3(i.placement.aabb.minX*.001,i.placement.mount_height_mm*.001,-i.placement.aabb.maxY*.001),
      new THREE.Vector3(i.placement.aabb.maxX*.001,(i.placement.mount_height_mm+i.height_mm)*.001,-i.placement.aabb.minY*.001))}));
    const before=JSON.stringify({box,bodies}),a={left:12,right:378,top:275,bottom:650,usable:true};
    const f=m.basisChooseRoomFrame(box,a,390,790,45,bodies,m.cameraFrameForBox(box,a,390,790,.6,.65,45));
    assert.ok(f.score>=1,o.id+' readable actual-size bodies');assert.equal(JSON.stringify({box,bodies}),before,'no model/furniture scaling');
  }
});
