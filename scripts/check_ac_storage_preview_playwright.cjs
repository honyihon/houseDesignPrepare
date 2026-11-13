// --preflight reads files only. Rendered checks are reserved for the owner's Windows terminal.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const ROOT=path.resolve(__dirname,'..'),OUT='structured/coordination/ac-storage-preview-v1';
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
function read(root,name){
  if(!/^[A-Za-z0-9_./-]+$/.test(name)||path.isAbsolute(name)||name.split('/').some(v=>v==='..'||v==='private'))throw Error('Unsafe public preview path');
  return fs.readFileSync(path.join(root,name));
}
function parsePayload(text){
  const m=text.match(/^\s*var DATA = (.+);\s*$/m);if(!m)throw Error('Missing main-viewer payload');
  return JSON.parse(m[1]).kaohsiung_options;
}
function validateModels(report,preview,base){
  if(report.schema!=='house-ac-upper-floor-storage-preview-v1'||report.revision!==1||report.display_revision!==3||preview.display_revision!==3||report.adopted!==false||
     report.original_main_3d_changed!==false||report.B_not_imported_or_rebased!==true||report.rendered_qa!=='not-run-owner-separate-terminal-required'||
     report.cases.length!==6||!same(preview.options.map(o=>o.id),['a-rear-study','c-split'])||preview.report_hash!==report.report_hash)throw Error('A/C preview scope differs');
  for(const option of preview.options){
    const original=base.options.find(o=>o.id===option.id).states.find(s=>s.id==='daily').model;
    const control=option.states.find(s=>s.id==='daily'),proposed=option.states.find(s=>s.id==='storage');
    if(!control||!proposed||option.states.length!==2||!same(control.model,original))throw Error('Original control model changed');
    const restored=structuredClone(proposed.model),cells=restored.buildings[0].floors.flatMap(f=>f.cells);
    const active=cells.filter(c=>c.tour_active),basis={};active.forEach(c=>c.furniture.forEach(i=>{basis[i.basis]=(basis[i.basis]||0)+1;}));
    const summary={...structuredClone(original.furniture),items:active.reduce((n,c)=>n+c.furniture.length,0),
      rooms:active.filter(c=>c.furniture.length).length,basis_counts:basis};
    if(!same(proposed.model.furniture,summary)||proposed.model.bc_option.use_state!=='storage')throw Error('Unexpected inventory summary/product data changed');
    for(const c of report.cases.filter(c=>c.option===option.id)){
      const cell=cells.find(v=>v.id===c.host_room_id),items=cell.furniture.filter(i=>i.id===c.proposed_item_id);
      const p=cell.furniture_placements.tour_mm[c.proposed_item_id],vertical=c.rect_mm[2]<c.rect_mm[3];
      if(items.length!==1||items[0].storage_case!==c.case||items[0].shape!=='cabinet'||items[0].height_mm!==c.height_mm||
         items[0].width_mm!==(vertical?c.rect_mm[3]:c.rect_mm[2])||items[0].depth_mm!==(vertical?c.rect_mm[2]:c.rect_mm[3])||
         !p||p.rotation_deg!==(vertical?90:180)||!same(p.aabb,{minX:c.rect_mm[0],maxX:c.rect_mm[0]+c.rect_mm[2],minY:c.rect_mm[1],maxY:c.rect_mm[1]+c.rect_mm[3]})||
         !same(p.operation_mm,{minX:c.operation_mm[0],maxX:c.operation_mm[0]+c.operation_mm[2],minY:c.operation_mm[1],maxY:c.operation_mm[1]+c.operation_mm[3]})||p.issues.length)throw Error('New cabinet source differs: '+c.case);
      cell.furniture=cell.furniture.filter(i=>i.id!==c.proposed_item_id);delete cell.furniture_placements.tour_mm[c.proposed_item_id];
    }
    restored.furniture=structuredClone(original.furniture);restored.bc_option.use_state=original.bc_option.use_state;
    if(!same(restored,original))throw Error('Original furniture, architecture or systems changed');
    const saved=report.options.find(o=>o.id===option.id);
    for(const state of option.states){
      const plans=saved.states.find(s=>s.id===state.id).plans;
      for(const floor of plans.floors){
        const actual=state.model.buildings[0].floors.find(f=>f.id===floor.id),rooms=actual.cells.filter(c=>c.tour_active);
        if(actual.base_mm!==floor.base_mm||actual.height_mm!==floor.height_mm||rooms.length!==floor.rooms.length)throw Error('Floor levels or rooms differ');
        for(const room of floor.rooms){
          const cell=rooms.find(c=>c.id===room.id);
          if(!cell||!same(cell.tour_mm,room.geometry)||!same(cell.tour_features,room.features)||
             !same(cell.furniture.map(i=>({...i,placement:cell.furniture_placements.tour_mm[i.id]})),room.furniture))throw Error('Model/plan differs: '+room.id);
        }
      }
    }
  }
  return report.summary;
}
function preflight(root){
  const report=JSON.parse(read(root,OUT+'/review.json')),manifest=JSON.parse(read(root,OUT+'/artifact-manifest.json'));
  for(const [n,h]of Object.entries(report.source_hashes))if(hash(read(root,n))!==h)throw Error('Stale A/C preview source: '+n);
  for(const [n,h]of Object.entries(manifest.artifacts))if(hash(read(root,OUT+'/'+n))!==h)throw Error('Changed preview artifact: '+n);
  if(manifest.report_hash!==report.report_hash)throw Error('Mixed preview manifest');
  const text=read(root,OUT+'/index.html').toString('utf8'),payload=parsePayload(text);
  const base=parsePayload(read(root,'structured/candidates/kaohsiung-house-options-3d.html').toString('utf8'));
  const counts=validateModels(report,payload,base);
  if(!text.includes('id="ac-adoption-warning"')||!text.includes('window.__AC_STORAGE_QA__')||!same(payload.source_hashes,report.source_hashes))throw Error('Missing preview identity/evidence');
  return {report,counts};
}
function validateBody(ev,c,baseMm){
  const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<.2;
  if(ev.focusPending||!ev.frame?.ready)throw Error('Cabinet viewport still updating: '+c.case);
  if(!ev.present||!ev.visible||ev.overflow||ev.collision||!Array.isArray(ev.newItems)||ev.newItems.length!==3||!ev.newItems.includes(c.proposed_item_id)||
     !Array.isArray(ev.actualRectMm)||ev.actualRectMm.length!==4||
     !ev.actualRectMm.every((v,n)=>near(v,c.rect_mm[n]))||!near(ev.actualHeightMm,c.height_mm)||
     !near(ev.actualBottomMm,baseMm)||!near(ev.actualTopMm,baseMm+c.height_mm))throw Error('Actual cabinet mesh differs: '+c.case);
  const b=ev.projected,s=ev.stage,a=ev.safeArea,p=ev.pixels;
  if(!b||!b.inFront||![b.left,b.top,b.right,b.bottom,b.width,b.height].every(Number.isFinite)||
     b.left<0||b.top<0||b.right>s.width||b.bottom>s.height||b.left<a.left||b.right>a.right||b.top<a.top||b.bottom>a.bottom||
     b.width<55||b.height<60||b.width*b.height<5000)throw Error('Actual cabinet too small/clipped/under controls: '+c.case);
  if(!p||p.method!=='webgl-readPixels-cabinet-aabb'||!Number.isFinite(p.sampled)||!Number.isFinite(p.orange)||
     p.sampled<80||p.orange<40||p.orange>p.sampled||p.ratio<.05||
     !Number.isFinite(p.ratio)||Math.abs(p.ratio-p.orange/p.sampled)>1e-9)throw Error('Actual cabinet body pixels missing: '+c.case);
  return true;
}
async function worker(root,output,channel){
  const expected=preflight(root).report,report={schema:'house-ac-storage-preview-browser-qa-v1',display_revision:expected.display_revision,status:'incomplete',
    report_hash:expected.report_hash,source_hashes:expected.source_hashes,checks:[],cases:[],screenshots:[],console_errors:[],closed:false};
  let browser,page;
  const assert=(v,name)=>{report.checks.push({name,passed:Boolean(v)});if(!v)throw Error(name);};
  const settled=async()=>{
    await page.evaluate(()=>{window.__AC_STORAGE_QA_STABLE_STAMP__=null;});
    await page.waitForFunction(()=>{
      const e=window.__AC_STORAGE_QA__?.(),previous=window.__AC_STORAGE_QA_STABLE_STAMP__;
      window.__AC_STORAGE_QA_STABLE_STAMP__=e?.frame?.ready?e.frame.stamp:null;
      return e?.frame?.ready&&previous===e.frame.stamp;
    },null,{polling:'raf'});
  };
  const panel=async open=>{const b=page.locator('#mobile-panel-toggle');if(await b.isVisible()&&(await b.getAttribute('aria-expanded'))!==String(open))await b.click();};
  const capture=async name=>{const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);};
  try{
    const {chromium}=require(path.join(root,'node_modules','playwright'));
    browser=await chromium.launch({channel,headless:true});page=await browser.newPage();page.setDefaultTimeout(12000);
    page.on('pageerror',e=>report.console_errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.console_errors.push(m.text());});
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      await page.setViewportSize(viewport);
      for(const c of expected.cases)for(const use of ['storage','daily']){
        report.active_case={case:c.case,use,viewport};
        const url=pathToFileURL(path.join(root,OUT,'index.html'));url.searchParams.set('scheme',c.option);url.searchParams.set('use',use);url.searchParams.set('cabinet','1');
        url.hash='mode=tour&building='+c.building+'&floor='+c.floor+'&room='+encodeURIComponent(c.host_room_id)+'&focus=room&view=front';
        await page.goto(url.href,{waitUntil:'load'});
        await page.waitForFunction(id=>window.__htmlModel3dDebug?.().cameraFraming.ready&&window.__AC_STORAGE_QA__?.().caseId===id&&!window.__AC_STORAGE_QA__().focusPending,c.case);
        await settled();
        const ev=await page.evaluate(()=>window.__AC_STORAGE_QA__(true)),d=await page.evaluate(()=>{
          const v=window.__htmlModel3dDebug();return {state:v.state,roomCloseup:v.roomCloseup,panelCollapsed:v.panelCollapsed,
            roomIds:v.tour.rooms.map(r=>r.id),cStair:v.cStair||null};
        });
        report.active_case.evidence=ev;report.active_case.context=d;
        assert(ev.reportHash===expected.report_hash&&ev.displayRevision===expected.display_revision&&ev.option===c.option&&ev.use===use&&ev.caseId===c.case&&!ev.webglLost,'Source/state '+c.case+' '+use+' '+viewport.width);
        assert(ev.labelMode==='all'&&!ev.furnitureNames.disabled,'Default all-name mode enables furniture control '+c.case+' '+use);
        assert((await page.title()).includes('討論未採用')&&await page.locator('#study-stage-note').isVisible()&&(await page.locator('#study-stage-note').textContent()).includes(c.label)&&
          (await page.locator('#study-stage-note').textContent()).includes('未採用'),'Visible identity and full storage name '+c.case+' '+use);
        assert(await page.locator('#study-plan-link').getAttribute('href')===c.option+'_'+use+'_'+c.floor+'.svg','Matching state plan '+c.case+' '+use);
        const state=expected.options.find(o=>o.id===c.option).states.find(s=>s.id===use),floor=state.plans.floors.find(f=>f.id===c.floor);
        if(use==='storage')assert(validateBody(ev,c,floor.base_mm),'Actual body geometry and pixels '+c.case+' '+viewport.width);
        else assert(!ev.present&&ev.newItems.length===0,'Original control has no new cabinet '+c.case+' '+viewport.width);
        if(c.building==='C')assert(d.cStair?.active&&d.cStair.ownerConfirmedLayout===true&&d.cStair.floorOmissions.every(f=>f.omitted),'Selected C stair context preserved '+c.case+' '+use);
        await capture(c.case+'-'+use+'-'+viewport.width);
        if(use==='storage'){
          await panel(true);
          if(c.case==='A-2F'){
            await page.locator('#b32-label-mode').selectOption('compact');await settled();
            const compact=await page.evaluate(()=>window.__AC_STORAGE_QA__());report.active_case.compact_controls=compact;
            assert(compact.labelMode==='compact'&&compact.furnitureNames.disabled,'Compact mode describes a disabled furniture-name control '+viewport.width);
          }
          await page.locator('#b32-label-mode').selectOption('all');await settled();
          const controls=await page.evaluate(()=>window.__AC_STORAGE_QA__());report.active_case.names_on_controls=controls;
          assert(controls.labelMode==='all'&&!controls.furnitureNames.disabled,'All-name mode enables the normal checkbox '+c.case+' '+viewport.width);
          await page.locator('#furniture-names').uncheck();await panel(false);await settled();
          const bare=await page.evaluate(()=>window.__AC_STORAGE_QA__(true));report.active_case.names_off_evidence=bare;
          assert(!bare.furnitureNames.checked&&bare.furnitureNames.visibleLabels.length===0&&validateBody(bare,c,floor.base_mm),'Actual cabinet body with furniture names off '+c.case+' '+viewport.width);
          await panel(true);await page.locator('#furniture-names').check();await settled();
          const checked=await page.evaluate(()=>window.__AC_STORAGE_QA__());report.active_case.names_restored_controls=checked;
          assert(checked.furnitureNames.checked&&!checked.furnitureNames.disabled,'Furniture names restored through normal control '+c.case+' '+viewport.width);
          await page.locator('#ac-storage-floor-view').click();await settled();
          const full=await page.evaluate(()=>({storage:window.__AC_STORAGE_QA__(),d:window.__htmlModel3dDebug()}));
          assert(!full.d.roomCloseup&&same(full.d.tour.rooms.map(r=>r.id).sort(),floor.rooms.map(r=>r.id).sort())&&full.storage.visible,'Whole floor retains original rooms and cabinet '+c.case+' '+viewport.width);
          report.active_case.floor_context={roomIds:full.d.tour.rooms.map(r=>r.id),case:full.storage.caseId,visible:full.storage.visible};
          await capture(c.case+'-floor-'+viewport.width);
          if(c.case==='A-2F'){
            await panel(true);await page.locator('#study-use').selectOption('daily');
            await page.waitForFunction(()=>window.__AC_STORAGE_QA__?.().use==='daily'&&window.__htmlModel3dDebug?.().cameraFraming.ready);
            await settled();
            const control=await page.evaluate(()=>window.__AC_STORAGE_QA__());
            assert(control.caseId===c.case&&!control.present&&control.newItems.length===0,'State selector removes only new cabinets '+viewport.width);
            await panel(true);await page.locator('#study-use').selectOption('storage');
            await page.waitForFunction(()=>window.__AC_STORAGE_QA__?.().use==='storage'&&window.__htmlModel3dDebug?.().cameraFraming.ready);
            await settled();
            const restored=await page.evaluate(()=>window.__AC_STORAGE_QA__());
            assert(restored.caseId===c.case&&restored.present&&restored.newItems.length===3,'State selector restores same-floor cabinets '+viewport.width);
            report.active_case.state_switch={control,restored};
          }
        }
        report.cases.push(report.active_case);report.active_case=null;
      }
    }
    assert(report.console_errors.length===0,'No console/page errors');assert(preflight(root).report.report_hash===expected.report_hash,'Sources unchanged');report.status='passed';
  }catch(error){
    report.status='failed';report.error=error.stack||String(error);
    if(page){try{report.failure_evidence=await page.evaluate(()=>window.__AC_STORAGE_QA__?.(true)||null);await capture('failure');}catch(captureError){report.capture_error=String(captureError);}}
  }finally{
    if(browser){try{await browser.close();report.closed=true;}catch{}}
    if(report.status==='passed'&&!report.closed){report.status='incomplete';report.error='Browser cleanup not confirmed';}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
  }
  return report.status==='passed'?0:1;
}
function main(){
  const args=process.argv.slice(2);if(args[0]==='--worker')return worker(args[1],args[2],args[3]).then(code=>{process.exitCode=code;});
  const ready=preflight(ROOT);console.log('A/C storage preview preflight passed: '+JSON.stringify(ready.counts));
  console.log('A/C storage display revision: '+ready.report.display_revision+'; atomic resize/focus and matching rendered viewport required. Geometry unchanged.');
  if(args.includes('--preflight')){console.log('Files only; no rendered QA or professional approval.');return;}
  if(process.platform!=='win32')throw Error('Use native Windows PowerShell for browser QA; --preflight only in WSL.');
  const channel=args.find(v=>v.startsWith('--browser='))?.slice(10)||'msedge';if(!['msedge','chrome'].includes(channel))throw Error('Use msedge or chrome');
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-ac-storage-'));console.log('QA output: '+output);
  const result=spawnSync(process.execPath,[__filename,'--worker',ROOT,output,channel],{encoding:'utf8',timeout:120000,killSignal:'SIGTERM'}),file=path.join(output,'result.json');
  const report=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{status:'incomplete',closed:false,error:'No completed structured result'};
  if(result.error||result.signal||result.status!==0){if(report.status==='passed')report.status='incomplete';report.process_error=result.error?.message||result.signal||'worker exit '+result.status;}
  fs.writeFileSync(file,JSON.stringify(report,null,2));console.log('Automated A/C storage browser checks: '+report.status);console.log('Result: '+file);
  if(report.error)console.log('Failure: '+String(report.error).split('\n')[0]);
  console.log('Screenshots need visual review. Original ABC viewer unchanged; no adoption or professional approval.');
  if(report.status!=='passed')process.exitCode=1;
}
module.exports={parsePayload,validateModels,preflight,validateBody};
if(require.main===module){try{main();}catch(error){console.error(error.message);process.exitCode=1;}}
