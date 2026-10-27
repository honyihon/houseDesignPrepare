// Files-only preflight here; owner starts rendered QA from native Windows Node.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const MARKER='house-current-design-qa',INDEX='structured/candidates/current-design-basis.html',VIEWER='structured/candidates/current-design-basis-3d.html',REPORT='structured/candidates/current-design-basis/review.json';
function closeupCases(study){
  return study.options.flatMap(o=>o.states.map(s=>{
    const floor=o.id==='a-current'?'floor-3':'floor-2',key=o.id==='a-current'?'bath3':o.id==='a-ensuite'?'ensuite-study':o.building==='B'?'master2':'balcony2f';
    const f=s.plans.floors.find(f=>f.id===floor),r=f.rooms.find(r=>r.key===key);
    const items=r.furniture.map(i=>{
      // Explicit QA pixel budgets, independently checked against the actual
      // projected mesh corners. Optimizer scores cannot replace this evidence.
      const large=['bed','sofa','clothes-rack','treadmill','altar'].includes(i.shape),utility=['washer','utility-sink-planning'].includes(i.catalog_id),bath=['toilet','vanity','shower'].includes(i.shape);
      return {id:i.id,short:large?40:utility||bath?32:16,long:large?96:utility?48:bath?64:28};
    });
    return {option:o.id,use:s.id,building:o.building,floor,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),items};
  }));
}
function inspectMobileView(e,expected){
  const fail=message=>{throw Error('Current mobile body evidence: '+message);};
  const equal=(a,b)=>Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&new Set(a).size===a.length&&JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
  const overview=e.phase==='overview',{width,height}=e.stage||{},a=e.safeArea,draw=e.draw;
  if(!['initial','equipment-return','overview'].includes(e.phase)||e.option!==expected.option||e.use!==expected.use||e.building!==expected.building||e.floor!==expected.floor||
    e.room!==(overview?'':expected.room)||e.closeup!==!overview||e.panelCollapsed!==true||e.displayRevision!==2||
    e.viewport?.width!==expected.viewport.width||e.viewport?.height!==expected.viewport.height||!equal(e.visibleRoomIds,expected.roomIds)||
    !Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0||!a?.usable||
    ![a.left,a.right,a.top,a.bottom].every(Number.isFinite)||a.left<0||a.top<0||a.right>width||a.bottom>height||a.right-a.left<48||a.bottom-a.top<48)
    fail('wrong option/state/room, incomplete floor or unusable viewport');
  if(!draw||draw.clipped!==!overview||draw.clearedOutside!==!overview||e.scissorTestRestored!==true||
    draw.stage?.width!==width||draw.stage?.height!==height||draw.renderSize?.width!==width||draw.renderSize?.height!==height||
    e.fit?.viewport?.width!==width||e.fit?.viewport?.height!==height||
    (overview?e.fit.closeupPolicy!==null:e.fit.closeupPolicy!=='current-design-readable-v2')||
    !['left','right','top','bottom'].every(k=>Number.isFinite(e.fit?.area?.[k])&&Math.abs(e.fit.area[k]-a[k])<1))
    fail('stale canvas/camera or drawing clip not restored');
  if(overview){
    if(draw.area!==null)fail('overview retained closeup clip');
    return {...e,limitation:'Complete floor visibility and unclipped draw state only; screenshot review still required.'};
  }
  if(!draw.area||!['left','right','top','bottom'].every(k=>Number.isFinite(draw.area[k])&&Math.abs(draw.area[k]-a[k])<1.01))fail('draw region does not match measured text-free area');
  if(!Array.isArray(e.overlays)||!['stage-title','room-view-actions','compass','orientation','study-stage-note'].every(id=>e.overlays.some(o=>o.id===id)))fail('missing measured text overlays');
  for(const o of e.overlays){
    if(![o.left,o.right,o.top,o.bottom].every(Number.isFinite))fail('invalid overlay bounds');
    if(o.left<a.right&&o.right>a.left&&o.top<a.bottom&&o.bottom>a.top)fail('drawing region overlaps controls: '+o.id);
  }
  const rect=points=>{
    if(!Array.isArray(points)||points.length!==8||points.some(p=>!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite)||Math.abs(p[2])>1))fail('missing/invalid actual projected mesh corners');
    const xs=points.map(p=>(1+p[0])*width/2),ys=points.map(p=>(1-p[1])*height/2);
    return {left:Math.min(...xs),right:Math.max(...xs),top:Math.min(...ys),bottom:Math.max(...ys)};
  };
  const inside=r=>r.left>=a.left-1&&r.right<=a.right+1&&r.top>=a.top-1&&r.bottom<=a.bottom+1;
  const roomRect=rect(e.roomCorners),occupiedFraction=(roomRect.right-roomRect.left)*(roomRect.bottom-roomRect.top)/((a.right-a.left)*(a.bottom-a.top));
  if(!inside(roomRect)||occupiedFraction<.2)fail('room too small or underneath controls');
  if(!expected.items.length||!Array.isArray(e.items)||!equal(e.items.map(i=>i.id),expected.items.map(i=>i.id)))fail('missing/unexpected furniture bodies');
  const bodyRects=e.items.map(i=>{
    const budget=expected.items.find(b=>b.id===i.id),r=rect(i.corners),short=Math.min(r.right-r.left,r.bottom-r.top),long=Math.max(r.right-r.left,r.bottom-r.top);
    if(!inside(r)||short<budget.short||long<budget.long)fail('actual body too small/under controls: '+i.id);
    return {id:i.id,rect:r,shortSidePx:short,longSidePx:long,budget};
  });
  return {...e,roomRect,occupiedFraction,bodyRects,limitation:'Actual projected mesh size, not pixel occlusion/clearance or professional approval. Screenshots still require review.'};
}
function validateIndexWarning(source){
  const warnings=[...source.matchAll(/<p\b([^>]*)>([\s\S]*?)<\/p>/g)].filter(m=>/\bclass="[^"]*\bwarning\b[^"]*"/.test(m[1]));
  if((source.match(/\bid="basis-adoption-warning"/g)||[]).length!==1||!warnings.length||
    !/\bid="basis-adoption-warning"/.test(warnings[0][1])||!warnings[0][2].includes('未採用')||!warnings[0][2].includes('專業未核'))throw Error('Missing explicit first-page non-adoption warning');
  return warnings[0][2];
}
function preflight(project){
  const primary=legacy.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-current-design-basis-v1'||study.revision!==1||study.display_revision!==2||study.status!=='discussion-only-not-adopted'||study.adopted!==false||study.rendered_qa!=='not-run'||
    study.default_option!=='b-rear-refined'||!same(study.frame_mm,[6000,17630])||Object.values(study.professional_status).some(v=>v!=='unknown')||
    !same(study.options.map(o=>o.id),['a-current','a-ensuite','b-rear-refined','b-front-refined','c-care-refined'])||study.requirement_ledger.canonical_requirements!==66||study.requirement_ledger.verified_requirements!==0)throw Error('Invalid discussion/adoption/requirement status');
  const files=[INDEX,VIEWER,REPORT,'structured/candidates/current-design-basis/requirement-ledger.json'];
  validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8'));
  for(const [rel,digest]of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').some(p=>p==='..'||p.toLowerCase().includes('private'))||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe evidence source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale discussion source: '+rel);files.push(rel);
  }
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),match=text.match(/^\s*var DATA = (.+);\s*$/m),payload=match&&JSON.parse(match[1]).current_design_basis;
  if(!payload||payload.display_revision!==2||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id))||!text.includes('b32SyncDensityControl')||!text.includes('id="b32-room-details"')||!text.includes('basisRenderFrame();'))throw Error('Missing independent compact/readable viewer');
  const ledger=JSON.parse(fs.readFileSync(path.join(project,files[3]),'utf8'));
  if(!same(ledger,study.requirement_ledger))throw Error('Ledger file differs from current plans');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    const expected=o.building==='B'?['daily','ritual','carry']:['daily'];
    if(o.adopted!==false||!same(o.states.map(s=>s.id),expected))throw Error('Missing independent use state');
    const overlay='structured/candidates/current-design-basis/'+o.id+'_coordination.svg';files.push(overlay);
    if(!fs.readFileSync(path.join(project,overlay),'utf8').includes('width="880"'))throw Error('Missing bounded engineering projection');
    for(const s of o.states){
      const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.buildings[0].id!==o.building||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Mixed plan/model/state');
      for(const f of s.plans.floors){
        const active=model.buildings[0].floors.find(p=>p.id===f.id).cells.filter(c=>c.tour_active);
        if(active.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Expanded or incomplete floor');
        for(const r of f.rooms){const c=active.find(c=>c.id===r.id);if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('HTML/3D furniture/door/window mismatch');}
        const rel='structured/candidates/current-design-basis/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');files.push(rel);
        if(!svg.includes('width="660"')||!svg.includes('data-basis-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"')||f.rooms.some(r=>r.furniture.some(i=>!svg.includes('data-furniture-id="'+i.id+'"'))))throw Error('Missing full-size SVG item/state');
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      if(o.building==='B'&&(s.review.operation_vs_fixed_body.length||s.review.furniture_body_sensitivity.some(r=>!r.room.startsWith('B:floor-1:'))))throw Error('B upper body issues remain');
      if(o.building==='C'&&s.plans.floors.flatMap(f=>f.rooms.flatMap(r=>r.furniture.filter(i=>i.catalog_id==='washer').map(()=>f.id))).join(',')!=='floor-2')throw Error('C must retain one 2F washer');
      counts.states++;
    }
    counts.options++;
  }
  return {study,counts,closeupCases:closeupCases(study),cli:primary.cli,mainCounts:primary.counts,sourceFiles:[...new Set([...primary.sourceFiles,...files])]};
}
async function checkPages(page,base,output,study,expected,cases,inspectMobileView){
  const checks=[],screenshots=[],messages=[],mobileEvidence=[],counts={options:0,states:0,floors:0,rooms:0,items:0};
  const assert=(ok,name)=>{checks.push({name,passed:Boolean(ok)});if(!ok)throw Error(name);};
  const capture=async name=>{const p=output+'/'+name;await page.screenshot({path:p,fullPage:false});screenshots.push(p);};
  const ready=async(o,s)=>page.waitForFunction(([o,s])=>document.body.dataset.studyOption===o&&document.body.dataset.studyUse===s&&window.__htmlModel3dDebug?.().cameraFraming.ready,[o,s]);
  const fitted=async overview=>page.waitForFunction(overview=>{
    const d=window.__htmlModel3dDebug(),f=d.cameraFraming,c=d.currentDesignCamera,draw=c?.lastDraw,canvas=document.getElementById('canvas');
    return d.panelCollapsed&&f.ready&&f.safeArea.usable&&c.revision===2&&c.scissorTestRestored&&
      d.roomCloseup!==overview&&draw?.clipped!==overview&&draw.stage.width===f.width&&draw.stage.height===f.height&&
      draw.renderSize.width===f.width&&draw.renderSize.height===f.height&&f.autoFit?.viewport?.width===f.width&&f.autoFit?.viewport?.height===f.height&&
      Math.abs(canvas.width/f.width-canvas.height/f.height)<.005&&
      (overview?f.autoFit.closeupPolicy===null:f.autoFit.closeupPolicy==='current-design-readable-v2')&&
      ['left','right','top','bottom'].every(k=>Math.abs(f.autoFit.area[k]-f.safeArea[k])<1&&
        (overview||Math.abs(draw.area[k]-f.safeArea[k])<1.01));
  },overview);
  const readMobile=async phase=>page.evaluate(phase=>{
    const d=window.__htmlModel3dDebug(),f=d.cameraFraming,c=d.currentDesignCamera;
    return {phase,option:document.body.dataset.studyOption,use:document.body.dataset.studyUse,building:d.state.building,floor:d.state.floor,room:d.state.room,
      closeup:d.roomCloseup,panelCollapsed:d.panelCollapsed,displayRevision:c.revision,viewport:{width:innerWidth,height:innerHeight},
      stage:{width:f.width,height:f.height},safeArea:f.safeArea,fit:f.autoFit,draw:c.lastDraw,scissorTestRestored:c.scissorTestRestored,
      overlays:f.overlays,visibleRoomIds:d.visibleRooms,roomCorners:d.focusedScreenBounds,items:f.selectedItems};
  },phase);
  const checkWarning=async label=>{
    const warning=page.locator('#basis-adoption-warning'),visible=await warning.isVisible(),text=visible?await warning.innerText():'';
    assert(visible&&text.includes('未採用')&&text.includes('專業未核'),'Visible non-adoption warning '+label);
    const box=await warning.boundingBox(),viewport=page.viewportSize();
    assert(box&&viewport&&box.width>0&&box.height>0&&box.x>=0&&box.y>=0&&box.x+box.width<=viewport.width+1&&box.y+box.height<=viewport.height+1,'Non-adoption warning within first viewport '+label);
  };
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['warning','error'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/current-design-basis.html');
    assert((await page.title()).includes('目前討論基準')&&await page.locator('section[data-option]').count()===5,'Correct nonblank five-option hub');
    await checkWarning('desktop');await capture('index-desktop.png');
    await page.goto(base+'structured/candidates/current-design-basis-3d.html');await ready('b-rear-refined','daily');
    assert(await page.locator('#b32-label-mode').inputValue()==='compact'&&await page.locator('#furniture-names').isDisabled(),'Compact labels selected and enforced');
    await page.locator('#study-scheme').selectOption('a-current');await ready('a-current','daily');
    assert((await page.evaluate(()=>window.__htmlModel3dDebug())).state.building==='A','Scheme selector changes actual independent building');
    for(const o of study.options){
      for(const s of o.states){
        await page.setViewportSize({width:1440,height:900});
        await page.goto(base+'structured/candidates/current-design-basis-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building='+o.building+'&floor=floor-1&view=plan');await ready(o.id,s.id);
        assert((await page.title()).includes(o.label)&&await page.locator('#study-stage-note').isVisible(),'Visible isolated option '+o.id+' '+s.id);
        assert(await page.locator('#study-plan-link').getAttribute('href')==='current-design-basis.html#'+o.id+'-'+s.id&&!(await page.locator('#tour-actions').isVisible()),'Correct state return link and no main shortcuts '+o.id+' '+s.id);
        for(const f of s.plans.floors){
          await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();await page.waitForFunction(id=>window.__htmlModel3dDebug().state.floor===id,f.id);
          const d=await page.evaluate(()=>window.__htmlModel3dDebug());
          assert(d.presentation==='tour'&&d.state.building===o.building&&d.visibleRooms.length===f.rooms.length,'Complete isolated floor '+o.id+' '+s.id+' '+f.id);
          assert(await page.locator('#furniture-names').isDisabled(),'Compact policy survives synchronization '+o.id+' '+s.id+' '+f.id);
          for(const r of f.rooms){const actual=d.tour.rooms.find(t=>t.id===r.id);
            assert(actual&&JSON.stringify(actual.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(actual.features)===JSON.stringify(r.features),'Actual room/door/window parity '+o.id+' '+s.id+' '+r.id);
            if(r.features.window_review?.renderable)assert(actual.windowParts>0,'Actual candidate window mesh '+o.id+' '+s.id+' '+r.id);
            for(const i of r.furniture){const p=d.furniture.shapes.find(v=>v.id===i.id);
              assert(p?.visible&&p.parts>0&&!p.overflow&&!p.collision&&p.width===i.width_mm&&p.depth===i.depth_mm&&p.height===i.height_mm&&Math.abs(p.center[0]-i.placement.center_x_mm)<.05&&Math.abs(p.center[1]-i.placement.center_y_mm)<.05,'Actual unscaled furniture '+o.id+' '+s.id+' '+i.id);}}
          if(f.id==='floor-2')await capture(o.id+'-'+s.id+'-desktop.png');
          counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
        }
        await page.setViewportSize({width:390,height:844});
        const specification=cases.find(c=>c.option===o.id&&c.use===s.id),{floor,room}=specification;
        await page.goto(base+'structured/candidates/current-design-basis-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building='+o.building+'&floor='+floor+'&room='+encodeURIComponent(room)+'&focus=room&view=front');await ready(o.id,s.id);
        const toggle=page.locator('#mobile-panel-toggle');if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
        await fitted(false);
        mobileEvidence.push(inspectMobileView(await readMobile('initial'),specification));
        assert(mobileEvidence.at(-1).bodyRects.length===specification.items.length,'Mobile actual body pixel sizes and text-free draw '+o.id+' '+s.id);await capture(o.id+'-'+s.id+'-mobile.png');
        await page.locator('#b32-room-details').click();assert(await page.locator('#furniture-list').isVisible()&&(await page.locator('#b32-room-entry-status').innerText()).includes('未核'),'Accessible equipment and conditional entrance list '+o.id+' '+s.id);
        await page.locator('#b32-details-back').click();await fitted(false);
        mobileEvidence.push(inspectMobileView(await readMobile('equipment-return'),specification));
        assert(mobileEvidence.at(-1).room===room,'Equipment return preserves readable bodies '+o.id+' '+s.id);
        await page.locator('#room-overview').click();await fitted(true);
        mobileEvidence.push(inspectMobileView(await readMobile('overview'),specification));
        assert(mobileEvidence.at(-1).draw.clipped===false,'Return to whole floor restores unclipped draw '+o.id+' '+s.id);
        counts.states++;
      }
      counts.options++;
    }
    await page.goto(base+'structured/candidates/current-design-basis.html');await checkWarning('mobile');await capture('index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'Every independent state/floor inspected');
    assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained runtime or console error');
    return {marker:'house-current-design-qa',revision:2,displayRevision:2,status:'passed',counts,checks,screenshots,messages,mobileEvidence};
  }catch(e){await capture('failure.png').catch(()=>{});await page.goto('about:blank').catch(()=>{});return {marker:'house-current-design-qa',revision:2,displayRevision:2,status:'failed',error:String(e),counts,checks,screenshots,messages,mobileEvidence};}
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${inspectMobileView.toString()}))`;}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function validateReport(r,counts,cases){if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw Error('No completed structured QA result');
  if(r.status==='passed'){
    if(r.revision!==2||r.displayRevision!==2||!same(r.counts,counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||!Array.isArray(r.screenshots)||r.screenshots.length<2+2*counts.states||
      !Array.isArray(cases)||cases.length!==counts.states||!Array.isArray(r.mobileEvidence)||r.mobileEvidence.length!==3*cases.length)throw Error('Incomplete passing evidence');
    const seen=new Set();
    for(const e of r.mobileEvidence){
      const key=[e.option,e.use,e.phase].join('/'),c=cases.find(c=>c.option===e.option&&c.use===e.use);
      if(!c||seen.has(key))throw Error('Missing/duplicate mobile evidence');seen.add(key);inspectMobileView(e,c);
    }
    for(const c of cases)for(const phase of ['initial','equipment-return','overview'])if(!seen.has([c.option,c.use,phase].join('/')))throw Error('Missing mobile interaction phase');
  }return r;}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-current-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.study,prepared.counts,prepared.closeupCases));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:12*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));if(required&&(r.error||r.status!==0))throw Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);
    if(response?.isError)throw Error('Playwright CLI error; see checks.log');report=validateReport(findReport(response),prepared.counts,prepared.closeupCases);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Source hashes changed during QA';}}
  catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}return report;
}
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_current_design_playwright.cjs [--preflight] [--project <path>]; no install or adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node for rendered QA; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('Current design preflight passed: '+JSON.stringify(p.counts));
  console.log('Five independent discussion options. A suite choice pending; B rear/front retained; C one 2F washer. Not adopted.');
  console.log('Display revision: 2; actual mobile body pixels, text-free draw and equipment-return/overview required. Layouts unchanged.');
  if(o.preflight){console.log('Files only; no browser/rendered/professional approval.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-current-design-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated current-design browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('This session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. No legal, religious, care, transport or construction approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={closeupCases,inspectMobileView,validateIndexWarning,preflight,checkPages,makeBrowserScript,findReport,validateReport,runQa};
