// Infrastructure checks only. Fake CLI reports are never browser evidence.
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const vm=require('node:vm');
const {URL: NodeURL}=require('node:url');
const qa=require('../../scripts/check_preparation_playwright.cjs');
const root=path.resolve(__dirname,'../..');
const manifest=()=>JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/preparation-review/layout.js'),'utf8').split(' = ')[1].replace(/;\s*$/,''));
const counts={options:7,floors:28,rooms:281,items:284};
const report=()=>({marker:'house-preparation-cli-qa',revision:2,status:'passed',counts,checks:[{name:'fixture-not-rendered',passed:true}],screenshots:Array.from({length:10},(_,n)=>n+'.png')});

test('all new artifacts current, without approving main or comparisons',()=>{
  const result=qa.preflight(root);
  assert.deepEqual(result.counts,counts);
  assert.deepEqual(result.mainCounts,{floors:12,rooms:112,items:128});
  assert.ok(result.sourceFiles.includes('structured/candidates/preparation-review-3d.html'));
});
test('adoption, changed area frame, professional approval and unresolved furniture are rejected',()=>{
  for(const mutate of [s=>s.active_design='c-window-3000',s=>s.professional_status.accessibility='passed',
    s=>s.options[4].frame_mm=[6000,17630],s=>s.options[0].review.coordinate_screen.fixed_body_failures.push({issue:'bad'}),
    s=>s.options[0].review.coordinate_screen.operation_sharing.push({issue:'operation-vs-body'})]){
    const s=manifest();mutate(s);assert.throws(()=>qa.validateStudy(s));
  }
});
test('v2 rejects stale revision, optimistic finished widths and nominal-only regression',()=>{
  for(const mutate of [s=>s.revision=1,
    s=>s.options[0].review.program.revision_checks.wash_shares_door_approach=true,
    s=>s.options[0].plans.floors[0].rooms.find(r=>r.key==='dining').features.window_ratio=.4,
    s=>s.options[4].review.program.transport.clearance_budget.segments[0].finished_clear_mm=1520,
    s=>s.options[4].plans.floors[0].rooms.find(r=>r.key==='entry').geometry.w_mm=1600,
    s=>s.options[4].review.program.transport.clearance_budget.frame_product='verified']){
    const s=manifest();mutate(s);assert.throws(()=>qa.validateStudy(s));
  }
});
test('new browser function is self-contained and exercises selection/mobile/floor return',()=>{
  const script=qa.makeBrowserScript('file:///C:/house/',os.tmpdir(),counts);
  new vm.Script(script);
  for(const expected of ['selectOption','study-stage-note','public-bath','bath1','room-overview',
    'preparation-review.html#','focus=room','1440','390','__htmlModel3dDebug'])assert.ok(script.includes(expected));
});
for (const alreadySelected of [true,false]) {
  test('CLI VM without global URL reaches renderer readiness: '+(alreadySelected?'keep option':'switch option'),async()=>{
    const id='c-window-3000', sentinel='unit fixture stops at renderer readiness';
    const target='file:///C:/house/structured/candidates/preparation-review-3d.html?scheme='+id;
    let selected=alreadySelected?id:'b-fixed-3000', waits=0;
    const selections=[];
    const page={
      setDefaultTimeout(){},setDefaultNavigationTimeout(){},on(){},
      async setViewportSize(){},async goto(){},async screenshot(){},async addScriptTag(){},
      async title(){return 'ABC前期整合比較';},
      url(){return target;},
      async evaluate(){return {options:[{id}]};},
      locator(selector){return {
        async count(){return ({'section[data-option]':7,'[data-clearance-budget]':4,'[data-revision-checks]':3})[selector]||0;},
        first(){return this;},async innerText(){return '比較方案未採用';},
        async getAttribute(name){
          assert.equal(selector,'body');assert.equal(name,'data-study-option');return selected;
        },
        async selectOption(value){assert.equal(selector,'#study-scheme');selections.push(value);selected=value;},
      };},
      async waitForURL(predicate){
        await Promise.resolve();
        assert.equal(predicate(new NodeURL(target)),true);waits++;
      },
      async waitForFunction(){throw new Error(sentinel);},
    };
    const context=vm.createContext({});
    assert.equal(vm.runInContext('typeof URL',context),'undefined');
    const run=new vm.Script(qa.makeBrowserScript('file:///C:/house/','/fixture-not-screenshots',counts)).runInContext(context);
    const result=await run(page);
    // Deliberately stops before any renderer: this is NOT browser evidence.
    assert.equal(result.status,'failed');assert.equal(result.error,'Error: '+sentinel);
    assert.deepEqual(selections,alreadySelected?[]:[id]);
    assert.equal(waits,alreadySelected?0:1);
  });
}
for (const sourceDefault of ['tour','declared']) {
  test('production tour selectors ignore inactive legacy source: '+sourceDefault,()=>{
    const html=fs.readFileSync(path.join(root,'scripts/templates/model3d.html'),'utf8');
    const initialization=html.match(/  var geomSource = [^\n]+;/)[0];
    const selectors=['geomOf','featuresOf','placementOf'].map(name=>
      html.match(new RegExp('  function '+name+'\\([^\\n]+\\) \\{[\\s\\S]*?\\n  \\}'))[0]).join('\n');
    const cell={tour_mm:{tag:'proposal'},auto_mm:{tag:'historical'},declared_mm:{tag:'legacy-override'},
      tour_features:{geometry_source:'tour_mm'},architecture_auto:{geometry_source:'auto_mm'},
      architecture_declared:{geometry_source:'declared_mm'},furniture_placements:{
        tour_mm:{item:{tag:'proposal'}},auto_mm:{item:{tag:'historical'}},declared_mm:{item:{tag:'legacy-override'}},
      }};
    const context=vm.createContext({DATA:{geom_source_default:sourceDefault},presentation:'tour',viewState:{room:''},cell});
    vm.runInContext(initialization+'\n'+selectors,context);
    assert.equal(vm.runInContext('geomSource',context),sourceDefault==='declared'?'declared':'auto');
    assert.equal(vm.runInContext('geomOf(cell)',context),cell.tour_mm);
    assert.equal(vm.runInContext('featuresOf(cell)',context),cell.tour_features);
    assert.equal(vm.runInContext('placementOf(cell,{id:"item"})',context),cell.furniture_placements.tour_mm.item);
  });
}
async function runFirstFloorStateFixture(mutate) {
  const original=manifest().options[0], floor=original.plans.floors[0];
  const option={...original,plans:{...original.plans,floors:[floor]}};
  const sentinel='unit fixture reached room focus after verified tour state';
  const debug={bcOption:{id:option.id},presentation:'tour',geomSource:'auto',
    state:{building:option.building,floor:floor.id,room:'',view:'front'},
    visibleRooms:floor.rooms.map(r=>r.id),tour:{rooms:floor.rooms.map(r=>({id:r.id,
      geometry:{...r.geometry},features:{...r.features},base_mm:floor.base_mm,height_mm:floor.height_mm,
      architectureVisible:true,architectureParts:1}))},
    furniture:{shapes:floor.rooms.flatMap(r=>r.furniture.map(i=>({id:i.id,visible:true,parts:1,
      width:i.width_mm,depth:i.depth_mm,height:i.height_mm,overflow:false,collision:false,
      center:[i.placement.center_x_mm,i.placement.center_y_mm]})))},
  };
  mutate(debug);
  let route='';
  const page={
    setDefaultTimeout(){},setDefaultNavigationTimeout(){},on(){},
    async setViewportSize(){},async goto(url){route=url;},async screenshot(){},async addScriptTag(){},
    async title(){return route.includes('preparation-review-3d')?option.label:'ABC前期整合比較';},
    async evaluate(fn){return String(fn).includes('HOUSE_PREPARATION_REVIEW')?{options:[option]}:debug;},
    async waitForFunction(){},
    locator(selector){return {
      async count(){return ({'section[data-option]':7,'[data-clearance-budget]':4,'[data-revision-checks]':3})[selector]||0;},first(){return this;},
      async innerText(){return '比較方案未採用';},
      async isVisible(){return selector==='#study-stage-note';},
      async getAttribute(name){
        if(selector==='body'&&name==='data-study-option')return option.id;
        if(selector==='#study-plan-link'&&name==='href')return 'preparation-review.html#'+option.id;
        throw new Error('Unexpected fixture attribute: '+selector+' '+name);
      },
      async click(){if(selector.startsWith('#scope-rooms'))throw new Error(sentinel);},
    };},
  };
  const run=new vm.Script(qa.makeBrowserScript('file:///C:/house/','/fixture-not-screenshots',counts)).runInNewContext({});
  return {result:await run(page),sentinel};
}
for (const legacySource of ['auto','declared']) {
  test('serialized CLI accepts real tour geometry with inactive '+legacySource+' selector',async()=>{
    const {result,sentinel}=await runFirstFloorStateFixture(d=>{d.geomSource=legacySource;});
    assert.equal(result.status,'failed');assert.equal(result.error,'Error: '+sentinel);
    assert.equal(result.counts.floors,1);
    assert.ok(result.checks.some(c=>c.name.startsWith('isolated tour state')&&c.passed));
  });
}
for (const [name,mutate] of [
  ['wrong active geometry despite a tour flag',d=>{d.geomSource='tour';d.tour.rooms[0].features.geometry_source='auto_mm';}],
  ['wrong option',d=>{d.bcOption.id='b-fixed-3000';}],
  ['wrong presentation',d=>{d.presentation='interior';}],
  ['wrong building',d=>{d.state.building='B';}],
  ['wrong floor',d=>{d.state.floor='floor-2';}],
  ['missing tour room',d=>{d.tour.rooms.pop();}],
]) {
  test('serialized CLI rejects '+name,async()=>{
    const {result}=await runFirstFloorStateFixture(mutate);
    assert.equal(result.status,'failed');assert.match(result.error,/isolated tour state/);
    assert.equal(result.counts.floors,0);
    const failure=result.checks.find(c=>!c.passed&&c.name.startsWith('isolated tour state'));
    assert.equal(failure.details.expected.geometry,'tour_mm');
    assert.ok(failure.details.actual.geometrySources);
  });
}
test('serialized CLI still rejects rendered geometry drift after valid tour state',async()=>{
  const {result}=await runFirstFloorStateFixture(d=>{d.tour.rooms[0].geometry.w_mm+=100;});
  assert.equal(result.status,'failed');assert.match(result.error,/rendered dimensions/);
  assert.equal(result.counts.floors,0);
});
test('passing reports need actual check records, matching counts and screenshot list',()=>{
  assert.deepEqual(qa.validateReport(report(),counts),report());
  for(const mutate of [r=>r.revision=1,r=>delete r.revision,r=>delete r.screenshots,r=>r.screenshots=[],r=>r.checks=[],
    r=>r.checks[0].passed=false,r=>r.counts={options:1},r=>r.marker='house-windows-cli-qa']){
    const r=report();mutate(r);assert.throws(()=>qa.validateReport(r,counts));
  }
  assert.equal(qa.findReport({result:JSON.stringify(report())}).marker,'house-preparation-cli-qa');
  assert.equal(qa.findReport('not json'),null);
});
function fixture(t){
  const project=fs.mkdtempSync(path.join(os.tmpdir(),'preparation-qa-test-'));
  t.after(()=>fs.rmSync(project,{recursive:true,force:true}));
  fs.writeFileSync(path.join(project,'source.txt'),'unchanged');
  const output=path.join(project,'output');fs.mkdirSync(output);
  return {project,output,prepared:{cli:'fixture-cli.js',sourceFiles:['source.txt'],counts}};
}
test('one temporary CLI session, no install, and close even when request fails',t=>{
  const {project,output,prepared}=fixture(t), calls=[];
  const execute=(_,args)=>{calls.push(args);return args.includes('run-code')?
    {status:0,stdout:JSON.stringify({result:JSON.stringify(report())})}:
    {status:0,stdout:JSON.stringify({status:args.includes('close')?'closed':'open'})};};
  const r=qa.runQa({project,browser:'msedge'},prepared,output,execute);
  assert.equal(r.status,'passed');assert.equal(r.sessionClosed,true);
  assert.equal(calls.length,3);assert.ok(calls[2].includes('close'));
  assert.equal(new Set(calls.map(c=>c.find(a=>a.startsWith('-s=')))).size,1);
  assert.ok(calls.every(c=>!c.includes('install')&&!c.includes('pull')));
});
test('changed sources cannot yield passing browser QA',t=>{
  const {project,output,prepared}=fixture(t);
  const execute=(_,args)=>{
    if(args.includes('run-code')){fs.writeFileSync(path.join(project,'source.txt'),'changed');return {status:0,stdout:JSON.stringify({result:JSON.stringify(report())})};}
    return {status:0,stdout:JSON.stringify({status:args.includes('close')?'closed':'open'})};
  };
  const r=qa.runQa({project,browser:'msedge'},prepared,output,execute);
  assert.equal(r.status,'incomplete');assert.match(r.error,/Sources changed/);assert.equal(r.sessionClosed,true);
});
test('failed open leaves incomplete result and still closes only its session',t=>{
  const {project,output,prepared}=fixture(t), calls=[];
  const execute=(_,args)=>{calls.push(args);return args.includes('open')?{status:1,stdout:'',stderr:'blocked'}:
    {status:0,stdout:JSON.stringify({status:'closed'})};};
  const r=qa.runQa({project,browser:'msedge'},prepared,output,execute);
  assert.equal(r.status,'incomplete');assert.equal(calls.length,2);assert.equal(r.sessionClosed,true);
});
