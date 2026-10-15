// Seven isolated preparation comparisons. Native Windows CLI, no installs,
// adoption, source writes or implied professional approval. Node.js 20+.
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const {isDeepStrictEqual: same} = require('node:util');
const legacy = require('./check_windows_playwright.cjs');
const MARKER = 'house-preparation-cli-qa';
const MANIFEST = 'structured/candidates/preparation-review/layout.js';
const IDS = ['c-window-3000','c-window-3600','c-window-4000','b-fixed-3000',
  'b-program-3000','b-program-3600','b-program-4000'];

function hash(project, file) {
  return crypto.createHash('sha256').update(fs.readFileSync(path.join(project,file))).digest('hex');
}
function assignment(project, file, name) {
  const source = fs.readFileSync(path.join(project,file),'utf8');
  const match = source.match(new RegExp('^\\s*window\\.'+name+'\\s*=\\s*([\\s\\S]+?)\\s*;\\s*$'));
  if (!match) throw new Error('Invalid assignment: '+file);
  return JSON.parse(match[1]);
}
function validateStudy(study) {
  if (study.schema !== 'house-preparation-review-v1' || study.revision !== 2 || study.status !== 'comparison-only-not-adopted' ||
      study.active_design !== 'baseline' || study.default_option !== IDS[0] ||
      !same(study.options?.map(o=>o.id),IDS) ||
      Object.keys(study.professional_status||{}).length !== 8 ||
      Object.values(study.professional_status).some(v=>v!=='unknown')) throw new Error('Adopted, approved or incomplete preparation study');
  const counts = {options:0,floors:0,rooms:0,items:0};
  for (const o of study.options) {
    if (o.status !== study.status || o.plans.id !== o.building ||
        !same(o.review.professional_status,study.professional_status) ||
        !same(o.plans.floors.map(f=>f.id),['floor-1','floor-2','floor-3','floor-4'])) throw new Error('Invalid option: '+o.id);
    const frame = o.id.startsWith('b-program') ? [6000,20530] : [6000,17630];
    if (!same(o.frame_mm,frame)) throw new Error('Unexpected site assumption: '+o.id);
    let base = 0;
    for (const f of o.plans.floors) {
      if (!same([f.width_mm,f.depth_mm],frame) || f.base_mm!==base ||
          f.height_mm!==(f.id==='floor-1'?o.height_mm:3000)) throw new Error('Frame or elevation mismatch: '+o.id);
      base += f.height_mm;
      if (f.plan_file!==o.id+'_'+f.id+'.svg' ||
          f.rooms.reduce((a,r)=>a+r.geometry.w_mm*r.geometry.h_mm,0)!==frame[0]*frame[1]) throw new Error('Incomplete floor: '+o.id);
      counts.floors++; counts.rooms+=f.rooms.length;
      counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
    }
    const screen=o.review.coordinate_screen;
    if (screen.fixed_body_failures.length || screen.pending_solver_items.length || screen.operation_limits.length ||
        screen.operation_sharing.some(s=>s.issue==='operation-vs-body') ||
        screen.full_human_door_sweeps!=='unknown') throw new Error('Unresolved coordinate defect: '+o.id);
    if (!o.review.program.area_checks?.length || o.review.program.area_checks.some(r=>r.finished_and_legal_area!==null)) throw new Error('Missing or falsely approved area checks');
    const front=o.plans.floors[0].rooms.find(r=>r.key==='garage');
    if (!front?.outdoor || front.furniture.length || front.geometry.h_mm!==3900) throw new Error('Front strip is not clear');
    const first=o.plans.floors[0], room=key=>first.rooms.find(r=>r.key===key);
    const product=(key,local)=>room(key).furniture.find(i=>i.id.endsWith(':'+local)).placement;
    const intersects=(a,b)=>a.minX<b.maxX-1&&a.maxX>b.minX+1&&a.minY<b.maxY-1&&a.maxY>b.minY+1;
    if(o.building==='C'){
      const r=o.review.program.revision_checks, wc=room('public-bath'), dining=room('dining');
      const wash=product('public-bath','vanity'), shoe=product('entrance','shoe-cabinet');
      const washShares=wc.features.reserved_mm.some(z=>z.kind==='door-approach'&&intersects(wash.operation_mm,z.aabb));
      const shoeShares=room('entrance').features.reserved_mm.some(z=>z.kind==='door-approach'&&intersects(shoe.operation_mm,z.aabb));
      const gap=product('living','sofa').aabb.minX-product('living','coffee-table').aabb.maxX;
      const door=dining.features.doors.find(d=>d.neighbor===null), g=dining.geometry;
      const separation=(door.ratio-dining.features.window_ratio)*g.w_mm-(door.width_mm+dining.features.window_mm)/2;
      if(washShares||shoeShares||gap!==600||Math.abs(separation-300)>1||!r||
        r.wash_shares_door_approach!==washShares||r.shoe_shares_door_approach!==shoeShares||
        r.sofa_coffee_gap_mm!==gap||Math.abs(r.front_window_door_nominal_separation_mm-separation)>1||
        wc.features.doors[0].width_mm!==900||r.visitor_door_nominal_mm!==900||
        r.sliding_leaf_track_handle_and_rescue!=='unknown')throw new Error('C v2 operations or nominal buffers differ: '+o.id);
    }else{
      const budget=o.review.program.transport.clearance_budget;
      const entry=room('entry'), storage=room('storage');
      const exterior=entry.features.doors.find(d=>d.neighbor===null);
      const gate=storage.features.doors.find(d=>d.purpose==='palanquin-storage');
      const nominal=[entry.geometry.w_mm,room('corridor1').geometry.w_mm,exterior.width_mm,gate.width_mm];
      const segmentIds=['entry-corridor','rear-corridor','external-gate','storage-gate'];
      if(!budget||budget.status!=='unverified-discussion-budget-not-transport-approval'||budget.segments.length!==4||
        budget.segments.some((s,n)=>s.id!==segmentIds[n]||s.nominal_mm!==nominal[n]||s.assumed_each_side_mm!==80||
          s.discussion_clear_mm!==nominal[n]-160||s.target_mm!==1500||s.finished_clear_mm!==null||
          s.target_state!==(nominal[n]-160<1500?'below-target':'nominal-budget-only'))||
        budget.minimum_discussion_clear_mm!==Math.min(...nominal)-160||budget.frame_product!=='unknown')
        throw new Error('B v2 transport budget differs from geometry: '+o.id);
      if(o.id.startsWith('b-program')&&(budget.minimum_discussion_clear_mm<1500||
        o.review.program.area_checks.find(r=>r.id==='B.floor-1.shrine').discussion_inset_sqm<22||
        !o.review.program.dry_altar_backing||o.review.program.wet_above_whole_shrine.length))
        throw new Error('B v2 loses shrine or transport targets: '+o.id);
    }
    counts.options++;
  }
  return counts;
}
function preflight(project) {
  const main = legacy.preflight(project);
  const study = assignment(project,MANIFEST,'HOUSE_PREPARATION_REVIEW');
  const counts = validateStudy(study);
  const files = [MANIFEST,'scripts/check_preparation_playwright.cjs',
    'structured/candidates/preparation-review.html','structured/candidates/preparation-review-3d.html',
    'structured/discussions/abc-preparation-meeting.html','structured/discussions/abc-preparation-meeting.json'];
  for (const [file,sha] of Object.entries({...study.source_hashes,...study.protected_main_hashes})) {
    if (!/^(inputs|scripts|structured|assets|house_design|Docs)\/[\w./-]+$/.test(file) &&
        !/^[ABC]buildingView\.html$/.test(file)) throw new Error('Unsafe source path: '+file);
    if (file.split('/').includes('..') || !/^[a-f0-9]{64}$/.test(sha) || hash(project,file)!==sha) throw new Error('Stale preparation source: '+file+'; regenerate the comparison');
    files.push(file);
  }
  for (const o of study.options) {
    for (const f of o.plans.floors) files.push('structured/candidates/preparation-review/'+f.plan_file);
    files.push('structured/candidates/preparation-review/'+o.id+'_front.svg');
  }
  for (const file of files) if (!fs.existsSync(path.join(project,file))) throw new Error('Missing artifact: '+file);
  const viewer=fs.readFileSync(path.join(project,files[3]),'utf8');
  const match=viewer.match(/^\s*var DATA = (.+);\s*$/m);
  if (!match) throw new Error('Missing embedded 3D models');
  const models=JSON.parse(match[1]).bc_options;
  if (models.default_option!==study.default_option || !same(models.options.map(o=>o.id),IDS)) throw new Error('3D options differ');
  for (const o of study.options) {
    const m=models.options.find(m=>m.id===o.id).model;
    if (m.buildings.length!==1 || m.buildings[0].id!==o.building ||
        m.bc_option.status!==study.status || !same(m.bc_option.geometry_review,o.review)) throw new Error('3D metadata differs: '+o.id);
    for (const [index,f] of o.plans.floors.entries()) {
      const mf=m.buildings[0].floors[index], active=mf.cells.filter(c=>c.tour_active);
      if (active.length!==f.rooms.length || mf.base_mm!==f.base_mm || mf.height_mm!==f.height_mm) throw new Error('3D floor differs');
      for (const r of f.rooms) {
        const c=active.find(c=>c.id===r.id);
        if (!c || !same(c.tour_mm,r.geometry) || !same(c.tour_features,r.features) || c.furniture.length!==r.furniture.length ||
            r.furniture.some(i=>!same(c.furniture_placements.tour_mm[i.id],i.placement))) throw new Error('3D room differs: '+r.id);
      }
    }
  }
  const packet=JSON.parse(fs.readFileSync(path.join(project,files[5])));
  if (packet.status!==study.status || packet.professional_approval!=='unknown' ||
      packet.scenarios.length!==22 || packet.scenarios.some(s=>s.status!=='unknown'||s.evidence!==null)) throw new Error('Meeting packet implies approval');
  return {cli:main.cli,revision:study.revision,sourceFiles:[...new Set([...main.sourceFiles,...files])],counts,mainCounts:main.counts};
}

async function checkPages(page, baseUrl, outputDir, expected) {
  const checks=[],screenshots=[],messages=[];
  const counts={options:0,floors:0,rooms:0,items:0};
  const assert=(v,name,details)=>{
    const passed=Boolean(v);checks.push({name,passed,...(!passed&&details?{details}:{})});
    if(!passed)throw new Error(name+(details?' '+JSON.stringify(details):''));
  };
  const capture=async name=>{const p=outputDir+'/'+name;await page.screenshot({path:p,fullPage:false});screenshots.push(p);};
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  const ready=async id=>page.waitForFunction(id=>document.body.dataset.studyOption===id&&window.__htmlModel3dDebug?.().cameraFraming.ready,id);
  const collapse=async()=>{const t=page.locator('#mobile-panel-toggle');if(await t.isVisible()&&await t.getAttribute('aria-expanded')==='true')await t.click();};
  try {
    await page.setViewportSize({width:1440,height:900});
    await page.goto(baseUrl+'structured/candidates/preparation-review.html',{waitUntil:'load'});
    assert((await page.title()).includes('ABC前期整合比較'),'index page identity');
    assert(await page.locator('section[data-option]').count()===7,'seven meaningful option sections');
    assert(await page.locator('[data-clearance-budget]').count()===4&&await page.locator('[data-revision-checks]').count()===3,'v2 visible clearance and operation summaries');
    assert((await page.locator('.warning').first().innerText()).includes('未採用'),'visible comparison warning');
    await capture('preparation-index-desktop.png');
    await page.addScriptTag({url:baseUrl+'structured/candidates/preparation-review/layout.js'});
    const study=await page.evaluate(()=>window.HOUSE_PREPARATION_REVIEW);
    await page.goto(baseUrl+'structured/candidates/preparation-review-3d.html?scheme='+study.options[0].id,{waitUntil:'load'});
    for (const o of study.options) {
      // CLI run-code has no global WHATWG URL constructor. Read the active
      // rendered option; waitForURL receives its URL object from Playwright.
      if (await page.locator('body').getAttribute('data-study-option')!==o.id) {
        await Promise.all([page.waitForURL(u=>u.searchParams.get('scheme')===o.id),page.locator('#study-scheme').selectOption(o.id)]);
      }
      await ready(o.id);
      assert((await page.title()).includes(o.label),'3D page identity '+o.id);
      assert(await page.locator('#study-stage-note').isVisible(),'visible stage warning '+o.id);
      assert((await page.locator('#study-stage-note').innerText()).includes('未採用'),'not-adopted stage text '+o.id);
      assert(!(await page.locator('#tour-actions').isVisible()),'no primary-design shortcut leakage '+o.id);
      assert((await page.locator('#study-plan-link').getAttribute('href'))==='preparation-review.html#'+o.id,'index return matches option '+o.id);
      for (const f of o.plans.floors) {
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();
        await page.waitForFunction(fid=>window.__htmlModel3dDebug().state.floor===fid,f.id);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.visibleRooms.length===f.rooms.length,'complete rendered floor '+o.id+' '+f.id);
        // geomSource selects only the inactive historical auto/declared mode.
        // Tour rendering uses tour_mm regardless of that selector's value.
        const tourRooms=d.tour?.rooms||[];
        const activeSources=[...new Set(tourRooms.map(r=>r.features?.geometry_source))];
        assert(d.bcOption?.id===o.id&&d.presentation==='tour'&&d.state?.building===o.building&&d.state?.floor===f.id&&
          tourRooms.length===f.rooms.length&&activeSources.length===1&&activeSources[0]==='tour_mm',
          'isolated tour state '+o.id+' '+f.id,{expected:{option:o.id,building:o.building,floor:f.id,presentation:'tour',geometry:'tour_mm'},
            actual:{option:d.bcOption?.id,building:d.state?.building,floor:d.state?.floor,presentation:d.presentation,
              inactiveLegacySelector:d.geomSource,geometrySources:activeSources,tourRooms:tourRooms.length}});
        for (const r of f.rooms) {
          const rr=d.tour.rooms.find(c=>c.id===r.id);
          assert(rr&&JSON.stringify(rr.geometry)===JSON.stringify(r.geometry)&&rr.base_mm===f.base_mm&&rr.height_mm===f.height_mm,'rendered dimensions '+o.id+' '+r.id);
          assert(r.outdoor||rr.architectureVisible&&rr.architectureParts>0,'nonblank room architecture '+o.id+' '+r.id);
          for (const i of r.furniture) {
            const shape=d.furniture.shapes.find(s=>s.id===i.id);
            assert(shape?.visible&&shape.parts>0&&shape.width===i.width_mm&&shape.depth===i.depth_mm&&
              shape.height===i.height_mm&&!shape.overflow&&!shape.collision&&
              Math.abs(shape.center[0]-i.placement.center_x_mm)<.05&&Math.abs(shape.center[1]-i.placement.center_y_mm)<.05,
              'rendered full-size furniture '+o.id+' '+i.id);
          }
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
        if(f.id==='floor-1')await capture(o.id+'-1f-desktop.png');
      }
      const key=o.building==='C'?'public-bath':'storage', id=o.building+':floor-1:'+key;
      await page.locator('#scope-floors [data-floor="floor-1"]').click();
      await page.locator('#scope-rooms [data-room="'+id+'"]').click();await page.locator('#focus-room').click();
      const close=await page.evaluate(()=>window.__htmlModel3dDebug());
      assert(close.roomCloseup&&close.state.room===id&&close.visibleRooms.length===o.plans.floors[0].rooms.length,'room focus retains full floor '+o.id);
      assert((await page.locator('#info a.info-link').first().getAttribute('href'))==='preparation-review.html#'+o.id,'focused room returns to new comparison '+o.id);
      await page.locator('#room-overview').click();
      counts.options++;
    }
    for (const id of ['c-window-4000','b-program-4000']) {
      const o=study.options.find(o=>o.id===id), key=o.building==='C'?'public-bath':'bath1';
      await page.setViewportSize({width:390,height:844});
      await page.goto(baseUrl+'structured/candidates/preparation-review-3d.html?scheme='+id+'#mode=tour&building='+o.building+'&floor=floor-1&room='+encodeURIComponent(o.building+':floor-1:'+key)+'&focus=room&view=front');
      await ready(id);await collapse();
      assert(await page.locator('#study-stage-note').isVisible(),'mobile stage warning '+id);
      const d=await page.evaluate(()=>window.__htmlModel3dDebug());
      assert(d.roomCloseup&&d.visibleRooms.length===o.plans.floors[0].rooms.length,'mobile focus keeps complete floor '+id);
      assert(d.focusedScreenBounds.length===8&&d.focusedScreenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1),'mobile selected geometry fits '+id);
      await capture(id+'-mobile-focus.png');
      await page.locator('#room-overview').click();
      assert(!(await page.evaluate(()=>window.__htmlModel3dDebug().roomCloseup)),'mobile floor return '+id);
    }
    await page.goto(baseUrl+'structured/discussions/abc-preparation-meeting.html');
    assert((await page.title()).includes('會談補充包'),'meeting identity and meaningful content');
    assert((await page.locator('main').innerText()).includes('未知不算通過'),'meeting approval caveat');
    await capture('meeting-mobile.png');
    await page.setViewportSize({width:1440,height:900});
    await page.goto(baseUrl+'structured/candidates/model3d.html#mode=tour&building=C&floor=floor-1&view=front');
    await page.waitForFunction(()=>window.__htmlModel3dDebug?.().cameraFraming.ready);
    const main=await page.evaluate(()=>window.__htmlModel3dDebug());
    assert(main.bcOption===null&&main.furniture.items===128&&!await page.locator('body').getAttribute('data-study-option'),'return to current independent ABC primary design');
    assert(Object.keys(expected).every(k=>counts[k]===expected[k]),'all seven options/floors/rooms/products covered');
    const unexpected=messages.filter(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(unexpected.length===0,'no relevant console or runtime errors');
    return {marker:'house-preparation-cli-qa',revision:study.revision,status:'passed',counts,checks,messages,screenshots,
      limitation:'Automated rendered QA only. Screenshots need visual review; no design, accessibility, religious or regulatory approval.'};
  } catch(e) {
    await capture('failure.png').catch(()=>{});
    return {marker:'house-preparation-cli-qa',status:'failed',error:String(e),counts,checks,messages,screenshots};
  }
}
function makeBrowserScript(baseUrl, output, counts) {
  return `async page => (${checkPages.toString()})(page,${JSON.stringify(baseUrl)},${JSON.stringify(output)},${JSON.stringify(counts)})`;
}
function findReport(value) {
  if(value&&typeof value==='object'){
    if(value.marker===MARKER)return value;
    for(const v of Object.values(value)){const r=findReport(v);if(r)return r;}
  }else if(typeof value==='string'){try{return findReport(JSON.parse(value));}catch{}}
  return null;
}
function validateReport(r, counts) {
  if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw new Error('Missing complete preparation browser result');
  if(r.status==='passed'&&(r.revision!==2||!Array.isArray(r.checks)||!r.checks.length||r.checks.some(c=>c.passed!==true)||!same(r.counts,counts)||
      !Array.isArray(r.screenshots)||r.screenshots.length<10))throw new Error('Incomplete passing report');
  return r;
}
function runQa(options, prepared, output, execute=spawnSync) {
  const session='house-preparation-'+crypto.randomBytes(5).toString('hex');
  const config=path.join(output,'cli.config.json'), script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href;
  const sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},
    contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.counts));
  const invoke=(name,args,required=true)=>{
    const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,
      maxBuffer:8*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));
    if(required&&(r.error||r.status!==0))throw new Error(name+' failed; see '+name+'.log');return r;
  };
  let report={marker:MARKER,status:'incomplete'};
  try{
    invoke('open',['open',base+'structured/candidates/preparation-review.html','--config='+config]);
    report=validateReport(findReport(JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout)),prepared.counts);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Sources changed during QA; rerun one unchanged version.';}
  }catch(e){report.status='incomplete';report.error=String(e);}
  finally{
    Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});
    try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
  }
  return report;
}
function main(){
  const o=legacy.parseArguments(process.argv.slice(2));
  if(o.help){console.log('Windows: node scripts/check_preparation_playwright.cjs [--preflight] [--project <folder>] [--browser=chrome]\nNo installation or adoption; artifacts only in a fresh TEMP directory.');return;}
  if(!o.preflight&&process.platform!=='win32')throw new Error('Run rendered QA with Windows Node, not WSL. --preflight is read-only.');
  console.log('Project: '+o.project);
  const p=preflight(o.project);
  console.log('Preparation revision: v'+p.revision+'; comparisons only, not adopted.');
  console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));
  console.log('Preparation preflight passed: '+JSON.stringify(p.counts));
  if(o.preflight){console.log('Files/geometry only; no browser or rendered approval.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-preparation-cli-'));
  console.log('QA output folder: '+output);
  const r=runQa(o,p,output);
  console.log('Automated preparation browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));
  if(r.error)console.error(r.error);
  if(!r.sessionClosed)console.warn('Session cleanup unconfirmed; see close.log.');
  console.log('Screenshots require visual review. This is not professional approval.');
  if(r.status!=='passed')process.exitCode=1;
}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={preflight,validateStudy,checkPages,makeBrowserScript,findReport,validateReport,runQa};
