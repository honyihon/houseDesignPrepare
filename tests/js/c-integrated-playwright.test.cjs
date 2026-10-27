'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const qa=require('../../scripts/check_c_integrated_playwright.cjs');
const legacy=require('../../scripts/check_windows_playwright.cjs');
const root=path.resolve(__dirname,'../..');
const load=rel=>JSON.parse(fs.readFileSync(path.join(root,rel),'utf8').split(' = ')[1].replace(/;\s*$/,''));
const study=load('structured/candidates/c-integrated-options/layout.js');
const main=load('structured/candidates/furniture-plans/layout.js');
test('C manifest counts stay isolated from the original ABC and B32',()=>{
  assert.deepEqual(qa.validateStudy(study),{options:3,floors:12,rooms:117,items:141});
  assert.doesNotThrow(()=>legacy.preflightOpenings(main));
});
for(const [name,mutate] of [
  ['adopt',s=>{s.active_design='c-integrated-3600';}],
  ['approve',s=>{s.professional_status.site='approved';}],
  ['owner decision',s=>{s.owner_decisions[0].status='accepted';}],
  ['land expansion',s=>{s.frame_mm[1]+=100;}],
  ['guest window',s=>{s.options[0].plans.floors[1].rooms.find(r=>r.key==='guestroom2f').features.window_face=null;}],
  ['exercise over guest',s=>{s.options[0].plans.floors[2].rooms.find(r=>r.key==='fitness3f').features.exercise_review.zones[0].aabb.minY=5000;}],
  ['lower target',s=>{s.options[0].review.program.upper_area_checks[1].target_sqm=9;}],
  ['double count area',s=>{s.options[0].review.program.upper_area_checks[0].discussion_inset_sqm+=4;}],
  ['false finished area',s=>{s.options[0].review.program.upper_area_checks[0].finished_and_legal_area=22;}],
  ['manufacturer known',s=>{s.options[0].review.program.exercise.manual_source='imaginary';}],
])test('rejects '+name,()=>{const s=structuredClone(study);mutate(s);assert.throws(()=>qa.validateStudy(s));});
for(const [name,mutate] of [
  ['C oversized kitchen window',s=>{s.buildings[2].floors[1].rooms.find(r=>r.key==='kitchen2f').features.window_mm=3100;}],
  ['A maintenance door missing',s=>{const r=s.buildings[0].floors[2].rooms.find(r=>r.key==='entertainment');r.features.doors=r.features.doors.filter(d=>d.purpose!=='ac-maintenance');}],
  ['missing window validation',s=>{delete s.buildings[0].floors[1].rooms[0].features.window_review;}],
])test('main rejects '+name,()=>{const s=structuredClone(main);mutate(s);assert.throws(()=>legacy.preflightOpenings(s));});
test('serialized browser callback parses and does not depend on VM URL/Node globals',()=>{
  const source=qa.makeBrowserScript('file:///project/','C:/Temp/c-integrated',{options:3,floors:12,rooms:117,items:141});
  assert.doesNotThrow(()=>new vm.Script(source));
  assert.equal(/\b(?:require|process|new URL)\b/.test(qa.checkPages.toString()),false);
});
test('partial and fake reports are not passing browser evidence',()=>{
  const counts={options:3,floors:12,rooms:117,items:141};
  assert.throws(()=>qa.validateReport(null,counts));
  assert.throws(()=>qa.validateReport({marker:'house-c-integrated-cli-qa',status:'passed',counts,checks:[],screenshots:[]},counts));
  assert.equal(qa.findReport({isError:true}),null);
});
// Synthetic NDC corners exercise production pixel checks, not rendered proof.
const cases=qa.closeupCases(study);
function closeupFixture(c){
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[.8,.9].map(z=>[x/195-1,1-y/395,z])));
  return {option:c.option,room:c.room,floor:c.floor,building:'C',closeup:true,policy:'c-integrated-readable-v1',viewport:c.viewport,
    stage:{width:390,height:790},safeArea:{left:12,right:378,top:180,bottom:650,usable:true},visibleRoomIds:c.roomIds,
    roomCorners:corners(30,200,360,630),items:c.itemIds.map(id=>({id,corners:corners(70,230,210,430)}))};
}
test('pixel evidence is measured from corners and can be rechecked without trusting optimizer score',()=>{
  for(const c of cases){const evidence=qa.inspectCloseup(closeupFixture(c),c);
    assert.ok(evidence.occupiedFraction>.2);assert.equal(evidence.bodyRects.length,c.itemIds.length);
    assert.ok(evidence.bodyRects.every(r=>r.shortSidePx>=40&&r.longSidePx>=96));}
});
for(const defect of ['tiny-body','missing-body','wrong-body','wrong-room','missing-floor-room','under-controls','tiny-room','old-policy','nonfinite','behind-camera'])
  test('real closeup pixel check rejects '+defect,()=>{
    const c=cases[1],e=structuredClone(closeupFixture(c));
    if(defect==='tiny-body')e.items[0].corners=e.items[0].corners.map((p,n)=>[n<4?.001:-.001,p[1],p[2]]);
    if(defect==='missing-body')e.items.pop();
    if(defect==='wrong-body')e.items[0].id='unrelated-label';
    if(defect==='wrong-room')e.room='C:floor-1:elder';
    if(defect==='missing-floor-room')e.visibleRoomIds.pop();
    if(defect==='under-controls')e.safeArea.top=250;
    if(defect==='tiny-room')e.roomCorners=e.roomCorners.map(p=>[p[0]*.05,p[1]*.05,p[2]]);
    if(defect==='old-policy')e.policy=null;
    if(defect==='nonfinite')e.items[0].corners[0][0]=NaN;
    if(defect==='behind-camera')e.items[0].corners[0][2]=1.1;
    assert.throws(()=>qa.inspectCloseup(e,c));
  });
test('old browser pass and incomplete/forged pixel evidence cannot pass revision 2',()=>{
  const counts={options:3,floors:12,rooms:117,items:141};
  const report={marker:'house-c-integrated-cli-qa',revision:2,displayRevision:2,status:'passed',counts,checks:[{passed:true}],
    screenshots:Array(14).fill('fixture-not-a-screenshot.png'),closeupEvidence:cases.map(closeupFixture)};
  assert.equal(qa.validateReport(report,counts,cases),report);
  for(const patch of [{revision:undefined},{displayRevision:1},{closeupEvidence:undefined},{closeupEvidence:report.closeupEvidence.slice(0,2)},
    {closeupEvidence:report.closeupEvidence.map(v=>({...v,roomCorners:v.roomCorners.map(p=>[p[0],1,p[2]])}))}])
    assert.throws(()=>qa.validateReport({...report,...patch},counts,cases));
  assert.throws(()=>qa.validateReport(report,counts),'expected case identities are required');
});
