'use strict';
// Small renderer/control units with boxes only; no complete Three.js scene or WebGL.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const qa=require('../../scripts/check_c_stair_merged_playwright.cjs');
const root=path.resolve(__dirname,'../..'),prepared=qa.preflight(root);
const text=fs.readFileSync(path.join(root,'structured/candidates/kaohsiung-house-options-3d.html'),'utf8');
const payload=JSON.parse(text.match(/^\s*var DATA = (.+);\s*$/m)[1]).kaohsiung_options;
const selected=payload.options.find(o=>o.id==='c-split').states[0].model;
function smallRuntime(model,floorId){
 const nodes=new Map(),parts=[];
 function element(tag){return {tag,children:[],style:{},handlers:{},value:'',textContent:'',
  appendChild(child){this.children.push(child);if(child.id)nodes.set(child.id,child);return child;},
  setAttribute(k,v){this[k]=v;},addEventListener(k,fn){this.handlers[k]=fn;}};}
 const host=element('section');nodes.set('bc-study-controls',host);nodes.set('full-walls',{checked:false});
 const document={body:{dataset:{}},createElement:element,getElementById:id=>nodes.get(id)||null};
 const meshes=[];
 for(const floor of model.buildings[0].floors)for(const cell of floor.cells.filter(c=>c.tour_active)){
  const group={visible:floor.id===floorId,parent:{visible:true}};
  meshes.push({userData:{cell,floor,building:model.buildings[0],shell:group,edges:{}},parent:group,material:{opacity:.2,depthWrite:true}});
 }
 const context={DATA:model,document,URL,URLSearchParams,location:{href:'file:///model.html?scheme=c-split',search:'?scheme=c-split'},
  history:{replaceState(){}},MM:.001,wz:y=>-y*.001,presentation:'tour',viewState:{room:'',floor:floorId},studyChoice:{id:'c-split'},pickables:meshes,
  featuresOf:cell=>cell.tour_features,trackArchitecturePart(){},applyViewPreset(){},
  mode:'kind',overlappingKeys:{},furnitureIsVisible:()=>true,renderLegend(){},
  PROV_STYLE:{auto:{color:0,opacity:1},declared:{color:0,opacity:1},measured:{color:0,opacity:1}},
  roomFloorMaterial:()=>({opacity:1,depthWrite:true}),
  solidMaterial:(_color,opacity)=>({opacity,depthWrite:true}),lineMaterial:()=>({}),
  THREE:{DoubleSide:2,MeshBasicMaterial:class{constructor(options){Object.assign(this,options);}}},
  scene:{traverse(fn){parts.forEach(fn);}},
  architectureBox(group,x,y,z,w,h,d,color,opacity){
   const p={userData:{},visible:true,parent:group,position:{x,y,z},scale:{x:w,y:h,z:d},material:{opacity:opacity??1}};
   parts.push(p);return p;
  }};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(root,'scripts/templates/c-stair-merged-runtime.js'),'utf8'),context);
 // Run the real generated colour pass too: applyLayout calls it after building geometry.
 const start=text.indexOf('  function applyMode() {'),end=text.indexOf('  function renderLegend() {',start);
 assert.ok(start>=0&&end>start);vm.runInContext(text.slice(start,end),context);
 context.applyLayout=()=>{parts.length=0;for(const mesh of meshes)context.csBuildParts(mesh,mesh.userData.shell,mesh.userData.cell.tour_features);context.applyMode();};
 context.applyLayout();
 return {context,nodes,parts,evidence:()=>JSON.parse(JSON.stringify(context.csEvidence()))};
}
test('existing URL static preflight binds new C plus untouched other options',()=>{
 assert.deepEqual(prepared.counts,{options:5,states:9,floors:36,rooms:334,items:340});
 assert.equal(prepared.study.integration_revision,2);assert.equal(prepared.study.rendered_qa,'not-run');
 assert.equal(prepared.study.stair_display_revision,2);
 assert.ok(prepared.sourceFiles.includes('scripts/check_c_stair_merged_playwright.cjs'));
});
test('new runtime gates move actual box parameters for all independent states',()=>{
 for(const floorId of ['floor-1','floor-2']){
  const runtime=smallRuntime(selected,floorId),floor=prepared.selected.plans.floors.find(f=>f.id===floorId);
  qa.inspectStair(runtime.evidence(),floor,'open','open');
  assert.equal(runtime.nodes.get('c-stair-front-door').style.cssText.includes('44px'),true);
  for(const [front,side]of [['closed','closed'],['closed','open'],['open','closed']]){
   for(const [id,value]of [['c-stair-front-door',front],['c-stair-side-door',side]]){const select=runtime.nodes.get(id);select.value=value;select.handlers.change();}
   qa.inspectStair(runtime.evidence(),floor,front,side);
  }
 }
});
test('floor omission survives the actual generated colour pass and presentation changes',()=>{
 const runtime=smallRuntime(selected,'floor-2'),context=runtime.context;
 for(const mode of ['kind','provenance'])for(const presentation of ['tour','diagnostic','interior','tour']){
  context.mode=mode;context.presentation=presentation;context.applyLayout();context.applyMode();
  for(const mesh of context.pickables){
   const omitted=presentation==='tour'&&!!mesh.userData.cell.tour_features.c_stair_full_floor_omitted;
   assert.equal(mesh.userData.csFloorOmitted===true,omitted);
   if(omitted){assert.equal(mesh.material.opacity,0);assert.equal(mesh.material.depthWrite,false);}
   else assert.ok(mesh.material.opacity>0);
  }
 }
 qa.inspectStair(runtime.evidence(),prepared.selected.plans.floors[1],'open','open');
});
test('a fake label-only toggle or recapped upper floor fails inspection',()=>{
 const runtime=smallRuntime(selected,'floor-2'),floor=prepared.selected.plans.floors[1];
 const e=runtime.evidence();e.frontState='closed';assert.throws(()=>qa.inspectStair(e,floor,'closed','open'),/actual leaf movement/);
 const bad=runtime.evidence();bad.parts.push({id:'bad-full-floor',role:'floor',floor:'floor-2',visible:true,actualRectMm:[4720,9760,1200,270],actualTopMm:4000});
 assert.throws(()=>qa.inspectStair(bad,floor,'open','open'),/blocks the last incoming/);
 const opaque=runtime.evidence();opaque.floorOmissions[1].actualOpacity=1;assert.throws(()=>qa.inspectStair(opaque,floor,'open','open'),/Opaque full/);
});
test('C original control creates no selected-C controls or meshes',()=>{
 const model=payload.options.find(o=>o.id==='c-control').states[0].model;
 const runtime=smallRuntime(model,'floor-2');assert.equal(runtime.nodes.has('c-stair-controls'),false);
 assert.deepEqual(runtime.evidence(),{revision:1,active:false,parts:[],floorOmissions:[]});
});
test('a rejected stair state retains raw material evidence in the failed result',async()=>{
 const e=smallRuntime(selected,'floor-1').evidence();e.floorOmissions[0].actualOpacity=1;
 let evaluations=0;
 const page={on(){},async setViewportSize(){},async goto(){},async waitForFunction(){},async screenshot(){},
  locator:()=>({isVisible:async()=>false}),
  evaluate:async()=>evaluations++?{cStair:e}:{cStair:{active:false,parts:[]}}};
 const r=await qa.checkStairPages(page,'file:///project/','/tmp/qa',prepared.selected,qa.inspectStair);
 assert.equal(r.status,'failed');assert.equal(r.stairEvidence.length,0);
 assert.equal(r.failureEvidence.floor,'floor-1');assert.equal(r.failureEvidence.viewport,'desktop');
 assert.equal(r.failureEvidence.evidence.floorOmissions[0].actualOpacity,1);
 assert.match(r.error,/Opaque full/);
});
test('browser script parses without running a scene and old passing reports are rejected',()=>{
 const code=qa.makeBrowserScript('file:///project/','/tmp/qa',prepared);
 assert.equal(typeof new vm.Script('('+code+')').runInNewContext(),'function');
 assert.throws(()=>qa.validateReport({marker:'house-kaohsiung-options-qa',revision:2,status:'passed'},prepared),/No valid selected-C/);
 assert.throws(()=>qa.validateReport({marker:'house-c-stair-merged-qa',revision:1,integrationRevision:1,status:'passed'},prepared));
 assert.throws(()=>qa.validateReport({marker:'house-c-stair-merged-qa',revision:2,integrationRevision:1,status:'passed'},prepared));
 assert.throws(()=>qa.validateReport({marker:'house-c-stair-merged-qa',revision:3,integrationRevision:2,ac01RouteRevision:1,status:'passed'},prepared));
});
function ac01Evidence(floor){
 const review=prepared.study.c_ac01_review,b=review.riser_envelope_mm;
 return {revision:1,active:true,professionalApproval:'unknown',state:{floor},
  envelopes:[{visible:true,floor,rect_mm:[b[0],b[1],b[3]-b[0],b[4]-b[1]],bottom_z_mm:floor==='floor-1'?b[2]:4000,top_z_mm:floor==='floor-1'?4000:b[5]}],
  routes:[{id:'C-AC01',room:review.new_indoor_room,visible:true,cameraFit:false,
   points:Array.from(new Float32Array(review.route.polyline_mm.flatMap(p=>[p[0]/1000,p[2]/1000,-p[1]/1000])))}]};
}
test('C-AC01 requires real pipe coordinates and riser bounds, not source labels',()=>{
 for(const floor of ['floor-1','floor-2'])qa.inspectAc01(ac01Evidence(floor),prepared.study.c_ac01_review,floor);
 const bad=ac01Evidence('floor-1');bad.routes[0].points[0]+=1;
 assert.throws(()=>qa.inspectAc01(bad,prepared.study.c_ac01_review,'floor-1'),/Actual refrigerant line/);
 const missing=ac01Evidence('floor-2');missing.envelopes[0].visible=false;
 assert.throws(()=>qa.inspectAc01(missing,prepared.study.c_ac01_review,'floor-2'),/Actual riser/);
 const flat=ac01Evidence('floor-1');flat.envelopes[0].top_z_mm=3500;
 assert.throws(()=>qa.inspectAc01(flat,prepared.study.c_ac01_review,'floor-1'),/Actual riser/);
});
test('C-AC01 controls and actual box bounds appear only in the new C candidate',()=>{
 const runtime=smallRuntime(selected,'floor-2');
 vm.runInContext(fs.readFileSync(path.join(root,'scripts/templates/c-ac01-route-runtime.js'),'utf8'),runtime.context);
 for(const mesh of runtime.context.pickables)runtime.context.caBuildParts(mesh,mesh.userData.shell,mesh.userData.cell.tour_features);
 const e=JSON.parse(JSON.stringify(runtime.context.caEvidence()));
 e.state={floor:'floor-2'};e.routes=[];qa.inspectAc01(e,prepared.study.c_ac01_review,'floor-2');
 assert.ok(runtime.nodes.get('c-ac01-indoor-link').href.includes('C%3Afloor-1%3Aentrance'));
 const control=smallRuntime(payload.options.find(o=>o.id==='c-control').states[0].model,'floor-2');
 vm.runInContext(fs.readFileSync(path.join(root,'scripts/templates/c-ac01-route-runtime.js'),'utf8'),control.context);
 assert.equal(control.nodes.has('c-ac01-controls'),false);
});
test('all generated inline scripts are syntactically valid',()=>{
 let count=0;
 for(const m of text.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)){
  if(m[1].trim()){new vm.Script(m[1]);count++;}
 }
 assert.ok(count>=1);
});
