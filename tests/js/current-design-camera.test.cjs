'use strict';
// Small vector/camera math and stubbed draw-state checks only, never a scene,
// WebGL context, browser or complete model runtime.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ROOT=path.resolve(__dirname,'../..'),THREE=require('../../assets/vendor/three/three.min.js');
const template=fs.readFileSync(path.join(ROOT,'scripts/templates/model3d.html'),'utf8');
const local=fs.readFileSync(path.join(ROOT,'scripts/templates/current-design-camera.js'),'utf8');
const shared=template.match(/  function cameraFrameForBox\([\s\S]*?(?=  function focusScope\()/)[0]+template.match(/  function boxCorners\([\s\S]*?(?=  function frameLighting\()/)[0];
const math=vm.runInNewContext(shared+local+';({basisBodyPixelBudget,basisChooseRoomFrame,boxCorners,cameraFrameForBox});',{THREE});
const qa=require('../../scripts/check_current_design_playwright.cjs');
const study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/current-design-basis/review.json'),'utf8'));
const projected=(box,frame,width,height)=>{
  const camera=new THREE.PerspectiveCamera(45,width/height,.01,1000);
  camera.position.copy(frame.target).addScaledVector(frame.direction,frame.radius);camera.lookAt(frame.target);camera.updateMatrixWorld();
  return math.boxCorners(box).map(p=>p.project(camera).toArray());
};
for(const o of study.options)test('all selected actual-size products have readable projections: '+o.id,()=>{
  const spec=qa.closeupCases({options:[o]})[0],f=o.states[0].plans.floors.find(f=>f.id===spec.floor),r=f.rooms.find(r=>r.id===spec.room),g=r.geometry;
  // Include wall thickness and full-height architecture in the camera box;
  // never pretend that the cutaway has removed a product or shortened a wall.
  const box=new THREE.Box3(new THREE.Vector3(g.x_mm*.001-.08,-.12,-(g.y_mm+g.h_mm)*.001-.08),new THREE.Vector3((g.x_mm+g.w_mm)*.001+.08,3.1,-g.y_mm*.001+.08));
  const bodies=r.furniture.map(i=>({id:i.id,budget:math.basisBodyPixelBudget(i),box:new THREE.Box3(
    new THREE.Vector3(i.placement.aabb.minX*.001,0,-i.placement.aabb.maxY*.001),
    new THREE.Vector3(i.placement.aabb.maxX*.001,i.height_mm*.001,-i.placement.aabb.minY*.001))}));
  const before=JSON.stringify({box,bodies});
  for(const area of [{left:12,right:378,top:275,bottom:670,usable:true},{left:12,right:378,top:340,bottom:650,usable:true}]){
    const width=390,height=790,baseline=math.cameraFrameForBox(box,area,width,height,.6,.65,45),result=math.basisChooseRoomFrame(box,area,width,height,45,bodies,baseline);
    assert.ok(result.score>=result.baselineScore&&result.score>=1,JSON.stringify({id:o.id,score:result.score,baseline:result.baselineScore}));
    const rect=points=>{const xs=points.map(p=>(1+p[0])*width/2),ys=points.map(p=>(1-p[1])*height/2);return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};};
    const actual=rect(projected(box,result.frame,width,height));
    assert.ok(actual.left>=area.left&&actual.right<=area.right&&actual.top>=area.top&&actual.bottom<=area.bottom);
    for(const b of bodies){
      const r=rect(projected(b.box,result.frame,width,height)),budget=spec.items.find(i=>i.id===b.id),w=r.right-r.left,h=r.bottom-r.top;
      assert.ok(Math.min(w,h)>=budget.short&&Math.max(w,h)>=budget.long,b.id);
    }
  }
  assert.equal(JSON.stringify({box,bodies}),before,'camera must not change any room/body dimensions');
});
test('no products or unusable stage retains baseline, does not invent readable evidence',()=>{
  const box=new THREE.Box3(new THREE.Vector3(0,0,0),new THREE.Vector3(3,3,3)),area={left:12,right:378,top:250,bottom:650,usable:true};
  const baseline=math.cameraFrameForBox(box,area,390,790,.6,.65,45);
  for(const [a,b] of [[area,[]],[{...area,usable:false},[{box,budget:{short:40,long:96}}]]]){
    const r=math.basisChooseRoomFrame(box,a,390,790,45,b,baseline);assert.equal(r.frame,baseline);assert.equal(r.score,null);
  }
});
function runtime(overrides={}){
  const calls=[],queued=[],observed=[],area={left:12.2,right:377.8,top:300.4,bottom:650.8,usable:true};
  const c={THREE,DATA:{source:{current_design_basis:true}},presentation:'tour',roomCameraFocused:true,viewState:{room:'A:floor-2:ensuite-study'},
    stage:{clientWidth:390,clientHeight:790},facadeIsActive:()=>false,cameraViewportRect:()=>area,scene:{},camera:{},
    renderer:{setScissorTest:v=>calls.push(['test',v]),clear:()=>calls.push(['clear']),setScissor:(...r)=>calls.push(['scissor',...r]),
      render:()=>calls.push(['render']),getSize:v=>v.set(390,790),getScissorTest:()=>false},
    window:{requestAnimationFrame:fn=>queued.push(fn)},resize:()=>calls.push(['resize']),document:{getElementById:id=>({id})},
    ResizeObserver:class{constructor(cb){this.cb=cb;}observe(el){observed.push(el);}},...overrides};
  vm.createContext(c);vm.runInContext(local,c);return {c,calls,queued,observed,area,run:code=>vm.runInContext(code,c)};
}
test('mobile draw clears the whole canvas, clips in logical pixels, and always resets scissor state',()=>{
  const r=runtime();r.run('basisRenderFrame()');
  assert.deepEqual(r.calls,[['test',false],['clear'],['scissor',13,140,364,349],['test',true],['render'],['test',false]]);
  const e=r.run('basisCameraEvidence()');assert.equal(e.lastDraw.clipped,true);assert.equal(e.lastDraw.clearedOutside,true);assert.equal(e.scissorTestRestored,true);
  assert.equal(e.lastDraw.area.top,301);assert.equal(e.lastDraw.area.bottom,650);
});
test('a failed draw restores renderer scissor state without inventing completed draw evidence',()=>{
  const r=runtime();r.c.renderer.render=()=>{throw Error('draw failed');};
  assert.throws(()=>r.run('basisRenderFrame()'),/draw failed/);assert.deepEqual(r.calls.at(-1),['test',false]);
  assert.equal(r.run('basisCameraEvidence().lastDraw'),null);
});
for(const change of ['overview','desktop','diagnostic','history','unusable'])test('full canvas is restored without hiding rooms: '+change,()=>{
  const r=runtime();r.run('basisRenderFrame()');r.calls.length=0;
  if(change==='overview')r.c.roomCameraFocused=false;if(change==='desktop')r.c.stage.clientWidth=1080;if(change==='diagnostic')r.c.presentation='diagnostic';
  if(change==='history')r.c.DATA.source={c_integrated_review:true};if(change==='unusable')r.area.usable=false;
  r.run('basisRenderFrame()');assert.deepEqual(r.calls,[['test',false],['render'],['test',false]]);
  const e=r.run('basisCameraEvidence()');assert.equal(e.lastDraw.clipped,false);assert.equal(e.lastDraw.area,null);
  assert(!/\.visible\s*=/.test(local));assert(!/setSize\(|scale\.set|position\.set/.test(local));
});
test('panel and overlay resize requests coalesce into one animation frame, no timers or polling',()=>{
  const r=runtime();r.run('basisScheduleResize();basisScheduleResize();basisScheduleResize()');assert.equal(r.queued.length,1);assert.equal(r.calls.length,0);
  r.queued.shift()();assert.deepEqual(r.calls,[['resize']]);r.run('basisScheduleResize()');assert.equal(r.queued.length,1);
  r.run('basisObserveViewport()');assert.equal(r.observed.length,6);assert(!/setInterval|setTimeout/.test(local));
});
