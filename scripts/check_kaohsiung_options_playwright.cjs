// Native Windows browser QA is owner-run; --preflight never launches a browser.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const INDEX='structured/candidates/kaohsiung-house-options.html',VIEWER='structured/candidates/kaohsiung-house-options-3d.html';
const REPORT='structured/candidates/kaohsiung-house-options/review.json',MARKER='house-kaohsiung-options-qa';
function canonical(v){
  if(Array.isArray(v))return v.map(canonical);
  if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));
  return v;
}
function hash(v){return crypto.createHash('sha256').update(typeof v==='string'||Buffer.isBuffer(v)?v:JSON.stringify(canonical(v))).digest('hex');}
function publicFile(project,rel){
  if(typeof rel!=='string'||! /^(inputs|structured|assets|scripts|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').some(p=>p.startsWith('.')||p.toLowerCase()==='private'))throw Error('Unsafe public source path');
  const target=path.resolve(project,...rel.split('/')),real=fs.realpathSync(target),relative=path.relative(fs.realpathSync(project),real);
  if(relative.startsWith('..')||path.isAbsolute(relative)||relative.split(path.sep).some(p=>p.startsWith('.')||p.toLowerCase()==='private'))throw Error('Source leaves public project');
  return target;
}
function inspectZones(e,zone,room,option,use){
  if(!e||e.revision!==1||e.option!==option||e.use!==use||e.adopted!==false||e.legalAndStructuralApproval!=='unknown'||e.soilDepthMm!==null||!Array.isArray(e.parts))throw Error('Incomplete independent zone evidence');
  const visible=e.parts.filter(p=>p.visible);
  if(!zone){if(visible.length)throw Error('Control has unexpected garden meshes');return;}
  const target=visible.filter(p=>p.room===room);
  if(visible.length!==1+zone.soil_rects_mm.length+2*zone.woody_points_mm.length||target.length!==visible.length)throw Error('Missing or unexpected visible real garden parts');
  const expected=[{id:'garden',rect:zone.garden_mm},...zone.soil_rects_mm.map((r,n)=>({id:'soil-'+n,rect:r}))];
  for(const x of expected){
    const matches=target.filter(p=>p.id===x.id);if(matches.length!==1||!same(matches[0].rect_mm,x.rect))throw Error('Garden/soil mesh source differs');
    const p=matches[0];
    if(x.id==='garden'){
      const [a,b,w,h]=x.rect,corners=[[a,b],[a+w,b],[a+w,b+h],[a,b+h],[a,b]];
      if(!Array.isArray(p.actualLinePointsMm)||p.actualLinePointsMm.length!==5||p.actualLinePointsMm.some((point,n)=>!Array.isArray(point)||point.length!==2||point.some((v,k)=>!Number.isFinite(v)||Math.abs(v-corners[n][k])>.1)))throw Error('Actual garden outline differs from plan');
    }
    if(x.id!=='garden'&&(!p.actualGeometry||Math.abs(p.actualGeometry.widthMm-x.rect[2])>.1||Math.abs(p.actualGeometry.depthMm-x.rect[3])>.1||
      !Array.isArray(p.actualCenterMm)||Math.abs(p.actualCenterMm[0]-x.rect[0]-x.rect[2]/2)>.1||Math.abs(p.actualCenterMm[1]-x.rect[1]-x.rect[3]/2)>.1))throw Error('Actual soil geometry differs from plan');
  }
  for(let n=0;n<zone.woody_points_mm.length;n++)for(const prefix of ['trunk-','woody-'])if(target.filter(p=>p.id===prefix+n).length!==1)throw Error('Missing symbolic woody plant mesh');
}
function inspectEquipment(e,c){
  if(!e||e.displayRevision!==2||e.option!==c.option||e.use!==c.use||e.room!==c.room||e.panelOpen!==true||
    !e.box||![e.box.width,e.box.height].every(v=>Number.isFinite(v)&&v>0)||!Array.isArray(e.rows)||
    e.rows.length!==c.equipmentIds.length||new Set(e.rows.map(r=>r.id)).size!==e.rows.length||
    c.equipmentIds.some(id=>!e.rows.some(r=>r.id===id&&typeof r.text==='string'&&r.text.trim().length>0)))throw Error('Incomplete visible equipment readout');
  for(const u of c.hvac){
    const row=e.rows.find(r=>r.id==='hvac-'+u.type+'-'+u.id);
    if(!row?.text.includes(u.id)||!row.text.includes(u.width_mm+'×'+u.depth_mm+'×'+u.height_mm))throw Error('Equipment readout omits real unit identity/dimensions');
  }
  if(c.zone){
    const area=c.zone.garden_mm[2]*c.zone.garden_mm[3]/1e6;
    if(!e.rows.find(r=>r.id==='garden').text.includes(String(area))||
      !e.rows.find(r=>r.id==='woody').text.includes(c.zone.woody_points_mm.length+'株')||
      !e.rows.find(r=>r.id==='soil').text.includes('未核'))throw Error('Incomplete landscape readout');
  }
}
function preflight(project){
  if(fs.existsSync(path.join(project,'structured/candidates/kaohsiung-house-options/c-stair-integration.json')))return require('./check_c_stair_merged_playwright.cjs').preflight(project);
  return preflightOriginal(project);
}
function preflightOriginal(project){
  const report=JSON.parse(fs.readFileSync(path.join(project,REPORT),'utf8'));
  if(report.schema!=='house-kaohsiung-options-v1'||report.status!=='comparison-only-not-adopted'||report.revision!==1||report.display_revision!==2||report.adopted!==false||report.rendered_qa!=='not-run'||
    !same(report.frame_mm,[6000,17630])||report.default_option!=='c-split'||!same(report.options.map(o=>o.id),['a-rear-study','b-rear-split','b-front-split','c-control','c-split'])||
    Object.values(report.professional_status).some(v=>v!=='unknown')||!report.source_hashes||!report.artifact_hashes)throw Error('Invalid independent discussion package');
  const files=[REPORT,'scripts/check_kaohsiung_options_playwright.cjs','scripts/check_current_design_playwright.cjs','scripts/check_windows_playwright.cjs'];
  for(const [rel,digest]of Object.entries({...report.source_hashes,...report.artifact_hashes})){
    if(!/^[a-f0-9]{64}$/.test(digest)||hash(fs.readFileSync(publicFile(project,rel)))!==digest)throw Error('Changed study source/artifact: '+rel);files.push(rel);
  }
  const source=fs.readFileSync(path.join(project,VIEWER),'utf8'),match=source.match(/^\s*var DATA = (.+);\s*$/m);
  const payload=match&&JSON.parse(match[1]).kaohsiung_options;
  if(!payload||payload.display_revision!==2||!same(payload.options.map(o=>o.id),report.options.map(o=>o.id))||!source.includes('khBuildZones(mesh,group,base,features);')||!source.includes('kaohsiung:khEvidence()')||!source.includes('if(mesh){khAppendEquipmentReadout(list,mesh.userData.cell,featuresOf(mesh.userData.cell));}'))throw Error('Missing local viewer adapter');
  if(payload.report_hash!==report.report_hash||!same(payload.source_hashes,report.source_hashes)||!same(payload.cost_studies,report.cost_studies)||!same(payload.professional_status,report.professional_status))throw Error('Embedded snapshot metadata differs from report');
  const reconstructed=structuredClone(report);delete reconstructed.artifact_hashes;
  const counts={options:0,states:0,floors:0,rooms:0,items:0},cases=[];
  for(const o of reconstructed.options){
    const po=payload.options.find(x=>x.id===o.id);
    if(o.adopted!==false||!same(o.states.map(s=>s.id),o.building==='B'?['daily','ritual','carry']:['daily']))throw Error('Missing independent use states');
    for(const s of o.states){
      const state=po.states.find(x=>x.id===s.id),model=state?.model;s.model=model;
      if(!model||model.buildings.length!==1||model.buildings[0].id!==o.building||model.bc_option.id!==o.id||model.bc_option.use_state!==s.id||!same(model.bc_option.geometry_review,s.review))throw Error('Mixed model/state review');
      for(const f of s.plans.floors){
        const mf=model.buildings[0].floors.find(x=>x.id===f.id),active=mf.cells.filter(c=>c.tour_active);
        if(active.length!==f.rooms.length||mf.base_mm!==f.base_mm||mf.height_mm!==f.height_mm||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Mixed or expanded floor');
        for(const r of f.rooms){
          const c=active.find(c=>c.id===r.id);
          if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||!same(c.furniture.map(i=>({...i,placement:c.furniture_placements.tour_mm[i.id]})),r.furniture))throw Error('HTML/3D room/furniture mismatch');
        }
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      const f=s.plans.floors.find(f=>f.id==='floor-2'),room=f.rooms.find(r=>r.key===(o.building==='C'?'balcony2f':'balcony2'));
      const zone=room.features.kaohsiung_zones||null,hvac=room.features.hvac_units||[];
      cases.push({option:o.id,use:s.id,building:o.building,room:room.id,zone,hvac,
        equipmentIds:[...(!room.furniture.length?['empty-furniture']:[]),...(zone?['garden','soil','woody']:[]),...hvac.map(u=>'hvac-'+u.type+'-'+u.id)]});
      counts.states++;
    }
    counts.options++;
  }
  const index=fs.readFileSync(path.join(project,INDEX),'utf8');
  if((index.match(/id="kh-adoption-warning"/g)||[]).length!==1||!index.includes('未採用／專業未核'))throw Error('Missing visible discussion warning');
  return {study:report,counts,cases,sourceFiles:[...new Set(files)],cli:path.join(project,'node_modules','playwright','cli.js')};
}
async function checkPages(page,base,output,study,expected,cases,inspectZones,inspectEquipment){
  const checks=[],screenshots=[],messages=[],zoneEvidence=[],equipmentEvidence=[],counts={options:0,states:0,floors:0,rooms:0,items:0};
  const assert=(ok,name)=>{checks.push({name,passed:Boolean(ok)});if(!ok)throw Error(name);};
  const capture=async name=>{const p=output+'/'+name;await page.screenshot({path:p,fullPage:false});screenshots.push(p);};
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['warning','error'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  const ready=async(o,s,f)=>page.waitForFunction(([o,s,f])=>document.body.dataset.studyOption===o&&document.body.dataset.studyUse===s&&window.__htmlModel3dDebug?.().state.floor===f&&window.__htmlModel3dDebug().cameraFraming.ready,[o,s,f]);
  const warning=async()=>{
    const w=page.locator('#kh-adoption-warning'),box=await w.boundingBox(),v=page.viewportSize();
    assert(await w.isVisible()&&(await w.innerText()).includes('未採用')&&box&&box.x>=0&&box.y>=0&&box.x+box.width<=v.width+1&&box.y+box.height<=v.height+1,'Visible first-viewport non-adoption warning');
  };
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/kaohsiung-house-options.html');
    assert((await page.title()).includes('高雄厝')&&await page.locator('section[data-option]').count()===5,'Nonblank five-option index');await warning();await capture('index-desktop.png');
    await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html');await ready('c-split','daily','floor-2');
    await page.locator('#study-scheme').selectOption('c-control');await ready('c-control','daily','floor-2');
    assert((await page.evaluate(()=>window.__htmlModel3dDebug())).kaohsiung.parts.filter(p=>p.visible).length===0,'Switching to control removes candidate garden');
    await page.locator('#study-scheme').selectOption('c-split');await ready('c-split','daily','floor-2');
    for(const o of study.options){
      for(const s of o.states){
        await page.setViewportSize({width:1440,height:900});
        await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building='+o.building+'&floor=floor-2&view=plan');await ready(o.id,s.id,'floor-2');
        assert((await page.locator('#study-stage-note').innerText()).includes('未採用')&&await page.locator('#study-plan-link').getAttribute('href')==='kaohsiung-house-options.html#'+o.id+'-'+s.id,'Correct independent state warning and return link '+o.id+'/'+s.id);
        const c=cases.find(c=>c.option===o.id&&c.use===s.id);
        let d=await page.evaluate(()=>window.__htmlModel3dDebug());inspectZones(d.kaohsiung,c.zone,c.room,o.id,s.id);zoneEvidence.push(d.kaohsiung);
        await capture(o.id+'-'+s.id+'-desktop.png');
        for(const f of s.plans.floors){
          await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();await ready(o.id,s.id,f.id);
          d=await page.evaluate(()=>window.__htmlModel3dDebug());
          assert(d.visibleRooms.length===f.rooms.length&&d.state.building===o.building,'Complete independent floor '+o.id+'/'+s.id+'/'+f.id);
          for(const r of f.rooms){
            const actual=d.tour.rooms.find(x=>x.id===r.id);
            assert(actual&&JSON.stringify(actual.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(actual.features)===JSON.stringify(r.features),'Room/door/window data matches '+r.id);
            for(const i of r.furniture){const p=d.furniture.shapes.find(x=>x.id===i.id);assert(p&&p.visible&&p.parts>0&&p.width===i.width_mm&&p.depth===i.depth_mm&&p.height===i.height_mm&&Math.abs(p.center[0]-i.placement.center_x_mm)<.1&&Math.abs(p.center[1]-i.placement.center_y_mm)<.1,'Actual full-size product '+i.id);}
          }
          counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
        }
        await page.setViewportSize({width:390,height:844});
        await page.goto(base+'structured/candidates/kaohsiung-house-options-3d.html?scheme='+o.id+'&use='+s.id+'#mode=tour&building='+o.building+'&floor=floor-2&room='+encodeURIComponent(c.room)+'&focus=room&view=plan');await ready(o.id,s.id,'floor-2');
        const toggle=page.locator('#mobile-panel-toggle');if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
        await page.waitForFunction(()=>window.__htmlModel3dDebug().roomCloseup&&window.__htmlModel3dDebug().currentDesignCamera?.lastDraw?.clipped===true);
        d=await page.evaluate(()=>window.__htmlModel3dDebug());inspectZones(d.kaohsiung,c.zone,c.room,o.id,s.id);zoneEvidence.push(d.kaohsiung);
        assert(d.visibleRooms.length===s.plans.floors[1].rooms.length,'Mobile closeup retains all rooms '+o.id+'/'+s.id);await capture(o.id+'-'+s.id+'-mobile.png');
        await page.locator('#b32-room-details').click();
        await page.locator('#kh-room-equipment').waitFor({state:'visible'});
        const equipment=await page.evaluate(()=>{
          const list=document.getElementById('kh-room-equipment'),box=list.getBoundingClientRect();
          return {displayRevision:Number(document.body.dataset.khDisplayRevision),option:document.body.dataset.studyOption,use:document.body.dataset.studyUse,
            room:list.getAttribute('data-room'),panelOpen:!document.getElementById('app').classList.contains('panel-collapsed'),
            box:{width:box.width,height:box.height},rows:[...list.querySelectorAll('[data-kh-equipment-id]')].map(r=>({id:r.getAttribute('data-kh-equipment-id'),text:r.textContent}))};
        });
        inspectEquipment(equipment,c);equipmentEvidence.push(equipment);
        assert(await page.locator('#furniture-list').isVisible(),'Accessible equipment and landscape list '+o.id+'/'+s.id);
        if(s.id==='daily'&&['a-rear-study','b-rear-split','c-control','c-split'].includes(o.id))await capture(o.id+'-'+s.id+'-equipment-mobile.png');
        await page.locator('#b32-details-back').click();
        await page.waitForFunction(room=>window.__htmlModel3dDebug().state.room===room&&window.__htmlModel3dDebug().roomCloseup&&window.__htmlModel3dDebug().currentDesignCamera?.lastDraw?.clipped===true,c.room);
        await page.locator('#room-overview').click();
        await page.waitForFunction(()=>!window.__htmlModel3dDebug().roomCloseup&&window.__htmlModel3dDebug().currentDesignCamera?.lastDraw?.clipped===false);
        counts.states++;
      }
      counts.options++;
    }
    await page.goto(base+'structured/candidates/kaohsiung-house-options.html');await warning();await capture('index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'All independent floors and use states checked');
    assert(!messages.some(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated')))),'No unexplained browser/console error');
    return {marker:'house-kaohsiung-options-qa',revision:2,displayRevision:2,status:'passed',counts,checks,screenshots,messages,zoneEvidence,equipmentEvidence};
  }catch(e){await capture('failure.png').catch(()=>{});return {marker:'house-kaohsiung-options-qa',revision:2,displayRevision:2,status:'failed',error:String(e),counts,checks,screenshots,messages,zoneEvidence,equipmentEvidence};}
}
function makeBrowserScript(base,output,study,counts,cases){return `async page => { const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b); return (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)},${JSON.stringify(cases)},(${inspectZones.toString()}),(${inspectEquipment.toString()})); }`;}
function findReport(value){
  if(value&&typeof value==='object'){if(value.marker===MARKER)return value;for(const v of Object.values(value)){const r=findReport(v);if(r)return r;}}
  else if(typeof value==='string'){try{return findReport(JSON.parse(value));}catch{}}
  return null;
}
function validateReport(r,counts,cases){
  if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw Error('No valid structured result');
  if(r.status==='passed'){
    if(r.revision!==2||r.displayRevision!==2||!same(r.counts,counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||r.screenshots?.length!==6+2*counts.states||r.zoneEvidence?.length!==2*counts.states||r.equipmentEvidence?.length!==counts.states)throw Error('Incomplete passing evidence');
    const previous=new Map();for(const e of r.zoneEvidence){const c=cases.find(c=>c.option===e.option&&c.use===e.use);if(!c)throw Error('Unexpected zone evidence');inspectZones(e,c.zone,c.room,c.option,c.use);previous.set(c.option+'/'+c.use,(previous.get(c.option+'/'+c.use)||0)+1);}
    if(cases.some(c=>previous.get(c.option+'/'+c.use)!==2))throw Error('Missing desktop/mobile zone evidence');
    const equipmentSeen=new Set();for(const e of r.equipmentEvidence){const c=cases.find(c=>c.option===e.option&&c.use===e.use);if(!c||equipmentSeen.has(e.option+'/'+e.use))throw Error('Missing or duplicated equipment evidence');inspectEquipment(e,c);equipmentSeen.add(e.option+'/'+e.use);}
    if(equipmentSeen.size!==cases.length)throw Error('Missing equipment evidence');
    for(const option of ['a-rear-study','b-rear-split','c-control','c-split'])if(!r.screenshots.some(p=>p.endsWith(option+'-daily-equipment-mobile.png')))throw Error('Missing equipment screenshot');
  }return r;
}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-kaohsiung-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  const code=makeBrowserScript(base,output,prepared.study,prepared.counts,prepared.cases);
  fs.writeFileSync(script,code);
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:12*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));if(required&&(r.error||r.status!==0))throw Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);if(response?.isError)throw Error('Playwright CLI failed; see checks.log');report=validateReport(findReport(response),prepared.counts,prepared.cases);if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Source changed during QA';}}
  catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}return report;
}
function main(){
  const options=legacy.parseArguments(process.argv.slice(2));if(options.help){console.log('node scripts/check_kaohsiung_options_playwright.cjs [--preflight] [--project <path>]');return;}
  if(fs.existsSync(path.join(options.project,'structured/candidates/kaohsiung-house-options/c-stair-integration.json')))return require('./check_c_stair_merged_playwright.cjs').main(options);
  if(!options.preflight&&process.platform!=='win32')throw Error('Rendered QA uses native Windows Node; --preflight is files only.');
  const prepared=preflight(options.project);console.log('Project: '+options.project);console.log('Kaohsiung options preflight passed: '+JSON.stringify(prepared.counts));console.log('Independent frozen-input comparison, not adopted; no legal/energy/soil/structure approval.');
  console.log('Kaohsiung display revision: 2; meaningful landscape/HVAC equipment lists; all layouts unchanged.');
  if(options.preflight){console.log('Files only; no browser launched.');return;}
  if(!fs.existsSync(prepared.cli))throw Error('Pinned Playwright CLI missing; no automatic installation attempted.');
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-kaohsiung-cli-'));console.log('QA output folder: '+output);const result=runQa(options,prepared,output);
  console.log('Automated Kaohsiung browser checks: '+result.status);console.log('Result: '+path.join(output,'result.json'));if(result.error)console.error(result.error);if(!result.sessionClosed)console.warn('This QA session cleanup is unconfirmed; no other browser was targeted.');console.log('Screenshots require visual review; no legal, care, religious, energy or construction approval.');if(result.status!=='passed')process.exitCode=1;
}
module.exports={canonical,hash,publicFile,inspectZones,inspectEquipment,preflight,preflightOriginal,checkPages,makeBrowserScript,findReport,validateReport,runQa};
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
