'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const qa=require('../../scripts/check_interior_improvements_playwright.cjs');
const ROOT=path.resolve(__dirname,'../..');
const counts={options:10,floors:40,rooms:360,items:352};
const passed=()=>({marker:'house-interior-improvements-qa',revision:7,status:'passed',counts,
  checks:[{name:'actual model',passed:true}],screenshots:Array.from({length:29},(_,n)=>'screenshot-'+n+'.png')});
test('preflight checks all real sources without a browser',()=>{
  const result=qa.preflight(ROOT);
  assert.deepEqual(result.counts,counts);assert.deepEqual(result.mainCounts,{floors:12,rooms:112,items:128});
  assert(result.sourceFiles.includes('scripts/check_interior_improvements_playwright.cjs'));
  assert.equal(result.study.rendered_qa,'not-run');
  assert.equal(result.study.revision,7);assert.equal(result.study.default_option,'b-rear-dry-service');
  assert.equal(result.study.owner_decisions.filter(d=>d.status==='confirmed-preference').length,3);
  assert.equal(result.study.owner_decisions.filter(d=>d.status==='pending').length,4);
  const accepted=result.study.owner_decisions.find(d=>d.id==='c-kitchen').accepted_scope;
  assert.equal(accepted.nominal_public_loss_sqm,1.08);assert.equal(accepted.whole_c_layout_adopted,false);
  assert.equal(accepted.professional_approval,'unknown');
});
test('serialized browser program has no unbound module closure',()=>{
  const code=qa.makeBrowserScript('file:///project/','C:/temp/review',{},counts);
  assert.doesNotThrow(()=>new vm.Script('('+code+')'));
  assert(code.includes('data-plan-action="in"'));assert(code.includes('Actual full-size furniture'));
  assert(code.includes('Mobile comparison warning'));assert(code.includes("page.goto('about:blank')"));
  assert(code.includes('C only original second-floor washer'));assert(code.includes('A retained bathroom has actual rear candidate window'));
  assert(code.includes('Actual candidate window geometry'));assert(code.includes('c-single-washer-second-floor-desktop.png'));
  assert(code.includes('C actual front fridge orientation and retained 900mm counter operation band'));
  assert(code.includes('Actual furniture rotation'));assert(code.includes('C kitchen owner acceptance and area cost visible without construction approval'));
  assert(code.includes('B actual right bathroom and separate left dry entrance'));
  assert(code.includes('B actual full-size dry cabinet moves to right wall'));
  assert(code.includes('B mobile area, route and window tradeoffs available in open details'));
  assert(code.includes('B actual direct rear bathroom window and independent dry-cabinet door'));
  assert(code.includes('B actual wall-backed toilet, rear basin and forward washer'));
  assert(code.includes('B mobile rear-window budget, ritual conflict and ventilation limits remain readable'));
  assert(code.includes('All ten navigation labels distinguish controls and use studies'));
  assert(code.includes('B actual small open drying rack and dehumidifier without resized catalog rack'));
  assert(code.includes('B mobile ceremony failure and unapproved drying ventilation remain explicit'));
  assert(code.includes('B mobile new equipment has 16px projected bodies inside safe area, not label-only evidence'));
  assert(code.includes("page.locator('#info')"));assert(!code.includes('#cell-info'));
});
test('finds nested/string reports, never treats empty output as pass',()=>{
  assert.deepEqual(qa.findReport({content:JSON.stringify(passed())}),passed());
  assert.equal(qa.findReport({content:''}),null);
  assert.throws(()=>qa.validateReport(null,counts),/completed/);
});
for(const name of ['wrong revision','missing floor','failed check','missing screenshots']){
  test('rejects '+name+' in a passing result',()=>{
    const result=passed();
    if(name==='wrong revision')result.revision=6;
    if(name==='missing floor')result.counts={...counts,floors:39};
    if(name==='failed check')result.checks[0].passed=false;
    if(name==='missing screenshots')result.screenshots.pop();
    assert.throws(()=>qa.validateReport(result,counts),/Incomplete/);
  });
}
test('retains a genuine browser failure instead of converting it to pass',()=>{
  const result={marker:'house-interior-improvements-qa',status:'failed',error:'Door not visible'};
  assert.equal(qa.validateReport(result,counts).status,'failed');
});
test('one named session, temp artifacts, no installs/retries/global cleanup',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-interior-unit-'));
  const calls=[];
  const execute=(bin,argv)=>{
    calls.push(argv);
    const command=argv[4];
    if(command==='open')return {status:0,stdout:'{}'};
    if(command==='run-code')return {status:0,stdout:JSON.stringify({result:passed()})};
    if(command==='close')return {status:0,stdout:'{"status":"closed"}'};
    throw Error('Unexpected command '+command);
  };
  const result=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing-cli.cjs',sourceFiles:[],study:{},counts},output,execute);
  assert.equal(result.status,'passed');assert.equal(result.sessionClosed,true);
  assert.deepEqual(calls.map(a=>a[4]),['open','run-code','close']);
  assert.equal(new Set(calls.map(a=>a[2])).size,1);
  assert(!calls.flat().some(a=>/install|pkill|kill-all|--force/.test(a)));
  assert(fs.existsSync(path.join(output,'result.json')));
});
test('CLI error is incomplete and closes only this session once',()=>{
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-interior-failure-'));
  const calls=[];
  const execute=(bin,argv)=>{
    calls.push(argv[4]);
    if(argv[4]==='run-code')return {status:0,stdout:'{"isError":true}'};
    return {status:0,stdout:argv[4]==='close'?' {"status":"closed"}':'{}'};
  };
  const result=qa.runQa({project:ROOT,browser:'msedge'},{cli:'existing-cli.cjs',sourceFiles:[],study:{},counts},output,execute);
  assert.equal(result.status,'incomplete');assert.deepEqual(calls,['open','run-code','close']);
});
