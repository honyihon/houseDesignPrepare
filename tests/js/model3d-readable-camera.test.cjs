'use strict';
// Vector/camera projections only: never construct a scene or WebGL renderer.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),THREE=require('../../assets/vendor/three/three.min.js');
const template=fs.readFileSync(path.join(root,'scripts/templates/model3d.html'),'utf8');
const helpers=template.match(/  function cameraFrameForBox\([\s\S]*?(?=  function focusScope\()/)[0];
const corners=template.match(/  function boxCorners\([\s\S]*?(?=  function frameLighting\()/)[0];
const math=vm.runInNewContext(helpers+corners+';({cameraFrameForBox,frameBodyRect,chooseReadableRoomFrame,boxCorners});',{THREE});
const area={left:12,right:378,top:180,bottom:650,usable:true};
const project=(box,frame,width,height)=>{
  const camera=new THREE.PerspectiveCamera(45,width/height,.01,1000);
  camera.position.copy(frame.target).addScaledVector(frame.direction,frame.radius);camera.lookAt(frame.target);camera.updateMatrixWorld();
  const p=math.boxCorners(box).map(v=>v.project(camera)),xs=p.map(p=>(1+p.x)*width/2),ys=p.map(p=>(1-p.y)*height/2);
  return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};
};
test('pure fitter and actual Three camera agree on off-centre safe-area projection',()=>{
  const box=new THREE.Box3(new THREE.Vector3(-1,-.12,-5),new THREE.Vector3(2,2.6,1));
  for(const [width,height,theta,phi] of [[390,790,0,.25],[390,790,.6,.65],[844,336,-.6,1],[1080,900,1.2,.45]]){
    const a={left:12,right:width-12,top:Math.min(180,height*.3),bottom:height-100,usable:true};
    const frame=math.cameraFrameForBox(box,a,width,height,theta,phi,45),r=math.frameBodyRect(box,frame,width,height),actual=project(box,frame,width,height);
    for(const key of ['left','right','top','bottom'])assert.ok(Math.abs(r[key]-actual[key])<1e-6,key);
    assert.ok(r.left>=a.left&&r.right<=a.right&&r.top>=a.top&&r.bottom<=a.bottom,'whole real box stays outside overlays');
  }
});
const s=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/c-integrated-options/layout.js'),'utf8').split(' = ')[1].replace(/;\s*$/,''));
for(const [n,o] of s.options.entries())test('readable C camera improves catalog-body projections without moving anything: '+o.id,()=>{
  const f=o.plans.floors[n],r=f.rooms.find(r=>r.key===['public-bath','guestroom2f','fitness3f'][n]),g=r.geometry;
  const box=new THREE.Box3(new THREE.Vector3(g.x_mm*.001,-.12,-(g.y_mm+g.h_mm)*.001),new THREE.Vector3((g.x_mm+g.w_mm)*.001,2.6,-g.y_mm*.001));
  const bodies=r.furniture.map(i=>({id:i.id,primary:['bed','treadmill','toilet','vanity'].includes(i.shape),box:
    new THREE.Box3(new THREE.Vector3(i.placement.aabb.minX*.001,0,-i.placement.aabb.maxY*.001),
      new THREE.Vector3(i.placement.aabb.maxX*.001,i.height_mm*.001,-i.placement.aabb.minY*.001))}));
  const snapshot=JSON.stringify({box,bodies}),baseline=math.cameraFrameForBox(box,area,390,790,.6,.65,45);
  const result=math.chooseReadableRoomFrame(box,area,390,790,45,bodies,baseline);
  assert.ok(result.score>=result.baselineScore&&result.score>=1,JSON.stringify({score:result.score,baseline:result.baselineScore}));
  assert.equal(JSON.stringify({box,bodies}),snapshot,'fit must never resize/translate models');
  const room=project(box,result.frame,390,790);assert.ok(room.left>=area.left&&room.right<=area.right&&room.top>=area.top&&room.bottom<=area.bottom);
});
test('empty furniture or unusable viewport keeps original camera',()=>{
  const box=new THREE.Box3(new THREE.Vector3(0,0,0),new THREE.Vector3(2,2,4)),baseline=math.cameraFrameForBox(box,area,390,790,.6,.65,45);
  for(const [a,bodies] of [[area,[]],[{...area,usable:false},[{primary:true,box}]]]){
    const result=math.chooseReadableRoomFrame(box,a,390,790,45,bodies,baseline);assert.equal(result.frame,baseline);assert.equal(result.score,null);
  }
});
test('camera optimization stays opt-in; ABC, B32, plan and desktop retain original angles',()=>{
  const focus=template.match(/  function focusScope\([\s\S]*?(?=  function boxCorners\()/)[0];
  for(const [source,presentation,width,kind] of [[{},'tour',390,'front'],[{b32_entry_options:true},'tour',390,'front'],
    [{c_integrated_review:true},'tour',1080,'front'],[{c_integrated_review:true},'tour',390,'plan'],[{c_integrated_review:true},'diagnostic',390,'front']]){
    const context={THREE,DATA:{source},presentation,viewState:{building:'C',floor:'floor-1',room:'C:floor-1:public-bath'},roomCameraFocused:true,
      stage:{clientWidth:width,clientHeight:790},camera:{fov:45},spherical:{},target:new THREE.Vector3(),furnitureEntries:[],
      scopedViewBox:()=>new THREE.Box3(new THREE.Vector3(0,0,0),new THREE.Vector3(2,2,2)),facadeIsActive:()=>false,
      frameLighting(){},updateRoomCutaway(){},cameraViewportRect:()=>({...area,right:width-12})};
    const result=vm.runInNewContext(helpers+corners+focus+';focusScope('+JSON.stringify(kind)+');({fit:cameraFitState,spherical});',context);
    assert.equal(result.fit.closeupPolicy,null);assert.equal(result.spherical.theta,kind==='plan'?Math.PI:presentation!=='diagnostic'?.6:0);
    assert.equal(result.spherical.phi,kind==='plan'?.1:presentation!=='diagnostic'?.65:Math.PI*.34);
  }
});
