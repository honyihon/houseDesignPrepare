// Files-only preflight; owner runs the single native Windows browser session.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const basis=require('./check_current_design_playwright.cjs'),legacy=require('./check_windows_playwright.cjs');
const MARKER='house-c-care-entry-qa',INDEX='structured/candidates/c-care-entry.html',VIEWER='structured/candidates/c-care-entry-3d.html',REPORT='structured/candidates/c-care-entry/review.json';
function mobileCases(study){return study.options.flatMap(o=>o.states.map(s=>{
  const f=s.plans.floors[0],r=f.rooms.find(r=>r.key==='elder');
  return {option:o.id,use:s.id,building:'C',floor:f.id,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),
    items:r.furniture.map(i=>({id:i.id,short:i.shape==='bed'?40:16,long:i.shape==='bed'?96:28}))};
}));}
function leafSpecs(state){return state.plans.floors[0].rooms.flatMap(r=>(r.features.care_entry_leaves||[]).map(l=>({...l,room:r.id})));}
function inspectLeaves(actual,expected){
  if(!Array.isArray(actual)||actual.length!==expected.length||new Set(actual.map(a=>a.id)).size!==actual.length)throw Error('Missing/duplicate actual door-leaf meshes');
  for(const e of expected){
    const a=actual.find(a=>a.id===e.id),b=a?.actualBoundsMm,[x,y,w,d]=e.rect_mm;
    const coords={minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:0,maxHeight:e.height_mm};
    if(!a||a.state!==e.state||a.room!==e.room||a.counts_as_furniture!==false||a.status!=='generic-leaf-envelope-not-selected-product'||
      !b||Object.entries(coords).some(([k,v])=>!Number.isFinite(b[k])||Math.abs(b[k]-v)>.1))throw Error('Actual unscaled door-leaf body differs: '+e.id);
  }return actual;
}
function preflight(project){
  const primary=basis.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-c-care-entry-v1'||study.revision!==1||study.display_revision!==2||study.adopted!==false||study.status!=='discussion-only-not-adopted'||study.rendered_qa!=='not-run'||
    study.default_option!=='c-entry-refined'||!same(study.frame_mm,[6000,17630])||Object.values(study.professional_status).some(s=>s!=='unknown')||
    !same(study.options.map(o=>o.id),['c-entry-control','c-entry-refined'])||study.requirement_ledger.canonical_requirements!==66||study.requirement_ledger.scenario_rows!==40||study.requirement_ledger.verified_requirements!==0)
    throw Error('Invalid care scope, original requirements or professional/adoption status');
  const files=[INDEX,VIEWER,REPORT,'structured/candidates/c-care-entry/requirement-ledger.json','scripts/check_c_care_entry_playwright.cjs'];
  basis.validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8').replaceAll('care-adoption-warning','basis-adoption-warning'));
  for(const [rel,digest] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe care source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale care source: '+rel);files.push(rel);
  }
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),m=text.match(/^\s*var DATA = (.+);\s*$/m),payload=m&&JSON.parse(m[1]).c_care_entry;
  if(!payload||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id))||!text.includes('careEntryEvidence()')||text.includes('DATA.source.current_design_basis'))throw Error('Mixed or missing independent care viewer');
  if(!same(JSON.parse(fs.readFileSync(path.join(project,files[3]),'utf8')),study.requirement_ledger))throw Error('Stale care ledger');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(o.building!=='C'||o.adopted!==false||!same(o.states.map(s=>s.id),o.id==='c-entry-control'?['daily']:['open','closed']))throw Error('Invalid independent door states');
    for(const s of o.states){
      const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.buildings[0].id!=='C'||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Mixed care plan/model/review');
      for(const f of s.plans.floors){
        const cells=model.buildings[0].floors.find(v=>v.id===f.id).cells.filter(c=>c.tour_active);
        if(cells.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Care floor expanded or incomplete');
        for(const r of f.rooms){const c=cells.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('Care HTML/3D geometry, doors or furniture differ');}
        const rel='structured/candidates/c-care-entry/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');files.push(rel);
        if(!svg.includes('width="660"')||!svg.includes('data-care-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"'))throw Error('Missing bounded same-source care SVG');
        if(f.id==='floor-1')for(const l of leafSpecs(s))if(!svg.includes('data-care-leaf-id="'+l.id+'"')||!svg.includes('data-leaf-state="'+s.id+'"'))throw Error('Missing SVG door-leaf state');
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const detail='structured/candidates/c-care-entry/'+o.id+'_'+s.id+'_detail.svg';files.push(detail);
      if(!fs.readFileSync(path.join(project,detail),'utf8').includes('width="780"'))throw Error('Missing bounded care detail');
      if(o.id==='c-entry-refined'){
        const e=s.review.entry;
        if(e.entry_projects_onto_bed_body||e.turn_coordinate_failures.length||e.doors.some(d=>d.nominal_mm!==1200||d.operation!=='sliding'||d.sensitivity.at(-1).clear_assumption_mm!==970||d.selected_product!==null)||
          Object.values(e.routes).some(r=>s.id==='open'?r.coordinate_failures.length:!r.coordinate_failures.length))throw Error('Care route or negative closed-door evidence differs');
      }
      counts.states++;
    }counts.options++;
  }
  return {study,counts,closeupCases:mobileCases(study),mainCounts:primary.mainCounts,cli:primary.cli,sourceFiles:[...new Set([...primary.sourceFiles,...files])]};
}
async function checkPages(page,base,output,study,expected,cases,inspectMobileView,inspectLeaves){
  const checks=[],screenshots=[],messages=[],mobileEvidence=[],leafEvidence=[],counts={options:0,states:0,floors:0,rooms:0,items:0};
  const assert=(ok,name)=>{checks.push({name,passed:Boolean(ok)});if(!ok)throw Error(name);};
  const capture=async name=>{const p=output+'/'+name;await page.screenshot({path:p,fullPage:false});screenshots.push(p);};
  const ready=async(o,s)=>page.waitForFunction(([o,s])=>document.body.dataset.studyKind==='c-care-entry'&&document.body.dataset.studyOption===o&&document.body.dataset.studyUse===s&&window.__htmlModel3dDebug?.().cameraFraming.ready,[o,s]);
  const fitted=async overview=>page.waitForFunction(overview=>{
    const d=window.__htmlModel3dDebug(),f=d.cameraFraming,c=d.currentDesignCamera,draw=c?.lastDraw;
    return d.panelCollapsed&&f.ready&&f.safeArea.usable&&c.revision===2&&c.scissorTestRestored&&d.roomCloseup!==overview&&draw?.clipped!==overview&&
      draw.renderSize.width===f.width&&draw.renderSize.height===f.height&&draw.stage.width===f.width&&draw.stage.height===f.height&&
      f.autoFit?.viewport?.width===f.width&&f.autoFit?.viewport?.height===f.height&&
      (overview?f.autoFit.closeupPolicy===null:f.autoFit.closeupPolicy==='current-design-readable-v2')&&
      ['left','right','top','bottom'].every(k=>Math.abs(f.autoFit.area[k]-f.safeArea[k])<1&&(overview||Math.abs(draw.area[k]-f.safeArea[k])<1.01));
  },overview);
  const readMobile=async phase=>page.evaluate(phase=>{
    const d=window.__htmlModel3dDebug(),f=d.cameraFraming,c=d.currentDesignCamera;
    return {phase,option:document.body.dataset.studyOption,use:document.body.dataset.studyUse,building:d.state.building,floor:d.state.floor,room:d.state.room,
      closeup:d.roomCloseup,panelCollapsed:d.panelCollapsed,displayRevision:c.revision,viewport:{width:innerWidth,height:innerHeight},stage:{width:f.width,height:f.height},
      safeArea:f.safeArea,fit:f.autoFit,draw:c.lastDraw,scissorTestRestored:c.scissorTestRestored,overlays:f.overlays,visibleRoomIds:d.visibleRooms,roomCorners:d.focusedScreenBounds,items:f.selectedItems};
  },phase);
  const warning=async()=>{
    const w=page.locator('#care-adoption-warning'),b=await w.boundingBox(),v=page.viewportSize();
    assert(await w.isVisible()&&(await w.innerText()).includes('未採用')&&b&&b.x>=0&&b.y>=0&&b.x+b.width<=v.width+1&&b.y+b.height<=v.height+1,'Visible first-viewport care non-adoption warning');
  };
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));page.on('console',m=>{if(['warning','error'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/c-care-entry.html');
    assert((await page.title()).includes('C孝親房入口')&&await page.locator('section[data-option]').count()===2,'Correct nonblank C-only two-option index');await warning();await capture('index-desktop.png');
    await page.goto(base+'structured/candidates/c-care-entry-3d.html');await ready('c-entry-refined','open');
    await page.locator('#study-scheme').selectOption('c-entry-control');await ready('c-entry-control','daily');
    assert((await page.evaluate(()=>window.__htmlModel3dDebug())).state.building==='C','Actual independent C scheme switch');
    for(const o of study.options){for(const s of o.states){
      await page.setViewportSize({width:1440,height:900});
      await page.goto(base+'structured/candidates/c-care-entry-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building=C&floor=floor-1&view=plan');await ready(o.id,s.id);
      assert(await page.locator('#study-stage-note').isVisible()&&(await page.title()).includes(o.label),'Visible isolated care option '+o.id+' '+s.id);
      assert(await page.locator('#study-plan-link').getAttribute('href')==='c-care-entry.html#'+o.id+'-'+s.id&&!(await page.locator('#tour-actions').isVisible()),'No mixed main shortcuts '+o.id+' '+s.id);
      for(const f of s.plans.floors){
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();await page.waitForFunction(id=>window.__htmlModel3dDebug().state.floor===id,f.id);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.presentation==='tour'&&d.visibleRooms.length===f.rooms.length&&d.state.building==='C','Complete actual C floor '+o.id+' '+s.id+' '+f.id);
        for(const r of f.rooms){const a=d.tour.rooms.find(v=>v.id===r.id);
          assert(a&&JSON.stringify(a.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(a.features)===JSON.stringify(r.features),'Actual paired aperture/room parity '+o.id+' '+s.id+' '+r.id);
          if(r.features.window_review?.renderable)assert(a.windowParts>0,'Actual retained exterior window '+o.id+' '+s.id+' '+r.id);
          for(const i of r.furniture){const b=d.furniture.shapes.find(p=>p.id===i.id);
            assert(b?.visible&&b.parts>0&&!b.overflow&&!b.collision&&b.width===i.width_mm&&b.depth===i.depth_mm&&b.height===i.height_mm&&
              Math.abs(b.center[0]-i.placement.center_x_mm)<.05&&Math.abs(b.center[1]-i.placement.center_y_mm)<.05,'Actual unscaled retained furniture '+o.id+' '+s.id+' '+i.id);}
        }
        if(f.id==='floor-1'){
          const spec=s.plans.floors[0].rooms.flatMap(r=>(r.features.care_entry_leaves||[]).map(l=>({...l,room:r.id})));
          leafEvidence.push({option:o.id,use:s.id,leaves:inspectLeaves(d.careEntry,spec)});await capture(o.id+'-'+s.id+'-desktop.png');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const spec=cases.find(c=>c.option===o.id&&c.use===s.id);
      await page.setViewportSize(spec.viewport);
      await page.goto(base+'structured/candidates/c-care-entry-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building=C&floor=floor-1&room='+encodeURIComponent(spec.room)+'&focus=room&view=front');await ready(o.id,s.id);
      const toggle=page.locator('#mobile-panel-toggle');if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
      await fitted(false);mobileEvidence.push(inspectMobileView(await readMobile('initial'),spec));await capture(o.id+'-'+s.id+'-mobile.png');
      await page.locator('#b32-room-details').click();assert(await page.locator('#furniture-list').isVisible(),'Accessible actual equipment list '+o.id+' '+s.id);
      await page.locator('#b32-details-back').click();await fitted(false);mobileEvidence.push(inspectMobileView(await readMobile('equipment-return'),spec));
      await page.locator('#room-overview').click();await fitted(true);mobileEvidence.push(inspectMobileView(await readMobile('overview'),spec));
      counts.states++;
    }counts.options++;}
    await page.goto(base+'structured/candidates/c-care-entry.html');await warning();await capture('index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'All independent care states and retained floors inspected');
    assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained runtime/console errors');
    return {marker:'house-c-care-entry-qa',revision:2,displayRevision:2,status:'passed',counts,checks,screenshots,messages,mobileEvidence,leafEvidence};
  }catch(e){await capture('failure.png').catch(()=>{});return {marker:'house-c-care-entry-qa',revision:2,displayRevision:2,status:'failed',error:String(e),counts,checks,screenshots,messages,mobileEvidence,leafEvidence};}
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${basis.inspectMobileView.toString()}),(${inspectLeaves.toString()}))`;}
function validateReport(r,prepared){
  if(!r||r.marker!==MARKER)throw Error('No completed C care structured evidence');
  basis.validateReport({...r,marker:'house-current-design-qa'},prepared.counts,prepared.closeupCases);
  if(r.status==='passed'){
    if(!Array.isArray(r.leafEvidence)||r.leafEvidence.length!==prepared.counts.states)throw Error('Missing actual leaf evidence');
    const seen=new Set();
    for(const e of r.leafEvidence){const state=prepared.study.options.find(o=>o.id===e.option)?.states.find(s=>s.id===e.use),key=e.option+'/'+e.use;
      if(!state||seen.has(key))throw Error('Duplicate/unknown door-leaf state');seen.add(key);inspectLeaves(e.leaves,leafSpecs(state));}
  }return r;
}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function runQa(o,p,output,execute=spawnSync){
  const session='house-c-care-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(o.project+path.sep).href,sourceHashes=legacy.hashSources(o.project,p.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:o.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,p.study,p.counts,p.closeupCases));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[p.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:180000,maxBuffer:12*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+r.error:''));if(required&&(r.error||r.status!==0))throw Error(name+' failed; see '+name+'.log');return r;};
  let r={marker:MARKER,status:'incomplete'};
  try{invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);if(response.isError)throw Error('CLI error; see checks.log');
    r=validateReport(findReport(response),p);if(!same(sourceHashes,legacy.hashSources(o.project,p.sourceFiles))){r.status='incomplete';r.error='Sources changed during QA';}}
  catch(e){r.status='incomplete';r.error=String(e);}
  finally{Object.assign(r,{project:o.project,sourceHashes,browser:o.browser,session});try{const c=invoke('close',['close'],false);r.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{r.sessionClosed=false;}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(r,null,2));}return r;
}
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_c_care_entry_playwright.cjs [--preflight] [--project <path>]; no install or adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node for rendered QA; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('C care entry preflight passed: '+JSON.stringify(p.counts));
  console.log('Original C retained. 1200mm nominal sliders compare open/closed; actual 900mm clear, whole-route care and rescue NOT approved.');
  if(o.preflight){console.log('Files only; no browser or professional approval.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-care-entry-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated C care entry browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('This session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. No adoption, wheelchair, fengshui, legal or rescue approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={mobileCases,leafSpecs,inspectLeaves,preflight,checkPages,makeBrowserScript,validateReport,findReport,runQa};
