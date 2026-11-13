// --preflight is bounded file checking only. Browser QA runs in the owner's separate Windows terminal.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {isDeepStrictEqual:same}=require('node:util');
const {rectsOverlap}=require('./templates/upper-floor-storage-viewer.js');
const ROOT=path.resolve(__dirname,'..'),OUT='structured/coordination/upper-floor-storage-viewer-v1';
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
function read(root,name){
  if(!/^[A-Za-z0-9_./-]+$/.test(name)||path.isAbsolute(name)||name.split('/').includes('..')||name.split('/').includes('private'))throw Error('Unsafe public storage path');
  return fs.readFileSync(path.join(root,name));
}
function validateReport(r,source){
  if(r.schema!=='house-upper-floor-storage-viewer-v1'||r.display_revision!==3||r.case_count!==10||r.distinct_floors!==9||r.primary_3d_changed!==false||
     r.display_scope!=='storage-height-only-with-exact-source-floor-and-object-footprints'||r.adopted!==false||r.rendered_qa!=='not-run-owner-separate-terminal-required'||
     !same(r.cases.map(c=>c.id),source.cases.map(c=>c.id)))throw Error('Storage viewer scope differs');
  for(const c of r.cases){
    const old=source.cases.find(x=>x.id===c.id);
    for(const key of ['rect_mm','operation_mm','height_mm','rooms','fixed','routes','source_floor_hash'])if(!same(c[key],old[key]))throw Error('Plan/3D source differs: '+c.id+' '+key);
    if(c.review.failures.length||!same(c.storage_geometry,{rect_mm:c.rect_mm,operation_mm:c.operation_mm,height_mm:c.height_mm}))throw Error('Invalid cabinet source');
  }
  return {cases:10,floors:9};
}
function preflight(root){
  const r=JSON.parse(read(root,OUT+'/review.json')),m=JSON.parse(read(root,OUT+'/artifact-manifest.json'));
  const source=JSON.parse(read(root,'structured/coordination/upper-floor-storage-v1/review.json'));
  const counts=validateReport(r,source);
  if(r.source_storage_report_sha256!==hash(read(root,'structured/coordination/upper-floor-storage-v1/review.json'))||m.report_hash!==r.report_hash)throw Error('Mixed storage report');
  for(const [name,digest]of Object.entries(r.source_hashes))if(hash(read(root,name))!==digest)throw Error('Stale storage viewer source: '+name);
  for(const [name,digest]of Object.entries(m.artifacts))if(hash(read(root,OUT+'/'+name))!==digest)throw Error('Changed viewer artifact: '+name);
  const text=read(root,OUT+'/index.html').toString('utf8'),match=text.match(/<script id="storage-data" type="application\/json">([\s\S]+?)<\/script>/);
  if(!match||!same(JSON.parse(match[1]),r)||!text.includes('周邊房間、家具與設備只畫原平面投影'))throw Error('Embedded storage source or visible scope differs');
  for(const c of r.cases)if(hash(read(root,OUT+'/'+c.plan_file))!==c.plan_sha256)throw Error('Plan copy differs: '+c.id);
  return {report:r,counts};
}
function validateDisplayEvidence(ev){
  const b=ev.storageProjected,w=ev.canvas.clientWidth,h=ev.canvas.clientHeight,p=ev.bodyPixels;
  if(ev.displayRevision!==3||!b||![b.left,b.top,b.width,b.height,b.right,b.bottom].every(Number.isFinite)||!b.inFront||
     b.left<0||b.top<0||b.right>w||b.bottom>h||b.width<60||b.height<50||b.width*b.height<5000)throw Error('Actual cabinet body too small or clipped');
  if(!p||p.method!=='webgl-readPixels-rendered-cabinet-aabb'||!Number.isFinite(p.sampled)||p.sampled<80||
     !Number.isFinite(p.orange)||p.orange<60||p.orange>p.sampled||!Number.isFinite(p.ratio)||p.ratio<.08||
     Math.abs(p.ratio-p.orange/p.sampled)>1e-9)throw Error('Missing actual rendered orange body pixels');
  const labels=ev.labelRects;
  if(!Array.isArray(labels)||!labels.some(l=>l.kind==='storage'))throw Error('Selected storage name missing from scene');
  for(let i=0;i<labels.length;i++){
    const l=labels[i];
    if(![l.left,l.top,l.width,l.height,l.scrollWidth,l.clientWidth].every(Number.isFinite)||l.left<0||l.top<0||
       l.left+l.width>w||l.top+l.height>h||l.width<28||l.height>90||l.scrollWidth>l.clientWidth+1)throw Error('Clipped or squeezed scene name: '+l.text);
    if(rectsOverlap(l,b))throw Error('Scene name covers cabinet body: '+l.text);
    if(labels.slice(i+1).some(other=>rectsOverlap(l,other)))throw Error('Scene names overlap: '+l.text);
  }
  return true;
}
function captureNavigationEvidence(){
  const rect=element=>{
    if(!element)return null;
    const r=element.getBoundingClientRect(),s=getComputedStyle(element);
    return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height,
      visible:s.display!=='none'&&s.visibility==='visible'&&Number(s.opacity)>0};
  };
  const list=document.getElementById('item-list');
  return {viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY},focusedId:document.activeElement?.id||null,
    selectedCase:document.getElementById('case-select')?.value||null,
    heading:rect(document.getElementById('item-heading')),returnButton:rect(document.getElementById('return-scene')),
    selector:rect(document.getElementById('case-select')),itemCount:list?.children.length||0,
    firstItem:{text:list?.firstElementChild?.textContent||'',rect:rect(list?.firstElementChild)}};
}
function insideViewport(rect,viewport){
  return rect&&rect.visible&&[rect.left,rect.top,rect.right,rect.bottom,rect.width,rect.height].every(Number.isFinite)&&
    rect.width>0&&rect.height>0&&rect.left>=0&&rect.top>=0&&rect.right<=viewport.width&&rect.bottom<=viewport.height;
}
function navigationIssues(ev,c){
  const issues=[];
  if(ev.selectedCase!==c.id)issues.push('selected floor differs');
  if(ev.focusedId!=='item-heading')issues.push('focus is '+ev.focusedId);
  if(!insideViewport(ev.heading,ev.viewport))issues.push('heading outside viewport');
  if(!insideViewport(ev.returnButton,ev.viewport))issues.push('return button outside viewport');
  if(ev.itemCount<1||!ev.firstItem.text.includes(c.label)||!insideViewport(ev.firstItem.rect,ev.viewport))issues.push('first full name unavailable');
  return issues;
}
async function worker(root,output,browserChannel){
  const expected=preflight(root).report;
  const report={schema:'house-storage-3d-browser-qa-v1',display_revision:expected.display_revision,status:'incomplete',report_hash:expected.report_hash,
    source_hashes:expected.source_hashes,browser_channel:browserChannel,checks:[],screenshots:[],console_errors:[],cases:[],closed:false};
  let browser,page;
  const assert=(v,name)=>{report.checks.push({name,passed:Boolean(v)});if(!v)throw Error(name);};
  try{
    const {chromium}=require(path.join(root,'node_modules','playwright'));
    browser=await chromium.launch({channel:browserChannel,headless:true});
    page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(12000);
    page.on('pageerror',e=>report.console_errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')report.console_errors.push(m.text());});
    await page.goto(pathToFileURL(path.join(root,OUT,'index.html')).href,{waitUntil:'load'});
    await page.waitForFunction(()=>document.body.dataset.viewerState==='ready'&&window.__STORAGE3D_QA__?.().renderCount>0);
    assert(await page.title()==='ABC逐層儲藏立體檢視','Page identity');
    assert(await page.locator('#scope-warning').isVisible(),'Visible source-footprint scope warning');
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      await page.setViewportSize(viewport);
      for(const c of expected.cases){
        report.active_case={id:c.id,viewport};
        await page.locator('#case-select').selectOption(c.id);
        await page.waitForFunction(id=>window.__STORAGE3D_QA__?.().caseId===id,c.id);
        await page.evaluate(()=>window.scrollTo(0,0));await page.locator('#view-storage').click();
        await page.waitForFunction(()=>window.__STORAGE3D_QA__?.().mode==='storage');
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const ev=await page.evaluate(()=>window.__STORAGE3D_QA__(true));
        report.active_case.evidence=ev;
        assert(ev.reportHash===expected.report_hash&&ev.caseId===c.id&&same(ev.storageSizeMm,[c.rect_mm[2],c.height_mm,c.rect_mm[3]])&&
          same(ev.storageSourceRectMm,c.rect_mm)&&ev.storageSourceHeightMm===c.height_mm&&ev.polygonHash===c.source_floor_hash&&
          ev.planSha256===c.plan_sha256&&!ev.webglLost&&ev.canvas.width>0&&ev.canvas.clientHeight>=350,'Actual mesh/source parity '+c.id+' '+viewport.width);
        assert((await page.locator('#scene-name').textContent()).includes(c.label)&&(await page.locator('#item-list').textContent()).includes(c.label),'Full names in scene title and accessible list '+c.id);
        assert(await page.locator('#plan-link').getAttribute('href')===c.plan_file,'Matching plan link '+c.id);
        assert(validateDisplayEvidence(ev),'Actual cabinet pixels and unclipped, nonoverlapping names '+c.id+' '+viewport.width);
        const controls=await page.evaluate(()=>{
          const inside=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;};
          const body=window.__STORAGE3D_QA__().storageProjected,canvas=document.querySelector('#stage canvas').getBoundingClientRect();
          return {selector:inside(document.getElementById('case-select')),readout:inside(document.getElementById('case-readout')),
            selected:document.getElementById('selected-case').textContent,size:document.getElementById('selected-size').textContent,
            bodyVisible:canvas.left+body.left>=0&&canvas.top+body.top>=0&&canvas.left+body.right<=innerWidth&&canvas.top+body.bottom<=innerHeight};
        });
        report.active_case.controls=controls;
        assert(controls.selector&&controls.readout&&controls.selected.includes(c.id)&&controls.selected.includes(c.label)&&
          controls.size===c.rect_mm.slice(2).join('×')+'×'+c.height_mm+'mm'&&controls.bodyVisible,'First viewport floor selector, dimensions and actual body '+c.id+' '+viewport.width);
        await page.locator('#open-items').click();
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const navigation=await page.evaluate(captureNavigationEvidence),issues=navigationIssues(navigation,c);
        report.active_case.navigation=navigation;report.active_case.navigation_issues=issues;
        assert(issues.length===0,'Accessible full names navigation '+c.id+(issues.length?': '+issues.join('; '):''));
        await page.locator('#return-scene').click();
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const returned=await page.evaluate(captureNavigationEvidence);report.active_case.return_navigation=returned;
        assert(returned.focusedId==='case-select'&&returned.selectedCase===c.id&&insideViewport(returned.selector,returned.viewport),'Return to same floor controls '+c.id);
        await page.evaluate(()=>window.scrollTo(0,0));
        const position=ev.cameraPosition;
        await page.locator('#rotate-left').click();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        assert(!same((await page.evaluate(()=>window.__STORAGE3D_QA__())).cameraPosition,position),'Rotate control '+c.id);
        await page.locator('#show-labels').uncheck();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const bare=await page.evaluate(()=>window.__STORAGE3D_QA__(true));
        assert(bare.labelsChecked===false&&bare.labelRects.length===0&&bare.bodyPixels.orange>=60&&bare.bodyPixels.ratio>=.08,'Text-free actual body and names toggle '+c.id);
        await page.locator('#show-labels').check();
        await page.locator('#view-top').click();await page.waitForFunction(()=>window.__STORAGE3D_QA__().mode==='top');
        await page.locator('#view-overview').click();await page.waitForFunction(()=>window.__STORAGE3D_QA__().mode==='overview');
        await page.locator('#view-storage').click();await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        await page.evaluate(()=>window.scrollTo(0,0));
        const finalEvidence=await page.evaluate(()=>window.__STORAGE3D_QA__(true));
        assert(validateDisplayEvidence(finalEvidence),'Final screenshot body and names '+c.id+' '+viewport.width);
        const screenshot=path.join(output,c.id+'-'+viewport.width+'.png');await page.screenshot({path:screenshot,fullPage:false});report.screenshots.push(screenshot);
        report.cases.push({id:c.id,viewport,evidence:ev,controls,navigation,return_navigation:returned,text_free_evidence:bare,screenshot_evidence:finalEvidence});
        report.active_case=null;
      }
    }
    assert(report.console_errors.length===0,'No browser console/page errors');
    // Recheck bytes after the run; a passing result must bind to unchanged sources.
    assert(preflight(root).report.report_hash===expected.report_hash,'Sources unchanged after browser checks');
    report.status='passed';
  }catch(error){report.status='failed';report.error=error.stack||String(error);
    if(page){
      try{report.failure_navigation=await page.evaluate(captureNavigationEvidence);}catch(captureError){report.failure_navigation_error=String(captureError);}
      try{report.failure_runtime=await page.evaluate(()=>window.__STORAGE3D_QA__?.(true)||null);}catch(captureError){report.failure_runtime_error=String(captureError);}
    }
    if(page){try{const screenshot=path.join(output,'failure.png');await page.screenshot({path:screenshot});report.screenshots.push(screenshot);}catch{}}
  }finally{
    if(browser){try{await browser.close();report.closed=true;}catch{}}
    if(report.status==='passed'&&!report.closed){report.status='incomplete';report.error='Browser cleanup not confirmed';}
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));
  }
  return report.status==='passed'?0:1;
}
function main(){
  const args=process.argv.slice(2);
  if(args[0]==='--worker')return worker(args[1],args[2],args[3]).then(code=>{process.exitCode=code;});
  const prepared=preflight(ROOT);console.log('Storage viewer preflight passed: '+JSON.stringify(prepared.counts));
  console.log('Storage display revision: '+prepared.report.display_revision+'; inset list navigation, raw focus/position evidence and actual rendered body checks. Layouts unchanged.');
  if(args.includes('--preflight')){console.log('Files only; no browser, WebGL or rendered QA pass.');return;}
  if(process.platform!=='win32')throw Error('Run browser QA from native Windows PowerShell. Use --preflight in WSL.');
  const browserArg=args.find(v=>v.startsWith('--browser=')),channel=browserArg?browserArg.slice(10):'msedge';
  if(!['msedge','chrome'].includes(channel))throw Error('Use --browser=msedge or --browser=chrome');
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-storage-3d-'));console.log('QA output: '+output);
  const result=spawnSync(process.execPath,[__filename,'--worker',ROOT,output,channel],{encoding:'utf8',timeout:120000,killSignal:'SIGTERM'});
  const resultFile=path.join(output,'result.json');
  const report=fs.existsSync(resultFile)?JSON.parse(fs.readFileSync(resultFile,'utf8')):{status:'incomplete',error:result.error?.message||'No completed structured result',closed:false};
  if(result.error||result.signal||result.status!==0){if(report.status==='passed')report.status='incomplete';report.process_error=result.error?.message||result.signal||'worker exit '+result.status;}
  fs.writeFileSync(resultFile,JSON.stringify(report,null,2));
  console.log('Automated storage 3D browser checks: '+report.status);console.log('Result: '+resultFile);
  if(report.error)console.log('Failure: '+String(report.error).split('\n')[0]);
  console.log('Screenshots need visual review. This is not main-3D integration or professional approval.');
  if(report.status!=='passed')process.exitCode=1;
}
module.exports={validateReport,preflight,validateDisplayEvidence,navigationIssues};
if(require.main===module){try{main();}catch(error){console.error(error.message);process.exitCode=1;}}
