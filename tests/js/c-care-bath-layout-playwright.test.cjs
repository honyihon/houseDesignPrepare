'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),os=require('node:os');
const qa=require('../../scripts/check_c_care_bath_layout_playwright.cjs'),bath=require('../../scripts/check_c_care_bath_playwright.cjs');
const door=require('../../scripts/check_c_care_bath_door_playwright.cjs'),entry=require('../../scripts/check_c_care_entry_playwright.cjs'),route=require('../../scripts/check_c_care_route_playwright.cjs');
const ROOT=path.resolve(__dirname,'../..'),study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-layout/review.json'),'utf8'));
const counts={options:2,states:6,floors:24,rooms:234,items:300};
const accessories=spec=>spec.map(s=>({...s,actualBoundsMm:bath.accessoryBounds(s)}));
const leaves=spec=>spec.map(s=>{const [x,y,w,d]=s.rect_mm;return {...s,actualBoundsMm:{minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:s.height_mm}};});
const routes=spec=>spec.map(s=>({...s,actualPointsMm:structuredClone(s.points_mm)}));

test('independent package verifies frozen door parent, six snapshots, unchanged ABC and unknown approvals',()=>{
  const p=qa.preflight(ROOT);assert.deepEqual(p.counts,counts);assert.deepEqual(p.mainCounts,{floors:12,rooms:112,items:128});
  assert.equal(p.study.rendered_qa,'not-run');assert.equal(p.study.layout_display_revision,1);assert.equal(p.closeupCases.length,6);
  assert(p.closeupCases.every(c=>c.room==='C:floor-1:elder-bath'&&c.items.length===3&&c.items.every(i=>i.short===32&&i.long===64)));
});
test('owner page loop compiles, switches real independent layouts, checks yaw and all mobile return phases',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/test',study,counts,bath.mobileCases(study));
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const s of ["ready('side-basin','open')","ready('door-control','open')",'house-c-care-bath-layout-qa','layoutDisplayRevision:1',
    'equipment-return','overview','inspectOptionLabel(raw,spec)','dataset.layoutOption','dataset.layoutDisplayRevision',
    'Math.abs(b.rotation-i.placement.rotation_deg)<.05','doorEvidence','accessoryEvidence','actual-mesh-bounds-not-nominal-empty-envelope'])assert(code.includes(s),s);
  for(const s of ['c-care-bath-door.html','c-bath-refined','single-control','two-panel','door-adoption-warning','doorDisplayRevision:2'])assert(!qa.pageCheckSource().includes(s),s);
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-layout-3d.html'),'utf8');
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
  for(const s of ['DATA.source.c_care_bath_layout','c-care-bath-layout.html','layoutSyncRoomTitle(mesh,name);','layoutLabelBadge(badge,studyChoice,useChoice);'])assert(text.includes(s),s);
  assert(!text.includes('DATA.source.c_care_bath_door'));
});

function passing(){
  const cases=bath.mobileCases(study),safeArea={left:12,right:378,top:220,bottom:680,usable:true};
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
  return {marker:'house-c-care-bath-layout-qa',revision:2,displayRevision:2,bathDisplayRevision:2,layoutDisplayRevision:1,status:'passed',counts,
    checks:[{name:'unit fixture only, not rendered QA',passed:true}],screenshots:Array.from({length:14},(_,n)=>n+'.png'),
    mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>{const overview=phase==='overview',label=c.option==='side-basin'?'側盆比較':'原門組';return {
      phase,option:c.option,use:c.use,building:'C',floor:'floor-1',room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
      viewport:c.viewport,stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,
      fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2',bathDisplayRevision:2,bodyProjectionBasis:'actual-mesh-bounds-not-nominal-empty-envelope'},
      draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
      overlays:['stage-title','room-view-actions','compass'].map(id=>({id,left:14,right:376,top:60,bottom:210})).concat(['orientation','study-stage-note'].map(id=>({id,left:14,right:376,top:690,bottom:730}))),
      roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)})),
      optionLabelEvidence:{revision:1,option:c.option,use:c.use,
        heading:{option:c.option,text:label+' · C 1F · 套衛',visible:true,rect:{left:14,right:300,top:60,bottom:130}},
        badge:{option:c.option,text:label+' · '+({open:'門組全開',half:'半開不可通行',closed:'關門不可通行'}[c.use])+' · 未採用／濕地分時／照護救援未核',visible:true,rect:{left:14,right:376,top:690,bottom:730}}}};})),
    leafEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,leaves:leaves(entry.leafSpecs(s))}))),
    routeEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,outlines:routes(route.routeSpecs(s))}))),
    accessoryEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,components:accessories(bath.accessorySpecs(s))}))),
    doorEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,components:accessories(door.doorSpecs(s))})))};
}
test('requires all 18 actual mobile phases, leaf/route/accessory/hardware evidence and independent current marker',()=>{
  const p={study,counts,closeupCases:bath.mobileCases(study)};assert.equal(qa.validateReport(passing(),p).status,'passed');
  for(const kind of ['old-marker','old-revision','missing-label','missing-door','duplicate-door','missing-leaf','missing-route','missing-mobile','bad-stop','bad-alarm','missing-pixels']){
    const r=passing();if(kind==='old-marker')r.marker='house-c-care-bath-door-qa';if(kind==='old-revision')delete r.layoutDisplayRevision;
    if(kind==='missing-label')delete r.mobileEvidence[0].optionLabelEvidence;if(kind==='missing-door')r.doorEvidence.pop();
    if(kind==='duplicate-door')r.doorEvidence[1]=r.doorEvidence[0];if(kind==='missing-leaf')r.leafEvidence.pop();
    if(kind==='missing-route')r.routeEvidence.pop();if(kind==='missing-mobile')r.mobileEvidence.pop();
    if(kind==='bad-stop')r.doorEvidence[0].components[0].actualBoundsMm.maxY-=10;
    if(kind==='bad-alarm')r.accessoryEvidence.at(-1).components.find(c=>c.id==='alarm-toilet').actualBoundsMm.minX-=200;
    if(kind==='missing-pixels')r.mobileEvidence[0].items[0].corners=[];
    assert.throws(()=>qa.validateReport(r,p),kind);
  }
});
test('option identity rejects tooltip-only, mixed old titles, hidden or offscreen labels',()=>{
  const raw=passing().mobileEvidence[0],spec=bath.mobileCases(study)[0];
  assert.equal(qa.inspectOptionLabel(raw,spec).revision,1);
  assert.equal(vm.runInNewContext('('+qa.inspectOptionLabel.toString()+')(raw,spec)',{raw,spec}).revision,1);
  for(const kind of ['missing','old','wrong-id','wrong-text','tooltip-only','hidden','offscreen','nan','no-warning','wrong-state']){
    const r=structuredClone(raw),e=r.optionLabelEvidence;
    if(kind==='missing')delete r.optionLabelEvidence;if(kind==='old')e.revision=2;if(kind==='wrong-id')e.heading.option='side-basin';
    if(kind==='wrong-text')e.heading.text='側盆比較';if(kind==='tooltip-only'){e.heading.title=e.heading.text;e.heading.text='C套衛比較';}
    if(kind==='hidden')e.badge.visible=false;if(kind==='offscreen')e.heading.rect.right=430;if(kind==='nan')e.badge.rect.top=NaN;
    if(kind==='no-warning')e.badge.text=e.badge.text.replace('未採用','');if(kind==='wrong-state')e.badge.text=e.badge.text.replace('門組全開','半開不可通行');
    assert.throws(()=>qa.inspectOptionLabel(r,spec),kind);
  }
});
function node(tag,text=''){
  return {tag,dataset:{},title:'',children:[],value:text,
    get firstChild(){return this.children[0]||null;},
    get textContent(){return this.children.length?this.children.map(c=>c.textContent).join(''):this.value;},
    set textContent(value){this.value=value;this.children=tag==='#text'?[]:[node('#text',value)];},
    replaceChildren(...children){this.value='';this.children=children;},
    appendChild(child){this.children.push(child);return child;},
    querySelector(tag){return this.children.find(n=>n.tag===tag)||null;}};
}
test('small DOM identity helper preserves warning/tooltip in both layouts and all states, without scene work',()=>{
  const display=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-layout-display.js'),'utf8');
  assert(!/scale\.|position\.|\.visible\s*=|setTimeout|setInterval|MutationObserver/.test(display));
  for(const o of study.options)for(const s of o.states)for(const width of [390,1440])for(const closeup of [true,false]){
    const title=node('div'),badge=node('div'),body=node('body'),name=closeup?'C · 孝親套衛':'C 棟 1F';title.textContent=name;title.appendChild(node('small','同源 · 未採用'));
    const api=vm.runInNewContext(display+';({layoutSyncRoomTitle,layoutLabelBadge});',{
      document:{body,getElementById:()=>title,createTextNode:text=>node('#text',text)},stage:{clientWidth:width},presentation:'tour',studyChoice:o,bathSyncRoomTitle:()=>{}});
    api.layoutLabelBadge(badge,o,s);api.layoutSyncRoomTitle(closeup?{userData:{cell:{key:'elder-bath'}}}:null,name);
    const label=o.id==='side-basin'?'側盆比較':'原門組';assert(title.textContent.includes(label));assert(badge.textContent.includes(label));
    assert.equal(title.dataset.layoutOption,o.id);assert.equal(badge.dataset.layoutOption,o.id);assert.equal(body.dataset.layoutDisplayRevision,'1');
    assert(title.title.includes(o.label)&&title.title.includes(name));assert(title.querySelector('small'));
    for(const text of ['未採用','濕地分時','照護救援未核'])assert(badge.textContent.includes(text));
  }
});
test('raw failure evidence is retained before rejecting option labels, no state silently lost',async()=>{
  const helper=qa.pageCheckSource().match(/  const recordMobile=async\([\s\S]*?(?=  const warning=async)/)[0];
  const raw=passing().mobileEvidence[0],evidence=[],spec=bath.mobileCases(study)[0];
  const fn=vm.runInNewContext(helper+';recordMobile;',{
    mobileEvidence:evidence,readMobile:async()=>raw,inspectMobileView:()=>{throw Error('must not reach pixel check');},inspectOptionLabel:()=>{throw Error('wrong label');}});
  await assert.rejects(()=>fn('initial',spec),/wrong label/);assert.equal(evidence[0],raw);
});
test('one owner-only session with isolated output, no install or retry, missing structured result is incomplete',()=>{
  for(const good of [true,false]){
    const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-layout-unit-')),calls=[];
    const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify(good?{result:passing()}:{isError:true}):args[4]==='close'?'{"status":"closed"}':'{}'};};
    const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study,counts,closeupCases:bath.mobileCases(study)},output,execute);
    assert.equal(r.status,good?'passed':'incomplete');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
    assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
  }
});
