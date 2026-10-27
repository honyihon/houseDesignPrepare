// Files-only checks here; rendered QA is a single owner-run Windows session.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const bath=require('./check_c_care_bath_playwright.cjs'),route=require('./check_c_care_route_playwright.cjs'),entry=require('./check_c_care_entry_playwright.cjs');
const basis=require('./check_current_design_playwright.cjs'),legacy=require('./check_windows_playwright.cjs');
const DIR='structured/candidates/c-care-bath-door',INDEX=DIR+'.html',VIEWER=DIR+'-3d.html',REPORT=DIR+'/review.json',MARKER='house-c-care-bath-door-qa';
const doorSpecs=s=>s.plans.floors[0].rooms.flatMap(r=>(r.features.care_door_parts||[]).map(p=>({...p,room:r.id})));
function inspectOptionLabel(raw,spec){
  const e=raw.optionLabelEvidence,label={'single-control':'單片控制','two-panel':'兩片新案'}[spec.option];
  const state={open:'門組全開',half:'半開不可通行',closed:'關門不可通行'}[spec.use];
  if(!label||!state||!e||e.revision!==2||e.option!==spec.option||e.use!==spec.use)throw Error('Missing current door option identity evidence');
  for(const key of ['heading','badge']){
    const item=e[key],r=item?.rect,v=raw.viewport;
    if(!item||item.option!==spec.option||item.visible!==true||typeof item.text!=='string'||!item.text.includes(label)||
       item.text.includes(spec.option==='two-panel'?'單片控制':'兩片新案')||!r||!v||
       ['left','right','top','bottom'].some(k=>!Number.isFinite(r[k]))||r.right<=r.left||r.bottom<=r.top||
       r.left<-.5||r.top<-.5||r.right>v.width+.5||r.bottom>v.height+.5)throw Error('Door option label hidden, wrong or clipped: '+key);
  }
  if(![state,'未採用','濕地分時','照護救援未核'].every(s=>e.badge.text.includes(s)))throw Error('Door state or approval warning missing from visible badge');
  return e;
}
function preflight(project){
  const parent=bath.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(study.schema!=='house-c-care-bath-door-v1'||study.revision!==1||study.door_display_revision!==2||study.adopted!==false||study.status!=='discussion-only-not-adopted'||study.rendered_qa!=='not-run'||
     study.default_option!=='two-panel'||study.default_state!=='open'||Object.values(study.professional_status).some(v=>v!=='unknown')||
     !same(study.options.map(o=>o.id),['single-control','two-panel'])||!same(study.frame_mm,[6000,17630])||study.requirement_ledger.verified_requirements!==0)throw Error('Invalid independent door scope or approval');
  const files=[INDEX,VIEWER,REPORT,DIR+'/requirement-ledger.json',DIR+'/track-section.svg','scripts/check_c_care_bath_door_playwright.cjs'];
  if(!fs.readFileSync(path.join(project,DIR+'/track-section.svg'),'utf8').includes('width="840" height="320"'))throw Error('Missing bounded track section');
  basis.validateIndexWarning(fs.readFileSync(path.join(project,INDEX),'utf8').replaceAll('door-adoption-warning','basis-adoption-warning'));
  for(const [rel,digest] of Object.entries(study.source_hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').includes('..')||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe door source');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==digest)throw Error('Stale door source: '+rel);files.push(rel);
  }
  if(!same(JSON.parse(fs.readFileSync(path.join(project,DIR+'/requirement-ledger.json'),'utf8')),study.requirement_ledger))throw Error('Door ledger differs');
  const text=fs.readFileSync(path.join(project,VIEWER),'utf8'),payload=JSON.parse(text.match(/^\s*var DATA = (.+);\s*$/m)[1]).c_care_bath_door;
  if(!payload||!text.includes('careDoor:careDoorEvidence()')||!text.includes('doorSyncRoomTitle(mesh,name);')||!text.includes('doorLabelBadge(badge,studyChoice,useChoice);')||text.includes('DATA.source.c_care_bath;')||!same(payload.options.map(o=>o.id),study.options.map(o=>o.id)))throw Error('Mixed/missing door viewer');
  const counts={options:0,states:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    if(o.building!=='C'||o.adopted!==false||!same(o.states.map(s=>s.id),['open','half','closed']))throw Error('Invalid independent door states');
    for(const s of o.states){
      const model=payload.options.find(p=>p.id===o.id)?.states.find(p=>p.id===s.id)?.model;
      if(!model||model.buildings.length!==1||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Door snapshot/review differs');
      for(const f of s.plans.floors){
        const cells=model.buildings[0].floors.find(v=>v.id===f.id).cells.filter(c=>c.tour_active);
        if(cells.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Door study changed floor or frame');
        for(const r of f.rooms){const c=cells.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||r.furniture.some(i=>!same(i,{...c.furniture.find(p=>p.id===i.id),placement:c.furniture_placements.tour_mm[i.id]})))throw Error('Door HTML/3D furniture/aperture parity differs');}
        const file=DIR+'/'+f.plan_file,svg=fs.readFileSync(path.join(project,file),'utf8');files.push(file);
        if(!svg.includes('width="660"')||!svg.includes('data-door-option="'+o.id+'"')||!svg.includes('data-use-state="'+s.id+'"'))throw Error('Missing bounded door SVG');
        if(f.id==='floor-1'){
          for(const spec of entry.leafSpecs(s))if(!svg.includes('data-care-leaf-id="'+spec.id+'" data-leaf-state="'+spec.state+'"'))throw Error('SVG leaf differs');
          for(const spec of doorSpecs(s))if(!svg.includes('data-door-part="'+spec.id+'" data-leaf-state="'+spec.state+'"'))throw Error('SVG door hardware differs');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const file=DIR+'/'+o.id+'_'+s.id+'_detail.svg';files.push(file);if(!fs.readFileSync(path.join(project,file),'utf8').includes('width="780"'))throw Error('Missing bounded door detail');
      const d=s.review.door;
      if(d.professional_acceptance!=='unknown'||d.selected_product!==null||d.actual_product_clear_mm!==null||d.required_clear_mm!==900||
         d.turn_coordinate_failures.length||d.transfer_coordinate_failures.length||d.rescue_board_rotation_failures.length||d.upstream_routes['arcade-to-bed'].coordinate_failures.length||
         d.effective_width_assumption_mm!==(s.id==='open'?970:s.id==='closed'?0:o.id==='two-panel'?485:470)||
         d.rear_parking_after_20mm_stop_mm!==(o.id==='two-panel'?350:-20)||
         (o.id==='two-panel'?d.sweep_vs_fixed_conflicts.length||!d.original_turn_position_door_conflicts.length:!d.sweep_vs_fixed_conflicts.length)||
         Object.values(d.routes).some(r=>s.id==='open'?r.coordinate_failures.length:!r.coordinate_failures.length))throw Error('Door negative controls, parking or motion differs');
      counts.states++;
    }counts.options++;
  }
  return {study,counts,closeupCases:bath.mobileCases(study),mainCounts:parent.mainCounts,cli:parent.cli,sourceFiles:[...new Set([...parent.sourceFiles,...files])]};
}
function replaceExact(text,old,value){if(text.split(old).length!==2)throw Error('Door QA anchor changed: '+old);return text.replace(old,value);}
function pageCheckSource(){
  let text=bath.pageCheckSource().replaceAll('c-care-bath','c-care-bath-door').replaceAll('c-bath-refined','two-panel').replaceAll('c-bath-control','single-control')
    .replaceAll('bath-adoption-warning','door-adoption-warning').replaceAll('C孝親套衛','C套衛門組');
  text=replaceExact(text,"ready('two-panel','transfer')","ready('two-panel','open')");
  text=replaceExact(text,"ready('single-control','baseline')","ready('single-control','open')");
  text=replaceExact(text,'inspectAccessories,accessoryBounds)','inspectAccessories,accessoryBounds,inspectOptionLabel)');
  const identity=`(function(){
    const read=id=>{const el=document.getElementById(id),r=el?.getBoundingClientRect(),s=el&&getComputedStyle(el);
      return {option:el?.dataset.doorOption,text:el?.innerText||'',visible:!!el&&!!el.getClientRects().length&&s.display!=='none'&&s.visibility!=='hidden',
        rect:r?{left:r.left,right:r.right,top:r.top,bottom:r.bottom}:null};};
    return {revision:Number(document.body.dataset.doorDisplayRevision),option:document.body.dataset.studyOption,use:document.body.dataset.studyUse,
      heading:read('stage-title'),badge:read('study-stage-note')};
  })()`;
  text=replaceExact(text,'items:f.selectedItems};','items:f.selectedItems,optionLabelEvidence:'+identity+'};');
  text=replaceExact(text,'mobileEvidence[index]=inspectMobileView(raw,spec);','inspectOptionLabel(raw,spec);mobileEvidence[index]=inspectMobileView(raw,spec);');
  text=replaceExact(text,"(await page.title()).includes(o.label)","(await page.title()).includes(o.label)&&(await page.locator('#study-stage-note').innerText()).includes(o.id==='two-panel'?'兩片新案':'單片控制')");
  text=replaceExact(text,'accessoryEvidence=[],counts=','accessoryEvidence=[],doorEvidence=[],counts=');
  text=replaceExact(text,"(o.id==='two-panel'?8:0)",'8');
  const anchor='accessoryEvidence.push({option:o.id,use:s.id,components:inspectAccessories(d.careBath,accessories)});';
  text=replaceExact(text,anchor,anchor+'const hardware=s.plans.floors[0].rooms.flatMap(r=>(r.features.care_door_parts||[]).map(p=>({...p,room:r.id})));doorEvidence.push({option:o.id,use:s.id,components:inspectAccessories(d.careDoor,hardware)});');
  // Door equipment shares the same accessible list with the eight bath parts.
  text=replaceExact(text,"await page.locator('#bath-equipment-list [data-bath-component]').count()===8", "await page.locator('#bath-equipment-list [data-bath-component]').count()===8+(o.id==='two-panel'?2:1)");
  if(text.split('routeEvidence,accessoryEvidence}').length!==3)throw Error('Missing door result evidence anchors');
  if(text.split('bathDisplayRevision:2,status:').length!==3)throw Error('Missing door display revision anchors');
  return text.replaceAll('routeEvidence,accessoryEvidence}','routeEvidence,accessoryEvidence,doorEvidence}')
    .replaceAll('bathDisplayRevision:2,status:','bathDisplayRevision:2,doorDisplayRevision:2,status:');
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => (${pageCheckSource()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${basis.inspectMobileView.toString()}),(${entry.inspectLeaves.toString()}),(${route.inspectRoutes.toString()}),(${bath.inspectAccessories.toString()}),(${bath.accessoryBounds.toString()}),(${inspectOptionLabel.toString()}))`;}
function validateReport(r,p){
  if(!r||r.marker!==MARKER)throw Error('No current door QA result');
  bath.validateReport({...r,marker:'house-c-care-bath-qa'},p);
  if(r.status==='passed'){
    if(r.doorDisplayRevision!==2)throw Error('Old door display result cannot cover current option labels');
    for(const evidence of r.mobileEvidence){const spec=p.closeupCases.find(c=>c.option===evidence.option&&c.use===evidence.use);inspectOptionLabel(evidence,spec);}
    if(!Array.isArray(r.doorEvidence)||r.doorEvidence.length!==p.counts.states)throw Error('Missing actual door hardware meshes');
    const seen=new Set();for(const e of r.doorEvidence){const s=p.study.options.find(o=>o.id===e.option)?.states.find(s=>s.id===e.use),key=e.option+'/'+e.use;
      if(!s||seen.has(key))throw Error('Unknown/duplicate door hardware evidence');seen.add(key);bath.inspectAccessories(e.components,doorSpecs(s));}
  }return r;
}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function runQa(o,p,output,execute=spawnSync){
  const session='house-c-bath-door-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
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
function main(){const o=legacy.parseArguments(process.argv.slice(2));if(o.help){console.log('node scripts/check_c_care_bath_door_playwright.cjs [--preflight]; no install or adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Owner-run native Windows Node only; --preflight is files only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('C bath door preflight passed: '+JSON.stringify(p.counts));
  console.log('Single control vs two-panel rear stack; proposed aperture +200mm, same 900mm target. Full/half/closed states; not adopted or product/care approved.');
  console.log('Door display revision: 2; visible single/two-panel labels in stage title and badge. Layouts unchanged.');
  if(o.preflight){console.log('Files only; no browser launched.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-c-bath-door-cli-'));console.log('QA output folder: '+output);const r=runQa(o,p,output);
  console.log('Automated C bath door browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('This session cleanup unconfirmed; no other browser targeted.');
  console.log('Screenshots need visual review. No adoption, product, care, fire or rescue approval.');if(r.status!=='passed')process.exitCode=1;}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={doorSpecs,inspectOptionLabel,preflight,pageCheckSource,makeBrowserScript,validateReport,findReport,runQa};
