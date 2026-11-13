(function(global){
  'use strict';
  function objectBox(item,base){
    const [x,z,w,d]=item.rect_mm,height=item.height_mm;
    if(![x,z,w,d,base,item.mount_mm].every(Number.isFinite)||w<=0||d<=0||
       (height!==null&&(!Number.isFinite(height)||height<=0)))throw Error('Invalid source body envelope');
    const h=height===null?12:height;
    return {size:[w/1000,h/1000,d/1000],center:[(x+w/2)/1000,(base+item.mount_mm+h/2)/1000,(z+d/2)/1000],
      footprintOnly:height===null};
  }
  function surfaceTriangles(positions){
    const result=[];
    for(let n=0;n<positions.length;n+=9)result.push([[positions[n],positions[n+2]],[positions[n+3],positions[n+5]],[positions[n+6],positions[n+8]]]);
    return result;
  }
  function pointInTriangle(p,t){
    const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    const v=[cross(t[0],t[1],p),cross(t[1],t[2],p),cross(t[2],t[0],p)];
    return v.every(x=>x>=-1e-8)||v.every(x=>x<=1e-8);
  }
  function pose(floor,mode){
    const s=floor.source_floor.storage,r=s.rect_mm,b=floor.base_mm/1000;
    if(mode==='storage')return {target:[(r[0]+r[2]/2)/1000,b+s.height_mm/2000,(r[1]+r[3]/2)/1000],
      distance:Math.max(3.6,s.height_mm/1000*2.5),azimuth:-.7,polar:.95};
    if(mode==='stair')return {target:[1.2,b-.4,6.4],distance:11,azimuth:-.7,polar:.8};
    return {target:[3,b,8.815],distance:25,azimuth:-.7,polar:mode==='top'?.025:.65};
  }
  function roomDisplayName(floor,room){
    return floor.id==='B-2F'&&room.id==='stair'?'二樓L形到達／一樓原梯接Q3上層改梯':room.label;
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={objectBox,surfaceTriangles,pointInTriangle,pose,roomDisplayName};
  if(typeof document==='undefined')return;
  const data=JSON.parse(document.getElementById('b-upper-data').textContent),byId=new Map(data.floors.map(f=>[f.id,f]));
  const select=document.getElementById('floor-select'),stateSelect=document.getElementById('state-select'),stage=document.getElementById('stage');
  const labelsRoot=document.getElementById('labels'),linesRoot=document.getElementById('label-lines'),status=document.getElementById('status');
  const {placeLabels}=global.B_UPPER_LABELS;
  let current=byId.get(data.default_floor),stateId=data.default_state,mode='storage',scene,camera,renderer,content,surfaceMesh;
  let bodies=[],treadMeshes=[],labels=[],scheduled=false,renderCount=0,lastStamp=null,target,distance=5,azimuth=-.7,polar=.95,drag=null;
  data.floors.forEach(f=>{const o=document.createElement('option');o.value=f.id;o.textContent=f.id+'｜'+f.source_floor.storage.label;select.append(o);});
  function state(){return current.states.find(s=>s.id===stateId);}
  function storageEntry(){return bodies.find(b=>b.item.source.storage_case);}
  function stamp(){return JSON.stringify([current.id,stateId,mode,stage.clientWidth,stage.clientHeight,
    camera.position.toArray(),camera.quaternion.toArray(),camera.projectionMatrix.elements,document.getElementById('show-labels').checked]);}
  function ready(){return !!renderer&&!scheduled&&lastStamp===stamp()&&renderer.getSize(new THREE.Vector2()).x===stage.clientWidth&&renderer.getSize(new THREE.Vector2()).y===stage.clientHeight;}
  function entryLink(){
    const entry=document.getElementById('entry-select').value,use=document.getElementById('use-select').value;
    document.getElementById('ground-plan-link').href=entry+'_'+use+'_floor-1.svg';
  }
  function showText(){
    select.value=current.id;stateSelect.value=stateId;
    const s=current.source_floor.storage;
    document.getElementById('readout').textContent=current.id+'｜'+s.label+'｜'+s.rect_mm.slice(2).join('×')+'×'+s.height_mm+'mm｜'+(stateId==='storage'?'加櫃比較':'原配置對照');
    document.getElementById('identity').textContent=current.id+' · '+(stateId==='storage'?'加櫃比較':'原配置對照')+' · 未採用｜標高+'+current.base_mm+'mm';
    document.getElementById('case-note').textContent=s.note;
    document.getElementById('plan-link').href=state().plan_file;
    const list=document.getElementById('item-list');list.replaceChildren();
    const ordered=[...state().display_objects].sort((a,b)=>Number(!!b.source.storage_case)-Number(!!a.source.storage_case));
    ordered.forEach(item=>{const li=document.createElement('li');
      li.textContent=item.label+'｜'+item.rect_mm.slice(2).join('×')+'mm；'+(item.height_mm===null?'只畫平面投影':
        '高'+item.height_mm+'mm'+(item.height_basis==='owner-storage-proposal'?'（收納提案）':'（沿原概念外廓，非實測）'));list.append(li);});
    current.source_floor.fixed.forEach(i=>{const li=document.createElement('li');li.textContent=i.label+'｜原平面預留，未選產品';list.append(li);});
    document.getElementById('source-note').textContent='本批 '+data.report_hash+'；原ABC與已驗收A／C不改，這份B比較畫面待另驗。';
    document.body.dataset.floor=current.id;document.body.dataset.use=stateId;entryLink();
  }
  function schedule(){if(scheduled||!renderer)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;render();});}
  function label(text,p,kind='room'){const el=document.createElement('span');el.className='scene-label'+(kind==='storage'?' storage':'');el.textContent=text;
    labelsRoot.append(el);labels.push({el,position:p,kind});}
  function mesh(geo,color){const m=new THREE.Mesh(geo,new THREE.MeshLambertMaterial({color,side:THREE.DoubleSide}));content.add(m);return m;}
  function box(rect,height,bottom,color){const [x,z,w,d]=rect,m=mesh(new THREE.BoxGeometry(w/1000,height/1000,d/1000),color);
    m.position.set((x+w/2)/1000,(bottom+height/2)/1000,(z+d/2)/1000);return m;}
  function polygonGeometry(records,y){
    const shapes=records.map(rec=>{const shape=new THREE.Shape(rec.outer.map(p=>new THREE.Vector2(p[0]/1000,p[1]/1000)));
      rec.holes.forEach(h=>shape.holes.push(new THREE.Path(h.map(p=>new THREE.Vector2(p[0]/1000,p[1]/1000)))));return shape;});
    const g=new THREE.ShapeGeometry(shapes);g.rotateX(Math.PI/2);g.translate(0,y,0);return g;
  }
  function outline(points,y,color,closed=true){
    const p=points.map(v=>new THREE.Vector3(v[0]/1000,y,v[1]/1000)),g=new THREE.BufferGeometry().setFromPoints(p);
    const material=new THREE.LineDashedMaterial({color,dashSize:.12,gapSize:.08}),line=closed?new THREE.LineLoop(g,material):new THREE.Line(g,material);
    line.computeLineDistances();content.add(line);
  }
  function rectOutline(r,y,color){const [x,z,w,d]=r;outline([[x,z],[x+w,z],[x+w,z+d],[x,z+d]],y,color);}
  function resetContent(){if(content){scene.remove(content);content.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material)o.material.dispose();});}
    content=new THREE.Group();scene.add(content);labelsRoot.replaceChildren();linesRoot.replaceChildren();labels=[];bodies=[];treadMeshes=[];lastStamp=null;}
  function buildScene(){
    resetContent();
    const base=current.base_mm/1000;
    surfaceMesh=mesh(polygonGeometry(current.surface_polygons_mm,base),0xdce7d7);
    current.source_floor.rooms.forEach(r=>{
      outline(r.polygon_mm,base+.035,r.id==='dry-protection'?0xa36565:0x718579);
      outline(r.polygon_mm,base+data.config.boundary_display_height_mm/1000,0x9da79b);
      r.polygon_mm.slice(0,-1).forEach(p=>{
        const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(p[0]/1000,base,p[1]/1000),
          new THREE.Vector3(p[0]/1000,base+data.config.boundary_display_height_mm/1000,p[1]/1000)]);
        content.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0x9da79b})));
      });
    });
    current.room_anchors.forEach(r=>label(roomDisplayName(current,r),new THREE.Vector3(r.point_mm[0]/1000,base+.08,r.point_mm[1]/1000),r.id==='stair'?'stair':'room'));
    current.source_floor.fixed.forEach(r=>rectOutline(r.rect_mm,base+.05,0x7d8194));
    const st=current.source_floor.stair_interface,pads=st.arrival_polygons_mm||[st.arrival_polygon_mm];
    pads.forEach(p=>mesh(polygonGeometry([{outer:p,holes:[]}],base+.006),0xa5c899));
    current.stairs.forEach(t=>treadMeshes.push({source:t,mesh:box(t.rect_mm,t.height_mm,t.top_mm-t.height_mm,0x839c9f)}));
    current.middle_landings.forEach(p=>mesh(polygonGeometry([{outer:[[p.rect_mm[0],p.rect_mm[1]],[p.rect_mm[0]+p.rect_mm[2],p.rect_mm[1]],
      [p.rect_mm[0]+p.rect_mm[2],p.rect_mm[1]+p.rect_mm[3]],[p.rect_mm[0],p.rect_mm[1]+p.rect_mm[3]]],holes:[]}],p.top_mm/1000),0x8fa7a2));
    state().display_objects.forEach(item=>{
      const b=objectBox(item,current.base_mm),m=mesh(new THREE.BoxGeometry(...b.size),item.source.storage_case?0xf0a443:item.height_mm===null?0xc6cfc1:0xa7bbb2);
      m.position.set(...b.center);bodies.push({item,mesh:m});
      label(item.label,new THREE.Vector3(b.center[0],b.center[1]+b.size[1]/2+.1,b.center[2]),item.source.storage_case?'storage':'item');
    });
    const s=current.source_floor.storage;rectOutline(s.operation_mm,base+.06,0xba7029);
    if(st.stairwell_keep_open_mm)rectOutline(st.stairwell_keep_open_mm,base+.08,0xae6652);
    if(current.source_floor.roof_opening_mm)rectOutline(current.source_floor.roof_opening_mm,base+.08,0xae6652);
    setView(mode);status.textContent='已載入同版 '+current.id+'。樓板保留來源開口，未列高度的物件只畫平面。';document.body.dataset.viewerState='ready';
  }
  function overviewDistance(){const a=Math.max(.1,stage.clientWidth/stage.clientHeight),half=Math.atan(Math.tan(43*Math.PI/360)*Math.min(1,a));
    return Math.hypot(3,8.815,3)/Math.sin(half)*1.16;}
  function setView(next){mode=next;const p=pose(current,next);target=new THREE.Vector3(...p.target);distance=next==='overview'||next==='top'?overviewDistance():p.distance;
    azimuth=p.azimuth;polar=p.polar;schedule();}
  function bounds(meshObj){
    const b=new THREE.Box3().setFromObject(meshObj),points=[];
    for(const x of [b.min.x,b.max.x])for(const y of [b.min.y,b.max.y])for(const z of [b.min.z,b.max.z]){
      const p=new THREE.Vector3(x,y,z).project(camera);points.push({x:(p.x+1)*stage.clientWidth/2,y:(1-p.y)*stage.clientHeight/2,z:p.z});}
    const left=Math.min(...points.map(p=>p.x)),right=Math.max(...points.map(p=>p.x)),top=Math.min(...points.map(p=>p.y)),bottom=Math.max(...points.map(p=>p.y));
    return {left,right,top,bottom,width:right-left,height:bottom-top,inFront:points.every(p=>p.z>=-1&&p.z<=1)};
  }
  function storageBounds(){const e=storageEntry();return e?bounds(e.mesh):null;}
  function layoutLabels(){
    const w=stage.clientWidth,h=stage.clientHeight,enabled=document.getElementById('show-labels').checked,candidates=[];linesRoot.replaceChildren();
    labels.forEach(({el,position,kind},id)=>{const p=position.clone().project(camera);
      el.hidden=!enabled||p.z< -1||p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1;if(el.hidden)return;el.style.visibility='hidden';
      candidates.push({id,x:(p.x+1)*w/2,y:(1-p.y)*h/2,width:el.offsetWidth,height:el.offsetHeight,priority:kind==='storage'?0:kind==='item'||kind==='stair'?1:2});});
    const body=storageBounds(),placed=placeLabels(candidates,{width:w,height:h},body?[body]:[]),byId=new Map(placed.map(p=>[p.id,p.rect]));
    labels.forEach(({el},id)=>{const r=byId.get(id);el.hidden=!r;if(!r)return;el.style.left=r.left+'px';el.style.top=r.top+'px';el.style.visibility='visible';
      const c=candidates.find(c=>c.id===id),line=document.createElementNS('http://www.w3.org/2000/svg','line');
      Object.entries({x1:Math.max(r.left,Math.min(r.left+r.width,c.x)),y1:Math.max(r.top,Math.min(r.top+r.height,c.y)),x2:c.x,y2:c.y}).forEach(([k,v])=>line.setAttribute(k,v));linesRoot.append(line);});
  }
  function bodyPixels(b){
    if(!b)return null;const canvas=renderer.domElement,gl=renderer.getContext(),sx=canvas.width/stage.clientWidth,sy=canvas.height/stage.clientHeight;
    const x=Math.max(0,Math.floor(b.left*sx)),top=Math.max(0,Math.floor(b.top*sy)),right=Math.min(canvas.width,Math.ceil(b.right*sx)),bottom=Math.min(canvas.height,Math.ceil(b.bottom*sy));
    const w=right-x,h=bottom-top;if(w<=0||h<=0)return {method:'webgl-readPixels-cabinet-aabb',sampled:0,orange:0,ratio:0};
    const bytes=new Uint8Array(w*h*4);gl.readPixels(x,canvas.height-bottom,w,h,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
    let sampled=0,orange=0;const stride=Math.max(1,Math.ceil(Math.max(w,h)/220));
    for(let row=0;row<h;row+=stride)for(let col=0;col<w;col+=stride){const i=(row*w+col)*4,r=bytes[i],g=bytes[i+1],b=bytes[i+2];sampled++;
      if(bytes[i+3]>0&&r>90&&g>60&&r>g*1.08&&g>b*1.15&&r-b>35)orange++;}
    return {method:'webgl-readPixels-cabinet-aabb',sampled,orange,ratio:sampled?orange/sampled:0};
  }
  function render(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
    camera.position.set(target.x+distance*Math.sin(polar)*Math.sin(azimuth),target.y+distance*Math.cos(polar),target.z+distance*Math.sin(polar)*Math.cos(azimuth));
    camera.lookAt(target);camera.updateMatrixWorld();renderer.render(scene,camera);renderCount++;layoutLabels();lastStamp=stamp();}
  function qa(pixels=false){
    const entry=storageEntry(),b=storageBounds(),canvas=renderer.domElement,origin=canvas.getBoundingClientRect();
    let positions=surfaceMesh.geometry.attributes.position.array;
    if(surfaceMesh.geometry.index){const array=[],index=surfaceMesh.geometry.index.array;for(const n of index)array.push(...positions.slice(n*3,n*3+3));positions=array;}
    const triangles=surfaceTriangles(Array.from(positions));
    return {schema:'house-b-upper-runtime-v1',displayRevision:data.display_revision,reportHash:data.report_hash,floor:current.id,state:stateId,mode,ready:ready(),renderCount,
      webglLost:renderer.getContext().isContextLost(),surfaceTrianglesM:triangles,
      cabinet:entry?{rectMm:entry.item.rect_mm,meshSizeMm:new THREE.Box3().setFromObject(entry.mesh).getSize(new THREE.Vector3()).toArray().map(v=>v*1000),
        meshMinMm:new THREE.Box3().setFromObject(entry.mesh).min.toArray().map(v=>v*1000),projected:b,pixels:pixels?bodyPixels(b):null}:null,
      objects:bodies.map(({item,mesh})=>{const box=new THREE.Box3().setFromObject(mesh);return {key:item.key,heightBasis:item.height_basis,
        minMm:box.min.toArray().map(v=>v*1000),sizeMm:box.getSize(new THREE.Vector3()).toArray().map(v=>v*1000)};}),
      treads:treadMeshes.map(({source,mesh})=>({id:source.id,minMm:new THREE.Box3().setFromObject(mesh).min.toArray().map(v=>v*1000),
        maxMm:new THREE.Box3().setFromObject(mesh).max.toArray().map(v=>v*1000)})),
      sceneLabels:labels.map(({el,kind})=>({kind,text:el.textContent,hidden:el.hidden})),
      labelsChecked:document.getElementById('show-labels').checked,labelRects:labels.filter(l=>!l.el.hidden).map(({el,kind})=>{const r=el.getBoundingClientRect();return {kind,text:el.textContent,
        left:r.left-origin.left,top:r.top-origin.top,width:r.width,height:r.height,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth};}),
      canvas:{width:canvas.width,height:canvas.height,clientWidth:canvas.clientWidth,clientHeight:canvas.clientHeight},
      cameraPosition:camera.position.toArray(),stamp:stamp(),lastDrawStamp:lastStamp};
  }
  select.addEventListener('change',()=>{current=byId.get(select.value);showText();if(renderer)buildScene();});
  stateSelect.addEventListener('change',()=>{stateId=stateSelect.value;showText();if(renderer)buildScene();});
  ['entry-select','use-select'].forEach(id=>document.getElementById(id).addEventListener('change',entryLink));
  document.getElementById('open-items').addEventListener('click',()=>{const e=document.getElementById('item-heading');e.focus({preventScroll:true});e.scrollIntoView({block:'start',behavior:'instant'});});
  document.getElementById('return-scene').addEventListener('click',()=>{select.focus({preventScroll:true});document.getElementById('scene-controls').scrollIntoView({block:'start',behavior:'instant'});});
  showText();
  try{
    if(!global.THREE)throw Error('本機3D程式未載入');
    scene=new THREE.Scene();scene.background=new THREE.Color(0xedf2ec);camera=new THREE.PerspectiveCamera(43,1,.01,180);
    renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(global.devicePixelRatio||1,1.5));stage.insertBefore(renderer.domElement,linesRoot);
    scene.add(new THREE.HemisphereLight(0xffffff,0x66796a,2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(-8,20,12);scene.add(light);
    ['storage','overview','stair','top'].forEach(v=>document.getElementById('view-'+v).addEventListener('click',()=>setView(v)));
    document.getElementById('rotate-left').addEventListener('click',()=>{azimuth-=.3;schedule();});document.getElementById('rotate-right').addEventListener('click',()=>{azimuth+=.3;schedule();});
    document.getElementById('show-labels').addEventListener('change',schedule);
    stage.addEventListener('pointerdown',e=>{drag={id:e.pointerId,x:e.clientX,y:e.clientY};stage.setPointerCapture(e.pointerId);});
    stage.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;azimuth-=(e.clientX-drag.x)*.008;polar=Math.max(.025,Math.min(1.48,polar+(e.clientY-drag.y)*.006));drag.x=e.clientX;drag.y=e.clientY;schedule();});
    stage.addEventListener('pointerup',()=>{drag=null;});stage.addEventListener('pointercancel',()=>{drag=null;});
    stage.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(2,Math.min(90,distance*Math.exp(e.deltaY*.001)));schedule();},{passive:false});
    new ResizeObserver(()=>{if(mode==='overview'||mode==='top')distance=overviewDistance();schedule();}).observe(stage);
    buildScene();global.__B_UPPER_QA__=qa;
  }catch(error){document.body.dataset.viewerState='unavailable';status.setAttribute('role','alert');status.textContent='3D未能啟用：'+error.message+'；仍可讀品名及同版平面。';}
})(globalThis);
