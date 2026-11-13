// File preflight is bounded. Browser/WebGL QA is reserved for the owner's Windows terminal.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{isDeepStrictEqual:same}=require('node:util');
const {rectsOverlap}=require('./templates/upper-floor-storage-viewer.js');
const ROOT=path.resolve(__dirname,'..'),OUT='structured/coordination/b-upper-storage-3d-v1';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function read(root,n){if(!/^[A-Za-z0-9_./-]+$/.test(n)||path.isAbsolute(n)||n.split('/').some(p=>p==='..'||p==='private'))throw Error('Unsafe public path');return fs.readFileSync(path.join(root,n));}
function validateReport(r,sync){
  if(r.schema!=='house-b-upper-storage-viewer-v1'||r.display_revision!==2||r.main_3d_changed!==false||r.adopted!==false||
     r.rendered_qa!=='not-run-owner-separate-terminal-required'||r.floors.length!==4||!same(r.entry_options,sync.entry_options))throw Error('B viewer scope differs');
  for(const f of r.floors){
    const original=sync.floors.find(v=>v.key===f.id);
    if(!same(f.source_floor,original)||f.states.length!==2||f.base_mm!==original.base_mm)throw Error('B whole-floor source differs');
    for(const state of f.states){
      const old=original.states.find(v=>v.id===state.id);
      if(!same(state.objects,old.objects)||!same(state.display_objects.map(o=>o.source),old.objects)||state.plan_file!==old.plan_file)throw Error('B object/state source differs');
    }
  }
  return r.summary;
}
function preflight(root){
  const r=JSON.parse(read(root,OUT+'/review.json')),m=JSON.parse(read(root,OUT+'/artifact-manifest.json'));
  const sync=JSON.parse(read(root,'structured/coordination/b-upper-storage-sync-v1/review.json'));
  const counts=validateReport(r,sync);
  if(hash(read(root,'structured/coordination/b-upper-storage-sync-v1/review.json'))!==r.source_sync_report_sha256||r.source_sync_report_hash!==sync.report_hash||m.report_hash!==r.report_hash)throw Error('Mixed B source report');
  for(const [n,h]of Object.entries(r.source_hashes))if(hash(read(root,n))!==h)throw Error('Stale B viewer source: '+n);
  for(const [n,h]of Object.entries(m.artifacts))if(hash(read(root,OUT+'/'+n))!==h)throw Error('Changed B viewer artifact: '+n);
  const archive=JSON.parse(read(root,OUT+'/archive-manifest.json'));
  if(archive.archive!=='b-upper-storage-3d.zip'||hash(read(root,OUT+'/'+archive.archive))!==archive.sha256)throw Error('B offline ZIP differs');
  const html=read(root,OUT+'/index.html').toString('utf8'),match=html.match(/<script id="b-upper-data" type="application\/json">([\s\S]+?)<\/script>/);
  if(!match||!same(JSON.parse(match[1]),r))throw Error('B embedded data differs');
  for(const p of r.plans)if(hash(read(root,OUT+'/'+p.file))!==p.sha256)throw Error('B plan source differs');
  return {report:r,counts};
}
function area(p){return Math.abs(p.reduce((a,v,i)=>{const w=p[(i+1)%p.length];return a+v[0]*w[1]-w[0]*v[1];},0))/2;}
function clipArea(triangle,r){
  let p=triangle;
  for(const [axis,value,sign]of [[0,r[0],1],[0,r[0]+r[2],-1],[1,r[1],1],[1,r[1]+r[3],-1]]){
    const out=[];
    for(let i=0;i<p.length;i++){
      const a=p[i],b=p[(i+1)%p.length],insideA=sign*(a[axis]-value)>=0,insideB=sign*(b[axis]-value)>=0;
      if(insideA)out.push(a);
      if(insideA!==insideB){const t=(value-a[axis])/(b[axis]-a[axis]);out.push([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]);}
    }
    p=out;if(!p.length)return 0;
  }
  return area(p);
}
function validateGeometry(ev,floor,state){
  const near=(a,b)=>Number.isFinite(a)&&Math.abs(a-b)<.3;
  if(!ev.ready||ev.webglLost||ev.floor!==floor.id||ev.state!==state.id||ev.lastDrawStamp!==ev.stamp)throw Error('B draw/state not ready');
  if(!Array.isArray(ev.surfaceTrianglesM)||!ev.surfaceTrianglesM.length||ev.surfaceTrianglesM.some(t=>t.length!==3||t.some(p=>p.length!==2||!p.every(Number.isFinite))))throw Error('Missing actual floor triangles');
  const total=ev.surfaceTrianglesM.reduce((v,t)=>v+area(t),0);
  if(Math.abs(total-floor.surface_area_mm2/1e6)>.0001)throw Error('Actual polygon floor area differs');
  for(const rect of floor.forbidden_rects_mm){
    const r=rect.map(v=>v/1000),over=ev.surfaceTrianglesM.reduce((v,t)=>v+clipArea(t,r),0);
    if(over>.000003)throw Error('Actual floor covers a tread or void');
  }
  if(ev.objects.length!==state.display_objects.length||ev.treads.length!==floor.stairs.length)throw Error('Missing or duplicate B objects/stairs');
  for(const item of state.display_objects){
    const body=ev.objects.find(i=>i.key===item.key),r=item.rect_mm,h=item.height_mm===null?12:item.height_mm;
    if(!body||!body.sizeMm.every((v,n)=>near(v,[r[2],h,r[3]][n]))||!body.minMm.every((v,n)=>near(v,[r[0],floor.base_mm+item.mount_mm,r[1]][n])))throw Error('Actual B body differs: '+item.key);
  }
  for(const step of floor.stairs){
    const body=ev.treads.find(t=>t.id===step.id),r=step.rect_mm;
    if(!body||!body.minMm.every((v,n)=>near(v,[r[0],step.top_mm-step.height_mm,r[1]][n]))||
       !body.maxMm.every((v,n)=>near(v,[r[0]+r[2],step.top_mm,r[1]+r[3]][n])))throw Error('Actual stair geometry differs');
  }
  return true;
}
function validateCabinet(ev,floor){
  const c=ev.cabinet,p=c?.projected,v=ev.canvas,b=c?.pixels,s=floor.source_floor.storage;
  if(!c||!same(c.rectMm,s.rect_mm)||!p||!p.inFront||![p.left,p.right,p.top,p.bottom,p.width,p.height].every(Number.isFinite)||
    p.left<0||p.top<0||p.right>v.clientWidth||p.bottom>v.clientHeight||p.width<55||p.height<60||p.width*p.height<5000)throw Error('B actual cabinet too small/clipped');
  if(!b||b.method!=='webgl-readPixels-cabinet-aabb'||!Number.isFinite(b.sampled)||!Number.isFinite(b.orange)||!Number.isFinite(b.ratio)||
     b.sampled<80||b.orange<60||b.orange>b.sampled||b.ratio<.08||Math.abs(b.ratio-b.orange/b.sampled)>1e-9)throw Error('B actual cabinet pixels missing');
  if(ev.labelsChecked){
    if(!ev.labelRects.some(l=>l.kind==='storage'))throw Error('B storage name missing');
    for(let i=0;i<ev.labelRects.length;i++){
      const l=ev.labelRects[i];
      if(![l.left,l.top,l.width,l.height,l.scrollWidth,l.clientWidth].every(Number.isFinite)||l.width<28||l.height>90||l.left<0||l.top<0||
        l.left+l.width>v.clientWidth||l.top+l.height>v.clientHeight||l.scrollWidth>l.clientWidth+1||rectsOverlap(l,p)||ev.labelRects.slice(i+1).some(o=>rectsOverlap(l,o)))throw Error('B names clipped/overlap/body covered');
    }
  }else if(ev.labelRects.length)throw Error('B names remained visible');
  return true;
}
function validateStairCaption(ev,requireVisible=false){
  const caption='二樓L形到達／一樓原梯接Q3上層改梯';
  if(!ev.sceneLabels?.some(l=>l.kind==='stair'&&l.text===caption)||
     ev.sceneLabels.some(l=>l.kind==='stair'&&l.text.includes('未改本體')))throw Error('B 2F stair caption describes the wrong revision');
  if(requireVisible){
    const l=ev.labelRects?.find(l=>l.kind==='stair'&&l.text===caption),v=ev.canvas;
    if(!l||![l.left,l.top,l.width,l.height,l.scrollWidth,l.clientWidth].every(Number.isFinite)||l.width<=0||l.height<=0||
       l.left<0||l.top<0||l.left+l.width>v.clientWidth||l.top+l.height>v.clientHeight||l.scrollWidth>l.clientWidth+1)
      throw Error('B 2F stair caption is not visibly readable in the interface view');
  }
  return true;
}
async function worker(root,output,channel){
  const expected=preflight(root).report,report={schema:'house-b-upper-storage-browser-qa-v1',display_revision:expected.display_revision,browser_channel:channel,status:'incomplete',report_hash:expected.report_hash,source_hashes:expected.source_hashes,
    checks:[],cases:[],screenshots:[],console_errors:[],closed:false};
  let browser,page;const assert=(v,name)=>{report.checks.push({name,passed:Boolean(v)});if(!v)throw Error(name);};
  const settle=async()=>{await page.evaluate(()=>{window.__B_READY_STAMP__=null;});await page.waitForFunction(()=>{const e=window.__B_UPPER_QA__?.(),old=window.__B_READY_STAMP__;window.__B_READY_STAMP__=e?.ready?e.stamp:null;return e?.ready&&old===e.stamp;},null,{polling:'raf'});};
  const capture=async name=>{const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);};
  try{
    const {chromium}=require(path.join(root,'node_modules/playwright'));browser=await chromium.launch({channel,headless:true});page=await browser.newPage();page.setDefaultTimeout(12000);
    page.on('pageerror',e=>report.console_errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.console_errors.push(m.text());});
    await page.goto(pathToFileURL(path.join(root,OUT,'index.html')).href,{waitUntil:'load'});await settle();
    assert(await page.title()==='B同版上層與收納3D比較'&&await page.locator('#warning').isVisible(),'Page identity and visible non-adoption warning');
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      await page.setViewportSize(viewport);
      for(const floor of expected.floors)for(const state of floor.states){
        report.active_case={floor:floor.id,state:state.id,viewport};
        await page.locator('#floor-select').selectOption(floor.id);await page.locator('#state-select').selectOption(state.id);await page.locator('#view-storage').click();await page.evaluate(()=>scrollTo(0,0));await settle();
        const ev=await page.evaluate(()=>window.__B_UPPER_QA__(true));report.active_case.initial=ev;
        assert(ev.reportHash===expected.report_hash&&ev.displayRevision===expected.display_revision&&validateGeometry(ev,floor,state),'Actual B floor/body/stair source parity '+floor.id+' '+state.id+' '+viewport.width);
        if(floor.id==='B-2F')assert(validateStairCaption(ev),'2F stair label distinguishes original incoming from Q3 outgoing '+state.id+' '+viewport.width);
        assert((await page.locator('#readout').textContent()).includes(floor.source_floor.storage.label)&&(await page.locator('#plan-link').getAttribute('href'))===state.plan_file,'Full name and exact plan link '+floor.id+' '+state.id);
        if(state.id==='storage'){
          assert(validateCabinet(ev,floor),'Actual B cabinet pixels and names '+floor.id+' '+viewport.width);
          const controls=await page.evaluate(()=>{
            const inside=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;};
            const b=window.__B_UPPER_QA__().cabinet.projected,c=document.querySelector('#stage canvas').getBoundingClientRect();
            return {selector:inside(document.getElementById('floor-select')),state:inside(document.getElementById('state-select')),readout:inside(document.getElementById('readout')),
              body:c.left+b.left>=0&&c.top+b.top>=0&&c.left+b.right<=innerWidth&&c.top+b.bottom<=innerHeight};
          });
          report.active_case.controls=controls;assert(controls.selector&&controls.state&&controls.readout&&controls.body,'First viewport controls and actual B cabinet '+floor.id+' '+viewport.width);
        }
        else assert(!ev.cabinet,'Original state contains no added cabinet '+floor.id);
        await capture(floor.id+'-'+state.id+'-'+viewport.width);
        if(state.id==='storage'){
          await page.locator('#show-labels').uncheck();await settle();const bare=await page.evaluate(()=>window.__B_UPPER_QA__(true));report.active_case.names_off=bare;
          assert(validateCabinet(bare,floor),'Text-free actual B cabinet '+floor.id);await page.locator('#show-labels').check();await settle();
          await page.locator('#open-items').click();
          const navigation=await page.evaluate(()=>{const e=document.getElementById('item-heading'),r=e.getBoundingClientRect();return {focus:document.activeElement.id,top:r.top,bottom:r.bottom,items:document.getElementById('item-list').textContent};});
          report.active_case.navigation=navigation;
          assert(navigation.focus==='item-heading'&&navigation.top>=0&&navigation.bottom<=viewport.height&&navigation.items.includes(floor.source_floor.storage.label),'Full names navigation '+floor.id);
          await page.locator('#return-scene').click();await settle();await page.evaluate(()=>scrollTo(0,0));
          assert(await page.locator('#floor-select').inputValue()===floor.id,'Return to same B floor '+floor.id);
          const before=(await page.evaluate(()=>window.__B_UPPER_QA__())).cameraPosition;await page.locator('#rotate-left').click();await settle();
          assert(!same((await page.evaluate(()=>window.__B_UPPER_QA__())).cameraPosition,before),'B rotation '+floor.id);
          await page.locator('#view-overview').click();await settle();const whole=await page.evaluate(()=>window.__B_UPPER_QA__());
          report.active_case.overview=whole;assert(validateGeometry(whole,floor,state)&&whole.mode==='overview','B full floor geometry retained '+floor.id);await capture(floor.id+'-floor-'+viewport.width);
          await page.locator('#view-stair').click();await settle();const stair=await page.evaluate(()=>window.__B_UPPER_QA__());
          report.active_case.stair=stair;assert(validateGeometry(stair,floor,state)&&stair.mode==='stair','B stair interface parity '+floor.id);
          if(floor.id==='B-2F')assert(validateStairCaption(stair,true),'Visible 2F original/Q3 stair caption '+viewport.width);
          await capture(floor.id+'-stair-'+viewport.width);
          await page.locator('#view-top').click();await settle();assert((await page.evaluate(()=>window.__B_UPPER_QA__())).mode==='top','B top view '+floor.id);
        }
        report.cases.push(report.active_case);report.active_case=null;
      }
    }
    for(const entry of expected.entry_options)for(const use of entry.states){
      await page.locator('#entry-select').selectOption(entry.id);await page.locator('#use-select').selectOption(use.id);
      assert(await page.locator('#ground-plan-link').getAttribute('href')===entry.id+'_'+use.id+'_floor-1.svg','Separate ground reference '+entry.id+' '+use.id);
    }
    assert(report.console_errors.length===0,'No B console/page errors');assert(preflight(root).report.report_hash===expected.report_hash,'B sources unchanged after run');report.status='passed';
  }catch(error){report.status='failed';report.error=error.stack||String(error);if(page){try{report.failure_evidence=await page.evaluate(()=>window.__B_UPPER_QA__?.(true)||null);await capture('failure');}catch(captureError){report.capture_error=String(captureError);}}}
  finally{if(browser){try{await browser.close();report.closed=true;}catch{}}if(report.status==='passed'&&!report.closed)report.status='incomplete';fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}
  return report.status==='passed'?0:1;
}
function main(){
  const args=process.argv.slice(2);if(args[0]==='--worker')return worker(args[1],args[2],args[3]).then(code=>{process.exitCode=code;});
  const ready=preflight(ROOT);console.log('B upper storage 3D preflight passed: '+JSON.stringify(ready.counts));
  console.log('B upper storage display revision: '+ready.report.display_revision+'; 2F stair label distinguishes original incoming and Q3 outgoing. Geometry unchanged.');
  if(args.includes('--preflight')){console.log('Files only; no browser/WebGL or professional approval.');return;}
  if(process.platform!=='win32')throw Error('Run from native Windows PowerShell; use --preflight in WSL.');
  const channel=args.find(a=>a.startsWith('--browser='))?.slice(10)||'msedge';if(!['msedge','chrome'].includes(channel))throw Error('Use msedge or chrome');
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-b-upper-3d-'));console.log('QA output: '+output);
  const result=spawnSync(process.execPath,[__filename,'--worker',ROOT,output,channel],{encoding:'utf8',timeout:120000,killSignal:'SIGTERM'}),file=path.join(output,'result.json');
  const report=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{status:'incomplete',closed:false,error:'No completed structured result'};
  if(result.error||result.signal||result.status!==0){if(report.status==='passed')report.status='incomplete';report.process_error=result.error?.message||result.signal||'worker exit '+result.status;}
  fs.writeFileSync(file,JSON.stringify(report,null,2));console.log('Automated B upper storage 3D browser checks: '+report.status);console.log('Result: '+file);
  if(report.error)console.log('Failure: '+String(report.error).split('\n')[0]);
  console.log('Screenshots need visual review. Original ABC and accepted viewers unchanged; no adoption or professional approval.');if(report.status!=='passed')process.exitCode=1;
}
module.exports={validateReport,preflight,area,clipArea,validateGeometry,validateCabinet,validateStairCaption};
if(require.main===module){try{main();}catch(error){console.error(error.message);process.exitCode=1;}}
