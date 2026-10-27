// Files-only locally; a single native Windows browser session is owner-run.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const entry=require('./check_c_care_entry_playwright.cjs'),basis=require('./check_current_design_playwright.cjs'),legacy=require('./check_windows_playwright.cjs');
const MARKER='house-c-care-route-qa',DIR='structured/candidates/c-care-route',INDEX=DIR+'.html',VIEWER=DIR+'-3d.html',REPORT=DIR+'/review.json';
function mobileCases(study){return study.options.flatMap(o=>o.states.map(s=>{
  const f=s.plans.floors[0],r=f.rooms.find(r=>r.key===(s.id==='open'||s.id==='street-closed'?'dining':'elder'));
  return {option:o.id,use:s.id,building:'C',floor:f.id,room:r.id,viewport:{width:390,height:844},roomIds:f.rooms.map(r=>r.id),
    items:r.furniture.map(i=>({id:i.id,short:['bed','dining-set'].includes(i.shape)?40:16,long:['bed','dining-set'].includes(i.shape)?96:28}))};
}));}
function routeSpecs(state){return state.plans.floors[0].rooms.flatMap(r=>(r.features.care_route_overlays||[]).map(l=>({...l,room:r.id})));}
function inspectRoutes(actual,expected){
  if(!Array.isArray(actual)||actual.length!==expected.length||new Set(actual.map(a=>a.id)).size!==actual.length)throw Error('Missing/duplicate actual route outlines');
  for(const e of expected){const a=actual.find(a=>a.id===e.id);
    if(!a||a.room!==e.room||a.kind!==e.kind||a.blocked!==e.blocked||!Array.isArray(a.actualPointsMm)||a.actualPointsMm.length!==e.points_mm.length||
      a.actualPointsMm.some((p,n)=>!Array.isArray(p)||p.length!==2||p.some((v,k)=>!Number.isFinite(v)||Math.abs(v-e.points_mm[n][k])>.1)))throw Error('Actual route/sweep geometry differs: '+e.id);
  }return actual;
}
function preflight(project){
  const parent=entry.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-c-care-route-v1'||study.revision!==1||study.display_revision!==2||study.adopted!==false||study.status!=='discussion-only-not-adopted'||study.rendered_qa!=='not-run'||
    study.default_option!=='c-route-refined'||!same(study.frame_mm,[6000,17630])||Object.values(study.professional_status).some(s=>s!=='unknown')||
    !same(study.options.map(o=>o.id),['c-route-control','c-route-refined'])||study.requirement_ledger.canonical_requirements!==66||study.requirement_ledger.scenario_rows!==40||study.requirement_ledger.verified_requirements!==0)
    throw Error('Invalid route scope, original requirements or adoption status');
  const files=[INDEX,VIEWER,REPORT,DIR+'/requirement-ledger.json','scripts/check_c_care_route_playwright.cjs'];
  basis.validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8').replaceAll('route-adoption-warning','basis-adoption-warning'));
  for(const [rel,digest] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe route source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale route source: '+rel);files.push(rel);
  }
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),m=text.match(/^\s*var DATA = (.+);\s*$/m),payload=m&&JSON.parse(m[1]).c_care_route;
  if(!payload||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id))||!text.includes('careRoute:careRouteEvidence()')||text.includes('DATA.source.c_care_entry')||text.includes('DATA.source.current_design_basis'))throw Error('Mixed/missing route viewer');
  if(!same(JSON.parse(fs.readFileSync(path.join(project,files[3]),'utf8')),study.requirement_ledger))throw Error('Stale route ledger');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(o.building!=='C'||o.adopted!==false||!same(o.states.map(s=>s.id),o.id==='c-route-control'?['baseline']:['open','street-closed','bedroom-closed','bath-closed']))throw Error('Invalid independent route states');
    for(const s of o.states){
      const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.buildings[0].id!=='C'||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Mixed route plan/model/review');
      for(const f of s.plans.floors){
        const cells=model.buildings[0].floors.find(v=>v.id===f.id).cells.filter(c=>c.tour_active);
        if(cells.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Route floor expanded or incomplete');
        for(const r of f.rooms){const c=cells.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('Route HTML/3D room, aperture or furniture differs');}
        const rel=DIR+'/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');files.push(rel);
        if(!svg.includes('width="660"')||!svg.includes('data-route-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"'))throw Error('Missing bounded same-source route SVG');
        if(f.id==='floor-1'){
          for(const l of entry.leafSpecs(s))if(!svg.includes('data-care-leaf-id="'+l.id+'" data-leaf-state="'+l.state+'"'))throw Error('SVG actual leaf state differs');
          for(const k of Object.keys(s.review.route.routes))if(!svg.includes('data-care-route="'+k+'"'))throw Error('Missing full route in same-source SVG');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const r=s.review.route;
      if(o.id==='c-route-refined'){
        const block={'open':[false,false],'street-closed':[true,false],'bedroom-closed':[true,false],'bath-closed':[false,true]}[s.id];
        if(!same(r.body_mm,[900,900])||r.effective_open_street_width_assumption_mm!==970||r.front_window_to_opening_budget_mm!==100||r.arcade_occupied_by_sweep!==false||r.street_sweep_hits.length||r.operation_vs_fixed_body.length||r.turn_coordinate_failures.length||
          !same(['arcade-to-bed','bed-to-bath'].map(k=>Boolean(r.routes[k].coordinate_failures.length)),block)||r.gates.some(g=>g.nominal_mm!==1200||g.clear_assumption_at_115mm!==970||g.actual_finished_clear_and_product!=='unknown')||entry.leafSpecs(s).length!==3||routeSpecs(s).length!==3)throw Error('Route assumptions or independent closed controls differ');
      }else if(!r.routes['arcade-to-bed'].coordinate_failures.length)throw Error('Control lost known upstream bottlenecks');
      counts.states++;
    }counts.options++;
  }
  return {study,counts,closeupCases:mobileCases(study),mainCounts:parent.mainCounts,cli:parent.cli,sourceFiles:[...new Set([...parent.sourceFiles,...files])]};
}
function replaceExact(text,old,value){if(text.split(old).length!==2)throw Error('Verified page-check anchor changed: '+old);return text.replace(old,value);}
function pageCheckSource(){
  // Reuse the verified actual mesh/mobile interaction loop, not its old results.
  let text=entry.checkPages.toString().replaceAll('c-care-entry','c-care-route').replaceAll('c-entry-refined','c-route-refined').replaceAll('c-entry-control','c-route-control')
    .replaceAll('care-adoption-warning','route-adoption-warning').replaceAll('C孝親房入口','C騎樓至照護動線');
  text=replaceExact(text,"ready('c-route-control','daily')","ready('c-route-control','baseline')");
  text=replaceExact(text,'cases,inspectMobileView,inspectLeaves)','cases,inspectMobileView,inspectLeaves,inspectRoutes)');
  text=replaceExact(text,'leafEvidence=[],counts=','leafEvidence=[],routeEvidence=[],counts=');
  text=replaceExact(text,'leafEvidence.push({option:o.id,use:s.id,leaves:inspectLeaves(d.careEntry,spec)});',
    'leafEvidence.push({option:o.id,use:s.id,leaves:inspectLeaves(d.careEntry,spec)});const routeSpec=s.plans.floors[0].rooms.flatMap(r=>(r.features.care_route_overlays||[]).map(l=>({...l,room:r.id})));routeEvidence.push({option:o.id,use:s.id,outlines:inspectRoutes(d.careRoute,routeSpec)});');
  if(text.split('mobileEvidence,leafEvidence}').length!==3)throw Error('Missing successful/failed route evidence anchors');
  return text.replaceAll('mobileEvidence,leafEvidence}','mobileEvidence,leafEvidence,routeEvidence}');
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${pageCheckSource()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${basis.inspectMobileView.toString()}),(${entry.inspectLeaves.toString()}),(${inspectRoutes.toString()}))`;}
function validateReport(r,prepared){
  if(!r||r.marker!==MARKER)throw Error('No completed C route structured evidence');
  basis.validateReport({...r,marker:'house-current-design-qa'},prepared.counts,prepared.closeupCases);
  if(r.status==='passed'){
    for(const [key,inspect,specs] of [['leafEvidence',entry.inspectLeaves,entry.leafSpecs],['routeEvidence',inspectRoutes,routeSpecs]]){
      if(!Array.isArray(r[key])||r[key].length!==prepared.counts.states)throw Error('Missing actual '+key);
      const seen=new Set();
      for(const e of r[key]){const state=prepared.study.options.find(o=>o.id===e.option)?.states.find(s=>s.id===e.use),id=e.option+'/'+e.use;
        if(!state||seen.has(id))throw Error('Duplicate/unknown '+key);seen.add(id);inspect(e[key==='leafEvidence'?'leaves':'outlines'],specs(state));}
    }
  }return r;
}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function runQa(o,p,output,execute=spawnSync){
  const session='house-c-route-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
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
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_c_care_route_playwright.cjs [--preflight] [--project <path>]; no install or adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node for rendered QA; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('C care route preflight passed: '+JSON.stringify(p.counts));
  console.log('Arcade-point-to-bed rectangle study; inward street door, no-leaf care passage, three independent closed controls. Not adopted; fire, actual clear and wheelchair approval unknown.');
  if(o.preflight){console.log('Files only; no browser or professional approval.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-care-route-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated C care route browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('This session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. No adoption, wheelchair, fengshui, fire, legal or rescue approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={mobileCases,routeSpecs,inspectRoutes,preflight,pageCheckSource,makeBrowserScript,validateReport,findReport,runQa};
