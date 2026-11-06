'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const qa=require('../../scripts/check_kaohsiung_options_playwright.cjs');
const root=path.resolve(__dirname,'../..');
const zone={garden_mm:[2000,1650,4000,2250],soil_rects_mm:[[2115,1765,3770,900]],woody_points_mm:[[2590,2215]]};
function readoutRuntime(){
 const document={createElement:tag=>({tag,children:[],attributes:{},style:{},textContent:'',
  setAttribute(name,value){this.attributes[name]=value;},appendChild(child){this.children.push(child);}})};
 const context={document};vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(root,'scripts/templates/kaohsiung-options-overlay.js'),'utf8'),context);
 return context;
}
function evidence(){return {revision:1,option:'c-split',use:'daily',adopted:false,legalAndStructuralApproval:'unknown',soilDepthMm:null,parts:[
 {id:'garden',room:'C:floor-2:balcony2f',rect_mm:zone.garden_mm,visible:true,actualLinePointsMm:[[2000,1650],[6000,1650],[6000,3900],[2000,3900],[2000,1650]]},
 {id:'soil-0',room:'C:floor-2:balcony2f',rect_mm:zone.soil_rects_mm[0],visible:true,actualGeometry:{widthMm:3770,depthMm:900},actualCenterMm:[4000,2215]},
 {id:'trunk-0',room:'C:floor-2:balcony2f',visible:true},{id:'woody-0',room:'C:floor-2:balcony2f',visible:true}
]};}
test('actual soil mesh sizes and positions are required, not only source tags',()=>{
 const e=evidence();qa.inspectZones(e,zone,'C:floor-2:balcony2f','c-split','daily');
 e.parts[1].actualGeometry.widthMm=1;assert.throws(()=>qa.inspectZones(e,zone,'C:floor-2:balcony2f','c-split','daily'),/Actual soil geometry/);
});
test('unit-box mesh scales and local plan coordinates produce real soil bounds',()=>{
 const soil={userData:{khZone:{id:'soil-0',room:'C:floor-2:balcony2f',rect_mm:zone.soil_rects_mm[0]}},visible:true,
  geometry:{parameters:{width:1,height:1,depth:1}},scale:{x:3.77,y:.012,z:.9},position:{x:4,z:-2.215}};
 const context={MM:.001,scene:{traverse:fn=>fn(soil)},document:{body:{dataset:{studyOption:'c-split',studyUse:'daily'}}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'scripts/templates/kaohsiung-options-overlay.js'),'utf8'),context);
 const actual=context.khEvidence().parts[0];assert.equal(actual.actualGeometry.widthMm,3770);assert.equal(actual.actualGeometry.depthMm,900);
 assert.equal(actual.actualCenterMm[0],4000);assert.equal(actual.actualCenterMm[1],2215);
});
test('missing plant geometry, hidden soil, stale option and control pollution fail',()=>{
 for(const mutate of [e=>e.parts.pop(),e=>e.parts[1].visible=false,e=>e.option='b-rear-split']){
  const e=evidence();mutate(e);assert.throws(()=>qa.inspectZones(e,zone,'C:floor-2:balcony2f','c-split','daily'));
 }
 assert.throws(()=>qa.inspectZones(evidence(),null,'C:floor-2:balcony2f','c-split','daily'),/Control/);
});
test('browser script parses and does not reference Node-only equality or global document',()=>{
 const fn=new vm.Script('('+qa.makeBrowserScript('file:///x/','/tmp/qa',{}, {}, [])+')').runInNewContext();
 assert.equal(typeof fn,'function');assert.doesNotMatch(qa.checkPages.toString(),/document!==null/);
});
test('zero-furniture A balcony gets a real landscape and HVAC readout without changing model data',()=>{
 const report=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/kaohsiung-house-options/review.json'),'utf8'));
 const room=report.options.find(o=>o.id==='a-rear-study').states[0].plans.floors[1].rooms.find(r=>r.key==='balcony2');
 assert.equal(room.furniture.length,0);
 const before=JSON.stringify(room),runtime=readoutRuntime(),list={children:[],appendChild(child){this.children.push(child);}};
 runtime.khAppendEquipmentReadout(list,{id:room.id,furniture:room.furniture},room.features);
 assert.equal(list.children.length,1);const section=list.children[0];
 assert.equal(section.id,'kh-room-equipment');assert.equal(section.attributes['data-room'],room.id);
 const rows=section.children.filter(c=>c.attributes['data-kh-equipment-id']);
 assert.deepEqual(rows.map(r=>r.attributes['data-kh-equipment-id']),['empty-furniture','garden','soil','woody','hvac-outdoor-A-AC04','hvac-outdoor-A-AC05']);
 assert.ok(rows.find(r=>r.attributes['data-kh-equipment-id']==='garden').textContent.includes('8㎡'));
 assert.ok(rows.find(r=>r.attributes['data-kh-equipment-id']==='soil').textContent.includes('2.85㎡'));
 assert.ok(rows.find(r=>r.attributes['data-kh-equipment-id']==='hvac-outdoor-A-AC04').textContent.includes('900×350×800'));
 assert.equal(JSON.stringify(room),before);
});
test('each independent state exposes its own exact equipment rows, including the C control',()=>{
 const p=qa.preflight(root),runtime=readoutRuntime();
 for(const c of p.cases){
  const state=p.study.options.find(o=>o.id===c.option).states.find(s=>s.id===c.use);
  const room=state.plans.floors[1].rooms.find(r=>r.id===c.room);
  const rows=runtime.khEquipmentRows({furniture:room.furniture},room.features);
  const e=JSON.parse(JSON.stringify({displayRevision:2,option:c.option,use:c.use,room:c.room,panelOpen:true,box:{width:350,height:360},rows}));
  qa.inspectEquipment(e,c);
  const wrong=structuredClone(e);wrong.rows=[{id:'empty-furniture',text:'本區沒有家具'}];
  assert.throws(()=>qa.inspectEquipment(wrong,c),/Incomplete/);
  const closed=structuredClone(e);closed.panelOpen=false;assert.throws(()=>qa.inspectEquipment(closed,c),/Incomplete/);
  const shifted=structuredClone(e);shifted.room='unrelated-room';assert.throws(()=>qa.inspectEquipment(shifted,c),/Incomplete/);
  const badDimensions=structuredClone(e);badDimensions.rows.find(r=>r.id.startsWith('hvac-')).text='室外機（未核）';
  assert.throws(()=>qa.inspectEquipment(badDimensions,c),/identity\/dimensions/);
 }
});
test('structured results are discovered under CLI text and missing passes are rejected',()=>{
 const r={marker:'house-kaohsiung-options-qa',status:'failed'};
 assert.deepEqual(qa.findReport({content:[{text:JSON.stringify(r)}]}),r);
 assert.equal(qa.findReport({status:'passed'}),null);
 assert.throws(()=>qa.validateReport({...r,status:'passed',revision:1,counts:{}},{},[]),/Incomplete/);
});
test('public-source guard rejects traversal and private path names',()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'kh-qa-unit-'));
 try{
  fs.mkdirSync(path.join(temp,'inputs'));fs.writeFileSync(path.join(temp,'inputs','source.json'),'{}');
  assert.equal(qa.publicFile(temp,'inputs/source.json'),path.join(temp,'inputs','source.json'));
  for(const value of ['inputs/../source.json','inputs/private/data.json','/tmp/data','inputs/.hidden'])assert.throws(()=>qa.publicFile(temp,value));
 }finally{fs.rmSync(temp,{recursive:true,force:true});}
});
test('generated package preflight reads no browser and agrees with all independent data',()=>{
 const p=qa.preflight(root);
 assert.deepEqual(p.counts,{options:5,states:9,floors:36,rooms:334,items:340});
 assert.equal(p.cases.length,9);assert.equal(p.study.adopted,false);assert.equal(p.study.rendered_qa,'not-run');
 assert.equal(p.study.display_revision,2);
 assert.equal(p.study.historical_input_resolution.length,2);
});
