// New bath snapshot only. No automatic browser on WSL, install or parent writes.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const route=require('./check_c_care_route_playwright.cjs'),entry=require('./check_c_care_entry_playwright.cjs'),basis=require('./check_current_design_playwright.cjs'),legacy=require('./check_windows_playwright.cjs');
const MARKER='house-c-care-bath-qa',DIR='structured/candidates/c-care-bath',INDEX=DIR+'.html',VIEWER=DIR+'-3d.html',REPORT=DIR+'/review.json';
function mobileCases(study){return study.options.flatMap(o=>o.states.map(s=>{const f=s.plans.floors[0],r=f.rooms.find(r=>r.key==='elder-bath');
  return {option:o.id,use:s.id,building:'C',floor:f.id,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),items:r.furniture.map(i=>({id:i.id,short:32,long:64}))};}));}
function accessorySpecs(state){return state.plans.floors[0].rooms.flatMap(r=>(r.features.care_bath_components||[]).map(c=>({...c,room:r.id})));}
function accessoryBounds(c){
  if(c.kind==='box'){const [x,y,w,d]=c.rect_mm;return {minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:c.bottom_mm,maxHeight:c.bottom_mm+c.height_mm};}
  const radius=c.diameter_mm/2,x=c.points_mm.map(p=>p[0]),y=c.points_mm.map(p=>p[1]),z=c.points_mm.map(p=>p[2]);
  return {minX:Math.min(...x)-radius,maxX:Math.max(...x)+radius,minY:Math.min(...y)-radius,maxY:Math.max(...y)+radius,minHeight:Math.min(...z)-radius,maxHeight:Math.max(...z)+radius};
}
function inspectAccessories(actual,expected){
  if(!Array.isArray(actual)||actual.length!==expected.length||new Set(actual.map(a=>a.id)).size!==actual.length)throw Error('Missing/duplicate actual bath accessories');
  for(const e of expected){const a=actual.find(a=>a.id===e.id);let bounds;
    if(e.kind==='box'){const [x,y,w,d]=e.rect_mm;bounds={minX:x,maxX:x+w,minY:y,maxY:y+d,minHeight:e.bottom_mm,maxHeight:e.bottom_mm+e.height_mm};}
    else{const radius=e.diameter_mm/2,x=e.points_mm.map(p=>p[0]),y=e.points_mm.map(p=>p[1]),z=e.points_mm.map(p=>p[2]);bounds={minX:Math.min(...x)-radius,maxX:Math.max(...x)+radius,minY:Math.min(...y)-radius,maxY:Math.max(...y)+radius,minHeight:Math.min(...z)-radius,maxHeight:Math.max(...z)+radius};}
    if(!a||a.room!==e.room||a.state!==e.state||a.kind!==e.kind||a.status!=='generic-accessory-not-selected-product'||a.counts_as_furniture!==false||!a.actualBoundsMm||
      Object.entries(bounds).some(([k,v])=>!Number.isFinite(a.actualBoundsMm[k])||Math.abs(a.actualBoundsMm[k]-v)>.1))throw Error('Actual bath accessory body/state differs: '+e.id);
  }return actual;
}
function preflight(project){
  const parent=route.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-c-care-bath-v1'||study.revision!==1||study.display_revision!==2||study.bath_display_revision!==2||study.adopted!==false||study.status!=='discussion-only-not-adopted'||study.rendered_qa!=='not-run'||
    study.default_option!=='c-bath-refined'||!same(study.frame_mm,[6000,17630])||Object.values(study.professional_status).some(s=>s!=='unknown')||
    !same(study.options.map(o=>o.id),['c-bath-control','c-bath-refined'])||study.requirement_ledger.canonical_requirements!==66||study.requirement_ledger.scenario_rows!==40||study.requirement_ledger.verified_requirements!==0)throw Error('Invalid bath scope/target/approval');
  const files=[INDEX,VIEWER,REPORT,DIR+'/requirement-ledger.json','scripts/check_c_care_bath_playwright.cjs'];
  basis.validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8').replaceAll('bath-adoption-warning','basis-adoption-warning'));
  for(const [rel,digest] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe bath source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale bath source: '+rel);files.push(rel);
  }
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),m=text.match(/^\s*var DATA = (.+);\s*$/m),payload=m&&JSON.parse(m[1]).c_care_bath;
  if(!payload||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id))||!text.includes('careBath:careBathEvidence()')||!text.includes('readable=bathChooseRoomFrame(')||!text.includes('bodyProjectionBasis:"actual-mesh-bounds-not-nominal-empty-envelope"')||text.includes('DATA.source.c_care_route')||text.includes('DATA.source.current_design_basis'))throw Error('Mixed/missing independent bath viewer');
  if(!same(JSON.parse(fs.readFileSync(path.join(project,files[3]),'utf8')),study.requirement_ledger))throw Error('Stale bath ledger');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(o.building!=='C'||o.adopted!==false||!same(o.states.map(s=>s.id),o.id==='c-bath-control'?['baseline']:['transfer','shower','rail-down','door-closed']))throw Error('Invalid independent bath states');
    for(const s of o.states){const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.buildings[0].id!=='C'||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Mixed bath plan/model/review');
      for(const f of s.plans.floors){const cells=model.buildings[0].floors.find(v=>v.id===f.id).cells.filter(c=>c.tour_active);
        if(cells.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Bath study changed frame or floor count');
        for(const r of f.rooms){const c=cells.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('Bath HTML/3D room, furniture or engineering equipment differs');}
        const rel=DIR+'/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');files.push(rel);
        if(!svg.includes('width="660"')||!svg.includes('data-bath-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"'))throw Error('Missing bounded bath SVG');
        if(f.id==='floor-1')for(const c of accessorySpecs(s))if(!svg.includes('data-bath-component="'+c.id+'" data-component-state="'+c.state+'"'))throw Error('SVG accessory state differs');
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const detail=DIR+'/'+o.id+'_'+s.id+'_detail.svg';files.push(detail);if(!fs.readFileSync(path.join(project,detail),'utf8').includes('width="780"'))throw Error('Missing bounded bath detail');
      const b=s.review.bath;
      if(o.id==='c-bath-refined'){
        const expected={transfer:[false,false,false],shower:[true,false,true],'rail-down':[false,true,false],'door-closed':[false,false,false]}[s.id];
        if(!same(b.body_mm,[900,900])||!same(b.turn_reserve_mm.slice(2),[1500,1800])||!same([!!b.turn_coordinate_failures.length,!!b.transfer_coordinate_failures.length,!!b.rescue_board_rotation_failures.length],expected)||b.hardware_sweep_conflicts.length||b.professional_acceptance!=='unknown'||b.independent_dry_turn_floor!==false||accessorySpecs(s).length!==8)throw Error('Bath state assumed to fit falsely');
      }else if(!b.turn_coordinate_failures.length||!b.transfer_coordinate_failures.length)throw Error('Control lost known bath constraints');
      counts.states++;
    }counts.options++;
  }
  return {study,counts,closeupCases:mobileCases(study),mainCounts:parent.mainCounts,cli:parent.cli,sourceFiles:[...new Set([...parent.sourceFiles,...files])]};
}
function replaceExact(text,old,value){if(text.split(old).length!==2)throw Error('Verified bath page-check anchor changed: '+old);return text.replace(old,value);}
function pageCheckSource(){
  let text=route.pageCheckSource().replaceAll('c-care-route','c-care-bath').replaceAll('c-route-refined','c-bath-refined').replaceAll('c-route-control','c-bath-control')
    .replaceAll('route-adoption-warning','bath-adoption-warning').replaceAll('C騎樓至照護動線','C孝親套衛');
  text=replaceExact(text,"ready('c-bath-refined','open')","ready('c-bath-refined','transfer')");
  text=replaceExact(text,'inspectLeaves,inspectRoutes)','inspectLeaves,inspectRoutes,inspectAccessories,accessoryBounds)');
  text=replaceExact(text,'routeEvidence=[],counts=','routeEvidence=[],accessoryEvidence=[],counts=');
  const readAnchor='  const warning=async()=>{';
  const readCurrent=`  const recordMobile=async(phase,spec)=>{
    const raw=await readMobile(phase);mobileEvidence.push(raw);
    const index=mobileEvidence.length-1;
    if(raw.fit?.bathDisplayRevision!==2||raw.fit?.bodyProjectionBasis!=='actual-mesh-bounds-not-nominal-empty-envelope')throw Error('Missing current bath mobile camera evidence');
    mobileEvidence[index]=inspectMobileView(raw,spec);
  };
`;
  text=replaceExact(text,readAnchor,readCurrent+readAnchor);
  for(const phase of ['initial','equipment-return','overview'])text=replaceExact(text,"mobileEvidence.push(inspectMobileView(await readMobile('"+phase+"'),spec));","await recordMobile('"+phase+"',spec);");
  text=replaceExact(text,'routeEvidence.push({option:o.id,use:s.id,outlines:inspectRoutes(d.careRoute,routeSpec)});',
    'routeEvidence.push({option:o.id,use:s.id,outlines:inspectRoutes(d.careRoute,routeSpec)});const accessories=s.plans.floors[0].rooms.flatMap(r=>(r.features.care_bath_components||[]).map(c=>({...c,room:r.id})));accessoryEvidence.push({option:o.id,use:s.id,components:inspectAccessories(d.careBath,accessories)});');
  const listAnchor="assert(await page.locator('#furniture-list').isVisible(),'Accessible actual equipment list '+o.id+' '+s.id);";
  text=replaceExact(text,listAnchor,listAnchor+"assert(await page.locator('#bath-equipment-list [data-bath-component]').count()===(o.id==='c-bath-refined'?8:0),'Actual bath accessory list '+o.id+' '+s.id);");
  if(text.split('leafEvidence,routeEvidence}').length!==3)throw Error('Missing bath completion evidence anchors');
  text=text.replaceAll('leafEvidence,routeEvidence}','leafEvidence,routeEvidence,accessoryEvidence}');
  if(text.split('revision:2,displayRevision:2,status:').length!==3)throw Error('Missing current bath display-revision result anchors');
  return text.replaceAll('revision:2,displayRevision:2,status:','revision:2,displayRevision:2,bathDisplayRevision:2,status:');
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${pageCheckSource()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${basis.inspectMobileView.toString()}),(${entry.inspectLeaves.toString()}),(${route.inspectRoutes.toString()}),(${inspectAccessories.toString()}),(${accessoryBounds.toString()}))`;}
function validateReport(r,p){
  if(!r||r.marker!==MARKER)throw Error('No completed bath QA result');
  route.validateReport({...r,marker:'house-c-care-route-qa'},p);
  if(r.status==='passed'){
    if(r.bathDisplayRevision!==2||r.mobileEvidence.some(e=>e.fit?.bathDisplayRevision!==2||e.fit?.bodyProjectionBasis!=='actual-mesh-bounds-not-nominal-empty-envelope'))throw Error('Old or missing actual-mesh bath camera evidence');
    if(!Array.isArray(r.accessoryEvidence)||r.accessoryEvidence.length!==p.counts.states)throw Error('Missing actual bath accessory evidence');
    const seen=new Set();for(const e of r.accessoryEvidence){const s=p.study.options.find(o=>o.id===e.option)?.states.find(s=>s.id===e.use),key=e.option+'/'+e.use;
      if(!s||seen.has(key))throw Error('Unknown/duplicate bath accessory state');seen.add(key);inspectAccessories(e.components,accessorySpecs(s));}
  }return r;
}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function runQa(o,p,output,execute=spawnSync){
  const session='house-c-bath-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
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
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_c_care_bath_playwright.cjs [--preflight] [--project <path>]; no install/adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('C care bath preflight passed: '+JSON.stringify(p.counts));
  console.log('Existing 2.4x3m bath, shared wet turning floor, 8 engineering accessory candidates. Fold-seat/rail/door independent states; no care, rescue, fire or adoption approval.');
  console.log('Bath display revision: 2; actual thin fixture mesh bounds, compact mobile readout and raw failure evidence. Layouts unchanged.');
  if(o.preflight){console.log('Files only; no browser launched.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-care-bath-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated C care bath browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('Session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. Wet-floor use, care, rescue, products and construction remain unapproved.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={mobileCases,accessorySpecs,accessoryBounds,inspectAccessories,preflight,pageCheckSource,makeBrowserScript,validateReport,findReport,runQa};
