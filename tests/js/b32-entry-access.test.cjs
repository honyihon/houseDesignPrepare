'use strict';
// File/door-graph checks only; no browser, renderer or whole scene runtime.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const qa=require('../../scripts/check_b32_entry_playwright.cjs');
const s=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../structured/candidates/b32-entry-options/layout.js'),'utf8').split(' = ')[1].replace(/;\s*$/,''));
const rooms=o=>Object.fromEntries(o.plans.floors[0].rooms.map(r=>[r.key,r]));
test('B32 rear and front paths are conditional from street, never granted by an alley',()=>{
  assert.equal(s.entry_access_revision,1);
  for(const o of s.options){
    const r=qa.validateEntryAccess(o,s.floors['floor-1']);
    assert.equal(r.unresolved_room_ids.length,0);assert.equal(r.rear_alley_used_as_public_root,false);
    for(const room of r.rooms)assert.equal(room.professional_acceptance,'unknown');
  }
});
for(const defect of ['unpaired','shifted','wrong-kind','missing-reserve','partial-reserve','blocked-reserve','missing-street','wrong-group','rear-root','fake-approval','fake-work-independence','bath-through'])
  test('independent B32 verifier rejects '+defect,()=>{
    const o=structuredClone(s.options[0]),source=structuredClone(s.floors['floor-1']),c=rooms(o),r=o.review.program.entry_access;
    const update=(key,change)=>{const record=r.rooms.find(v=>v.room_id===c[key].id);change(record);c[key].features.entry_access_review=structuredClone(record);c[key].features.access_reason=record.note;};
    if(['unpaired','shifted','wrong-kind'].includes(defect)){
      const list=c.corridor1.features.open_connections,edge=list.find(v=>v.neighbor===c.shrine.id);
      if(defect==='shifted')edge.ratio+=.1;
      else {list.splice(list.indexOf(edge),1);if(defect==='wrong-kind')c.corridor1.features.doors.push(edge);}
    }else if(defect==='missing-reserve')c.shrine.features.reserved_mm=c.shrine.features.reserved_mm.filter(z=>z.kind!=='circulation');
    else if(defect==='partial-reserve')c.shrine.features.reserved_mm.find(z=>z.kind==='circulation').aabb.minY+=300;
    else if(defect==='blocked-reserve')c.shrine.furniture[0].placement.aabb=structuredClone(c.shrine.features.reserved_mm.find(z=>z.kind==='circulation').aabb);
    else if(defect==='missing-street')c['shrine-front'].features.doors=c['shrine-front'].features.doors.filter(d=>d.purpose!=='ritual-entry');
    else if(defect==='wrong-group')source.rooms.bath1.group='another-bath';
    else if(defect==='rear-root')r.rear_alley_used_as_public_root=true;
    else if(defect==='fake-approval')update('storage',v=>v.professional_acceptance='approved');
    else if(defect==='fake-work-independence')update('work-reserve',v=>v.independent_work_access=true);
    else if(defect==='bath-through'){
      c.bath1.features.doors.push({neighbor:c['work-reserve'].id,face:'rear',ratio:.48,width_mm:1000});
      c['work-reserve'].features.doors.push({neighbor:c.bath1.id,face:'front',ratio:.5,width_mm:1000});
      update('work-reserve',v=>{v.route_room_ids=[...r.rooms.find(v=>v.room_id===c.bath1.id).route_room_ids,c['work-reserve'].id];});
    }
    assert.throws(()=>qa.validateEntryAccess(o,source));
  });

const vm=require('node:vm');
const collect=vm.runInNewContext('('+qa.collectNavigationLabels.toString()+')',{getComputedStyle:node=>node.css});
function labelNodes(option){
  const html=fs.readFileSync(require('node:path').join(__dirname,'../../structured/candidates/b32-entry-options-3d.html'),'utf8');
  const all=JSON.parse(html.match(/^\s*var DATA = (.+);\s*$/m)[1]).bc_options;
  const cells=all.options.find(o=>o.id===option).model.buildings[0].floors[0].cells;
  return cells.map(c=>({room:c.id,textContent:c.name+(c.tour_features.access_pending?' · 入口待定':''),
    hidden:c.tour_active===false,css:{display:'block',visibility:'visible'},getAttribute(){return this.room;},
    getBoundingClientRect(){return {width:120,height:24};}}));
}
for(const option of s.options)test('hidden legacy entry/IDF text must not fail current '+option.id+' navigation',()=>{
  const nodes=labelNodes(option.id),ids=option.plans.floors[0].rooms.map(r=>r.id),labels=collect(nodes);
  assert.ok(labels.some(v=>!v.visible&&v.text.includes('入口待定')),'real computed model retains hidden old labels');
  const review=qa.inspectNavigationLabels(labels,ids);
  assert.deepEqual([...review.visibleRoomIds].sort(),ids.sort());
  assert.ok(review.ignoredHiddenRoomIds.includes('B:floor-1:entry'));
  assert.ok(review.ignoredHiddenRoomIds.includes('B:floor-1:idf-cabinet'));
});
for(const defect of ['visible-legacy','visible-other-floor','duplicate-active','missing-active','hidden-active-pending','visible-active-pending','blank-active','all-hidden'])
  test('production label collector/checker still rejects '+defect,()=>{
    const option=s.options[0],nodes=labelNodes(option.id),ids=option.plans.floors[0].rooms.map(r=>r.id);
    const legacy=nodes.find(n=>n.room==='B:floor-1:entry'),active=nodes.find(n=>n.room==='B:floor-1:storage');
    if(defect==='visible-legacy')legacy.hidden=false;
    if(defect==='visible-other-floor')nodes.push({...active,room:'B:floor-2:master2'});
    if(defect==='duplicate-active')nodes.push({...active});
    if(defect==='missing-active')nodes.splice(nodes.indexOf(active),1);
    if(defect==='hidden-active-pending'){active.hidden=true;active.textContent+=' · 入口待定';}
    if(defect==='visible-active-pending')active.textContent+=' · 入口待定';
    if(defect==='blank-active')active.textContent=' ';
    if(defect==='all-hidden')for(const node of nodes)node.hidden=true;
    assert.throws(()=>qa.inspectNavigationLabels(collect(nodes),ids),/B32 room navigation/);
  });
for(const mode of ['hidden-attribute','display-none','visibility-hidden','visibility-collapse','zero-size'])
  test('production collector preserves but excludes genuinely hidden old text: '+mode,()=>{
    const option=s.options[0],nodes=labelNodes(option.id),legacy=nodes.find(n=>n.room==='B:floor-1:entry');
    legacy.hidden=false;
    if(mode==='hidden-attribute')legacy.hidden=true;
    if(mode==='display-none')legacy.css.display='none';
    if(mode==='visibility-hidden')legacy.css.visibility='hidden';
    if(mode==='visibility-collapse')legacy.css.visibility='collapse';
    if(mode==='zero-size')legacy.getBoundingClientRect=()=>({width:0,height:0});
    const labels=collect(nodes);assert.equal(labels.find(v=>v.room===legacy.room).visible,false);
    assert.doesNotThrow(()=>qa.inspectNavigationLabels(labels,option.plans.floors[0].rooms.map(r=>r.id)));
  });
test('serialized B32 CLI executes the same tested navigation helpers without Node globals',()=>{
  const script=qa.makeBrowserScript('file:///project/','/fixture-only',{options:2,floors:8,rooms:64,items:60});
  assert.doesNotThrow(()=>new vm.Script(script));
  assert.ok(script.includes(qa.collectNavigationLabels.toString()));
  assert.ok(script.includes(qa.inspectNavigationLabels.toString()));
  assert.ok(!script.includes('.allTextContents()'),'raw hidden text is not the navigation acceptance condition');
});
