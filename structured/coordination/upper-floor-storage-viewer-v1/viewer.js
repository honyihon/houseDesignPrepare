(function (global) {
  'use strict';
  function storageBox(c) {
    const [x,z,w,d]=c.rect_mm,h=c.height_mm;
    if(![x,z,w,d,h].every(Number.isFinite)||w<=0||d<=0||h<=0)throw Error('Invalid storage dimensions');
    return {size:[w/1000,h/1000,d/1000],center:[(x+w/2)/1000,h/2000,(z+d/2)/1000]};
  }
  function visibleItems(c) {
    const result=[];
    c.rooms.forEach(r=>r.items.forEach(i=>{
      if(r.id===c.room&&i.id===c.reuse_item)return;
      result.push({...i,room:r.label||r.id});
    }));
    return result;
  }
  function viewPose(c,mode) {
    const b=storageBox(c);
    return mode==='storage'?{target:b.center,distance:Math.max(3.4,...b.size)*1.7,polar:.95,azimuth:-.7}:
      {target:[3,0,8.815],distance:22,polar:mode==='top'?.025:.7,azimuth:-.7};
  }
  function overviewDistance(width,height) {
    const aspect=Math.max(.1,width/height),halfFov=Math.atan(Math.tan(43*Math.PI/360)*Math.min(1,aspect));
    return Math.hypot(3,8.815,1.8)/Math.sin(halfFov)*1.12;
  }
  const reserveNames={'door-approach':'門前操作預留',stairs:'樓梯預留','stairs-landing':'樓梯平台預留',
    circulation:'公共通行預留','hvac-service':'冷氣檢修預留','basis-rack-loading':'晾衣架取放預留','basis-sink-use':'水槽使用預留'};
  function reserveName(label){return reserveNames[label]||label.replace(/^representative-slot-(\d+)｜/,'代表預留位$1｜');}
  function rectsOverlap(a,b,gap=0){
    return a.left<b.left+b.width+gap&&a.left+a.width+gap>b.left&&a.top<b.top+b.height+gap&&a.top+a.height+gap>b.top;
  }
  // CSS supplies measured, uncompressed label sizes. Place names, never move models.
  function placeLabels(candidates,viewport,obstacles=[]) {
    const margin=8,gap=6,placed=[];
    for(const c of [...candidates].sort((a,b)=>a.priority-b.priority)){
      if(![c.x,c.y,c.width,c.height].every(Number.isFinite)||c.width<=0||c.height<=0||
         c.width>viewport.width-2*margin||c.height>viewport.height-2*margin)continue;
      const choices=[];
      for(const step of [0,18,42,72,110,160]){
        for(const [dx,dy] of [[0,-1],[0,1],[-1,0],[1,0],[-1,-1],[1,-1],[-1,1],[1,1]]){
          const x=c.x+(dx<0?-c.width-gap-step:dx>0?gap+step:-c.width/2);
          const y=c.y+(dy<0?-c.height-gap-step:dy>0?gap+step:-c.height/2);
          const rect={left:Math.max(margin,Math.min(viewport.width-margin-c.width,x)),
            top:Math.max(margin,Math.min(viewport.height-margin-c.height,y)),width:c.width,height:c.height};
          const nearX=Math.max(rect.left,Math.min(rect.left+rect.width,c.x)),nearY=Math.max(rect.top,Math.min(rect.top+rect.height,c.y));
          choices.push({rect,score:(nearX-c.x)**2+(nearY-c.y)**2});
        }
      }
      choices.sort((a,b)=>a.score-b.score);
      const best=choices.find(({rect})=>!obstacles.some(o=>rectsOverlap(rect,o,gap))&&!placed.some(p=>rectsOverlap(rect,p.rect,gap)));
      if(best)placed.push({id:c.id,rect:best.rect});
    }
    return placed;
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={storageBox,visibleItems,viewPose,overviewDistance,reserveName,rectsOverlap,placeLabels};
  if(typeof document==='undefined')return;
  const data=JSON.parse(document.getElementById('storage-data').textContent);
  const byId=new Map(data.cases.map(c=>[c.id,c]));
  const select=document.getElementById('case-select'),stage=document.getElementById('stage'),labelsRoot=document.getElementById('labels');
  const status=document.getElementById('status'),linesRoot=document.getElementById('label-lines');
  let current=byId.get(data.default_case),mode='overview',scene,camera,renderer,content,storageMesh;
  let azimuth=-.7,polar=.7,distance=22,target,scheduled=false,renderCount=0;
  let labels=[],drag=null;
  data.cases.forEach(c=>{const option=document.createElement('option');option.value=c.id;option.textContent=c.id+'｜'+c.label;select.append(option);});
  function showText() {
    select.value=current.id;
    document.getElementById('scene-name').textContent=current.id+'｜'+current.label;
    document.getElementById('storage-size').textContent='平面 '+current.rect_mm.slice(2).join('×')+'mm；高 '+current.height_mm+'mm（提案）';
    document.getElementById('selected-case').textContent=current.id+'｜'+current.label;
    document.getElementById('selected-size').textContent=current.rect_mm.slice(2).join('×')+'×'+current.height_mm+'mm';
    document.getElementById('case-note').textContent=current.note;
    document.getElementById('plan-link').setAttribute('href',current.plan_file);
    document.getElementById('reuse-note').textContent=current.reuse_item?'本版沿原折衣桌占地與操作帶作下櫃工作檯；沒有同時加上舊桌。取物／折衣與原通路仍分時。':'新櫃與原衣櫃、弱電機櫃分開；櫃內有效容量、門片及搬入取物仍待核。';
    document.getElementById('source-id').textContent='本批 '+data.report_hash+'；平面原檔 SHA-256 '+current.plan_sha256;
    const list=document.getElementById('item-list');list.replaceChildren();
    const entries=['S1｜'+current.label+'｜'+current.rect_mm.slice(2).join('×')+'×'+current.height_mm+'mm'];
    visibleItems(current).forEach((i,n)=>entries.push((n+1)+'｜'+i.label+'｜'+i.rect_mm.slice(2).join('×')+'mm 平面'));
    current.fixed.forEach(i=>entries.push(reserveName(i.label)+'（原平面預留）'));
    entries.forEach(value=>{const li=document.createElement('li');li.textContent=value;list.append(li);});
    document.body.dataset.storageCase=current.id;
  }
  function schedule() {
    if(scheduled||!renderer)return;
    scheduled=true;
    requestAnimationFrame(()=>{scheduled=false;render();});
  }
  function addLabel(text,position,kind='room') {
    const el=document.createElement('span');el.className='scene-label'+(kind==='storage'?' storage':'');el.textContent=text;
    labelsRoot.append(el);labels.push({el,position,kind});
  }
  function mesh(geometry,color,y=0) {
    const item=new THREE.Mesh(geometry,new THREE.MeshLambertMaterial({color,side:THREE.DoubleSide}));
    item.position.y=y;content.add(item);return item;
  }
  function footprint(r,color,y=.025) {
    const [x,z,w,d]=r;
    const item=mesh(new THREE.BoxGeometry(w/1000,.018,d/1000),color,y);
    item.position.x=(x+w/2)/1000;item.position.z=(z+d/2)/1000;return item;
  }
  function outline(points,color,y=.055,closed=false) {
    const p=points.map(v=>new THREE.Vector3(v[0]/1000,y,v[1]/1000));
    const geometry=new THREE.BufferGeometry().setFromPoints(p);
    const material=new THREE.LineDashedMaterial({color,dashSize:.12,gapSize:.08});
    const line=closed?new THREE.LineLoop(geometry,material):new THREE.Line(geometry,material);
    line.computeLineDistances();content.add(line);
  }
  function rectangleOutline(r,color) {
    const [x,z,w,d]=r;outline([[x,z],[x+w,z],[x+w,z+d],[x,z+d]],color,.06,true);
  }
  function disposeContent() {
    if(!content)return;
    scene.remove(content);
    content.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material)o.material.dispose();});
    labelsRoot.replaceChildren();labels=[];
  }
  function buildScene() {
    disposeContent();content=new THREE.Group();scene.add(content);
    current.rooms.forEach(r=>{
      const shape=new THREE.Shape(r.polygon_mm.map(p=>new THREE.Vector2(p[0]/1000,p[1]/1000)));
      const m=mesh(new THREE.ShapeGeometry(shape),r.kind==='wet'||r.kind==='bath'?0xd2e6ed:0xdde6d8);
      m.rotation.x=Math.PI/2;
      const bounds=new THREE.Box2().setFromPoints(r.polygon_mm.map(p=>new THREE.Vector2(p[0]/1000,p[1]/1000)));
      const center=bounds.getCenter(new THREE.Vector2());
      addLabel(r.label||r.id,new THREE.Vector3(center.x,.06,center.y));
    });
    current.fixed.forEach(i=>rectangleOutline(i.rect_mm,0x6d8090));
    current.routes.forEach(r=>outline(r.points_mm,0x4c908d));
    visibleItems(current).forEach((i,n)=>{
      footprint(i.rect_mm,0xa8bcae);
      const [x,z,w,d]=i.rect_mm;
      addLabel((n+1)+'｜'+i.label,new THREE.Vector3((x+w/2)/1000,.07,(z+d/2)/1000),'item');
    });
    rectangleOutline(current.operation_mm,0xb65c1c);
    const b=storageBox(current);
    storageMesh=mesh(new THREE.BoxGeometry(...b.size),0xf0a443);
    storageMesh.position.set(...b.center);
    storageMesh.userData={storageCase:current.id,sourceRectMm:[...current.rect_mm],sourceHeightMm:current.height_mm};
    addLabel('S1｜'+current.label,new THREE.Vector3(b.center[0],b.size[1]+.1,b.center[2]),'storage');
    setView('overview');
    status.textContent='已載入 '+current.id+'。橙色櫃體有指定高度；周邊僅原平面投影，未併原主3D。';
    status.setAttribute('role','status');document.body.dataset.viewerState='ready';
  }
  function setView(next) {
    mode=next;
    const pose=viewPose(current,mode);distance=mode==='storage'?pose.distance:overviewDistance(stage.clientWidth,stage.clientHeight);polar=pose.polar;azimuth=pose.azimuth;target=new THREE.Vector3(...pose.target);schedule();
  }
  function projectedStorage() {
    const bounds=new THREE.Box3().setFromObject(storageMesh),points=[];
    for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
      const p=new THREE.Vector3(x,y,z).project(camera);points.push({x:(p.x+1)*stage.clientWidth/2,y:(1-p.y)*stage.clientHeight/2,z:p.z});
    }
    const left=Math.min(...points.map(p=>p.x)),top=Math.min(...points.map(p=>p.y));
    const right=Math.max(...points.map(p=>p.x)),bottom=Math.max(...points.map(p=>p.y));
    return {left,top,right,bottom,width:right-left,height:bottom-top,
      inFront:points.every(p=>p.z>=-1&&p.z<=1)};
  }
  function layoutLabels(w,h) {
    const candidates=[],enabled=document.getElementById('show-labels').checked;
    linesRoot.replaceChildren();
    labels.forEach(({el,position,kind},id)=>{
      const p=position.clone().project(camera),inside=p.z>=-1&&p.z<=1&&Math.abs(p.x)<1&&Math.abs(p.y)<1;
      el.hidden=!enabled||!inside;
      if(el.hidden)return;
      el.style.visibility='hidden';
      candidates.push({id,x:(p.x+1)*w/2,y:(1-p.y)*h/2,width:el.offsetWidth,height:el.offsetHeight,
        priority:kind==='storage'?0:kind==='item'?1:2});
    });
    const placed=placeLabels(candidates,{width:w,height:h},[projectedStorage()]),byId=new Map(placed.map(p=>[p.id,p.rect]));
    labels.forEach(({el},id)=>{
      const rect=byId.get(id);el.hidden=!rect;
      if(!rect)return;
      el.style.left=rect.left+'px';el.style.top=rect.top+'px';el.style.visibility='visible';
      const anchor=candidates.find(c=>c.id===id),line=document.createElementNS('http://www.w3.org/2000/svg','line');
      line.setAttribute('x1',Math.max(rect.left,Math.min(rect.left+rect.width,anchor.x)));
      line.setAttribute('y1',Math.max(rect.top,Math.min(rect.top+rect.height,anchor.y)));
      line.setAttribute('x2',anchor.x);line.setAttribute('y2',anchor.y);linesRoot.append(line);
    });
  }
  // Owner-run QA samples the rendered body, independently of mesh metadata or labels.
  function bodyPixels(bounds) {
    const canvas=renderer.domElement,gl=renderer.getContext(),sx=canvas.width/stage.clientWidth,sy=canvas.height/stage.clientHeight;
    const x=Math.max(0,Math.floor(bounds.left*sx)),top=Math.max(0,Math.floor(bounds.top*sy));
    const right=Math.min(canvas.width,Math.ceil(bounds.right*sx)),bottom=Math.min(canvas.height,Math.ceil(bounds.bottom*sy));
    const width=right-x,height=bottom-top;
    if(width<=0||height<=0)return {method:'webgl-readPixels-rendered-cabinet-aabb',sampled:0,orange:0,ratio:0};
    const bytes=new Uint8Array(width*height*4);gl.readPixels(x,canvas.height-bottom,width,height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
    const stride=Math.max(1,Math.ceil(Math.max(width,height)/256));let sampled=0,orange=0;
    for(let y=0;y<height;y+=stride)for(let x=0;x<width;x+=stride){
      const i=(y*width+x)*4,r=bytes[i],g=bytes[i+1],b=bytes[i+2];sampled++;
      if(bytes[i+3]>0&&r>90&&g>60&&r>g*1.08&&g>b*1.15&&r-b>35)orange++;
    }
    return {method:'webgl-readPixels-rendered-cabinet-aabb',sampled,orange,ratio:sampled?orange/sampled:0};
  }
  function render() {
    const w=stage.clientWidth,h=stage.clientHeight;
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
    camera.position.set(target.x+distance*Math.sin(polar)*Math.sin(azimuth),target.y+distance*Math.cos(polar),target.z+distance*Math.sin(polar)*Math.cos(azimuth));
    camera.lookAt(target);camera.updateMatrixWorld();renderer.render(scene,camera);renderCount++;
    layoutLabels(w,h);
  }
  select.addEventListener('change',()=>{current=byId.get(select.value);showText();if(renderer)buildScene();});
  document.getElementById('open-items').addEventListener('click',()=>{
    const heading=document.getElementById('item-heading');heading.focus({preventScroll:true});
    heading.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'});
  });
  document.getElementById('return-scene').addEventListener('click',()=>{
    select.focus({preventScroll:true});
    document.getElementById('scene-controls').scrollIntoView({block:'start',inline:'nearest',behavior:'instant'});
  });
  showText();
  try {
    if(!global.THREE)throw Error('本機3D程式未載入');
    scene=new THREE.Scene();scene.background=new THREE.Color(0xe9efe9);
    camera=new THREE.PerspectiveCamera(43,1,.01,150);
    renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    renderer.setPixelRatio(Math.min(global.devicePixelRatio||1,1.5));
    stage.insertBefore(renderer.domElement,linesRoot);
    scene.add(new THREE.HemisphereLight(0xffffff,0x66796a,2));
    const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(-8,14,10);scene.add(light);
    buildScene();
    ['overview','storage','top'].forEach(v=>document.getElementById('view-'+v).addEventListener('click',()=>setView(v)));
    document.getElementById('rotate-left').addEventListener('click',()=>{azimuth-=.3;schedule();});
    document.getElementById('rotate-right').addEventListener('click',()=>{azimuth+=.3;schedule();});
    document.getElementById('show-labels').addEventListener('change',schedule);
    stage.addEventListener('pointerdown',e=>{drag={id:e.pointerId,x:e.clientX,y:e.clientY};stage.setPointerCapture(e.pointerId);});
    stage.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;azimuth-=(e.clientX-drag.x)*.008;polar=Math.max(.025,Math.min(1.48,polar+(e.clientY-drag.y)*.006));drag.x=e.clientX;drag.y=e.clientY;schedule();});
    stage.addEventListener('pointerup',()=>{drag=null;});stage.addEventListener('pointercancel',()=>{drag=null;});
    stage.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(2,Math.min(70,distance*Math.exp(e.deltaY*.001)));schedule();},{passive:false});
    global.addEventListener('resize',schedule);
    const observer=new ResizeObserver(()=>{if(mode!=='storage')distance=overviewDistance(stage.clientWidth,stage.clientHeight);schedule();});observer.observe(stage);
    global.__STORAGE3D_QA__=(includePixels=false)=>{
      const bounds=new THREE.Box3().setFromObject(storageMesh),size=bounds.getSize(new THREE.Vector3());
      const canvas=renderer.domElement,gl=renderer.getContext(),origin=canvas.getBoundingClientRect(),projected=projectedStorage();
      const labelRects=labels.filter(l=>!l.el.hidden).map(({el,kind})=>{
        const r=el.getBoundingClientRect();return {text:el.textContent,kind,left:r.left-origin.left,top:r.top-origin.top,
          width:r.width,height:r.height,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth};
      });
      return {reportHash:data.report_hash,displayRevision:data.display_revision,caseId:current.id,mode,renderCount,storageSizeMm:size.toArray().map(v=>Math.round(v*1000)),
        storageSourceRectMm:storageMesh.userData.sourceRectMm,storageSourceHeightMm:storageMesh.userData.sourceHeightMm,
        polygonHash:current.source_floor_hash,planSha256:current.plan_sha256,labelsChecked:document.getElementById('show-labels').checked,
        webglLost:gl.isContextLost(),canvas:{width:canvas.width,height:canvas.height,clientWidth:canvas.clientWidth,clientHeight:canvas.clientHeight},
        surroundingHeightClaim:'2D-footprints-only',cameraPosition:camera.position.toArray(),storageProjected:projected,labelRects,
        bodyPixels:includePixels?bodyPixels(projected):null};
    };
  } catch(error) {
    document.body.dataset.viewerState='unavailable';status.setAttribute('role','alert');
    status.textContent='這個環境未能啟用3D：'+error.message+'。仍可選樓層、讀品名，並開啟同版平面。';
  }
})(globalThis);
