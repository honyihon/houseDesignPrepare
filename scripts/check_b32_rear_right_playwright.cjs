// Read-only preflight; native Windows browser QA is run separately by the owner.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const MARKER='house-b32-rear-right-qa',INDEX='structured/candidates/b32-rear-right.html',VIEWER='structured/candidates/b32-rear-right-3d.html',MANIFEST='structured/candidates/b32-rear-right/review.json';
function preflight(project){
  const primary=legacy.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,MANIFEST),'utf8'));
  if(study.schema!=='house-b32-rear-right-v1'||study.revision!==1||study.display_revision!==2||study.status!=='comparison-only-not-adopted'||study.rendered_qa!=='not-run'||
    study.default_option!=='rear-alley'||study.default_state!=='daily'||!same(study.frame_mm,[6000,17630])||
    !same(study.options.map(o=>o.id),['rear-alley','front-backup'])||Object.values(study.professional_status).some(v=>v!=='unknown')||
    study.rear_alley.existence!=='owner-reported-planning-premise'||study.rear_alley.access_rights_and_opening_permission!=='unknown')throw Error('Invalid B32 comparison, premise or approval');
  const files=[INDEX,VIEWER,MANIFEST,'scripts/check_b32_rear_right_playwright.cjs'];
  for(const [rel,sha] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').some(p=>p==='..'||p.toLowerCase().includes('private'))||!/^[a-f0-9]{64}$/.test(sha))throw Error('Unsafe source hash');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==sha)throw Error('Stale B32 source: '+rel);files.push(rel);
  }
  const assignment=fs.readFileSync(path.join(project,VIEWER),'utf8').match(/^\s*var DATA = (.+);\s*$/m);
  const payload=assignment&&JSON.parse(assignment[1]).b32_rear_right;
  if(!payload||payload.display_revision!==2||payload.default_option!=='rear-alley'||payload.default_state!=='daily'||!same(payload.options.map(o=>o.id),['rear-alley','front-backup']))throw Error('Missing independent 3D states or current display revision');
  const rendered=fs.readFileSync(path.join(project,VIEWER),'utf8');
  if(!rendered.includes('id="b32-label-mode"')||!rendered.includes('id="b32-room-details"')||
    !rendered.includes('b32LabelPolicy(entry,b32Context)')||rendered.includes('cell.name+(features.access_pending?" · 入口待定":"")'))throw Error('Missing compact labels/accessible equipment list or stale entrance wording');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(!same(o.states.map(s=>s.id),['daily','ritual','carry']))throw Error('Missing daily, ritual or prepared state');
    const areas=Object.fromEntries(o.area_rows.map(a=>[a.zone,a]));
    if(areas.bathroom.original_target_sqm!==7||areas.storage.original_target_sqm!==10.5||areas.laundry.original_target_sqm!==5||
      areas.bathroom.sensitivity.at(-1).area_sqm!==7.076||areas.laundry.original_minimum_sqm!==4||
      areas.laundry.target_shortfall_at_115_sqm!==(o.id==='rear-alley'?0:0.723))throw Error('Original area goals or explicit backup shortfall differ');
    if(o.id==='front-backup'&&(!o.staging_review?.full_size_furniture_retained||o.staging_review.coordinate_failures.length||o.staging_review.sequence.length!==3))throw Error('Incomplete full-size furniture staging');
    for(const s of o.states){
      const m=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!m||m.buildings.length!==1||m.buildings[0].id!=='B'||m.bc_option.use_state!==s.id||m.bc_option.id!==o.id||
        !same(m.bc_option.geometry_review,s.review))throw Error('Mixed state/model review');
      if(s.review.bath_route_sensitivity.some(r=>['bath_entry_route','bath_during_ritual','basin_route','toilet_side_route','shower_route','dry_cabinet_route','local_laundry_700mm_route','local_laundry_sink_700mm_route'].some(k=>r[k].coordinate_failures.length)||
        ['turn_circle_failures','bath_operation_failures','laundry_operation_failures','dry_door_swing_failures'].some(k=>r[k].length)))throw Error('Public bathroom floor envelopes blocked');
      if(s.id==='carry'&&s.review.carry_stored_body_115mm.coordinate_failures.length)throw Error('Prepared body carry blocked');
      if(o.id==='front-backup'&&s.id==='carry'&&(!s.review.continuous_1500mm_conservative_envelope_review.coordinate_failures.length||
        s.review.transport_aperture_shortfall_mm!==0))throw Error('Aperture budget must not conceal conservative continuous-turn target failure');
      if(o.id==='front-backup'&&s.id!=='carry'&&!s.review.carry_stored_body_115mm.coordinate_failures.length)throw Error('Unprepared transport must retain its furniture obstruction');
      for(const f of s.plans.floors){
        const mf=m.buildings[0].floors.find(p=>p.id===f.id),active=mf.cells.filter(c=>c.tour_active);
        if(active.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Missing floor or expanded frame');
        for(const r of f.rooms){const c=active.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('HTML/3D furniture or opening mismatch');}
        const rel='structured/candidates/b32-rear-right/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');
        if(!svg.includes('data-study-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"')||!svg.includes('width="660"')||
          f.rooms.some(r=>r.furniture.some(i=>!svg.includes('data-furniture-id="'+i.id+'"'))))throw Error('SVG state or body missing');
        files.push(rel);counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const rooms=s.plans.floors[0].rooms,bath=rooms.find(r=>r.key==='rear-bath'),storage=rooms.find(r=>r.key==='storage'),front=rooms.find(r=>r.key==='shrine-front');
      if(!same(bath.geometry,{x_mm:3330,y_mm:14500,w_mm:2670,h_mm:3130})||!same(storage.geometry,{x_mm:0,y_mm:14500,w_mm:3330,h_mm:3130})||
        !bath.features.window_review?.renderable||bath.features.window_face!=='rear'||bath.features.window_mm!==900||
        bath.features.window_sill_mm!==1500||bath.features.window_height_mm!==600||
        rooms.find(r=>r.key==='garage').furniture.length||rooms.filter(r=>r.key.startsWith('laundry-')).some(r=>r.outdoor))throw Error('Rear bathroom/storage/window or frontage differs');
      const rear=storage.features.doors.filter(d=>d.face==='rear'&&d.neighbor===null);
      if(rear.length!==(o.id==='rear-alley'?1:0)||o.id==='rear-alley'&&(rear[0].width_mm!==1960||Math.abs(rear[0].ratio*3330-1150)>.001))throw Error('Rear gate not independently moved/removed');
      const offering=rooms.flatMap(r=>r.furniture).find(i=>i.id.endsWith(':offering'));
      if(o.id==='front-backup'&&s.id==='carry'&&(!front.furniture.includes(offering)||storage.furniture.filter(i=>i.id.includes(':bench-')).length!==2))throw Error('Prepared furniture must actually move in both sources');
      counts.states++;
    }
    counts.options++;
  }
  return {study,counts,cli:primary.cli,mainCounts:primary.counts,sourceFiles:[...new Set([...primary.sourceFiles,...files])]};
}
async function checkPages(page,base,output,study,expected){
  const checks=[],screenshots=[],messages=[],counts={options:0,states:0,floors:0,rooms:0,items:0};
  const assert=(v,name)=>{checks.push({name,passed:Boolean(v)});if(!v)throw Error(name);};
  const capture=async name=>{const p=output+'/'+name;await page.screenshot({path:p,fullPage:false});screenshots.push(p);};
  const ready=async(o,s)=>page.waitForFunction(([o,s])=>document.body.dataset.studyOption===o&&document.body.dataset.studyUse===s&&document.body.dataset.studyDisplayRevision==='2'&&window.__htmlModel3dDebug?.().cameraFraming.ready,[o,s]);
  const fitted=async()=>page.waitForFunction(()=>{const d=window.__htmlModel3dDebug(),f=d.cameraFraming,c=document.getElementById('canvas');
    return f.safeArea?.usable&&f.autoFit?.area&&c.height>0&&Math.abs(c.width/c.height-f.width/f.height)<.005&&
      ['left','right','top','bottom'].every(k=>Math.abs(f.autoFit.area[k]-f.safeArea[k])<1);});
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['warning','error'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/b32-rear-right.html');
    assert((await page.title()).includes('兩版深化')&&await page.locator('section[data-option]').count()===2,'Correct nonblank two-version index');
    assert((await page.locator('.warning').first().innerText()).includes('未採用'),'Visible non-adoption warning');
    const plan=page.locator('[data-plan-viewer]').first();await plan.locator('[data-plan-controls]').waitFor({state:'visible'});
    const prior=await plan.getAttribute('data-plan-width');await plan.locator('[data-plan-action="in"]').click();
    assert(Number(await plan.getAttribute('data-plan-width'))>Number(prior),'Plan zoom changes actual width');await capture('index-desktop.png');
    await page.goto(base+'structured/candidates/b32-rear-right-3d.html');await ready('rear-alley','daily');
    assert((await page.evaluate(()=>new URL(location.href).searchParams.get('scheme')))==='rear-alley','Default rear-alley normalization before renderer');
    assert(await page.locator('#b32-label-mode').inputValue()==='compact'&&await page.locator('#furniture-names').isDisabled(),'Default compact display mode and contextual checkbox');
    await page.locator('#b32-label-mode').selectOption('all');
    await page.waitForFunction(()=>window.__htmlModel3dDebug().b32Display.mode==='all'&&Array.from(document.querySelectorAll('.nav-label.room')).some(e=>!e.hidden&&e.textContent.includes('通行未核')));
    assert((await page.locator('#navigation-labels').innerText()).includes('已排'),'Full label mode retains planned openings without approval');
    assert(await page.locator('#furniture-names').isEnabled(),'Full-mode furniture label checkbox available');
    await page.locator('#b32-label-mode').selectOption('compact');
    await page.locator('#study-scheme').selectOption('front-backup');await ready('front-backup','daily');
    await page.locator('#study-use').selectOption('carry');await ready('front-backup','carry');
    assert((await page.evaluate(()=>window.__htmlModel3dDebug())).bcOption.use_state==='carry','State selector loads actual prepared model');
    for(const o of study.options){
      for(const s of o.states){
        await page.setViewportSize({width:1440,height:900});
        await page.goto(base+'structured/candidates/b32-rear-right-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building=B&floor=floor-1&view=plan');await ready(o.id,s.id);
        assert((await page.title()).includes(o.label)&&await page.locator('#study-stage-note').isVisible(),'Isolated visible identity '+o.id+' '+s.id);
        assert(await page.locator('#study-plan-link').getAttribute('href')==='b32-rear-right.html#'+o.id+'-'+s.id&&!(await page.locator('#tour-actions').isVisible()),'State-specific link/no main shortcuts '+o.id+' '+s.id);
        for(const f of s.plans.floors){
          await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();await page.waitForFunction(id=>window.__htmlModel3dDebug().state.floor===id,f.id);
          const d=await page.evaluate(()=>window.__htmlModel3dDebug());
          assert(await page.locator('#furniture-names').isDisabled(),'Compact checkbox remains disabled after floor/scope synchronization '+o.id+' '+s.id+' '+f.id);
          assert(d.presentation==='tour'&&d.state.building==='B'&&d.bcOption.id===o.id&&d.bcOption.use_state===s.id&&d.visibleRooms.length===f.rooms.length,'Complete isolated floor '+o.id+' '+s.id+' '+f.id);
          for(const r of f.rooms){const rr=d.tour.rooms.find(t=>t.id===r.id);
            assert(rr&&JSON.stringify(rr.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(rr.features)===JSON.stringify(r.features),'Actual room/door/window parity '+o.id+' '+s.id+' '+r.id);
            if(r.features.window_review?.renderable)assert(rr.windowParts>0,'Actual candidate window mesh '+o.id+' '+s.id+' '+r.id);
            for(const i of r.furniture){const a=d.furniture.shapes.find(p=>p.id===i.id);
              assert(a?.visible&&a.parts>0&&!a.overflow&&!a.collision&&a.width===i.width_mm&&a.depth===i.depth_mm&&a.height===i.height_mm&&
                Math.abs(a.center[0]-i.placement.center_x_mm)<.05&&Math.abs(a.center[1]-i.placement.center_y_mm)<.05&&Math.abs(a.rotation-i.placement.rotation_deg)<.05,'Actual full-size use-state furniture '+o.id+' '+s.id+' '+i.id);}}
          if(f.id==='floor-1'){
            await page.waitForFunction(()=>{const a=Array.from(document.querySelectorAll('#navigation-labels .nav-label')).filter(e=>!e.hidden&&e.getClientRects().length);return a.length>0&&a.length<=6&&a.every(e=>e.classList.contains('room')&&e.textContent.length<=12);});
            assert(await page.locator('#navigation-labels .nav-label:visible').count()<=6,'Desktop compact major-room labels only '+o.id+' '+s.id);
            await capture(o.id+'-'+s.id+'-desktop.png');
          }
          counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
        }
        await page.setViewportSize({width:390,height:844});
        await page.goto(base+'structured/candidates/b32-rear-right-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building=B&floor=floor-1&room=B%3Afloor-1%3Arear-bath&focus=room&view=front');await ready(o.id,s.id);
        const toggle=page.locator('#mobile-panel-toggle');if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
        await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.roomCloseup&&d.visibleRooms.length===s.plans.floors[0].rooms.length&&d.tour.rooms.find(r=>r.id==='B:floor-1:rear-bath').windowParts>0,'Mobile actual window/complete cutaway '+o.id+' '+s.id);
        assert(await page.locator('#study-stage-note').isVisible(),'Mobile unadopted state warning '+o.id+' '+s.id);
        await page.waitForFunction(()=>{const d=window.__htmlModel3dDebug();return d.b32Display.mode==='compact'&&d.b32Display.focused&&!Array.from(document.querySelectorAll('.nav-label,.furniture-label')).some(e=>!e.hidden&&e.getClientRects().length);});
        assert(await page.locator('#navigation-labels .nav-label:visible, #furniture-labels .furniture-label:visible').count()===0,'Mobile closeup annotations do not cover fixture bodies '+o.id+' '+s.id);
        await fitted();
        const frame=await page.evaluate(()=>window.__htmlModel3dDebug().cameraFraming);
        assert(frame.selectedItems.length===3&&frame.selectedItems.every(i=>{const p=i.corners;if(p.length!==8||p.some(c=>!c.every(Number.isFinite)||Math.abs(c[2])>1))return false;
          const xs=p.map(c=>(c[0]+1)*frame.width/2),ys=p.map(c=>(1-c[1])*frame.height/2);
          return Math.max(...xs)-Math.min(...xs)>=16&&Math.max(...ys)-Math.min(...ys)>=16&&Math.min(...xs)>=frame.safeArea.left-1&&Math.max(...xs)<=frame.safeArea.right+1&&Math.min(...ys)>=frame.safeArea.top-1&&Math.max(...ys)<=frame.safeArea.bottom+1;}),'Mobile actual fixture bodies >=16px inside safe area '+o.id+' '+s.id);
        await capture(o.id+'-'+s.id+'-bath-mobile.png');
        await page.locator('#b32-room-details').click();await page.waitForFunction(()=>!window.__htmlModel3dDebug().panelCollapsed);
        const entryText=await page.locator('#b32-room-entry-status').innerText();
        assert(entryText.includes('已排門位')&&entryText.includes('通行未核')&&!entryText.includes('入口待定')&&
          await page.locator('#furniture-list .furniture-row').count()===3,'Mobile equipment list retains dimensions and conditional entrance status '+o.id+' '+s.id);
        assert((await page.locator('#furniture-list').innerText()).includes('600')&&(await page.locator('#furniture-list').innerText()).includes('1200'),'Actual device dimensions accessible without model labels '+o.id+' '+s.id);
        await page.locator('#b32-details-back').click();await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
        await fitted();
        assert((await page.evaluate(()=>window.__htmlModel3dDebug())).state.room==='B:floor-1:rear-bath','Equipment list return preserves selected room '+o.id+' '+s.id);
        await page.locator('#room-overview').click();
        assert(!(await page.evaluate(()=>window.__htmlModel3dDebug().roomCloseup)),'Mobile return to complete floor '+o.id+' '+s.id);
        await fitted();
        await page.waitForFunction(()=>{const a=Array.from(document.querySelectorAll('#navigation-labels .nav-label')).filter(e=>!e.hidden&&e.getClientRects().length);return a.length>0&&a.length<=4&&a.every(e=>e.classList.contains('room')&&e.textContent.length<=12);});
        assert(await page.locator('#navigation-labels .nav-label:visible').count()<=4,'Mobile whole-floor labels capped at four '+o.id+' '+s.id);
        await capture(o.id+'-'+s.id+'-whole-mobile.png');counts.states++;
      }
      counts.options++;
    }
    await page.goto(base+'structured/candidates/b32-rear-right.html');await capture('index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'All independent states/floors inspected');
    assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained runtime or console errors');
    return {marker:'house-b32-rear-right-qa',revision:1,displayRevision:2,status:'passed',counts,checks,screenshots,messages};
  }catch(e){await capture('failure.png').catch(()=>{});await page.goto('about:blank').catch(()=>{});return {marker:'house-b32-rear-right-qa',revision:1,displayRevision:2,status:'failed',error:String(e),counts,checks,screenshots,messages};}
}
function makeBrowserScript(base,output,study,counts){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)})`;}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function validateReport(r,counts){if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw Error('No completed structured QA result');
  if(r.status==='passed'&&(r.revision!==1||r.displayRevision!==2||!same(r.counts,counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||!Array.isArray(r.screenshots)||r.screenshots.length<20))throw Error('Incomplete passing evidence');return r;}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-b32-right-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.study,prepared.counts));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:8*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));if(required&&(r.error||r.status!==0))throw Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);
    if(response?.isError)throw Error('Playwright CLI error; see checks.log');report=validateReport(findReport(response),prepared.counts);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Source hashes changed during QA';}}
  catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}return report;
}
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_b32_rear_right_playwright.cjs [--preflight] [--project <path>]. No install or design adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node for browser QA; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('B32 rear-right preflight passed: '+JSON.stringify(p.counts));
  console.log('Rear alley is an owner-reported premise only. Two independent layouts, three use states each. Not adopted.');
  console.log('B32 display revision: 2; compact labels and accessible equipment list only. All layouts unchanged.');
  if(o.preflight){console.log('Files only; no browser/rendered/professional QA performed.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-b32-right-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated B32 rear-right browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('This session cleanup unconfirmed. No other browser was targeted.');
  console.log('Screenshots need visual review; no religious, care, legal access, transport or construction approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={preflight,checkPages,makeBrowserScript,findReport,validateReport,runQa};
