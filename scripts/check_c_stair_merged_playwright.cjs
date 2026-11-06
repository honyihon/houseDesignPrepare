// Native Windows only for rendered QA. --preflight is bounded read-only file work.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs'),kh=require('./check_kaohsiung_options_playwright.cjs');
const REPORT='structured/candidates/kaohsiung-house-options/c-stair-integration.json';
const BASE='structured/candidates/kaohsiung-house-options/review.json';
const VIEWER='structured/candidates/kaohsiung-house-options-3d.html',INDEX='structured/candidates/kaohsiung-house-options.html';
const MARKER='house-c-stair-merged-qa';
const ARCHIVE={
 'structured/candidates/kaohsiung-house-options.html':['inputs/references/source-history/20261104-before-c-stair-merge/index.html.txt','1ffc4ee8c94d12141b3feb932e2187230f3d9974ed26d20324f688b7f096199a'],
 'structured/candidates/kaohsiung-house-options-3d.html':['inputs/references/source-history/20261104-before-c-stair-merge/viewer.html.txt','cc8035e2afc4fec3cb417e0ec1053f4324487a0d2c5c865d03701d5d4fdcebc0']
};
function bytes(project,file){return fs.readFileSync(kh.publicFile(project,file));}
function json(project,file){return JSON.parse(bytes(project,file));}
function preflight(project){
 const study=json(project,REPORT),base=json(project,BASE),files=new Set([REPORT,BASE,
  'scripts/check_c_stair_merged_playwright.cjs','scripts/check_kaohsiung_options_playwright.cjs','scripts/check_windows_playwright.cjs','scripts/check_current_design_playwright.cjs']);
 if(study.integration_schema!=='house-c-stair-viewer-integration-v1'||study.integration_revision!==2||study.stair_display_revision!==2||study.ac01_route_revision!==1||study.owner_selected_partition!=='forward-closing-door'||
   study.adopted!==false||study.rendered_qa!=='not-run'||study.display_revision!==2||!study.preserved_other_options||!study.original_C_furniture_unchanged||
   kh.hash(bytes(project,BASE))!=='84f81465f280ec64931d29e49234b1dbcafc6b0b93a20b2a33f683e14f164fdf'||
   study.options.length!==5||Object.values(study.professional_status).some(v=>v!=='unknown'))throw Error('Invalid selected-C integration scope');
 for(const [name,digest]of Object.entries({...study.source_hashes,...study.artifact_hashes})){
  if(kh.hash(bytes(project,name))!==digest)throw Error('Changed merged source/artifact: '+name);files.add(name);
 }
 for(const [name,digest]of Object.entries({...base.source_hashes,...base.artifact_hashes})){
  const reference=ARCHIVE[name];
  if(reference){if(reference[1]!==digest||kh.hash(bytes(project,reference[0]))!==digest)throw Error('Original archived artifact changed');files.add(reference[0]);}
  else {if(kh.hash(bytes(project,name))!==digest)throw Error('Unrelated frozen source changed: '+name);files.add(name);}
 }
 const text=bytes(project,VIEWER).toString('utf8'),match=text.match(/^\s*var DATA = (.+);\s*$/m);
 if(!match||kh.hash(match[1])!==study.payload_sha256)throw Error('Integrated payload bytes differ');
 const payload=JSON.parse(match[1]).kaohsiung_options;
 if(payload.integration_revision!==2||payload.stair_display_revision!==2||payload.ac01_route_revision!==1||payload.report_hash!==study.report_hash||!same(payload.source_hashes,study.source_hashes)||
  !text.includes('csPrepareFloor(mesh);')||!text.includes('cStair:csEvidence()'))throw Error('Missing selected-C runtime');
 const oldText=bytes(project,ARCHIVE[VIEWER][0]).toString('utf8');
 const original=JSON.parse(oldText.match(/^\s*var DATA = (.+);\s*$/m)[1]).kaohsiung_options;
 const counts={options:0,states:0,floors:0,rooms:0,items:0},cases=[];
 for(const option of study.options){
  const actual=payload.options.find(o=>o.id===option.id),old=original.options.find(o=>o.id===option.id);
  if(!actual||!old||!same(option.states.map(s=>s.id),option.building==='B'?['daily','ritual','carry']:['daily']))throw Error('Missing original option/state');
  if(option.id!=='c-split'&&!same(actual,old))throw Error('A/B or old C control changed');
  for(const state of option.states){
   const model=actual.states.find(s=>s.id===state.id)?.model;
   if(!model||model.bc_option.id!==option.id||!same(model.bc_option.geometry_review,state.review))throw Error('Mixed selected layout review');
   for(const floor of state.plans.floors){
    const mf=model.buildings[0].floors.find(f=>f.id===floor.id),active=mf.cells.filter(c=>c.tour_active);
    if(active.length!==floor.rooms.length||mf.base_mm!==floor.base_mm||mf.height_mm!==floor.height_mm)throw Error('Floor elevation/room mismatch');
    for(const room of floor.rooms){
     const cell=active.find(c=>c.id===room.id);
     if(!cell||!same(cell.tour_mm,room.geometry)||!same(cell.tour_features,room.features)||
       !same(cell.furniture.map(i=>({...i,placement:cell.furniture_placements.tour_mm[i.id]})),room.furniture))throw Error('Plan/model mismatch: '+room.id);
    }
    counts.floors++;counts.rooms+=floor.rooms.length;counts.items+=floor.rooms.reduce((n,r)=>n+r.furniture.length,0);
   }
   const room=state.plans.floors[1].rooms.find(r=>r.key===(option.building==='C'?'balcony2f':'balcony2'));
   const zone=room.features.kaohsiung_zones||null,hvac=room.features.hvac_units||[];
   cases.push({option:option.id,use:state.id,building:option.building,room:room.id,zone,hvac,
    equipmentIds:[...(!room.furniture.length?['empty-furniture']:[]),...(zone?['garden','soil','woody']:[]),...hvac.map(u=>'hvac-'+u.type+'-'+u.id)]});
   counts.states++;
  }counts.options++;
 }
 const selected=study.options.find(o=>o.id==='c-split').states[0],cm=payload.options.find(o=>o.id==='c-split').states[0].model;
 if(!same(selected.plans.floors.map(f=>[f.base_mm,f.height_mm]),[[0,4000],[4000,3000],[7000,3000],[10000,3000]])||
   !cm.c_stair_merge?.owner_confirmed_layout||cm.c_stair_merge.display_revision!==2||cm.c_stair_merge.front_door_clear_width_mm!==null)throw Error('Selected C height/approval mismatch');
 if(!same(cm.c_ac01_routing,study.c_ac01_review)||study.c_ac01_review?.revision!==1||study.c_ac01_review.professional_approval!=='unknown'||
   !study.c_ac01_review.old_indoor_partition_conflict||study.c_ac01_review.candidate_low_arcade_segments.length||!text.includes('cAc01Routing:caEvidence()'))throw Error('Missing C-AC01 candidate review');
 for(const floor of selected.plans.floors){
  const filename='structured/candidates/kaohsiung-house-options/'+floor.plan_file,svg=bytes(project,filename).toString('utf8');
  if(!svg.includes('data-c-stair-integration="1"')||!svg.includes('data-c-stair-source-features="1"'))throw Error('Missing matching integrated SVG overlay');
 }
 return {study,counts,cases,selected,sourceFiles:[...files],cli:path.join(project,'node_modules','playwright','cli.js')};
}
function inspectStair(e,floor,front,side){
 if(!e?.active||e.revision!==1||e.displayRevision!==2||e.option!=='c-split'||e.frontState!==front||e.sideState!==side||
  e.ownerConfirmedLayout!==true||e.professionalApproval!=='unknown'||e.frontClearWidthMm!==null||e.sideClearWidthMm!==null)throw Error('Missing selected-C runtime evidence');
 if(!same(e.floorBases.map(f=>[f.base_mm,f.height_mm]),[[0,4000],[4000,3000],[7000,3000],[10000,3000]]))throw Error('Actual C floor levels differ');
 const room=floor.rooms.find(r=>r.features.c_stair_surfaces),parts=e.parts.filter(p=>p.visible&&p.floor===floor.id);
 if(e.floorOmissions.length!==4||e.floorOmissions.some(f=>!f.omitted||f.actualOpacity!==0||f.actualDepthWrite!==false))throw Error('Opaque full stair-room slab still caps the stairwell: '+JSON.stringify(e.floorOmissions));
 const close=(a,b)=>Array.isArray(a)&&a.length===b.length&&a.every((v,n)=>Number.isFinite(v)&&Math.abs(v-b[n])<.15);
 for(const s of room.features.c_stair_surfaces){
  const found=parts.filter(p=>p.id===s.id);
  if(found.length!==1||!close(found[0].actualRectMm,s.rect_mm)||Math.abs(found[0].actualTopMm-s.top_z_mm)>.15||
   Math.abs(found[0].actualHeightMm-150)>.15)throw Error('Actual stair surface differs: '+s.id);
 }
 if(room.features.c_stair_context_arrival){
  const expected=room.features.c_stair_context_arrival,found=parts.filter(p=>p.id===expected.id);
  if(found.length!==1||!close(found[0].actualRectMm,expected.rect_mm)||Math.abs(found[0].actualTopMm-expected.top_z_mm)>.15)throw Error('Isolated stair has no upper arrival connection');
 }
 if(room.features.c_front_gate){
  const gate=room.features.c_front_gate,leaf=parts.filter(p=>p.id==='front-leaf');
  if(leaf.length!==1||!close(leaf[0].actualRectMm,front==='open'?gate.parking_rect_mm:gate.closed_leaf_rect_mm)||leaf[0].opacity<.5)throw Error('Front door label changed without actual leaf movement');
 }
 if(room.features.c_side_gate){
  const gate=room.features.c_side_gate,leaf=parts.filter(p=>p.id==='side-leaf');
  if(leaf.length!==1||!close(leaf[0].actualRectMm,side==='open'?gate.open_rect_mm:gate.closed_rect_mm))throw Error('Side door actual leaf movement differs');
 }
 if(floor.id==='floor-2'){
  const hole=[4720,9760,1200,270];
  for(const p of parts.filter(p=>['floor','platform'].includes(p.role)&&Math.abs(p.actualTopMm-4000)<.15)){
   const r=p.actualRectMm,overlapX=Math.min(r[0]+r[2],hole[0]+hole[2])-Math.max(r[0],hole[0]),overlapY=Math.min(r[1]+r[3],hole[1]+hole[3])-Math.max(r[1],hole[1]);
   if(overlapX>.2&&overlapY>.2)throw Error('Second-floor slab blocks the last incoming tread');
  }
 }
}
async function checkStairPages(page,base,output,selected,inspect){
 const checks=[],screenshots=[],stairEvidence=[],messages=[];
 let failureEvidence=null;
 const record=(d,floor,front,side,viewport)=>{
  failureEvidence={viewport,floor:floor.id,requestedFront:front,requestedSide:side,evidence:d.cStair};
  inspect(d.cStair,floor,front,side);stairEvidence.push({viewport,floor:floor.id,evidence:d.cStair});
  failureEvidence=null;
 };
 const assert=(ok,name)=>{checks.push({name,passed:Boolean(ok)});if(!ok)throw Error(name);};
 const capture=async name=>{const file=output+'/'+name;await page.screenshot({path:file,fullPage:false});screenshots.push(file);};
 page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
 page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
 const ready=async floor=>page.waitForFunction(f=>window.__htmlModel3dDebug?.().state.floor===f&&window.__htmlModel3dDebug().cameraFraming.ready&&window.__htmlModel3dDebug().cStair?.active,floor);
 const panel=async open=>{const button=page.locator('#mobile-panel-toggle');if(await button.isVisible()&&await button.getAttribute('aria-expanded')!==String(open))await button.click();};
 try{
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html?scheme=c-control&use=daily#mode=tour&building=C&floor=floor-2&view=plan');
  await page.waitForFunction(()=>window.__htmlModel3dDebug?.().cameraFraming.ready);
  let d=await page.evaluate(()=>window.__htmlModel3dDebug());assert(d.cStair?.active===false&&d.cStair.parts.length===0,'Old C control has no selected stair/door pollution');
  for(const viewport of [{name:'desktop',width:1440,height:900},{name:'mobile',width:390,height:844}]){
   await page.setViewportSize({width:viewport.width,height:viewport.height});
   for(const floor of selected.plans.floors.slice(0,2)){
    const room=floor.rooms.find(r=>r.features.c_stair_surfaces).id;
    await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html?scheme=c-split&use=daily&gate=open&sidegate=open#mode=tour&building=C&floor='+floor.id+'&room='+encodeURIComponent(room)+'&focus=room&view=plan');await ready(floor.id);await panel(false);
    d=await page.evaluate(()=>window.__htmlModel3dDebug());record(d,floor,'open','open',viewport.name);
    assert(d.visibleRooms.length===floor.rooms.length,'Selected stair closeup retains entire floor '+viewport.name+'/'+floor.id);
    await capture('c-stair-'+floor.id+'-open-'+viewport.name+'.png');
    await panel(true);await page.locator('#c-stair-front-door').selectOption('closed');await page.locator('#c-stair-side-door').selectOption('closed');
    await page.waitForFunction(()=>window.__htmlModel3dDebug().cStair.frontState==='closed'&&window.__htmlModel3dDebug().cStair.sideState==='closed');await panel(false);
    d=await page.evaluate(()=>window.__htmlModel3dDebug());record(d,floor,'closed','closed',viewport.name);
    assert(true,'Actual open and closed door rectangles checked '+viewport.name+'/'+floor.id);await capture('c-stair-'+floor.id+'-closed-'+viewport.name+'.png');
    if(viewport.name==='desktop'&&floor.id==='floor-2'){
     for(const state of [['closed','open'],['open','closed']]){
      await panel(true);await page.locator('#c-stair-front-door').selectOption(state[0]);await page.locator('#c-stair-side-door').selectOption(state[1]);
      d=await page.evaluate(()=>window.__htmlModel3dDebug());record(d,floor,state[0],state[1],viewport.name);
     }
     assert(true,'Both independent second-floor mixed door states checked');
    }
   }
  }
  assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained selected-C browser errors');
  return {status:'passed',checks,screenshots,stairEvidence,messages};
 }catch(error){await capture('c-stair-failure.png').catch(()=>{});return {status:'failed',error:String(error),checks,screenshots,stairEvidence,messages,failureEvidence};}
}
function inspectAc01(e,review,floor){
 if(!e?.active||e.revision!==1||e.professionalApproval!=='unknown'||e.state.floor!==floor)throw Error('Missing actual C-AC01 candidate evidence');
 const near=(a,b)=>Array.isArray(a)&&a.length===b.length&&a.every((n,i)=>Number.isFinite(n)&&Math.abs(n-b[i])<.2);
 const box=review.riser_envelope_mm,expected=[box[0],box[1],box[3]-box[0],box[4]-box[1]];
 const part=e.envelopes.filter(p=>p.visible&&p.floor===floor);
 if(part.length!==1||!near(part[0].rect_mm,expected)||Math.abs(part[0].bottom_z_mm-(floor==='floor-1'?box[2]:4000))>.2||
   Math.abs(part[0].top_z_mm-(floor==='floor-1'?4000:box[5]))>.2)throw Error('Actual riser coordination envelope differs');
 if(floor==='floor-1'){
  const lines=e.routes.filter(p=>p.id==='C-AC01'&&p.room===review.new_indoor_room&&p.visible);
  const points=review.route.polyline_mm.flatMap(p=>[p[0]/1000,p[2]/1000,-p[1]/1000]);
  if(lines.length!==1||lines[0].cameraFit!==false||!Array.isArray(lines[0].points)||lines[0].points.length!==points.length||
    lines[0].points.some((n,i)=>!Number.isFinite(n)||Math.abs(n-points[i])>.0002))throw Error('Actual refrigerant line differs from the C-AC01 candidate');
 }
}
async function checkAc01Pages(page,base,output,review,inspect){
 const checks=[],screenshots=[],ac01Evidence=[],messages=[];let failureEvidence=null;
 const assert=(ok,name)=>{checks.push({name,passed:!!ok});if(!ok)throw Error(name);};
 const panel=async open=>{const b=page.locator('#mobile-panel-toggle');if(await b.isVisible()&&await b.getAttribute('aria-expanded')!==String(open))await b.click();};
 page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
 page.on('console',m=>{if(['warning','error'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
 try{
  for(const viewport of [{name:'desktop',width:1440,height:900},{name:'mobile',width:390,height:844}]){
   await page.setViewportSize({width:viewport.width,height:viewport.height});
   await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html?scheme=c-split&use=daily#mode=tour&building=C&floor=floor-1&view=plan');
   await page.waitForFunction(()=>window.__htmlModel3dDebug?.().cameraFraming.ready);
   for(const [floor,room,id]of [['floor-1',review.new_indoor_room,'c-ac01-indoor-link'],['floor-2','C:floor-2:living2f','c-ac01-riser-link']]){
    await panel(true);await page.locator('#'+id).click();
    await page.waitForFunction(w=>{const d=window.__htmlModel3dDebug?.();return d?.state.floor===w.floor&&d.state.room===w.room&&d.cameraFraming.ready;},{floor,room});await panel(false);
    const d=await page.evaluate(()=>window.__htmlModel3dDebug());
    const evidence={...d.cAc01Routing,state:d.state,routes:d.cameraFraming.routes};failureEvidence={viewport:viewport.name,floor,evidence};
    inspect(evidence,review,floor);ac01Evidence.push(failureEvidence);failureEvidence=null;
    assert(true,'C-AC01 actual line/envelope and navigation '+viewport.name+'/'+floor);
    const file=output+'/c-ac01-'+floor+'-'+viewport.name+'.png';await page.screenshot({path:file,fullPage:false});screenshots.push(file);
   }
  }
  assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained C-AC01 browser error');
  return {status:'passed',checks,screenshots,ac01Evidence,messages};
 }catch(error){await page.screenshot({path:output+'/c-ac01-failure.png',fullPage:false}).then(()=>screenshots.push(output+'/c-ac01-failure.png')).catch(()=>{});return {status:'failed',error:String(error),checks,screenshots,ac01Evidence,messages,failureEvidence};}
}
function makeBrowserScript(base,output,prepared){
 return `async page => {
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const header={marker:${JSON.stringify(MARKER)},revision:3,integrationRevision:2,ac01RouteRevision:1};
 const baseQA=await (${kh.checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(prepared.study)},${JSON.stringify(prepared.counts)},${JSON.stringify(prepared.cases)},(${kh.inspectZones.toString()}),(${kh.inspectEquipment.toString()}));
 if(baseQA.status!=='passed')return {...header,status:'failed',baseQA,error:baseQA.error};
 const stairs=await (${checkStairPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(prepared.selected)},(${inspectStair.toString()}));
 const common={...header,counts:baseQA.counts,checks:baseQA.checks.concat(stairs.checks),screenshots:baseQA.screenshots.concat(stairs.screenshots),baseQA,stairEvidence:stairs.stairEvidence,messages:baseQA.messages.concat(stairs.messages)};
 if(stairs.status!=='passed')return {...common,status:'failed',error:stairs.error,failureEvidence:stairs.failureEvidence||null};
 const ac01=await (${checkAc01Pages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(prepared.study.c_ac01_review)},(${inspectAc01.toString()}));
 return {...common,status:ac01.status,checks:common.checks.concat(ac01.checks),screenshots:common.screenshots.concat(ac01.screenshots),ac01Evidence:ac01.ac01Evidence,messages:common.messages.concat(ac01.messages),error:ac01.error,failureEvidence:ac01.failureEvidence||null};
 }`;
}
function findReport(value){
 if(value&&typeof value==='object'){if(value.marker===MARKER)return value;for(const v of Object.values(value)){const r=findReport(v);if(r)return r;}}
 else if(typeof value==='string'){try{return findReport(JSON.parse(value));}catch{}}
 return null;
}
function validateReport(r,prepared){
 if(!r||r.marker!==MARKER||r.revision!==3||r.integrationRevision!==2||r.ac01RouteRevision!==1||!['passed','failed'].includes(r.status))throw Error('No valid selected-C structured QA result');
 if(r.status==='passed'){
  kh.validateReport(r.baseQA,prepared.counts,prepared.cases);
  if(!same(r.counts,prepared.counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||r.screenshots?.length!==36||r.stairEvidence?.length!==10||r.ac01Evidence?.length!==4)throw Error('Incomplete selected-C integration evidence');
  const keys=new Set();for(const entry of r.stairEvidence){
   const floor=prepared.selected.plans.floors.find(f=>f.id===entry.floor);if(!floor)throw Error('Unexpected integrated stair floor');
   inspectStair(entry.evidence,floor,entry.evidence.frontState,entry.evidence.sideState);
   const key=[entry.viewport,entry.floor,entry.evidence.frontState,entry.evidence.sideState].join('/');if(keys.has(key))throw Error('Duplicated stair state evidence');keys.add(key);
  }
  for(const viewport of ['desktop','mobile'])for(const floor of ['floor-1','floor-2'])for(const state of ['open','closed']){
   if(!keys.has([viewport,floor,state,state].join('/'))||!r.screenshots.some(p=>p.endsWith('c-stair-'+floor+'-'+state+'-'+viewport+'.png')))throw Error('Missing actual desktop/mobile door state screenshot');
  }
  for(const state of [['closed','open'],['open','closed']])if(!keys.has(['desktop','floor-2',...state].join('/')))throw Error('Missing independent side-door state');
  const acKeys=new Set();for(const entry of r.ac01Evidence){inspectAc01(entry.evidence,prepared.study.c_ac01_review,entry.floor);acKeys.add(entry.viewport+'/'+entry.floor);}
  for(const viewport of ['desktop','mobile'])for(const floor of ['floor-1','floor-2']){
   if(!acKeys.has(viewport+'/'+floor)||!r.screenshots.some(p=>p.endsWith('c-ac01-'+floor+'-'+viewport+'.png')))throw Error('Missing actual C-AC01 line/envelope screenshot');
  }
 }return r;
}
function runQa(options,prepared,output,execute=spawnSync){
 const session='house-c-stair-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
 const sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles),base=pathToFileURL(options.project+path.sep).href;
 fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
 fs.writeFileSync(script,makeBrowserScript(base,output,prepared));
 const invoke=(name,args,required=true)=>{const x=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:16*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});fs.writeFileSync(path.join(output,name+'.log'),(x.stdout||'')+'\n'+(x.stderr||'')+(x.error?'\n'+String(x.error):''));if(required&&(x.error||x.status!==0))throw Error(name+' failed; see '+name+'.log');return x;};
 let result={marker:MARKER,revision:3,integrationRevision:2,ac01RouteRevision:1,status:'incomplete'};
 try{invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);if(response?.isError)throw Error('Playwright CLI failed; see checks.log');result=validateReport(findReport(response),prepared);if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){result.status='incomplete';result.error='Sources changed during QA';}}
 catch(error){result.status='incomplete';result.error=String(error);}
 finally{Object.assign(result,{project:options.project,sourceHashes,browser:options.browser,session});try{const closed=invoke('close',['close'],false);result.sessionClosed=!closed.error&&closed.status===0&&['closed','not-open'].includes(JSON.parse(closed.stdout).status);}catch{result.sessionClosed=false;}fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));}
 return result;
}
function main(given){
 const options=given||legacy.parseArguments(process.argv.slice(2));
 if(options.help){console.log('node scripts/check_c_stair_merged_playwright.cjs [--preflight]');return;}
 if(!options.preflight&&process.platform!=='win32')throw Error('Run rendered QA with Windows Node; --preflight starts no browser.');
 const prepared=preflight(options.project);console.log('Project: '+options.project);console.log('C stair merged preflight passed: '+JSON.stringify(prepared.counts));
 console.log('C integration revision: 2; 4m/24 risers/270mm, shared platforms, front/side door open and closed. Products and approvals unknown.');
 console.log('C stair display revision: 2; stairwell floor omission survives material updates; stair geometry unchanged.');
 console.log('C-AC01 routing revision: 1; indoor moved clear of partition, interior riser and 2F high route are unapproved candidates.');
 if(options.preflight){console.log('Files only; no browser launched.');return;}
 if(!fs.existsSync(prepared.cli))throw Error('Pinned Playwright CLI missing; no installation attempted.');
 const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-stair-merged-cli-'));console.log('QA output folder: '+output);
 const result=runQa(options,prepared,output);console.log('Automated C stair merged browser checks: '+result.status);console.log('Result: '+path.join(output,'result.json'));
 if(result.error)console.error(result.error);if(!result.sessionClosed)console.warn('Only this QA session was targeted; its cleanup is unconfirmed.');
 console.log('Screenshots require visual review; no product, care, fire, legal or construction approval.');if(result.status!=='passed')process.exitCode=1;
}
if(require.main===module){try{main();}catch(error){console.error(String(error));process.exitCode=1;}}
module.exports={preflight,inspectStair,checkStairPages,inspectAc01,checkAc01Pages,makeBrowserScript,findReport,validateReport,runQa,main};
