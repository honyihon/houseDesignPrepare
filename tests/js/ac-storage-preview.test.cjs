'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {parsePayload,validateModels,preflight,validateBody}=require('../../scripts/check_ac_storage_preview_playwright.cjs');
const root=path.resolve(__dirname,'../..'),dir=path.join(root,'structured/coordination/ac-storage-preview-v1');
const text=fs.readFileSync(path.join(dir,'index.html'),'utf8'),report=JSON.parse(fs.readFileSync(path.join(dir,'review.json'),'utf8'));
const payload=parsePayload(text),base=parsePayload(fs.readFileSync(path.join(root,'structured/candidates/kaohsiung-house-options-3d.html'),'utf8'));
test('file preflight binds two A/C options, both before/after states and matching full-floor models',()=>{
  assert.deepEqual(preflight(root).counts,{buildings:2,states:4,floors:16,storage_cases:6,new_cabinets:6});
});
test('independent JS comparison rejects original furniture damage and a resized new cabinet',()=>{
  for(const defect of ['original','new','product-summary']){
    const p=structuredClone(payload),model=p.options[0].states.find(s=>s.id==='storage').model;
    if(defect==='product-summary'){model.furniture.physical_items.measured=99;assert.throws(()=>validateModels(report,p,base));continue;}
    const items=model.buildings[0].floors.flatMap(f=>f.cells.flatMap(c=>c.furniture));
    const item=items.find(i=>defect==='new'?i.storage_case:!i.storage_case);item.width_mm+=1;
    assert.throws(()=>validateModels(report,p,base));
  }
});
test('body QA rejects a label-only frame, wrong floor elevation or cabinet hidden behind controls',()=>{
  const c=report.cases[0],rect=c.rect_mm;
  const good={present:true,visible:true,overflow:false,collision:false,focusPending:false,frame:{ready:true},
    newItems:report.cases.filter(v=>v.option===c.option).map(v=>v.proposed_item_id),actualRectMm:rect,
    actualHeightMm:c.height_mm,actualBottomMm:3000,actualTopMm:3000+c.height_mm,
    projected:{left:100,right:230,top:150,bottom:400,width:130,height:250,inFront:true},
    stage:{width:390,height:700},safeArea:{left:10,right:380,top:120,bottom:600},
    pixels:{method:'webgl-readPixels-cabinet-aabb',sampled:1000,orange:500,ratio:.5}};
  assert.equal(validateBody(good,c,3000),true);
  for(const changed of [{...good,pixels:null},{...good,actualBottomMm:0},{...good,visible:false},
    {...good,focusPending:true},{...good,frame:{ready:false}},
    {...good,projected:{...good.projected,width:39.8,height:70.6}},
    {...good,actualRectMm:[]},{...good,pixels:{...good.pixels,orange:NaN}},
    {...good,projected:{...good.projected,top:20}},{...good,pixels:{...good.pixels,orange:0,ratio:0}}])assert.throws(()=>validateBody(changed,c,3000));
});
test('both complete inline scripts compile without executing Three.js or any scene code',()=>{
  const scripts=[...text.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  assert.equal(scripts.length,2);
  scripts.forEach((source,n)=>assert.doesNotThrow(()=>new vm.Script(source,{filename:'ac-preview-script-'+n})));
});
test('generated label bootstrap enables the default/all checkbox and keeps explicit compact mode contextual',()=>{
  const block=text.match(/  var b32LabelMode=document.getElementById\("b32-label-mode"\);[\s\S]*?  b32SyncDensityControl\(\);/);
  assert(block,'Actual generated label initialization must be tested');
  for(const [query,mode,disabled] of [['','all',false],['?labels=all','all',false],['?labels=compact','compact',true]]){
    const select={value:'all'},names={disabled:false},body={dataset:{}};
    const context={URL,location:{href:'file:///preview/index.html'+query},facadeIsActive:()=>false,
      document:{body,getElementById:id=>({'b32-label-mode':select,'furniture-names':names})[id]}};
    vm.runInNewContext(block[0],context,{timeout:100});
    assert.equal(select.value,mode);assert.equal(names.disabled,disabled);assert.equal(body.dataset.b32LabelMode,mode);
    select.value='all';context.b32SyncDensityControl();assert.equal(names.disabled,false);
  }
});
test('panel resize fits the current cabinet in the same callback and preserves whole-floor navigation',()=>{
  const start=text.indexOf('  function acStorageResize(){'),end=text.indexOf('  function acStorageFocus(){',start);
  assert(start>=0&&end>start);
  const source=text.slice(start,end),cabinet={host_room_id:'A:floor-4:laundry-rf'};
  for(const [focus,room,query,expected]of [[true,cabinet.host_room_id,'?cabinet=1',true],
    [false,'','?cabinet=1',false],[true,cabinet.host_room_id,'',false],[true,'other-room','?cabinet=1',false]]){
    const calls=[],queued=[],context={URL,location:{href:'file:///preview/index.html'+query},acStorageFocusPending:false,
      roomCameraFocused:focus,viewState:{room},acStorageCase:()=>cabinet,
      resize:()=>{calls.push('resize');context.cameraView='room';},
      acStorageFrameCabinet:c=>{assert.equal(c,cabinet);calls.push('cabinet');context.cameraView='cabinet';},
      requestAnimationFrame:fn=>queued.push(fn)};
    vm.runInNewContext(source,context,{timeout:100});context.acStorageResize();
    assert.deepEqual(calls,expected?['resize','cabinet']:['resize']);assert.equal(queued.length,0);
    assert.equal(context.cameraView,expected?'cabinet':'room');assert.equal(context.acStorageFocusPending,false);
    context.resize=()=>{throw Error('resize failed');};assert.throws(()=>context.acStorageResize());
    assert.equal(context.acStorageFocusPending,false);
  }
});
test('render readiness rejects stale viewport, camera, label and pending-resize states',()=>{
  const start=text.indexOf('  function acStorageViewStamp(){'),end=text.indexOf('  function acStorageReadout(){',start);
  assert(start>=0&&end>start);assert(text.includes('acStorageLastDrawStamp=acStorageViewStamp();'));
  const names={checked:true},labels={value:'all'},position=[1,2,3],area={left:12,right:378,top:244,bottom:681};
  const context={acStorageFocusPending:false,basisResizePending:false,acStorageLastDrawStamp:null,basisLastDraw:null,
    stage:{clientWidth:390,clientHeight:790},cameraViewportRect:()=>area,
    camera:{position:{toArray:()=>position.slice()},quaternion:{toArray:()=>[0,0,0,1]},projectionMatrix:{elements:[1,0,0,1]}},
    viewState:{building:'A',floor:'floor-4',room:'A:floor-4:laundry-rf'},roomCameraFocused:true,
    document:{getElementById:id=>({'furniture-names':names,'b32-label-mode':labels})[id]}};
  vm.runInNewContext(text.slice(start,end),context,{timeout:100});
  assert.equal(context.acStorageFrameReady().ready,false);
  const record=()=>{
    context.acStorageLastDrawStamp=context.acStorageViewStamp();
    context.basisLastDraw={renderSize:{width:context.stage.clientWidth,height:context.stage.clientHeight}};
    assert.equal(context.acStorageFrameReady().ready,true);
  };
  record();context.basisLastDraw.renderSize.height=1;assert.equal(context.acStorageFrameReady().ready,false);
  record();context.basisResizePending=true;assert.equal(context.acStorageFrameReady().ready,false);context.basisResizePending=false;
  context.acStorageFocusPending=true;assert.equal(context.acStorageFrameReady().ready,false);context.acStorageFocusPending=false;
  for(const change of [()=>{context.stage.clientHeight=473;},()=>{area.bottom=364;},()=>{position[0]=5;},
    ()=>{names.checked=false;},()=>{labels.value='compact';},()=>{context.viewState.floor='floor-3';}]){
    change();assert.equal(context.acStorageFrameReady().ready,false);record();
  }
});
