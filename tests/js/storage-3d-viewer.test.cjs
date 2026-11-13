'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {storageBox,visibleItems,viewPose,overviewDistance,reserveName,placeLabels,rectsOverlap}=require('../../scripts/templates/upper-floor-storage-viewer.js');
const {validateReport,preflight,validateDisplayEvidence,navigationIssues}=require('../../scripts/check_storage_3d_playwright.cjs');
const root=path.resolve(__dirname,'../..'),out='structured/coordination/upper-floor-storage-viewer-v1';
const report=JSON.parse(fs.readFileSync(path.join(root,out,'review.json'),'utf8'));
const original=JSON.parse(fs.readFileSync(path.join(root,'structured/coordination/upper-floor-storage-v1/review.json'),'utf8'));
test('each storage box preserves plan axes, coordinates and height without running THREE',()=>{
  for(const c of report.cases){const b=storageBox(c);assert.deepEqual(b.size,[c.rect_mm[2]/1000,c.height_mm/1000,c.rect_mm[3]/1000]);
    assert.deepEqual(b.center,[(c.rect_mm[0]+c.rect_mm[2]/2)/1000,c.height_mm/2000,(c.rect_mm[1]+c.rect_mm[3]/2)/1000]);}
});
test('reused roof tables are excluded exactly once, all other item names stay visible',()=>{
  for(const c of report.cases){const actual=visibleItems(c),all=c.rooms.flatMap(r=>r.items);assert.equal(actual.length,all.length-(c.reuse_item?1:0));assert(actual.every(i=>i.label));}
});
test('viewport fit budgets both mobile and desktop field of view',()=>{
  assert(overviewDistance(366,439)>overviewDistance(1000,650));
  for(const c of report.cases){const close=viewPose(c,'storage');assert.deepEqual(close.target,storageBox(c).center);assert(close.distance>c.height_mm/1000);
    assert.equal(close.azimuth,-.7);assert.equal(viewPose(c,'overview').azimuth,close.azimuth);assert.equal(viewPose(c,'top').azimuth,close.azimuth);}
});
test('file preflight independently rejects a changed cabinet or B polygon',()=>{
  assert.deepEqual(validateReport(report,original),{cases:10,floors:9});
  for(const key of ['rect_mm','rooms']){const changed=JSON.parse(JSON.stringify(report));
    if(key==='rect_mm')changed.cases[0].rect_mm[2]+=1;else changed.cases.find(c=>c.id==='B-3F').rooms[0].polygon_mm[0][0]+=1;
    assert.throws(()=>validateReport(changed,original));}
  assert.deepEqual(preflight(root).counts,{cases:10,floors:9});
});
test('invalid dimensions fail instead of scaling or dropping storage',()=>{
  const c={...report.cases[0],height_mm:0};assert.throws(()=>storageBox(c));
  assert.throws(()=>storageBox({...c,height_mm:NaN}));
});
test('right-edge long names keep measured width and avoid the actual cabinet and one another',()=>{
  const viewport={width:364,height:350},body={left:115,top:100,width:134,height:160};
  const candidates=[
    {id:'room',x:180,y:160,width:160,height:30,priority:2},
    {id:'bed',x:362,y:170,width:180,height:38,priority:1},
    {id:'S1',x:182,y:90,width:220,height:38,priority:0},
    {id:'tank',x:355,y:8,width:170,height:38,priority:1}
  ];
  const placed=placeLabels(candidates,viewport,[body]);
  assert.equal(placed[0].id,'S1');assert(placed.some(p=>p.id==='bed'));
  for(const p of placed){
    assert.equal(p.rect.width,candidates.find(c=>c.id===p.id).width);
    assert(p.rect.left>=8&&p.rect.top>=8&&p.rect.left+p.rect.width<=356&&p.rect.top+p.rect.height<=342);
    assert(!rectsOverlap(p.rect,body));
    assert(placed.every(other=>other===p||!rectsOverlap(p.rect,other.rect)));
  }
});
test('a crowded small stage retains the selected cabinet name without squeezing other names',()=>{
  const c={x:120,y:60,width:190,height:35,priority:1};
  const result=placeLabels([{...c,id:'S1',priority:0},...Array.from({length:15},(_,n)=>({...c,id:n}))],{width:250,height:180},[{left:70,top:80,width:110,height:80}]);
  assert.equal(result[0].id,'S1');assert(result.length<16);assert(result.every(p=>p.rect.width===190));
  assert.deepEqual(placeLabels([{...c,width:500,id:'too-wide'}],{width:250,height:180}),[]);
});
test('reserve labels use readable Chinese while source identifiers remain untouched',()=>{
  for(const name of ['door-approach','stairs','stairs-landing','basis-rack-loading','basis-sink-use','circulation','hvac-service']){
    assert.match(reserveName(name),/[\u3400-\u9fff]/);
  }
  assert.equal(reserveName('representative-slot-1｜冷氣室外機'),'代表預留位1｜冷氣室外機');
  assert.equal(reserveName('水塔／泵浦整組預留'),'水塔／泵浦整組預留');
});
test('display QA rejects metadata-only, clipped, overlapping and cabinet-covering evidence',()=>{
  const ev={displayRevision:3,canvas:{clientWidth:364,clientHeight:350},
    storageProjected:{left:120,top:100,right:230,bottom:260,width:110,height:160,inFront:true},
    bodyPixels:{method:'webgl-readPixels-rendered-cabinet-aabb',sampled:1000,orange:500,ratio:.5},
    labelRects:[{text:'S1｜儲藏櫃',kind:'storage',left:90,top:58,width:180,height:28,scrollWidth:178,clientWidth:178}]};
  assert.equal(validateDisplayEvidence(ev),true);
  const bads=[{...ev,displayRevision:2},{...ev,bodyPixels:null},{...ev,bodyPixels:{...ev.bodyPixels,orange:0,ratio:0}},
    {...ev,storageProjected:{...ev.storageProjected,right:400}},
    {...ev,labelRects:[{...ev.labelRects[0],left:-4}]},
    {...ev,labelRects:[{...ev.labelRects[0],width:6,height:180}]},
    {...ev,labelRects:[{...ev.labelRects[0],top:105}]},
    {...ev,labelRects:[...ev.labelRects,{...ev.labelRects[0],kind:'item'}]}];
  for(const bad of bads)assert.throws(()=>validateDisplayEvidence(bad));
});
test('full-name navigation requires real visible content, focus and an unchanged selected floor',()=>{
  const box={left:20,top:16,right:350,bottom:46,width:330,height:30,visible:true},c={id:'A-2F',label:'書房入口側獨立雜物櫃'};
  const ev={viewport:{width:390,height:844},focusedId:'item-heading',selectedCase:c.id,heading:box,
    returnButton:{...box,top:52,bottom:96,height:44},itemCount:14,
    firstItem:{text:'S1｜'+c.label+'｜900×450×1800mm',rect:{...box,top:104,bottom:148,height:44}}};
  assert.deepEqual(navigationIssues(ev,c),[]);
  for(const [change,issue] of [
    [{heading:{...box,top:-.2}},'heading outside viewport'],
    [{focusedId:'open-items'},'focus is open-items'],
    [{selectedCase:'C-2F'},'selected floor differs'],
    [{returnButton:{...box,bottom:900}},'return button outside viewport'],
    [{firstItem:{...ev.firstItem,rect:{...box,visible:false}}},'first full name unavailable'],
    [{firstItem:{...ev.firstItem,text:'S1'}},'first full name unavailable']
  ])assert(navigationIssues({...ev,...change},c).includes(issue));
});
