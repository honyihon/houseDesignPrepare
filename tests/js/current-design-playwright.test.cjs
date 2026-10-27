'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_current_design_playwright.cjs'),ROOT=path.resolve(__dirname,'../..');
const counts={options:5,states:9,floors:36,rooms:340,items:341};
const study=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/current-design-basis/review.json'),'utf8')),cases=qa.closeupCases(study);
const corners=(left,top,right,bottom)=>[left,right].flatMap(x=>[top,bottom].flatMap(y=>[0,.5].map(z=>[2*x/390-1,1-2*y/790,z])));
function evidence(c,phase='initial'){
  const safeArea={left:12,right:378,top:220,bottom:680,usable:true},overview=phase==='overview';
  return {phase,option:c.option,use:c.use,building:c.building,floor:c.floor,room:overview?'':c.room,closeup:!overview,panelCollapsed:true,displayRevision:2,
    viewport:{width:390,height:844},stage:{width:390,height:790},safeArea,visibleRoomIds:c.roomIds,
    fit:{area:safeArea,viewport:{width:390,height:790},closeupPolicy:overview?null:'current-design-readable-v2'},
    draw:{clipped:!overview,clearedOutside:!overview,area:overview?null:safeArea,stage:{width:390,height:790},renderSize:{width:390,height:790}},scissorTestRestored:true,
    overlays:[{id:'stage-title',left:14,right:300,top:60,bottom:110},{id:'room-view-actions',left:14,right:376,top:120,bottom:210},
      {id:'compass',left:320,right:374,top:14,bottom:68},{id:'orientation',left:14,right:376,top:740,bottom:780},{id:'study-stage-note',left:14,right:376,top:690,bottom:730}],
    roomCorners:corners(20,240,370,650),items:c.items.map(i=>({id:i.id,corners:corners(80,300,200,460)}))};
}
const passed=()=>({marker:'house-current-design-qa',revision:2,displayRevision:2,status:'passed',counts,checks:[{name:'mesh parity',passed:true}],
  screenshots:Array.from({length:20},(_,n)=>n+'.png'),mobileEvidence:cases.flatMap(c=>['initial','equipment-return','overview'].map(phase=>evidence(c,phase)))});
test('current preflight reads source-bound five options, does not allocate any browser',()=>{
  const r=qa.preflight(ROOT);assert.deepEqual(r.counts,counts);assert.deepEqual(r.mainCounts,{floors:12,rooms:112,items:128});
  assert.equal(r.study.requirement_ledger.scenario_rows,112);assert.equal(r.study.rendered_qa,'not-run');
  assert.equal(r.study.display_revision,2);assert.equal(r.closeupCases.length,9);
});
test('serialized program has no module closure and checks actual unscaled bodies',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/qa',{},counts,cases);
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const s of ['Actual unscaled furniture','Actual room/door/window parity','Actual candidate window mesh','Compact policy survives synchronization',
    'Mobile actual body pixel sizes and text-free draw','Equipment return preserves readable bodies','Return to whole floor restores unclipped draw'])assert(code.includes(s));
  assert(!code.includes('new URL(page.url())'));
  assert(code.includes("page.locator('#basis-adoption-warning')"));
  assert(code.includes("checkWarning('desktop')")&&code.includes("checkWarning('mobile')"));
  assert(code.includes('warning.isVisible()')&&code.includes('warning.boundingBox()'));
});
test('first-page warning is explicit and uniquely addressed in actual generated HTML',()=>{
  const source=fs.readFileSync(path.join(ROOT,'structured/candidates/current-design-basis.html'),'utf8');
  assert(qa.validateIndexWarning(source).startsWith('比較方案，未採用／專業未核。'));
});
test('old negative phrasing or a later warning must not satisfy the first-page warning',()=>{
  assert.throws(()=>qa.validateIndexWarning('<p id="basis-adoption-warning" class="warning">不是已採用主案</p><p class="warning">未採用／專業未核</p>'),/non-adoption warning/);
  assert.throws(()=>qa.validateIndexWarning('<p class="warning">不是已採用主案</p><p id="basis-adoption-warning" class="warning">未採用／專業未核</p>'),/non-adoption warning/);
  assert.throws(()=>qa.validateIndexWarning('<p id="basis-adoption-warning" class="warning">未採用／專業未核</p><p id="basis-adoption-warning">重複</p>'),/non-adoption warning/);
});
test('display-only fixes preserve all five options, nine states and the full requirement ledger',()=>{
  const r=JSON.parse(fs.readFileSync(path.join(ROOT,'structured/candidates/current-design-basis/review.json'),'utf8'));
  function ordered(v){return Array.isArray(v)?v.map(ordered):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])):v;}
  const digest=require('node:crypto').createHash('sha256').update(JSON.stringify(ordered({options:r.options,ledger:r.requirement_ledger}))).digest('hex');
  assert.equal(digest,'52531744588429de35e65c25248e1202609cd4e2c32c35fb85a233d7c4165c3b');
});
for(const bad of ['empty','revision','display','checks','screenshots','counts','mobile','duplicate','unreadable','return','overview'])test('incomplete evidence never passes '+bad,()=>{
  const r=passed();if(bad==='revision')r.revision=1;if(bad==='display')r.displayRevision=1;if(bad==='checks')r.checks[0].passed=false;if(bad==='screenshots')r.screenshots.pop();if(bad==='counts')r.counts={...counts,states:8};
  if(bad==='mobile')delete r.mobileEvidence;if(bad==='duplicate')r.mobileEvidence[1]=r.mobileEvidence[0];
  if(bad==='unreadable')r.mobileEvidence[0].items[0].corners=corners(80,300,85,310);
  if(bad==='return')r.mobileEvidence[1].draw.renderSize.height=470;if(bad==='overview')r.mobileEvidence[2].draw.clipped=true;
  assert.throws(()=>qa.validateReport(bad==='empty'?null:r,counts,cases));
});
test('passing evidence is revalidated from raw mesh corners, not a cached score/bodyRects',()=>{
  const r=passed();assert.equal(qa.validateReport(r,counts,cases).status,'passed');
  r.mobileEvidence[0].bodyRects=[{shortSidePx:100,longSidePx:1000}];r.mobileEvidence[0].items[0].corners=[];
  assert.throws(()=>qa.validateReport(r,counts,cases),/projected mesh/);
});
for(const bad of ['room','state','missing-room','missing-item','duplicate-item','nonfinite','depth','small-room','overlay','clip','canvas','fit','policy','viewport','expanded','missing-overlay'])test('mobile evidence rejects '+bad,()=>{
  const c=cases[0],e=evidence(c);
  if(bad==='room')e.room='A:floor-1:garage';if(bad==='state')e.use='carry';if(bad==='missing-room')e.visibleRoomIds=e.visibleRoomIds.slice(1);
  if(bad==='missing-item')e.items.pop();if(bad==='duplicate-item')e.items[1]=e.items[0];if(bad==='nonfinite')e.items[0].corners[0][0]=NaN;
  if(bad==='depth')e.roomCorners[0][2]=2;if(bad==='small-room')e.roomCorners=corners(50,300,70,320);
  if(bad==='overlay')e.overlays[0].bottom=400;if(bad==='clip')e.draw.area={...e.safeArea,top:100};
  if(bad==='canvas')e.draw.renderSize.width=300;if(bad==='fit')e.fit.viewport.height=470;if(bad==='policy')e.fit.closeupPolicy='c-integrated-readable-v1';
  if(bad==='viewport')e.viewport.height=790;if(bad==='expanded')e.panelCollapsed=false;if(bad==='missing-overlay')e.overlays=[];
  assert.throws(()=>qa.inspectMobileView(e,c));
});
test('owner-run QA uses one session, closes it, never installs or retries',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-current-unit-')),calls=[];
  const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify({result:passed()}):args[4]==='close'?' {"status":"closed"}':'{}'};};
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study:{},counts,closeupCases:cases},output,execute);
  assert.equal(r.status,'passed');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);assert.equal(new Set(calls.map(a=>a[2])).size,1);
  assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
});
test('denied CLI is incomplete, not passed',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-current-denied-'));
  const execute=(bin,args)=>({status:0,stdout:args[4]==='run-code'?' {"isError":true}':args[4]==='close'?' {"status":"closed"}':'{}'});
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study:{},counts},output,execute);
  assert.equal(r.status,'incomplete');assert.equal(r.sessionClosed,true);
});
function bootstrap(href){
  const options=[['a-current','A',['daily']],['b-rear-refined','B',['daily','ritual','carry']],['c-care-refined','C',['daily']]].map(([id,building,states])=>({id,building,label:id,states:states.map(s=>({id:s,label:s,model:{bc_option:{id,label:id,tradeoffs:['not adopted']}}}))}));
  const c={URL,URLSearchParams,DATA:{current_design_basis:{default_option:'b-rear-refined',options}},elements:{},handlers:{},assigned:null,redirect:null};
  const el=id=>c.elements[id]||=( {children:[],value:'',setAttribute(){},appendChild(x){this.children.push(x);},addEventListener(n,fn){c.handlers[id+':'+n]=fn;}} );
  c.document={body:{classList:{add(){}},dataset:{}},querySelector:()=>el('h1'),getElementById:el,createElement:()=>({setAttribute(){}})};
  c.location={href,hash:new URL(href).hash,replace:v=>{c.redirect=v;},assign:v=>{c.assigned=v;}};c.history={replaceState(){}};
  new vm.Script('(function(){'+fs.readFileSync(path.join(ROOT,'scripts/templates/current-design-bootstrap.js'),'utf8')+'})();').runInNewContext(c);return c;
}
test('unknown scheme normalizes before model allocation',()=>{
  const c=bootstrap('file:///p/v.html?scheme=bad&use=bad');assert(c.redirect.includes('scheme=b-rear-refined'));assert(c.redirect.includes('use=daily'));assert.deepEqual(Object.keys(c.elements),[]);
});
test('switching B carry to C resets unsupported state and stale building/room',()=>{
  const c=bootstrap('file:///p/v.html?scheme=b-rear-refined&use=carry#room=B%3Afloor-1%3Ashrine');
  c.elements['study-scheme'].value='c-care-refined';c.handlers['study-scheme:change']();const url=new URL(c.assigned);
  assert.equal(url.searchParams.get('use'),'daily');assert.equal(new URLSearchParams(url.hash.slice(1)).get('building'),'C');assert(!url.hash.includes('room='));
});
test('generated synchronization composes facade and compact label controls',()=>{
  const text=fs.readFileSync(path.join(ROOT,'structured/candidates/current-design-basis-3d.html'),'utf8');
  assert(text.includes('(id==="furniture-names" && document.getElementById("b32-label-mode").value!=="all")'));
  assert(text.includes('!!viewState.room && b32DisplayContext().mode==="all"'));
  assert(text.includes('basisRenderFrame();')&&text.includes('basisObserveViewport();'));
  assert(!text.includes('window.setTimeout(resize, 220)'));
  for(const m of text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))assert.doesNotThrow(()=>new vm.Script(m[1]));
});
