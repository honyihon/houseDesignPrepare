'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const qa=require('../../scripts/check_b32_entry_playwright.cjs');
const planViewer=require('../../scripts/templates/b32-plan-viewer.js');
const root=path.resolve(__dirname,'../..');
function manifest(){return JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/b32-entry-options/layout.js'),'utf8').split(' = ')[1].replace(/;\s*$/,''));}
test('B32 files, source hashes and same-source geometry preflight',()=>{
  const r=qa.preflight(root);assert.deepEqual(r.mainCounts,{floors:12,rooms:112,items:128});
  assert.deepEqual(r.counts,{options:2,floors:8,rooms:64,items:60});
  assert.equal(r.displayRevision,2);assert.ok(r.sourceFiles.includes('scripts/templates/b32-plan-viewer.js'));
  assert.ok(r.sourceFiles.includes('structured/candidates/b32-entry-options-3d.html'));
});
for(const defect of ['approval','missing-rights','over32','rear-leak','missing-route','resized-body'])test('rejects '+defect,()=>{
  const s=manifest();
  if(defect==='approval')s.professional_status.transport='passed';
  if(defect==='missing-rights')delete s.access_evidence.rear_route_rights;
  if(defect==='over32')s.options[0].frame_mm[1]=20530;
  if(defect==='rear-leak')s.options[1].plans.floors[0].rooms.find(r=>r.key==='storage').features.doors.push({purpose:'rear-palanquin-entry'});
  if(defect==='missing-route')s.options[0].review.program.transport.segments=[];
  if(defect==='resized-body')s.options[0].plans.floors[0].rooms.find(r=>r.key==='storage').furniture[0].placement.aabb.maxX+=100;
  assert.throws(()=>qa.validateStudy(s));
});
test('generated script is self-contained in CLI VM without global URL',()=>{
  const script=qa.makeBrowserScript('file:///C:/house/','C:/Temp/b32',{options:2,floors:8,rooms:64,items:60});
  assert.doesNotThrow(()=>new vm.Script(script));
  assert.ok(!script.includes('new URL('));
  for(const text of ['#study-scheme','transportRoutes','rear-palanquin-entry','390','844','data-plan-viewer','minimumLabelPx',"viewport.press('End')",'planReadability','session']){
    if(text==='session')continue;assert.ok(script.includes(text));
  }
});
test('both generated pages inline scripts compile',()=>{
  for(const file of ['b32-entry-options.html','b32-entry-options-3d.html']){
    const html=fs.readFileSync(path.join(root,'structured/candidates',file),'utf8');
    const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
    assert.ok(scripts.length>=1);for(const m of scripts)assert.doesNotThrow(()=>new vm.Script(m[1]));
  }
});
test('passing report requires new desktop/mobile reading coverage, not old screenshots only',()=>{
  const counts={options:2,floors:8,rooms:64,items:60};
  const planReadability=['b32-rear','b32-front'].flatMap(option=>[{width:1440,height:900},{width:390,height:844},{width:844,height:390}].map(viewport=>
    ({option,viewport,readableWidth:660,zoomWidth:891,overviewWidth:210,minimumLabelPx:14.5,loaded:true,keyboardScroll:true,independent:true,noPageOverflow:true})));
  const report={marker:'house-b32-entry-cli-qa',revision:2,displayRevision:2,status:'passed',counts,checks:[{name:'fixture',passed:true}],planReadability,screenshots:Array.from({length:16},(_,i)=>i+'.png')};
  assert.equal(qa.validateReport(report,counts),report);assert.deepEqual(qa.findReport({result:JSON.stringify(report)}),report);
  for(const patch of [{revision:1},{displayRevision:1},{screenshots:undefined},{screenshots:report.screenshots.slice(0,8)},
    {planReadability:undefined},{planReadability:planReadability.slice(0,5)},
    {planReadability:planReadability.map(v=>({...v,minimumLabelPx:6}))},
    {planReadability:planReadability.map(v=>({...v,loaded:false}))},
    {planReadability:planReadability.map(v=>({...v,option:'b32-rear'}))},
    {counts:{...counts,items:59}},{checks:[{passed:false}]},{status:'incomplete'}])assert.throws(()=>qa.validateReport({...report,...patch},counts));
});

// Exercise the serialized production callback, not a second copy of its checks.
// Native sizes/events are fixtures: reaching this gate is NOT rendered evidence.
async function readingCallbackFixture(defect){
  const s=manifest(),sentinel='unit fixture reached 3D; no browser rendered';
  let size={width:1440,height:900},route='',roots={},browserDocument={};
  const callbacks=node=>{node.handlers={};node.addEventListener=(name,fn)=>(node.handlers[name]??=[]).push(fn);
    node.dispatch=(name,extra={})=>{for(const fn of node.handlers[name]||[])fn({target:node,preventDefault(){},...extra});};return node;};
  function build(o){
    const object=callbacks({style:{width:'660px',height:'1903px'},contentDocument:null,
      getAttribute:name=>name==='data'?'b32-entry-options/'+o.plans.floors[0].plan_file:null,
      getBoundingClientRect(){return {width:parseFloat(this.style.width),height:parseFloat(this.style.height)};}});
    let left=0,top=0;
    const viewport=callbacks({tabIndex:0,clientWidth:Math.min(1080,size.width)-60,clientHeight:Math.max(280,Math.min(640,size.height*.65)),
      get scrollWidth(){return Math.max(this.clientWidth,parseFloat(object.style.width));},
      get scrollHeight(){return Math.max(this.clientHeight,parseFloat(object.style.height));},
      get scrollLeft(){return left;},set scrollLeft(n){left=Math.max(0,Math.min(this.scrollWidth-this.clientWidth,n));},
      get scrollTop(){return top;},set scrollTop(n){top=Math.max(0,Math.min(this.scrollHeight-this.clientHeight,n));},
      getAttribute:name=>name==='role'?'region':name==='aria-describedby'?o.id+'-hint':null});
    const buttons=['in','out','readable','overview'].map(action=>callbacks({dataset:{planAction:action},attrs:{},disabled:false,
      setAttribute(name,value){this.attrs[name]=value;},getAttribute(name){return this.attrs[name];},
      getBoundingClientRect:()=>({width:110,height:44})}));
    const controls={hidden:true,querySelectorAll:()=>buttons};
    const nodes={'[data-plan-viewport]':viewport,object,'[data-plan-controls]':controls,
      '[data-plan-state]':{getAttribute:name=>name==='aria-live'?'polite':null},
      '[data-original-plan]':{getAttribute:name=>object.getAttribute('data')},'[data-plan-error]':{hidden:true}};
    const root={dataset:{sourceWidth:'6600',sourceHeight:'19030',readableWidth:'660',minLabelUnits:'145'},
      querySelectorAll:selector=>selector==='[data-plan-action]'?buttons:[],
      querySelector(selector){if(selector.startsWith('[data-plan-action='))return buttons.find(b=>selector.includes('"'+b.dataset.planAction+'"'));return nodes[selector];}};
    const controller=planViewer.attach(root);object.dispatch('load');
    const rear=o.id==='b32-rear';
    if(rear&&defect==='wrong-source')object.getAttribute=()=> 'b32-entry-options/b32-front_floor-1.svg';
    if(rear&&defect==='unreadable')object.getBoundingClientRect=()=>({width:parseFloat(object.style.width)/2,height:parseFloat(object.style.height)/2});
    if(rear&&defect==='bad-reset'){
      let clicks=0;buttons.find(b=>b.dataset.planAction==='readable').addEventListener('click',()=>{if(++clicks>1)root.dataset.planMode='zoom';});
    }
    return {root,viewport,object,buttons,controller};
  }
  const locateNode=(root,node)=>({
    async evaluate(fn){return vm.runInNewContext('('+fn.toString()+')(node)',{node,document:browserDocument,innerWidth:size.width,getComputedStyle:()=>({touchAction:'auto'})});},
    locator(selector){return locateNode(root,root.querySelector(selector));},
    async click(){assert.ok(node&&!node.disabled);node.dispatch('click');},
    async focus(){assert.ok(node);},async scrollIntoViewIfNeeded(){assert.ok(node);},
    async getAttribute(name){return node.getAttribute(name);},
    async press(key){if(key==='Enter')node.dispatch('click');else node.dispatch('keydown',{key});},
  });
  const page={setDefaultTimeout(){},setDefaultNavigationTimeout(){},on(){},
    async setViewportSize(value){size=value;},
    async goto(url){
      route=url;if(url.includes('b32-entry-options-3d'))throw new Error(sentinel);
      roots=Object.fromEntries(s.options.map(o=>[o.id,build(o)]));
      if(defect==='linked-zoom')roots['b32-rear'].buttons.find(b=>b.dataset.planAction==='in').addEventListener('click',()=>roots['b32-front'].controller.action('in'));
      browserDocument={documentElement:{scrollWidth:size.width+(defect==='page-overflow'?10:0)},getElementById:()=>({})};
    },
    async title(){return 'B 32地坪';},url(){return route;},async addScriptTag(){},async screenshot(){},
    async waitForFunction(_,id){assert.equal(roots[id].root.dataset.planLoaded,'true');},
    async evaluate(){return s;},
    locator(selector){
      if(selector.startsWith('[data-plan-viewer=')){const id=selector.match(/"([^"]+)"/)[1];return locateNode(roots[id].root,roots[id].root);}
      return {async count(){return selector==='[data-option]'?2:0;},async innerText(){return '後巷／通行權未核';},async getAttribute(){return '2';}};
    },
  };
  const context=vm.createContext({});assert.equal(vm.runInContext('typeof URL',context),'undefined');
  const run=new vm.Script(qa.makeBrowserScript('file:///C:/house/','/fixture-not-screenshots',{options:2,floors:8,rooms:64,items:60})).runInContext(context);
  return {result:await run(page),sentinel};
}
test('serialized CLI without global URL completes all six reading flows before the 3D gate',async()=>{
  const {result,sentinel}=await readingCallbackFixture();
  assert.equal(result.status,'failed');assert.equal(result.error,'Error: '+sentinel);
  assert.equal(result.planReadability.length,6);assert.ok(result.checks.every(c=>c.passed));
  assert.equal(result.counts.floors,0,'fixture must never claim actual 3D coverage');
});
for(const [defect,message] of [['wrong-source','unchanged same-option SVG'],['unreadable','readable vector and label scale'],
  ['page-overflow','no page overflow'],['linked-zoom','independent plan zoom'],['bad-reset','reading reset restores source and origin']]){
  test('production reading callback rejects '+defect,async()=>{
    const {result}=await readingCallbackFixture(defect);
    assert.equal(result.status,'failed');assert.ok(result.error.includes(message),result.error);
    assert.ok(result.checks.some(c=>!c.passed&&c.name.startsWith(message)));
  });
}

// Reuse the existing scene-math/DOM contract harness without editing old
// comparisons. Only WebGLRenderer is doubled: this is NOT browser/CSS proof.
const harness=fs.readFileSync(path.join(__dirname,'model3d-facade-runtime.test.cjs'),'utf8').split("test('BC real scene math")[0]
  .replace("options.bc?'bc-options':","options.b32?'b32-entry-options':options.bc?'bc-options':");
const {runtime}=vm.runInNewContext(harness+'\n({runtime});',{require,__dirname,console,URL,URLSearchParams});
test('B32 actual Three scene math retains all 8 floors and oriented transport coordinates',()=>{
  for(const o of manifest().options){
    const r=runtime('#mode=tour&building=B&floor=floor-1&view='+(o.entry_mode==='rear'?'rear':'front'),1080,900,{b32:true,scheme:o.id});
    assert.equal(r.body.getAttribute('data-study-option'),o.id);
    assert.equal(r.nodes['study-plan-link'].href,'b32-entry-options.html#'+o.id);
    for(const floor of o.plans.floors){
      r.button('scope-floors','data-floor',floor.id);r.frame();const d=r.debug();
      assert.equal(d.visibleRooms.length,floor.rooms.length);assert.equal(d.bcOption.id,o.id);
      for(const room of floor.rooms){const c=d.tour.rooms.find(c=>c.id===room.id);assert.equal(JSON.stringify(c.geometry),JSON.stringify(room.geometry));
        for(const i of room.furniture){const p=d.furniture.shapes.find(v=>v.id===i.id);
          assert.ok(p.visible&&p.parts>0&&!p.overflow&&!p.collision,i.id);assert.equal(p.width,i.width_mm);assert.equal(p.depth,i.depth_mm);}}
      if(floor.id==='floor-1'){
        assert.equal(d.transportRoutes.length,o.review.program.transport.segments.length);
        for(const rendered of d.transportRoutes){
          const part=o.review.program.transport.segments.find(s=>s.id===rendered.segment.id);assert.equal(JSON.stringify(rendered.segment),JSON.stringify(part));
          const expected=part.centerline_mm.flatMap(([x,y])=>[x*.001,.05,-y*.001]);
          assert.equal(rendered.renderedPoints.length,expected.length);
          expected.forEach((v,n)=>assert.ok(Math.abs(v-rendered.renderedPoints[n])<.00001));
        }
      }else assert.equal(d.transportRoutes.length,0,'1F routes do not leak into other floors');
    }
  }
});
test('B32 normalization, switch, no-WebGL fallback and mobile focus stay in their own option',()=>{
  const redirect=runtime('#mode=tour&building=B&floor=floor-1',1080,900,{b32:true,scheme:'invalid'});
  assert.equal(redirect.renderCount,0);assert.match(redirect.assigned[0],/scheme=b32-rear/);
  for(const o of manifest().options){
    const unavailable=runtime('#mode=tour&building=B&floor=floor-1',1080,900,{b32:true,scheme:o.id,noWebGL:true});
    assert.equal(unavailable.find('renderer-fallback').hidden,false);
    assert.equal(unavailable.find('renderer-fallback').children.find(n=>n.tagName==='a').href,'b32-entry-options.html#'+o.id);
    assert.equal(unavailable.nodes['study-plan-link'].href,'b32-entry-options.html#'+o.id);
    for(const [width,height] of [[390,450],[844,336]]){
      const r=runtime('#mode=tour&building=B&floor=floor-1&room=B:floor-1:storage&focus=room&view='+(o.entry_mode==='rear'?'rear':'front'),width,height,{b32:true,scheme:o.id});r.frame();
      const d=r.debug();assert.ok(d.roomCloseup);assert.equal(d.visibleRooms.length,o.plans.floors[0].rooms.length);
      assert.ok(d.focusedScreenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
      r.nodes['study-scheme'].value=o.id==='b32-rear'?'b32-front':'b32-rear';r.nodes['study-scheme'].dispatchEvent({type:'change'});
      assert.match(r.assigned[0],new RegExp('scheme='+(o.id==='b32-rear'?'b32-front':'b32-rear')));
      assert.equal(r.debug().bcOption.id,o.id,'switch must navigate, not mutate or adopt the active model');
    }
  }
});
