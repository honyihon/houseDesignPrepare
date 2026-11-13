'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const runtime=require('../../scripts/templates/b-upper-storage-viewer.js');
const {preflight,validateReport,clipArea,validateGeometry,validateCabinet,validateStairCaption}=require('../../scripts/check_b_upper_storage_3d_playwright.cjs');
const root=path.resolve(__dirname,'../..'),dir=path.join(root,'structured/coordination/b-upper-storage-3d-v1');
const report=JSON.parse(fs.readFileSync(path.join(dir,'review.json'))),sync=JSON.parse(fs.readFileSync(path.join(root,'structured/coordination/b-upper-storage-sync-v1/review.json')));
test('preflight binds four true B floor variants and independent original/storage states',()=>{assert.equal(preflight(root).counts.states,8);});
test('B preview rejects changed source polygons and inventory',()=>{
  const changed=structuredClone(report);changed.floors[1].source_floor.rooms[0].polygon_mm[0][0]+=1;assert.throws(()=>validateReport(changed,sync));
  const duplicated=structuredClone(report);duplicated.floors[0].states[0].objects.push(duplicated.floors[0].states[0].objects[0]);assert.throws(()=>validateReport(duplicated,sync));
});
test('source height envelopes preserve floor level; unknowns stay thin plan projections',()=>{
  assert.deepEqual(runtime.objectBox({rect_mm:[100,200,450,1200],height_mm:1800,mount_mm:0},4000),{size:[.45,1.8,1.2],center:[.325,4.9,.8],footprintOnly:false});
  assert.equal(runtime.objectBox({rect_mm:[0,0,600,900],height_mm:null,mount_mm:0},10000).size[1],.012);
  assert.throws(()=>runtime.objectBox({rect_mm:[0,0,-1,900],height_mm:900,mount_mm:0},4000));
});
test('triangle clipping detects actual surface coverage of a rectangular void',()=>{
  assert.equal(clipArea([[0,0],[2,0],[0,2]],[.25,.25,.25,.25]),.0625);
  assert.equal(clipArea([[0,0],[2,0],[0,2]],[4,4,1,1]),0);
});
test('geometry evidence rejects same-area floors shifted over a void, stale frames and missing stairs',()=>{
  const floor={id:'B-test',base_mm:4000,surface_area_mm2:4000000,forbidden_rects_mm:[[3000,3000,500,500]],stairs:[{id:'incoming:1',rect_mm:[0,0,1000,270],height_mm:166,top_mm:3800}]};
  const state={id:'storage',display_objects:[{key:'cabinet',rect_mm:[0,0,900,450],height_mm:1800,mount_mm:0}]};
  const good={ready:true,webglLost:false,floor:'B-test',state:'storage',stamp:'x',lastDrawStamp:'x',
    surfaceTrianglesM:[[[0,0],[2,0],[2,2]],[[0,0],[2,2],[0,2]]],objects:[{key:'cabinet',sizeMm:[900,1800,450],minMm:[0,4000,0]}],
    treads:[{id:'incoming:1',minMm:[0,3634,0],maxMm:[1000,3800,270]}]};
  assert.equal(validateGeometry(good,floor,state),true);
  for(const bad of [{...good,ready:false},{...good,lastDrawStamp:'old'},{...good,treads:[]},{...good,
    surfaceTrianglesM:good.surfaceTrianglesM.map(t=>t.map(p=>p.map(v=>v+2)))}])assert.throws(()=>validateGeometry(bad,floor,state));
});
test('actual cabinet evidence rejects label-only images and body-covering labels',()=>{
  const floor={source_floor:{storage:{rect_mm:[0,0,900,450]}}};
  const good={canvas:{clientWidth:390,clientHeight:350},cabinet:{rectMm:[0,0,900,450],projected:{left:80,top:100,right:220,bottom:300,width:140,height:200,inFront:true},
    pixels:{method:'webgl-readPixels-cabinet-aabb',sampled:1000,orange:500,ratio:.5}},labelsChecked:true,
    labelRects:[{kind:'storage',text:'儲藏櫃',left:80,top:30,width:140,height:30,scrollWidth:140,clientWidth:140}]};
  assert.equal(validateCabinet(good,floor),true);
  const noPixels=structuredClone(good);noPixels.cabinet.pixels.orange=0;noPixels.cabinet.pixels.ratio=0;assert.throws(()=>validateCabinet(noPixels,floor));
  const covered=structuredClone(good);covered.labelRects[0].top=150;assert.throws(()=>validateCabinet(covered,floor));
  const bare=structuredClone(good);bare.labelsChecked=false;bare.labelRects=[];assert.equal(validateCabinet(bare,floor),true);
});
test('new browser scripts and extracted label helper compile without executing a scene',()=>{
  for(const n of ['viewer.js','label-layout.js'])assert.doesNotThrow(()=>new vm.Script(fs.readFileSync(path.join(dir,n),'utf8')));
  assert.equal(runtime.pose(report.floors[2],'storage').target[1],10.45);
});
test('2F stair caption describes the Q3 outgoing change while retaining source names in data',()=>{
  const floor=report.floors[0],stair=floor.room_anchors.find(r=>r.id==='stair');
  assert(stair.label.includes('未改本體'));
  assert.equal(runtime.roomDisplayName(floor,stair),'二樓L形到達／一樓原梯接Q3上層改梯');
  assert.equal(runtime.roomDisplayName(report.floors[1],report.floors[1].room_anchors.find(r=>r.id==='stair')),
    report.floors[1].room_anchors.find(r=>r.id==='stair').label);
  const room=floor.room_anchors.find(r=>r.id==='quiet-living');assert.equal(runtime.roomDisplayName(floor,room),room.label);
  const caption={kind:'stair',text:runtime.roomDisplayName(floor,stair)};
  const ev={sceneLabels:[caption],canvas:{clientWidth:390,clientHeight:350},
    labelRects:[{...caption,left:20,top:30,width:170,height:44,scrollWidth:170,clientWidth:170}]};
  assert.equal(validateStairCaption(ev,true),true);
  assert.throws(()=>validateStairCaption({...ev,sceneLabels:[{kind:'stair',text:stair.label}]}));
  assert.throws(()=>validateStairCaption({...ev,labelRects:[]},true));
  assert.throws(()=>validateStairCaption({...ev,labelRects:[{...ev.labelRects[0],left:-5}]},true));
});
