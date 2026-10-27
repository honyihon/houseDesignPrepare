'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_b32_rear_right_playwright.cjs');
const ROOT=path.resolve(__dirname,'../..'),counts={options:2,states:6,floors:24,rooms:213,items:198};
const passed=()=>({marker:'house-b32-rear-right-qa',revision:1,displayRevision:2,status:'passed',counts,checks:[{name:'actual state',passed:true}],screenshots:Array.from({length:20},(_,i)=>'s'+i+'.png')});
test('file preflight verifies independent layouts/use states/source hashes without a renderer',()=>{
  const r=qa.preflight(ROOT);assert.deepEqual(r.counts,counts);assert.deepEqual(r.mainCounts,{floors:12,rooms:112,items:128});
  assert.equal(r.study.default_option,'rear-alley');assert.equal(r.study.rear_alley.existence,'owner-reported-planning-premise');
  assert.equal(r.study.display_revision,2);
  assert(r.sourceFiles.includes('scripts/check_b32_rear_right_playwright.cjs'));
});
test('browser program serializes without module closure and has actual body evidence',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/qa',{},counts);assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  for(const text of ['Plan zoom changes actual width','State selector loads actual prepared model','Actual full-size use-state furniture',
    'Actual candidate window mesh','Mobile actual fixture bodies >=16px inside safe area','Mobile return to complete floor',"page.goto('about:blank')"])
    assert(code.includes(text));
  assert(!code.includes('new URL(page.url())')); // Playwright run-code VM lacks Node URL.
});
for(const name of ['revision','display revision','states','failed check','screenshots'])test('reject incomplete passing '+name,()=>{
  const r=passed();if(name==='revision')r.revision=2;if(name==='states')r.counts={...counts,states:5};if(name==='failed check')r.checks[0].passed=false;if(name==='screenshots')r.screenshots.pop();
  if(name==='display revision')delete r.displayRevision;
  assert.throws(()=>qa.validateReport(r,counts),/Incomplete/);
});
test('empty and actual failed outputs are not converted into passing QA',()=>{
  assert.equal(qa.findReport({text:''}),null);assert.throws(()=>qa.validateReport(null,counts),/completed/);
  assert.equal(qa.validateReport({marker:'house-b32-rear-right-qa',status:'failed',error:'window not rendered'},counts).status,'failed');
});
test('one owner-run session, no install/retry/global cleanup',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'b32-right-unit-')),calls=[];
  const execute=(bin,args)=>{calls.push(args);return {status:0,stdout:args[4]==='run-code'?JSON.stringify({result:passed()}):args[4]==='close'?' {"status":"closed"}':'{}'};};
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study:{},counts},output,execute);
  assert.equal(r.status,'passed');assert.equal(r.sessionClosed,true);assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
  assert.equal(new Set(calls.map(a=>a[2])).size,1);assert(!calls.flat().some(a=>/install|pkill|kill-all/.test(a)));
});
test('CLI denial remains incomplete and closes only its own named session',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'b32-right-denied-')),calls=[];
  const execute=(bin,args)=>{calls.push(args[4]);return {status:0,stdout:args[4]==='run-code'?' {"isError":true}':args[4]==='close'?' {"status":"closed"}':'{}'};};
  const r=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing.cjs',sourceFiles:[],study:{},counts},output,execute);
  assert.equal(r.status,'incomplete');assert.deepEqual(calls,['open','run-code','close']);
});
function bootstrap(href){
  const context={URL,URLSearchParams,DATA:{b32_rear_right:{display_revision:2,default_option:'rear-alley',default_state:'daily',options:['rear-alley','front-backup'].map(id=>({id,label:id,states:['daily','ritual','carry'].map(s=>({id:s,label:s,model:{bc_option:{id,use_state:s,label:id+' '+s,tradeoffs:['not adopted']}}}))}))}},handlers:{},elements:{},redirect:null,assigned:null};
  const element=id=>context.elements[id] ||= {id,children:[],textContent:'',value:'',setAttribute(){},appendChild(c){this.children.push(c);},addEventListener(name,fn){context.handlers[id+':'+name]=fn;}};
  context.document={body:{classList:{add(){}},dataset:{}},title:'',querySelector:()=>element('h1'),getElementById:element,createElement:()=>({setAttribute(){}})};
  context.location={href,hash:new URL(href).hash,replace:url=>{context.redirect=url;},assign:url=>{context.assigned=url;}};context.history={replaceState(){}};
  const code=fs.readFileSync(path.join(ROOT,'scripts/templates/b32-rear-right-bootstrap.js'),'utf8');
  new vm.Script('(function(){'+code+'})();').runInNewContext(context);return context;
}
test('bootstrap normalizes unknown URLs before choosing or allocating model',()=>{
  const c=bootstrap('file:///p/viewer.html?scheme=bad&use=bad');assert(c.redirect.includes('scheme=rear-alley'));assert(c.redirect.includes('use=daily'));
  assert.equal(c.DATA.b32_rear_right.options.length,2);assert.deepEqual(Object.keys(c.elements),[]);
});
test('bootstrap isolates actual use-state models and state-specific return links',()=>{
  const c=bootstrap('file:///p/viewer.html?scheme=front-backup&use=carry');
  assert.equal(c.DATA.bc_option.use_state,'carry');assert.equal(c.document.body.dataset.studyOption,'front-backup');assert.equal(c.document.body.dataset.studyUse,'carry');
  assert.equal(c.elements['study-plan-link'].href,'b32-rear-right.html#front-backup-carry');
  assert.equal(c.elements['study-use'].children.length,3);
  assert.equal(c.document.body.dataset.studyDisplayRevision,'2');
  c.elements['study-use'].value='ritual';c.handlers['study-use:change']();assert(c.assigned.includes('scheme=front-backup'));assert(c.assigned.includes('use=ritual'));
});
test('display change preserves every plan, body, opening and review from accepted v1 snapshot',()=>{
  const r=qa.preflight(ROOT).study;
  function ordered(v){return Array.isArray(v)?v.map(ordered):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])):v;}
  const snap=r.options.map(o=>({id:o.id,states:o.states.map(s=>({id:s.id,plans:s.plans,review:s.review})),area_rows:o.area_rows,staging_review:o.staging_review}));
  const digest=require('node:crypto').createHash('sha256').update(JSON.stringify(ordered(snap))).digest('hex');
  assert.equal(digest,'04a9d3f7aead2cb9d0960e6dbbf6d76eeb5871ea7836164543d57f068076aefb');
});
test('manual browser script checks actual label limits, clean models and accessible detail roundtrip',()=>{
  const code=qa.makeBrowserScript('file:///p/','C:/temp/qa',{},counts);
  for(const text of ['Desktop compact major-room labels only','Mobile closeup annotations do not cover fixture bodies',
    'Mobile equipment list retains dimensions and conditional entrance status','Equipment list return preserves selected room','Mobile whole-floor labels capped at four'])assert(code.includes(text));
});
