'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),os=require('node:os');
const qa=require('../../scripts/check_c_care_bath_door_playwright.cjs'),bath=require('../../scripts/check_c_care_bath_playwright.cjs');
const entry=require('../../scripts/check_c_care_entry_playwright.cjs'),route=require('../../scripts/check_c_care_route_playwright.cjs');
const ROOT=path.resolve(__dirname,'../..'),study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-door/review.json'),'utf8'));
const counts={options:2,states:6,floors:24,rooms:234,items:300};
const accessories=spec=>spec.map(s=>({...s,actualBoundsMm:bath.accessoryBounds(s)}));
const leaves=spec=>spec.map(s=>{const [x,y,w,d]=s.rect_mm;return {...s,actualBoundsMm:{minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:s.height_mm}};});
const routes=spec=>spec.map(s=>({...s,actualPointsMm:structuredClone(s.points_mm)}));
test('new package verifies parents and independent two-option six-state counts, no rendered claim',()=>{
  const p=qa.preflight(ROOT);assert.deepEqual(p.counts,counts);assert.deepEqual(p.mainCounts,{floors:12,rooms:112,items:128});
  assert.equal(p.study.rendered_qa,'not-run');assert.equal(p.study.door_display_revision,2);assert.equal(p.closeupCases.length,6);
  assert(p.closeupCases.every(c=>c.room==='C:floor-1:elder-bath'&&c.items.length===3&&c.items.every(i=>i.short===32&&i.long===64)));
});
test('owner page loop compiles with current marker, same-source links, both independent scheme switches, half/closed states',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/test',study,counts,bath.mobileCases(study));
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const s of ["ready('two-panel','open')","ready('single-control','open')",'house-c-care-bath-door-qa','doorEvidence','careDoor','equipment-return','overview','actual-mesh-bounds-not-nominal-empty-envelope','doorDisplayRevision:2','optionLabelEvidence','inspectOptionLabel(raw,spec)'])assert(code.includes(s),s);
  assert(!qa.pageCheckSource().includes('c-care-bath.html'));assert(!qa.pageCheckSource().includes('c-bath-refined'));assert(!qa.pageCheckSource().includes('c-care-entry.html'));
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/c-care-bath-door-3d.html'),'utf8');
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
  for(const s of ['careDoor:careDoorEvidence()','careEntry:careEntryEvidence()','careRoute:careRouteEvidence()','DATA.source.c_care_bath_door','c-care-bath-door.html','half:"半開不可通行"','doorSyncRoomTitle(mesh,name);','doorLabelBadge(badge,studyChoice,useChoice);'])assert(text.includes(s),s);
  assert(!text.includes('DATA.source.c_care_bath;'));assert(!text.includes('DATA.c_care_bath,'));
});
test('one/two actual hardware envelopes include stop and outward pull and reject shrunken or metadata-only evidence',()=>{
  for(const o of study.options)for(const s of o.states){const spec=qa.doorSpecs(s),a=accessories(spec);
    assert.equal(spec.length,o.id==='two-panel'?2:1);assert.equal(bath.inspectAccessories(a,spec).length,spec.length);
    for(const field of ['actualBoundsMm','state','room']){const bad=structuredClone(a);delete bad[0][field];assert.throws(()=>bath.inspectAccessories(bad,spec));}
    const bad=structuredClone(a);bad[0].actualBoundsMm.maxY-=10;assert.throws(()=>bath.inspectAccessories(bad,spec));
  }
});
test('tiny door-hardware meshes agree with actual bounds in all states; no Scene, WebGL or full floor runtime',()=>{
  const THREE=require('../../assets/vendor/three/three.min.js'),source=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-door-overlay.js'),'utf8');
  for(const o of study.options)for(const s of o.states){
    const expected=qa.doorSpecs(s),group=new THREE.Group();
    vm.runInNewContext(source,{THREE,group,features:{care_door_parts:expected},base:0,MM:.001,wz:y=>-y*.001,clipPlane:new THREE.Plane(new THREE.Vector3(0,-1,0),3.6)});
    group.updateMatrixWorld(true);
    const actual=group.children.map(p=>{const b=new THREE.Box3().setFromObject(p);return {...p.userData.careDoor,room:'C:floor-1:elder-bath',actualBoundsMm:{minX:b.min.x*1000,maxX:b.max.x*1000,minY:-b.max.z*1000,maxY:-b.min.z*1000,minHeight:b.min.y*1000,maxHeight:b.max.y*1000}};});
    assert.equal(bath.inspectAccessories(actual,expected).length,expected.length);
    group.traverse(p=>{p.geometry?.dispose();p.material?.dispose();});
  }
});
function passing(){
  const cases=bath.mobileCases(study),safeArea={left:12,right:378,top:220,bottom:680,usable:true};
  const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
  return {marker:'house-c-care-bath-door-qa',revision:2,displayRevision:2,bathDisplayRevision:2,doorDisplayRevision:2,status:'passed',counts,checks:[{name:'actual geometry',passed:true}],screenshots:Array.from({length:14},(_,n)=>n+'.png'),
    mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>{const overview=phase==='overview';return {phase,option:c.option,use:c.use,building:'C',floor:'floor-1',room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
      viewport:c.viewport,stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2',bathDisplayRevision:2,bodyProjectionBasis:'actual-mesh-bounds-not-nominal-empty-envelope'},
      draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
      overlays:['stage-title','room-view-actions','compass'].map(id=>({id,left:14,right:376,top:60,bottom:210})).concat(['orientation','study-stage-note'].map(id=>({id,left:14,right:376,top:690,bottom:730}))),
      roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)})),
      optionLabelEvidence:{revision:2,option:c.option,use:c.use,
        heading:{option:c.option,text:(c.option==='two-panel'?'兩片新案':'單片控制')+' · C 1F · 套衛',visible:true,rect:{left:14,right:300,top:60,bottom:130}},
        badge:{option:c.option,text:(c.option==='two-panel'?'兩片新案':'單片控制')+' · '+({open:'門組全開',half:'半開不可通行',closed:'關門不可通行'}[c.use])+' · 未採用／濕地分時／照護救援未核',visible:true,rect:{left:14,right:376,top:690,bottom:730}}}};})),
    leafEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,leaves:leaves(entry.leafSpecs(s))}))),
    routeEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,outlines:routes(route.routeSpecs(s))}))),
    accessoryEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,components:accessories(bath.accessorySpecs(s))}))),
    doorEvidence:study.options.flatMap(o=>o.states.map(s=>({option:o.id,use:s.id,components:accessories(qa.doorSpecs(s))})))};
}
test('current result requires all 18 mobile phases, every leaf, route and actual stop/pull mesh; rejects old passed',()=>{
  const p={study,counts,closeupCases:bath.mobileCases(study)};assert.equal(qa.validateReport(passing(),p).status,'passed');
  for(const kind of ['old-marker','old-display','missing-label','missing-door','duplicate-door','missing-leaf','missing-route','missing-mobile','bad-stop','bad-accessory']){
    const r=passing();if(kind==='old-marker')r.marker='house-c-care-bath-qa';if(kind==='missing-door')r.doorEvidence.pop();
    if(kind==='old-display')delete r.doorDisplayRevision;if(kind==='missing-label')delete r.mobileEvidence[0].optionLabelEvidence;
    if(kind==='duplicate-door')r.doorEvidence[1]=r.doorEvidence[0];if(kind==='missing-leaf')r.leafEvidence.pop();
    if(kind==='missing-route')r.routeEvidence.pop();if(kind==='missing-mobile')r.mobileEvidence.pop();
    if(kind==='bad-stop')r.doorEvidence[0].components[0].actualBoundsMm.maxY-=10;
    if(kind==='bad-accessory')r.accessoryEvidence[0].components[0].actualBoundsMm.maxX-=100;
    assert.throws(()=>qa.validateReport(r,p),kind);
  }
});
function node(tag,text=''){
  return {tag,dataset:{},title:'',children:[],value:text,
    get firstChild(){return this.children[0]||null;},
    get textContent(){return this.children.length?this.children.map(c=>c.textContent).join(''):this.value;},
    set textContent(value){this.value=value;this.children=tag==='#text'?[]:[node('#text',value)];},
    appendChild(child){this.children.push(child);return child;},
    replaceChildren(...children){this.value='';this.children=children;},
    querySelector(tag){return this.children.find(n=>n.tag===tag)||null;}};
}
test('visible title and badge distinguish both options in room/overview at mobile and desktop, retaining full tooltip and warnings',()=>{
  const display=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-door-display.js'),'utf8');
  const camera=fs.readFileSync(path.join(ROOT,'scripts/templates/c-care-bath-camera.js'),'utf8');
  assert(!/scale\.|position\.|\.visible\s*=|setTimeout|setInterval|MutationObserver/.test(display));
  for(const o of study.options)for(const s of o.states)for(const width of [390,1440])for(const closeup of [true,false]){
    const title=node('div'),badge=node('div'),body=node('body'),name=closeup?'C 棟 · 1F · 孝親套衛比較（無固定玻璃／濕地分時轉位）':'C 棟 1F';
    title.textContent=name;title.appendChild(node('small','與 HTML 同源 · 未採用'));
    const document={body,getElementById:()=>title,createElement:tag=>node(tag),createTextNode:text=>node('#text',text)};
    const api=vm.runInNewContext(camera+display+';({doorSyncRoomTitle,doorLabelBadge,doorShortLabel});',
      {document,stage:{clientWidth:width},presentation:'tour',studyChoice:o});
    api.doorLabelBadge(badge,o,s);api.doorSyncRoomTitle(closeup?{userData:{cell:{key:'elder-bath'}}}:null,name);
    const expected=o.id==='two-panel'?'兩片新案':'單片控制';
    assert(title.textContent.includes(expected));assert(badge.textContent.includes(expected));
    assert.equal(title.dataset.doorOption,o.id);assert.equal(badge.dataset.doorOption,o.id);assert.equal(body.dataset.doorDisplayRevision,'2');
    assert(title.title.includes(o.label)&&title.title.includes(name));assert(title.querySelector('small'));
    for(const text of ['未採用','濕地分時','照護救援未核'])assert(badge.textContent.includes(text));
  }
});
test('identity inspector is closure-free and rejects hidden/clipped, wrong, tooltip-only or old option labels',()=>{
  const raw=passing().mobileEvidence[0],spec=bath.mobileCases(study)[0];
  assert.equal(qa.inspectOptionLabel(raw,spec).revision,2);
  assert.equal(vm.runInNewContext('('+qa.inspectOptionLabel.toString()+')(raw,spec)',{raw,spec}).revision,2);
  for(const kind of ['missing','old','wrong-id','wrong-heading','wrong-badge','tooltip-only','hidden','offscreen','nan','no-warning','wrong-state']){
    const r=structuredClone(raw),e=r.optionLabelEvidence;
    if(kind==='missing')delete r.optionLabelEvidence;if(kind==='old')e.revision=1;if(kind==='wrong-id')e.heading.option='two-panel';
    if(kind==='wrong-heading')e.heading.text='兩片新案';if(kind==='wrong-badge')e.badge.text=e.badge.text.replace('單片控制','兩片新案');
    if(kind==='tooltip-only'){e.heading.title=e.heading.text;e.heading.text='C 孝親套衛比較';}
    if(kind==='hidden')e.badge.visible=false;if(kind==='offscreen')e.heading.rect.right=430;if(kind==='nan')e.badge.rect.top=NaN;
    if(kind==='no-warning')e.badge.text=e.badge.text.replace('未採用','');if(kind==='wrong-state')e.badge.text=e.badge.text.replace('門組全開','半開不可通行');
    assert.throws(()=>qa.inspectOptionLabel(r,spec),kind);
  }
});
test('raw mobile label evidence is saved before identity rejection, not lost at first failure',async()=>{
  const source=qa.pageCheckSource(),helper=source.match(/  const recordMobile=async\([\s\S]*?(?=  const warning=async)/)[0];
  const raw=passing().mobileEvidence[0],evidence=[],spec=bath.mobileCases(study)[0];
  const fn=vm.runInNewContext(helper+';recordMobile;',{
    mobileEvidence:evidence,readMobile:async()=>raw,inspectMobileView:()=>{throw Error('must not reach pixel check');},inspectOptionLabel:()=>{throw Error('wrong visible option');}});
  await assert.rejects(()=>fn('initial',spec),/wrong visible option/);assert.equal(evidence.length,1);assert.equal(evidence[0],raw);
});
test('one owner-only session, no dependency install/retry; incomplete if missing structured result',()=>{
  for(const good of [true,false]){
    const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-door-unit-')),calls=[];
    const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify(good?{result:passing()}:{isError:true}):args[4]==='close'?'{"status":"closed"}':'{}'};};
    const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study,counts,closeupCases:bath.mobileCases(study)},output,execute);
    assert.equal(r.status,good?'passed':'incomplete');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
    assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
  }
});
