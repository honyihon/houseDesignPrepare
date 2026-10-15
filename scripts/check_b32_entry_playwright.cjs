// B32 rear priority / front fallback. Existing Windows Playwright CLI only.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const MARKER='house-b32-entry-cli-qa';
const DISPLAY_REVISION=2;
const IDS=['b32-rear','b32-front'];
const MANIFEST='structured/candidates/b32-entry-options/layout.js';
const INDEX='structured/candidates/b32-entry-options.html';
const VIEWER='structured/candidates/b32-entry-options-3d.html';
function assignment(project,file){
  const match=fs.readFileSync(path.join(project,file),'utf8').match(/^\s*window\.HOUSE_B32_ENTRY_OPTIONS\s*=\s*([\s\S]+?)\s*;\s*$/);
  if(!match)throw new Error('Missing B32 manifest');return JSON.parse(match[1]);
}
function validateStudy(s){
  if(s.schema!=='house-b32-entry-options-v1'||s.revision!==1||s.status!=='comparison-only-not-adopted'||
     s.active_design!=='baseline'||s.default_option!==IDS[0]||s.land_cap_ping!==32||!same(s.options.map(o=>o.id),IDS)||
     Object.keys(s.professional_status).length!==7||Object.values(s.professional_status).some(v=>v!=='unknown')||Object.keys(s.access_evidence).length!==5||
     Object.values(s.access_evidence).some(v=>!same(v,{status:'unknown',value:null,source:null})))throw new Error('B32 adoption, access or scope differs');
  const counts={options:0,floors:0,rooms:0,items:0};
  const overlap=(a,b)=>a.minX<b.maxX-1&&a.maxX>b.minX+1&&a.minY<b.maxY-1&&a.maxY>b.minY+1;
  for(const [index,o] of s.options.entries()){
    if(o.building!=='B'||o.entry_mode!==(index===0?'rear':'front')||!same(o.frame_mm,[6000,17630])||
       o.frame_mm[0]*o.frame_mm[1]/1e6>32*(400/121)||o.status!==s.status||
       !same(o.plans.floors.map(f=>f.id),['floor-1','floor-2','floor-3','floor-4']))throw new Error('B32 frame/mode differs');
    let base=0;
    for(const f of o.plans.floors){
      if(f.base_mm!==base||f.height_mm!==(f.id==='floor-1'?4000:3000)||!same([f.width_mm,f.depth_mm],o.frame_mm)||
         f.rooms.reduce((n,r)=>n+r.geometry.w_mm*r.geometry.h_mm,0)!==6000*17630)throw new Error('B32 incomplete floor or level');
      base+=f.height_mm;
      for(const [n,r] of f.rooms.entries()){
        const g=r.geometry,b={minX:g.x_mm,maxX:g.x_mm+g.w_mm,minY:g.y_mm,maxY:g.y_mm+g.h_mm};
        if(b.minX<0||b.minY<0||b.maxX>6000||b.maxY>17630||f.rooms.slice(n+1).some(t=>overlap(b,{minX:t.geometry.x_mm,maxX:t.geometry.x_mm+t.geometry.w_mm,minY:t.geometry.y_mm,maxY:t.geometry.y_mm+t.geometry.h_mm})))throw new Error('B32 overlapping/outside room');
        for(const i of r.furniture){const a=i.placement.aabb,rot=i.placement.rotation_deg%180;
          if(Math.abs(a.maxX-a.minX-(rot?i.depth_mm:i.width_mm))>1||Math.abs(a.maxY-a.minY-(rot?i.width_mm:i.depth_mm))>1)throw new Error('B32 resized product');}
      }
      counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
    }
    const p=o.review.program,c=o.review.coordinate_screen;
    if(!same(o.review.professional_status,s.professional_status)||c.fixed_body_failures.length||c.pending_solver_items.length||c.operation_limits.length||
       c.operation_sharing.some(v=>v.issue==='operation-vs-body')||!p.street_facing_axial_door||!p.dry_altar_backing||
       p.stair_or_hall_behind_altar.length||p.sleep_wet_stairs_above_whole_shrine.length||p.statutory_building_area!==null||p.rear_access!=='unknown')throw new Error('B32 coordinate/family or legal state differs');
    const storage=o.plans.floors[0].rooms.find(r=>r.key==='storage');
    const rear=storage.features.doors.filter(d=>d.purpose==='rear-palanquin-entry');
    if(index===0&&(rear.length!==1||rear[0].face!=='rear'||rear[0].neighbor!==null||rear[0].width_mm!==o.rear_gate_nominal_mm)||
       index===1&&rear.length)throw new Error('Rear opening leaks into front fallback or is missing');
    const t=p.transport;
    const segments=o.plans.floors[0].rooms.flatMap(r=>r.features.b32_transport_segments||[]);
    if(t.entry_mode!==o.entry_mode||t.acceptance!=='unknown'||t.outdoor_approach!=='unknown-not-drawn'||
       t.people_poles_wheels_rain!=='unknown'||t.front_backup_in_rear_model!=='not-claimed-use-separate-front-option'||
       segments.length!==(index===0?2:6)||new Set(segments.map(v=>v.id)).size!==segments.length||
       !same([...segments].sort((a,b)=>a.id.localeCompare(b.id)),[...t.segments].sort((a,b)=>a.id.localeCompare(b.id)))||
       t.gate_budgets.some(g=>g.finished_clear_mm!==null||g.discussion_clear_mm!==g.nominal_mm-160||g.discussion_clear_mm<1500))throw new Error('B32 route proof or budget differs');
    counts.options++;
  }
  return counts;
}
function preflight(project){
  const main=legacy.preflight(project),s=assignment(project,MANIFEST),counts=validateStudy(s);
  const indexHtml=fs.readFileSync(path.join(project,INDEX),'utf8');
  if(s.display_revision!==DISPLAY_REVISION||!indexHtml.includes('data-display-revision="'+DISPLAY_REVISION+'"')||
     !s.source_hashes['scripts/templates/b32-plan-viewer.js'])throw new Error('Stale B32 plan-reading presentation; regenerate');
  const files=[MANIFEST,INDEX,VIEWER,'scripts/check_b32_entry_playwright.cjs'];
  for(const [file,sha] of Object.entries({...s.source_hashes,...s.protected_main_hashes})){
    if(!/^(inputs|scripts|structured|assets|house_design|Docs)\/[\w./-]+$/.test(file)&&!/^[ABC]buildingView\.html$/.test(file)||file.split('/').includes('..'))throw new Error('Unsafe B32 path');
    const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(project,file))).digest('hex');
    if(actual!==sha)throw new Error('Stale B32 source: '+file+'; regenerate');files.push(file);
  }
  const src=fs.readFileSync(path.join(project,VIEWER),'utf8');
  const match=src.match(/^\s*var DATA = (.+);\s*$/m);
  const all=match&&JSON.parse(match[1]).bc_options;
  if(!all||all.default_option!==s.default_option||!same(all.options.map(o=>o.id),IDS))throw new Error('B32 embedded options differ');
  for(const o of s.options){const m=all.options.find(v=>v.id===o.id).model;
    if(m.buildings.length!==1||m.buildings[0].id!=='B'||!same(m.bc_option.geometry_review,o.review))throw new Error('B32 model review differs');
    for(const [n,f] of o.plans.floors.entries()){
      const mf=m.buildings[0].floors[n],active=mf.cells.filter(c=>c.tour_active);
      if(active.length!==f.rooms.length||mf.base_mm!==f.base_mm||mf.height_mm!==f.height_mm)throw new Error('B32 model floor differs');
      for(const r of f.rooms){const c=active.find(c=>c.id===r.id);
        if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(c.furniture_placements.tour_mm[i.id],i.placement)))throw new Error('B32 HTML/3D parity differs');}
      const file='structured/candidates/b32-entry-options/'+f.plan_file;
      const svg=fs.readFileSync(path.join(project,file),'utf8');
      if(!svg.includes('data-study-option="'+o.id+'"')||!svg.includes('comparison-only-not-adopted')||
         f.rooms.some(r=>r.furniture.some(i=>!svg.includes('data-furniture-id="'+i.id+'"'))))throw new Error('B32 SVG is incomplete');
      if(n===0){
        const figure=indexHtml.match(new RegExp('<figure[^>]*data-plan-viewer="'+o.id+'"[^>]*>([\\s\\S]+?)</figure>'));
        const viewBox=svg.match(/viewBox="([^"]+)"/)[1].split(' ').map(Number);
        const labelUnits=Math.min(...[...svg.matchAll(/font-size="([\d.]+)"/g)].map(v=>Number(v[1])));
        if(!figure||!figure[0].includes('data-source-width="'+viewBox[2]+'"')||!figure[0].includes('data-source-height="'+viewBox[3]+'"')||
           !figure[0].includes('data-min-label-units="'+labelUnits+'"')||!figure[0].includes('data="b32-entry-options/'+f.plan_file+'"')||
           ['in','out','readable','overview'].some(a=>!figure[0].includes('data-plan-action="'+a+'"')))throw new Error('B32 plan viewport source/controls differ');
      }
      files.push(file);
    }
  }
  return {cli:main.cli,counts,mainCounts:main.counts,displayRevision:DISPLAY_REVISION,sourceFiles:[...new Set([...main.sourceFiles,...files])]};
}
async function checkPages(page,base,output,expected){
  const checks=[],screenshots=[],messages=[],planReadability=[],counts={options:0,floors:0,rooms:0,items:0};
  const assert=(v,name)=>{checks.push({name,passed:Boolean(v)});if(!v)throw new Error(name);};
  const capture=async name=>{const file=output+'/'+name;await page.screenshot({path:file,fullPage:false});screenshots.push(file);};
  const ready=async id=>page.waitForFunction(id=>document.body.dataset.studyOption===id&&window.__htmlModel3dDebug?.().cameraFraming.ready,id);
  const collapse=async()=>{const t=page.locator('#mobile-panel-toggle');if(await t.isVisible()&&await t.getAttribute('aria-expanded')==='true')await t.click();};
  const inspectPlan=async locator=>locator.evaluate(root=>{
    const viewport=root.querySelector('[data-plan-viewport]'),object=root.querySelector('object'),rect=object.getBoundingClientRect();
    return {mode:root.dataset.planMode,loaded:root.dataset.planLoaded==='true',width:rect.width,height:rect.height,
      viewportWidth:viewport.clientWidth,viewportHeight:viewport.clientHeight,scrollLeft:viewport.scrollLeft,scrollTop:viewport.scrollTop,
      scrollWidth:viewport.scrollWidth,scrollHeight:viewport.scrollHeight,readableWidth:Number(root.dataset.readableWidth),
      sourceWidth:Number(root.dataset.sourceWidth),sourceHeight:Number(root.dataset.sourceHeight),
      minimumLabelPx:Number(root.dataset.minLabelUnits)*rect.width/Number(root.dataset.sourceWidth),
      source:object.getAttribute('data'),original:root.querySelector('[data-original-plan]').getAttribute('href'),
      noPageOverflow:document.documentElement.scrollWidth<=innerWidth+1,
      accessible:viewport.tabIndex===0&&viewport.getAttribute('role')==='region'&&
        !!document.getElementById(viewport.getAttribute('aria-describedby'))&&root.querySelector('[data-plan-state]').getAttribute('aria-live')==='polite',
      nativeTouch:getComputedStyle(viewport).touchAction==='auto',
      controls:[...root.querySelectorAll('[data-plan-action]')].map(b=>{const r=b.getBoundingClientRect();return {width:r.width,height:r.height};})};
  });
  const checkPlan=async(o,size)=>{
    await page.setViewportSize(size);await page.goto(base+'structured/candidates/b32-entry-options.html#'+o.id);
    await page.waitForFunction(id=>document.querySelector('[data-plan-viewer="'+id+'"]')?.dataset.planLoaded==='true',o.id);
    const viewer=page.locator('[data-plan-viewer="'+o.id+'"]'),viewport=viewer.locator('[data-plan-viewport]');
    const control=name=>viewer.locator('[data-plan-action="'+name+'"]');
    const name=o.id+' '+size.width+'x'+size.height;
    await control('readable').click();const read=await inspectPlan(viewer);
    assert((await page.locator('body').getAttribute('data-display-revision'))==='2','reading revision '+name);
    assert(read.loaded&&read.mode==='readable'&&read.width>=read.readableWidth-.1&&read.minimumLabelPx>=14&&
      Math.abs(read.height/read.width-read.sourceHeight/read.sourceWidth)<.002,'readable vector and label scale '+name);
    assert(read.source==='b32-entry-options/'+o.plans.floors[0].plan_file&&read.original===read.source,'unchanged same-option SVG '+name);
    assert(read.accessible&&read.nativeTouch&&read.controls.length===4&&read.controls.every(b=>b.width>=44&&b.height>=44),'touch and keyboard reading controls '+name);
    assert(read.noPageOverflow,'no page overflow in reading mode '+name);
    const otherId=o.id==='b32-rear'?'b32-front':'b32-rear';
    const other=page.locator('[data-plan-viewer="'+otherId+'"]'),before=await inspectPlan(other);
    await control('in').click();const zoom=await inspectPlan(viewer);
    assert(zoom.width>read.width+1&&zoom.height>read.height+1,'zoom enlarges actual vector '+name);
    const after=await inspectPlan(other);
    assert(before.mode===after.mode&&Math.abs(before.width-after.width)<.1,'independent plan zoom '+name);
    await control('out').click();const smaller=await inspectPlan(viewer);
    assert(Math.abs(smaller.width-read.width)<1,'zoom out restores vector size '+name);
    await viewport.focus();await viewport.press('End');let scrolled=await inspectPlan(viewer);
    assert(scrolled.scrollTop>0&&scrolled.scrollTop+scrolled.viewportHeight>=scrolled.scrollHeight-2,'keyboard reads rear storage '+name);
    if(scrolled.scrollWidth>scrolled.viewportWidth+1){await viewport.press('ArrowRight');scrolled=await inspectPlan(viewer);assert(scrolled.scrollLeft>0,'horizontal keyboard reading '+name);}
    await viewer.locator('[data-plan-controls]').scrollIntoViewIfNeeded();await capture(o.id+'-plan-'+size.width+'-readable.png');
    await viewport.focus();await viewport.press('Home');const home=await inspectPlan(viewer);
    assert(home.scrollTop===0&&home.scrollLeft===0,'keyboard returns to road '+name);
    await control('overview').focus();await control('overview').press('Enter');const overview=await inspectPlan(viewer);
    assert(overview.mode==='overview'&&overview.width<=overview.viewportWidth+.1&&overview.height<=overview.viewportHeight+.1&&
      overview.width<read.width&&(await control('overview').getAttribute('aria-pressed'))==='true','whole-floor overview via keyboard '+name);
    assert(overview.noPageOverflow,'no page overflow in overview '+name);
    if(size.width===1440){await viewer.locator('[data-plan-controls]').scrollIntoViewIfNeeded();await capture(o.id+'-plan-desktop-overview.png');}
    await control('readable').click();const restored=await inspectPlan(viewer);
    assert(restored.mode==='readable'&&Math.abs(restored.width-read.width)<1&&restored.scrollTop===0&&restored.scrollLeft===0&&
      (await control('readable').getAttribute('aria-pressed'))==='true','reading reset restores source and origin '+name);
    planReadability.push({option:o.id,viewport:size,readableWidth:read.width,zoomWidth:zoom.width,overviewWidth:overview.width,
      minimumLabelPx:read.minimumLabelPx,loaded:read.loaded,keyboardScroll:true,independent:true,noPageOverflow:read.noPageOverflow&&overview.noPageOverflow});
  };
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/b32-entry-options.html');
    assert((await page.title()).includes('B 32地坪'),'B32 index identity');
    assert(page.url().includes('structured/candidates/b32-entry-options.html'),'index URL identity');
    assert(await page.locator('[data-option]').count()===2,'two complete alternatives');
    assert(await page.locator('vite-error-overlay,#webpack-dev-server-client-overlay,nextjs-portal').count()===0,'no framework error overlay');
    assert((await page.locator('[data-access-caveat]').innerText()).includes('通行權'),'rear-access caveat visible');
    await page.addScriptTag({url:base+'structured/candidates/b32-entry-options/layout.js'});
    const s=await page.evaluate(()=>window.HOUSE_B32_ENTRY_OPTIONS);await capture('index-desktop.png');
    for(const size of [{width:1440,height:900},{width:390,height:844},{width:844,height:390}])for(const o of s.options)await checkPlan(o,size);
    await page.setViewportSize({width:1440,height:900});
    for(const o of s.options){
      await page.goto(base+'structured/candidates/b32-entry-options-3d.html?scheme='+o.id+'#mode=tour&building=B&floor=floor-1&view='+(o.entry_mode==='rear'?'rear':'front'));await ready(o.id);
      assert((await page.title()).includes(o.label),'3D identity '+o.id);
      assert(await page.locator('#study-stage-note').isVisible()&&(await page.locator('#study-stage-note').innerText()).includes('未採用'),'stage caveat '+o.id);
      assert(!(await page.locator('#tour-actions').isVisible()),'no primary shortcut leakage '+o.id);
      assert((await page.locator('#study-plan-link').getAttribute('href'))==='b32-entry-options.html#'+o.id,'same-option return '+o.id);
      for(const f of o.plans.floors){
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();await page.waitForFunction(fid=>window.__htmlModel3dDebug().state.floor===fid,f.id);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.bcOption.id===o.id&&d.presentation==='tour'&&d.visibleRooms.length===f.rooms.length,'nonblank isolated floor '+o.id+' '+f.id);
        for(const r of f.rooms){const c=d.tour.rooms.find(c=>c.id===r.id);
          assert(c&&JSON.stringify(c.geometry)===JSON.stringify(r.geometry)&&c.base_mm===f.base_mm&&c.height_mm===f.height_mm,'same-source room '+o.id+' '+r.id);
          assert(r.outdoor||c.architectureVisible&&c.architectureParts>0,'architecture rendered '+o.id+' '+r.id);
          for(const i of r.furniture){const p=d.furniture.shapes.find(v=>v.id===i.id);
            assert(p?.visible&&p.parts>0&&!p.collision&&!p.overflow&&p.width===i.width_mm&&p.depth===i.depth_mm&&p.height===i.height_mm&&Math.abs(p.center[0]-i.placement.center_x_mm)<.05&&Math.abs(p.center[1]-i.placement.center_y_mm)<.05,'full-size furniture '+o.id+' '+i.id);}
        }
        if(f.id==='floor-1'){
          const routes=d.transportRoutes;
          assert(routes.length===o.review.program.transport.segments.length&&routes.every(v=>v.renderedPoints.length===6&&v.renderedPoints.every(Number.isFinite)),'body route rendered '+o.id);
          for(const r of routes)assert(o.review.program.transport.segments.some(v=>JSON.stringify(v)===JSON.stringify(r.segment)),'same-source route '+o.id);
          const storage=d.tour.rooms.find(r=>r.id==='B:floor-1:storage');
          assert(storage.features.doors.some(g=>g.purpose==='rear-palanquin-entry')===(o.entry_mode==='rear'),'rear opening only in priority '+o.id);
          await capture(o.id+'-desktop-1f.png');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      await page.locator('#study-scheme').selectOption(o.id==='b32-rear'?'b32-front':'b32-rear');await ready(o.id==='b32-rear'?'b32-front':'b32-rear');
      assert((await page.locator('body').getAttribute('data-study-option'))!==o.id,'actual alternative switch '+o.id);
      counts.options++;
      for(const size of [{width:390,height:844},{width:844,height:390}]){
        await page.setViewportSize(size);await page.goto(base+'structured/candidates/b32-entry-options-3d.html?scheme='+o.id+'#mode=tour&building=B&floor=floor-1&room=B%3Afloor-1%3Astorage&focus=room&view='+(o.entry_mode==='rear'?'rear':'front'));await ready(o.id);await collapse();
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.roomCloseup&&d.visibleRooms.length===o.plans.floors[0].rooms.length&&d.focusedScreenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1),'mobile storage focus retains floor '+o.id+' '+size.width);
        assert(await page.locator('#study-stage-note').isVisible(),'mobile caveat '+o.id+' '+size.width);
        await capture(o.id+'-mobile-'+size.width+'.png');await page.locator('#room-overview').click();
        assert(!(await page.evaluate(()=>window.__htmlModel3dDebug().roomCloseup)),'mobile overview return '+o.id+' '+size.width);
      }
      await page.setViewportSize({width:1440,height:900});
    }
    await page.setViewportSize({width:390,height:844});await page.goto(base+'structured/candidates/b32-entry-options.html#b32-front');
    assert((await page.locator('#b32-front h2').innerText()).includes('備案'),'mobile front alternative content');await capture('index-mobile-front.png');
    await page.goto(base+'structured/candidates/model3d.html#mode=tour&building=B&floor=floor-1');await page.waitForFunction(()=>window.__htmlModel3dDebug?.().cameraFraming.ready);
    assert((await page.evaluate(()=>window.__htmlModel3dDebug().bcOption))===null,'ABC primary remains separate');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'both alternatives fully covered');
    const unexpected=messages.filter(v=>!(v.level==='warning'&&(v.text.includes('GPU stall due to ReadPixels')||v.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(unexpected.length===0,'no relevant runtime or console errors');
    return {marker:'house-b32-entry-cli-qa',revision:2,displayRevision:2,status:'passed',counts,checks,messages,screenshots,planReadability,limitation:'Rendered automation only; screenshots and professional review remain required.'};
  }catch(e){await capture('failure.png').catch(()=>{});return {marker:'house-b32-entry-cli-qa',revision:2,displayRevision:2,status:'failed',counts,checks,messages,screenshots,planReadability,error:String(e)};}
}
function makeBrowserScript(base,output,counts){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(counts)})`;}
function findReport(value){if(value&&typeof value==='object'){if(value.marker===MARKER)return value;for(const v of Object.values(value)){const r=findReport(v);if(r)return r;}}else if(typeof value==='string'){try{return findReport(JSON.parse(value));}catch{}}return null;}
function validateReport(r,counts){if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw new Error('Missing completed B32 browser result');
  if(r.status==='passed'){
    const required=IDS.flatMap(id=>['1440x900','390x844','844x390'].map(size=>id+':'+size));
    const rows=r.planReadability;
    if(r.revision!==2||r.displayRevision!==DISPLAY_REVISION||!same(r.counts,counts)||!Array.isArray(r.checks)||!r.checks.length||
       r.checks.some(c=>c.passed!==true)||!Array.isArray(r.screenshots)||r.screenshots.length<16||!Array.isArray(rows)||rows.length!==6||
       !same(rows.map(v=>v.option+':'+v.viewport?.width+'x'+v.viewport?.height).sort(),required.sort())||rows.some(v=>
         !Number.isFinite(v.minimumLabelPx)||v.minimumLabelPx<14||!Number.isFinite(v.readableWidth)||v.readableWidth<660||
         !Number.isFinite(v.zoomWidth)||v.zoomWidth<=v.readableWidth||!Number.isFinite(v.overviewWidth)||v.overviewWidth<=0||v.overviewWidth>=v.readableWidth||
         v.loaded!==true||v.keyboardScroll!==true||v.independent!==true||v.noPageOverflow!==true))throw new Error('Incomplete B32 plan-reading passing report');
  }return r;}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-b32-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.counts));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:8*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));
    if(required&&(r.error||r.status!==0))throw new Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{invoke('open',['open',base+INDEX,'--config='+config]);report=validateReport(findReport(JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout)),prepared.counts);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Sources changed during QA; rerun an unchanged version.';}}
  catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}
  return report;
}
function main(){const o=legacy.parseArguments(process.argv.slice(2));
  if(o.help){console.log('Windows: node scripts/check_b32_entry_playwright.cjs [--preflight] [--project <folder>]');return;}
  if(!o.preflight&&process.platform!=='win32')throw new Error('Use Windows Node for rendered QA; WSL --preflight is file-only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('B32 preflight passed: '+JSON.stringify(p.counts));
  console.log('B32 display revision: '+p.displayRevision+'; plan reading only, layouts not adopted.');
  if(o.preflight){console.log('Files/geometry only; rear alley and rendered approval remain unknown.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-b32-entry-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated B32 browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('Session cleanup unconfirmed.');console.log('Screenshots require visual review; rear access and professional approval are not granted.');if(r.status!=='passed')process.exitCode=1;
}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={validateStudy,preflight,checkPages,makeBrowserScript,findReport,validateReport,runQa};
