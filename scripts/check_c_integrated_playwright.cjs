// Native Windows, one CLI session at a time. --preflight never opens a browser.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const MARKER='house-c-integrated-cli-qa';
const IDS=[3000,3600,4000].map(h=>'c-integrated-'+h);
const INDEX='structured/candidates/c-integrated-options.html',VIEWER='structured/candidates/c-integrated-options-3d.html';
const MANIFEST='structured/candidates/c-integrated-options/layout.js';
function closeupCases(s){
  return s.options.map((o,n)=>{
    const [floor,key]=[['floor-1','public-bath'],['floor-2','guestroom2f'],['floor-3','fitness3f']][n];
    const f=o.plans.floors.find(f=>f.id===floor),r=f.rooms.find(r=>r.key===key);
    return {option:o.id,floor,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),
      itemIds:r.furniture.map(i=>i.id),primaryIds:r.furniture.filter(i=>['bed','treadmill','toilet','vanity'].includes(i.shape)).map(i=>i.id)};
  });
}
function inspectCloseup(e,expected){
  // Pure pixel math from actual camera-projected body corners. No DOM labels,
  // optimizer score or furniture resizing can substitute for these bounds.
  const fail=message=>{throw new Error('C mobile readable closeup: '+message);};
  const equal=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
  const {width,height}=e.stage||{},a=e.safeArea;
  if(e.option!==expected.option||e.floor!==expected.floor||e.room!==expected.room||e.building!=='C'||e.closeup!==true||e.policy!=='c-integrated-readable-v1'||
     e.viewport?.width!==expected.viewport.width||e.viewport?.height!==expected.viewport.height||
     !equal(e.visibleRoomIds||[],expected.roomIds)||!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0||
     !a?.usable||![a.left,a.right,a.top,a.bottom].every(Number.isFinite)||a.left<0||a.top<0||a.right>width||a.bottom>height||a.right-a.left<48||a.bottom-a.top<48)
    fail('wrong option/room, incomplete floor or unusable viewport');
  const rect=points=>{
    if(!Array.isArray(points)||points.length!==8||points.some(p=>!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite)||Math.abs(p[2])>1))fail('missing/invalid projected body corners');
    const xs=points.map(p=>(1+p[0])*width/2),ys=points.map(p=>(1-p[1])*height/2);
    return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};
  };
  const inside=r=>r.left>=a.left-1&&r.right<=a.right+1&&r.top>=a.top-1&&r.bottom<=a.bottom+1;
  const roomRect=rect(e.roomCorners),occupiedFraction=(roomRect.right-roomRect.left)*(roomRect.bottom-roomRect.top)/((a.right-a.left)*(a.bottom-a.top));
  if(!inside(roomRect)||occupiedFraction<.2)fail('room too small or underneath controls');
  if(!Array.isArray(e.items)||!equal(e.items.map(i=>i.id),expected.itemIds)||!expected.primaryIds.length)fail('missing/unexpected furniture bodies');
  const bodyRects=e.items.map(i=>{
    const r=rect(i.corners),w=r.right-r.left,h=r.bottom-r.top,primary=expected.primaryIds.includes(i.id);
    if(!inside(r)||Math.min(w,h)<(primary?40:12)||Math.max(w,h)<(primary?96:28))fail('body too small/obscured by controls: '+i.id);
    return {id:i.id,primary,rect:r,shortSidePx:Math.min(w,h),longSidePx:Math.max(w,h)};
  });
  return {...e,roomRect,occupiedFraction,bodyRects,limitation:'Projected body size only; screenshot review still required for occlusion and legibility.'};
}
function assignment(project){
  const m=fs.readFileSync(path.join(project,MANIFEST),'utf8').match(/^\s*window\.HOUSE_C_INTEGRATED_OPTIONS\s*=\s*([\s\S]+?)\s*;\s*$/);
  if(!m)throw new Error('Invalid C integrated manifest');return JSON.parse(m[1]);
}
function validateStudy(s){
  if(s.schema!=='house-c-integrated-options-v1'||s.revision!==1||s.display_revision!==2||s.status!=='comparison-only-not-adopted'||s.active_design!=='baseline'||
    s.default_option!==IDS[1]||!same(s.options.map(o=>o.id),IDS)||!same(s.frame_mm,[6000,17630])||s.frontage_depth_mm!==3900||
    Object.keys(s.professional_status).length!==8||Object.values(s.professional_status).some(v=>v!=='unknown')||
    s.owner_decisions.length!==4||s.owner_decisions.some(d=>d.status!=='pending'))throw new Error('C integrated scope/adoption/approval differs');
  const counts={options:0,floors:0,rooms:0,items:0};
  const overlap=(a,b)=>a.minX<b.maxX-1&&a.maxX>b.minX+1&&a.minY<b.maxY-1&&a.maxY>b.minY+1;
  const box=g=>({minX:g.x_mm,maxX:g.x_mm+g.w_mm,minY:g.y_mm,maxY:g.y_mm+g.h_mm});
  for(const [index,o] of s.options.entries()){
    if(o.building!=='C'||o.status!==s.status||o.height_mm!==[3000,3600,4000][index]||!same(o.frame_mm,s.frame_mm)||
      !same(o.plans.floors.map(f=>f.id),['floor-1','floor-2','floor-3','floor-4'])||!same(o.review.professional_status,s.professional_status))throw new Error('C integrated option differs');
    let base=0;
    for(const f of o.plans.floors){
      if(f.base_mm!==base||f.height_mm!==(f.id==='floor-1'?o.height_mm:3000)||!same([f.width_mm,f.depth_mm],s.frame_mm)||
         f.rooms.reduce((n,r)=>n+r.geometry.w_mm*r.geometry.h_mm,0)!==6000*17630)throw new Error('C integrated incomplete frame/level');
      base+=f.height_mm;
      for(const [n,r] of f.rooms.entries()){
        const b=box(r.geometry);
        if(b.minX<0||b.minY<0||b.maxX>6000||b.maxY>17630||f.rooms.slice(n+1).some(t=>overlap(b,box(t.geometry))))throw new Error('C integrated overlapping/outside rooms');
        for(const i of r.furniture){const a=i.placement.aabb,rot=i.placement.rotation_deg%180;
          if(Math.abs(a.maxX-a.minX-(rot?i.depth_mm:i.width_mm))>1||Math.abs(a.maxY-a.minY-(rot?i.width_mm:i.depth_mm))>1)throw new Error('C integrated resized product');}
      }
      counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
    }
    const p=o.review.program,c=o.review.coordinate_screen;
    if(c.fixed_body_failures.length||c.pending_solver_items.length||c.operation_limits.length||c.operation_sharing.some(v=>v.issue==='operation-vs-body')||
       c.full_human_door_sweeps!=='unknown'||p.wet_rooms_over_bed.length||!same(p.visitor_route,['dining','entrance','public-bath'])||
       p.exercise_over_sleep_rooms.length||p.exercise.manual_source!==null||p.exercise.manufacturer_front_minimum_mm!==null||
       p.upper_area_checks.length!==5||p.upper_area_checks.some(r=>r.finished_and_legal_area!==null||r.minimum_state==='below-minimum'))throw new Error('C integrated unsupported function/approval claim');
    const room=(f,key)=>o.plans.floors[f].rooms.find(r=>r.key===key),guest=room(1,'guestroom2f'),gym=room(2,'fitness3f');
    if(!guest.features.window_review?.renderable||guest.features.window_face!=='front'||guest.features.window_mm!==1200||
       !guest.furniture.some(i=>i.catalog_id==='single-bed'&&i.width_mm===1050&&i.depth_mm===1880)||
       !room(0,'public-bath').features.window_review?.renderable||room(0,'garage').furniture.length||!room(0,'garage').outdoor)
      throw new Error('C integrated loses real guest bed/window, WC window or clear frontage');
    const exercise=gym.features.exercise_review;
    if(!same(exercise,p.exercise)||exercise.zones.length!==3||exercise.rear_budget_mm!==2000||exercise.side_budget_mm!==500)throw new Error('C integrated exercise budget differs');
    const objects=gym.furniture.map(i=>i.placement.aabb),envelopes=[...objects,...exercise.zones.map(z=>z.aabb)];
    const gymBox=box(gym.geometry);
    if(envelopes.some(b=>overlap(b,box(guest.geometry)))||exercise.zones.some(z=>objects.some(b=>overlap(z.aabb,b))||
      z.aabb.minX<gymBox.minX+80||z.aabb.maxX>gymBox.maxX-80||z.aabb.minY<gymBox.minY+80||z.aabb.maxY>gymBox.maxY-80))throw new Error('C integrated exercise overlaps sleeping room/body or leaves room');
    const cy=room(1,'stair2f').geometry.y_mm;
    const areas=[(6000-160)*(cy-3900-160)/1e6-2.8*3.7,
      (2800-160)*(3700-160)/1e6,(2400-160)*(3830-160)/1e6,
      (6000-160)*(room(2,'master3f').geometry.h_mm-160)/1e6,
      (2400-160)*(gym.geometry.h_mm-160)/1e6];
    const expectedAreas=[['C.floor-2.living2',16,22],['C.floor-2.guest2',9,12],['C.floor-2.kitchenette',4,6],['C.floor-3.master_c',14,20],['C.floor-3.gym',9,14]];
    if(p.upper_area_checks.some((r,n)=>!same([r.id,r.minimum_sqm,r.target_sqm],expectedAreas[n])||Math.abs(r.discussion_inset_sqm-areas[n])>.0001||
      r.target_state!==(areas[n]<r.target_sqm?'below-target':'area-only-not-function-approval')))throw new Error('C integrated areas are stale or double counted');
    counts.options++;
  }
  return counts;
}
function preflight(project){
  const main=legacy.preflight(project),s=assignment(project),counts=validateStudy(s);
  const files=[MANIFEST,INDEX,VIEWER,'scripts/check_c_integrated_playwright.cjs'];
  for(const [rel,sha] of Object.entries({...s.source_hashes,...s.protected_main_hashes})){
    if((!/^(inputs|scripts|structured|assets|house_design|Docs)\/[\w./-]+$/.test(rel)&&!/^[ABC]buildingView\.html$/.test(rel))||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(sha))throw new Error('Unsafe C integration source path');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==sha)throw new Error('Stale C integration source: '+rel+'; regenerate');files.push(rel);
  }
  const match=fs.readFileSync(path.join(project,VIEWER),'utf8').match(/^\s*var DATA = (.+);\s*$/m),all=match&&JSON.parse(match[1]).bc_options;
  if(!all||all.default_option!==s.default_option||!same(all.options.map(o=>o.id),IDS))throw new Error('C integration embedded options differ');
  for(const o of s.options){
    const m=all.options.find(v=>v.id===o.id).model;
    if(m.buildings.length!==1||m.buildings[0].id!=='C'||!same(m.bc_option.geometry_review,o.review)||m.bc_option.status!==s.status)throw new Error('C integration embedded review differs');
    for(const [n,f] of o.plans.floors.entries()){
      const mf=m.buildings[0].floors[n],active=mf.cells.filter(c=>c.tour_active);
      if(active.length!==f.rooms.length||mf.base_mm!==f.base_mm||mf.height_mm!==f.height_mm)throw new Error('C integration embedded floor differs');
      for(const r of f.rooms){const c=active.find(c=>c.id===r.id);
        if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||
          r.furniture.some(i=>!same(c.furniture_placements.tour_mm[i.id],i.placement)))throw new Error('C integration HTML/3D parity differs');}
      const rel='structured/candidates/c-integrated-options/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');
      if(!svg.includes('data-study-option="'+o.id+'"')||!svg.includes('comparison-only-not-adopted')||
        f.rooms.some(r=>r.furniture.some(i=>!svg.includes('data-furniture-id="'+i.id+'"')))||
        (n===2&&(svg.match(/data-exercise-allowance=/g)||[]).length!==3))throw new Error('C integration SVG incomplete');
      files.push(rel);
    }
    files.push('structured/candidates/c-integrated-options/'+o.id+'_front.svg');
  }
  return {cli:main.cli,counts,mainCounts:main.counts,closeupCases:closeupCases(s),sourceFiles:[...new Set([...main.sourceFiles,...files])]};
}
async function checkPages(page,base,output,expected,inspectCloseup){
  const checks=[],screenshots=[],messages=[],closeupEvidence=[],counts={options:0,floors:0,rooms:0,items:0};
  const assert=(v,name)=>{checks.push({name,passed:Boolean(v)});if(!v)throw new Error(name);};
  const capture=async name=>{const file=output+'/'+name;await page.screenshot({path:file,fullPage:false});screenshots.push(file);};
  const ready=async id=>page.waitForFunction(id=>document.body.dataset.studyOption===id&&window.__htmlModel3dDebug?.().cameraFraming.ready,id);
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/c-integrated-options.html');
    assert((await page.title()).includes('C整合比較')&&await page.locator('section[data-option]').count()===3,'C index identity/nonblank/three options');
    assert((await page.locator('.warning').first().innerText()).includes('不是新的主案'),'visible nonadoption scope');
    await capture('c-integrated-index-desktop.png');
    await page.addScriptTag({url:base+'structured/candidates/c-integrated-options/layout.js'});
    const study=await page.evaluate(()=>window.HOUSE_C_INTEGRATED_OPTIONS);
    await page.goto(base+'structured/candidates/c-integrated-options-3d.html?scheme='+study.options[0].id);
    for(const o of study.options){
      if(await page.locator('body').getAttribute('data-study-option')!==o.id)
        await Promise.all([page.waitForURL(u=>u.searchParams.get('scheme')===o.id),page.locator('#study-scheme').selectOption(o.id)]);
      await ready(o.id);
      assert((await page.title()).includes(o.label)&&await page.locator('#study-stage-note').isVisible(),'C isolated identity and visible warning '+o.id);
      assert(!(await page.locator('#tour-actions').isVisible())&&(await page.locator('#study-plan-link').getAttribute('href'))==='c-integrated-options.html#'+o.id,'C no main shortcuts and correct return '+o.id);
      for(const f of o.plans.floors){
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();
        await page.waitForFunction(fid=>window.__htmlModel3dDebug().state.floor===fid,f.id);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.presentation==='tour'&&d.bcOption?.id===o.id&&d.visibleRooms.length===f.rooms.length,'C isolated complete floor '+o.id+' '+f.id);
        for(const r of f.rooms){
          const rr=d.tour.rooms.find(t=>t.id===r.id);
          assert(rr&&JSON.stringify(rr.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(rr.features)===JSON.stringify(r.features),'C actual geometry/features '+o.id+' '+r.id);
          if(r.features.window_review?.renderable)assert(rr.windowParts>0,'C actual window geometry '+o.id+' '+r.id);
          if(r.features.exercise_review)assert(rr.exerciseAllowanceParts===3,'C actual exercise allowance outlines '+o.id);
          for(const i of r.furniture){const a=d.furniture.shapes.find(s=>s.id===i.id);
            assert(a?.visible&&a.parts>0&&!a.overflow&&!a.collision&&a.width===i.width_mm&&a.depth===i.depth_mm&&a.height===i.height_mm&&
              Math.abs(a.center[0]-i.placement.center_x_mm)<.05&&Math.abs(a.center[1]-i.placement.center_y_mm)<.05,'C actual full-size product '+o.id+' '+i.id);}
        }
        if(f.id!=='floor-4')await capture(o.id+'-'+f.id+'-desktop.png');
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      counts.options++;
    }
    for(const [n,o] of study.options.entries()){
      const [floor,key]=[['floor-1','public-bath'],['floor-2','guestroom2f'],['floor-3','fitness3f']][n];
      await page.setViewportSize({width:390,height:844});
      await page.goto(base+'structured/candidates/c-integrated-options-3d.html?scheme='+o.id+'#mode=tour&building=C&floor='+floor+'&room='+encodeURIComponent('C:'+floor+':'+key)+'&focus=room&view=front');
      await ready(o.id);
      const toggle=page.locator('#mobile-panel-toggle');if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
      await page.waitForFunction(()=>{
        const d=window.__htmlModel3dDebug(),f=d.cameraFraming;
        return d.panelCollapsed&&f.autoFit?.closeupPolicy==='c-integrated-readable-v1'&&
          ['left','right','top','bottom'].every(k=>Math.abs(f.autoFit.area[k]-f.safeArea[k])<1);
      });
      const d=await page.evaluate(()=>window.__htmlModel3dDebug());
      assert(d.roomCloseup&&d.visibleRooms.length===o.plans.floors.find(f=>f.id===floor).rooms.length&&
        d.focusedScreenBounds.length===8&&d.focusedScreenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1),'C mobile focus retains floor and fits '+o.id);
      assert(await page.locator('#study-stage-note').isVisible(),'C mobile visible nonadoption '+o.id);
      const f=o.plans.floors.find(f=>f.id===floor),r=f.rooms.find(r=>r.key===key);
      const specification={option:o.id,floor,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),itemIds:r.furniture.map(i=>i.id),
        primaryIds:r.furniture.filter(i=>['bed','treadmill','toilet','vanity'].includes(i.shape)).map(i=>i.id)};
      const evidence=inspectCloseup({option:d.bcOption?.id,floor:d.state.floor,room:d.state.room,building:d.state.building,closeup:d.roomCloseup,
        viewport:{width:390,height:844},stage:{width:d.cameraFraming.width,height:d.cameraFraming.height},safeArea:d.cameraFraming.safeArea,
        policy:d.cameraFraming.autoFit?.closeupPolicy,visibleRoomIds:d.visibleRooms,roomCorners:d.focusedScreenBounds,items:d.cameraFraming.selectedItems},specification);
      closeupEvidence.push(evidence);assert(evidence.bodyRects.length===r.furniture.length,'C mobile actual body pixel sizes '+o.id);
      await capture(o.id+'-mobile-focus.png');await page.locator('#room-overview').click();
      assert(!(await page.evaluate(()=>window.__htmlModel3dDebug().roomCloseup)),'C mobile return '+o.id);
    }
    await page.goto(base+'structured/candidates/c-integrated-options.html#c-integrated-3600');
    assert(await page.locator('[data-decision]').count()===4,'C pending owner decisions remain visible');await capture('c-integrated-index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'C all three options and twelve floors covered');
    const unexpected=messages.filter(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(unexpected.length===0,'C no relevant console/runtime errors');
    return {marker:'house-c-integrated-cli-qa',revision:2,displayRevision:2,status:'passed',counts,checks,screenshots,messages,closeupEvidence};
  }catch(e){await capture('failure.png').catch(()=>{});return {marker:'house-c-integrated-cli-qa',revision:2,displayRevision:2,status:'failed',error:String(e),counts,checks,screenshots,messages,closeupEvidence};}
}
function makeBrowserScript(base,output,counts){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(counts)},(${inspectCloseup.toString()}))`;}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function validateReport(r,counts,cases){
  if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw new Error('Missing completed C integrated QA result');
  if(r.status==='passed'){
    if(r.revision!==2||r.displayRevision!==2||!same(r.counts,counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||!Array.isArray(r.screenshots)||r.screenshots.length<14||
       !Array.isArray(cases)||cases.length!==3||!Array.isArray(r.closeupEvidence)||r.closeupEvidence.length!==3||
       !same(r.closeupEvidence.map(e=>e.option+':'+e.room).sort(),cases.map(e=>e.option+':'+e.room).sort()))throw new Error('Incomplete C readable-closeup passing report');
    for(const e of r.closeupEvidence)inspectCloseup(e,cases.find(c=>c.option===e.option&&c.room===e.room));
  }return r;
}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-c-integrated-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.counts));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:8*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));if(required&&(r.error||r.status!==0))throw new Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{
    invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);
    if(response?.isError)throw new Error('Playwright CLI error; see checks.log. Verification incomplete.');
    report=validateReport(findReport(response),prepared.counts,prepared.closeupCases);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Sources changed during QA; rerun unchanged version.';}
  }catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}
  return report;
}
function main(){
  const o=legacy.parseArguments(process.argv.slice(2));
  if(o.help){console.log('Windows: node scripts/check_c_integrated_playwright.cjs [--preflight] [--project <folder>]. One browser; no installs, adoption or source edits.');return;}
  if(!o.preflight&&process.platform!=='win32')throw new Error('Use native Windows Node for browser QA; WSL --preflight is file-only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC: '+JSON.stringify(p.mainCounts));console.log('C integrated preflight passed: '+JSON.stringify(p.counts));
  console.log('C display revision: 2; mobile closeups require actual body pixel evidence, not adoption.');
  if(o.preflight){console.log('Files only; no browser or professional approval.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-integrated-cli-'));console.log('QA output folder: '+output);
  const r=runQa(o,p,output);console.log('Automated C integrated browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));
  if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('Session cleanup unconfirmed; only this session was targeted.');
  console.log('Screenshots need visual review; drawings not adopted. Regulatory, religious, care and exercise approval unknown.');if(r.status!=='passed')process.exitCode=1;
}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={validateStudy,closeupCases,inspectCloseup,preflight,checkPages,makeBrowserScript,findReport,validateReport,runQa};
