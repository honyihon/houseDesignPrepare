// Files/math only in WSL. Rendered QA is one owner-run native Windows session.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const door=require('./check_c_care_bath_door_playwright.cjs'),bath=require('./check_c_care_bath_playwright.cjs');
const route=require('./check_c_care_route_playwright.cjs'),entry=require('./check_c_care_entry_playwright.cjs');
const basis=require('./check_current_design_playwright.cjs'),legacy=require('./check_windows_playwright.cjs');
const DIR='structured/candidates/c-care-bath-layout',INDEX=DIR+'.html',VIEWER=DIR+'-3d.html',REPORT=DIR+'/review.json',MARKER='house-c-care-bath-layout-qa';

function inspectOptionLabel(raw,spec){
  const e=raw.optionLabelEvidence,label={'door-control':'原門組','side-basin':'側盆比較'}[spec.option];
  const state={open:'門組全開',half:'半開不可通行',closed:'關門不可通行'}[spec.use];
  if(!label||!state||!e||e.revision!==1||e.option!==spec.option||e.use!==spec.use)throw Error('Missing independent bath-layout option identity');
  for(const key of ['heading','badge']){
    const item=e[key],r=item?.rect,v=raw.viewport;
    if(!item||item.option!==spec.option||item.visible!==true||typeof item.text!=='string'||!item.text.includes(label)||
      item.text.includes(spec.option==='side-basin'?'原門組':'側盆比較')||!r||!v||
      ['left','right','top','bottom'].some(k=>!Number.isFinite(r[k]))||r.right<=r.left||r.bottom<=r.top||
      r.left<-.5||r.top<-.5||r.right>v.width+.5||r.bottom>v.height+.5)throw Error('Bath-layout label hidden, wrong or clipped: '+key);
  }
  if(![state,'未採用','濕地分時','照護救援未核'].every(s=>e.badge.text.includes(s)))throw Error('Bath-layout state/warning missing');
  return e;
}

function preflight(project){
  const parent=door.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-c-care-bath-layout-v1'||study.revision!==1||study.layout_display_revision!==1||study.bath_display_revision!==2||
    study.adopted!==false||study.status!=='discussion-only-not-adopted'||study.rendered_qa!=='not-run'||
    study.default_option!=='side-basin'||study.default_state!=='open'||Object.values(study.professional_status).some(v=>v!=='unknown')||
    !same(study.frame_mm,[6000,17630])||!same(study.options.map(o=>o.id),['door-control','side-basin'])||
    study.requirement_ledger.canonical_requirements!==66||study.requirement_ledger.scenario_rows!==40||study.requirement_ledger.verified_requirements!==0||
    study.base_report_hash!==parent.study.report_hash)throw Error('Invalid independent layout scope, frozen parent or approval');
  const files=[INDEX,VIEWER,REPORT,DIR+'/requirement-ledger.json','scripts/check_c_care_bath_layout_playwright.cjs'];
  basis.validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8').replaceAll('layout-adoption-warning','basis-adoption-warning'));
  for(const [rel,digest] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe layout source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale layout source: '+rel);files.push(rel);
  }
  if(!same(JSON.parse(fs.readFileSync(path.join(project,DIR+'/requirement-ledger.json'),'utf8')),study.requirement_ledger))throw Error('Layout ledger differs');
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),payload=JSON.parse(text.match(/^\s*var DATA = (.+);\s*$/m)[1]).c_care_bath_layout;
  if(!payload||payload.default_option!=='side-basin'||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id))||
    !text.includes('layoutSyncRoomTitle(mesh,name);')||!text.includes('layoutLabelBadge(badge,studyChoice,useChoice);')||
    !text.includes('careDoor:careDoorEvidence()')||!text.includes('DATA.source.c_care_bath_layout')||text.includes('DATA.source.c_care_bath_door'))throw Error('Mixed/missing independent layout viewer');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(o.building!=='C'||o.adopted!==false||!same(o.states.map(s=>s.id),['open','half','closed']))throw Error('Invalid independent layout states');
    for(const s of o.states){
      const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Layout snapshot/review differs');
      for(const f of s.plans.floors){
        const cells=model.buildings[0].floors.find(v=>v.id===f.id).cells.filter(c=>c.tour_active);
        if(cells.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Layout floor/frame changed');
        for(const r of f.rooms){const c=cells.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||
            r.furniture.some(i=>!same(i,{...c.furniture.find(p=>p.id===i.id),placement:c.furniture_placements.tour_mm[i.id]})))throw Error('Layout HTML/3D furniture, aperture or accessory differs');}
        const file=DIR+'/'+f.plan_file,svg=fs.readFileSync(path.join(project,file),'utf8');files.push(file);
        if(!svg.includes('width="660"')||!svg.includes('data-layout-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"')||svg.includes('c-care-bath-door-3d.html'))throw Error('Missing bounded same-source layout SVG');
        if(f.id==='floor-1'){
          for(const spec of entry.leafSpecs(s))if(!svg.includes('data-care-leaf-id="'+spec.id+'" data-leaf-state="'+spec.state+'"'))throw Error('Layout SVG leaf differs');
          for(const spec of door.doorSpecs(s))if(!svg.includes('data-door-part="'+spec.id+'" data-leaf-state="'+spec.state+'"'))throw Error('Layout SVG door part differs');
          for(const spec of bath.accessorySpecs(s))if(!svg.includes('data-bath-component="'+spec.id+'" data-leaf-state="'+spec.state+'"'))throw Error('Layout SVG bath component differs');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const detail=DIR+'/'+o.id+'_'+s.id+'_detail.svg';files.push(detail);if(!fs.readFileSync(path.join(project,detail),'utf8').includes('width="780"'))throw Error('Missing bounded layout detail');
      const d=s.review.layout,side=o.id==='side-basin',m=d.critical_margins_mm;
      if(d.professional_acceptance!=='unknown'||d.actual_product_clear_mm!==null||d.required_clear_mm!==900||d.selected_product!==null||
        d.construction_release!==false||d.seated_tap_reach!=='unknown'||d.centered_basin_arrival_demonstrated!==false||d.knee_clearance_credit_mm!==0||d.independent_dry_turn_floor!==false||
        d.simultaneous_basin_and_toilet_transfer!==false||d.vanity_operation_fixed_conflicts.length||d.hardware_sweep_conflicts.length||
        d.turn_coordinate_failures.length||d.transfer_coordinate_failures.length||d.rescue_board_rotation_failures.length||d.sweep_vs_fixed_conflicts.length||
        !same([m.vanity_final_arrival,m.transfer_to_vanity,m.board_turn_to_folded_seat],side?[50,165,58.5]:[0,15,8.5])||
        d.rear_parking_after_20mm_stop_mm!==(side?200:350)||d.basin_arrival_lateral_offset_mm!==(side?250:160)||
        d.basin_operation_transfer_overlap_sqm!==(side?.2675:0)||d.door_center_y_mm!==(side?15175:15025)||
        d.effective_width_assumption_mm!==({open:970,half:485,closed:0}[s.id])||
        d.upstream_routes['arcade-to-bed'].coordinate_failures.length||
        Object.values(d.routes).some(r=>s.id==='open'?r.coordinate_failures.length:!r.coordinate_failures.length))throw Error('Layout margins, oriented approach or negative controls differ');
      if(s.plans.floors.flatMap(f=>f.rooms.flatMap(r=>r.furniture.filter(i=>i.catalog_id==='washer').map(()=>f.id))).join(',')!=='floor-2')throw Error('Retain one existing 2F washer');
      counts.states++;
    }counts.options++;
  }
  return {study,counts,closeupCases:bath.mobileCases(study),mainCounts:parent.mainCounts,cli:parent.cli,sourceFiles:[...new Set([...parent.sourceFiles,...files])]};
}

function replaceExact(text,old,value){if(text.split(old).length!==2)throw Error('Layout QA anchor changed: '+old);return text.replace(old,value);}
function pageCheckSource(){
  let text=door.pageCheckSource().replaceAll('c-care-bath-door','c-care-bath-layout').replaceAll('two-panel','side-basin').replaceAll('single-control','door-control')
    .replaceAll('door-adoption-warning','layout-adoption-warning').replaceAll('C套衛門組','C套衛餘量')
    .replaceAll('兩片新案','側盆比較').replaceAll('單片控制','原門組')
    .replaceAll('dataset.doorOption','dataset.layoutOption').replaceAll('dataset.doorDisplayRevision','dataset.layoutDisplayRevision')
    .replaceAll('doorDisplayRevision:2','layoutDisplayRevision:1');
  text=replaceExact(text,"8+(o.id==='side-basin'?2:1)",'10');
  text=replaceExact(text,"Math.abs(b.center[1]-i.placement.center_y_mm)<.05", "Math.abs(b.center[1]-i.placement.center_y_mm)<.05&&Math.abs(b.rotation-i.placement.rotation_deg)<.05");
  return text;
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${pageCheckSource()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${basis.inspectMobileView.toString()}),(${entry.inspectLeaves.toString()}),(${route.inspectRoutes.toString()}),(${bath.inspectAccessories.toString()}),(${bath.accessoryBounds.toString()}),(${inspectOptionLabel.toString()}))`;}
function validateReport(r,p){
  if(!r||r.marker!==MARKER)throw Error('No current independent bath-layout result');
  bath.validateReport({...r,marker:'house-c-care-bath-qa'},p);
  if(r.status==='passed'){
    if(r.layoutDisplayRevision!==1)throw Error('Old display result cannot cover current layout');
    for(const e of r.mobileEvidence)inspectOptionLabel(e,p.closeupCases.find(c=>c.option===e.option&&c.use===e.use));
    if(!Array.isArray(r.doorEvidence)||r.doorEvidence.length!==p.counts.states)throw Error('Missing actual layout door-part meshes');
    const seen=new Set();for(const e of r.doorEvidence){const s=p.study.options.find(o=>o.id===e.option)?.states.find(s=>s.id===e.use),key=e.option+'/'+e.use;
      if(!s||seen.has(key))throw Error('Unknown/duplicate layout hardware state');seen.add(key);bath.inspectAccessories(e.components,door.doorSpecs(s));}
  }return r;
}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function runQa(o,p,output,execute=spawnSync){
  const session='house-c-bath-layout-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
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
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_c_care_bath_layout_playwright.cjs [--preflight]; no install, adoption or parent writes.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Owner-run native Windows Node only; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('C bath layout preflight passed: '+JSON.stringify(p.counts));
  console.log('Frozen two-panel control vs left-wall basin/another 150mm door shift. Margins 0/15/8.5 -> 50/165/58.5mm; rear spare 350 -> 200mm.');
  console.log('Offset basin arrival 250mm, original 700mm operation and toilet transfer sequential. Full/half/closed; not adopted, products/reach/care unknown.');
  if(o.preflight){console.log('Files only; no browser launched.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-bath-layout-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated C bath layout browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('Session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. No adoption, product, seated-reach, care, religious, fire or rescue approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={inspectOptionLabel,preflight,pageCheckSource,makeBrowserScript,validateReport,findReport,runQa};
