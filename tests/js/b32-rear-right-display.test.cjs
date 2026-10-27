// Pure policy/DOM-control checks only, never allocate a scene or WebGL context.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../scripts/templates/b32-rear-right-display.js'),'utf8');
function policy(){const c={Number};new vm.Script(source.split('  var b32LabelMode=')[0]).runInNewContext(c);return c;}
const opening={face:'front',width_mm:1130,ratio:.5};
const cell=(key,kind='other')=>({key,kind,id:'B:floor-1:'+key,name:key,is_outdoor:false});
const label=(key,kind='room',roomKind='other',floor='floor-1')=>({kind,mesh:{userData:{cell:cell(key,roomKind),floor:{id:floor}}}});
test('planned door is not described as missing nor as approved access',()=>{
  const p=policy(),c=cell('rear-bath'),features={access_pending:true,doors:[opening],open_connections:[]};
  const before=JSON.stringify(features);assert.equal(p.b32EntryDescription(c,features),'已排門位，通行未核');
  assert(p.b32RoomText(c,features).includes('通行未核'));assert(!p.b32RoomText(c,features).includes('入口待定'));
  assert.equal(JSON.stringify(features),before);
});
test('open seam is distinct from a door; no-opening conditions remain pending',()=>{
  const p=policy(),c=cell('entry');
  assert.equal(p.b32EntryDescription(c,{doors:[],open_connections:[opening]}),'已排開口，通行未核');
  assert.equal(p.b32EntryDescription(c,{doors:[],open_connections:[]}), '入口資料不足，仍待配置');
  assert.equal(p.b32EntryDescription({...c,is_outdoor:true},{doors:[]}), '戶外範圍／使用權利未核');
});
test('invalid or zero-width openings do not erase missing-entry warning',()=>{
  const p=policy();for(const bad of [{...opening,width_mm:0},{...opening,ratio:NaN},{...opening,face:'bad'},null])
    assert.equal(p.b32EntryDescription(cell('bad'),{doors:[bad]}),'入口資料不足，仍待配置');
});
test('compact overview keeps only major room labels, fewer on mobile',()=>{
  const p=policy(),base={mode:'compact',focused:false,selected:'',width:1080};
  assert(p.b32LabelPolicy(label('garage'),base));assert(p.b32LabelPolicy(label('laundry-base'),base));
  assert(!p.b32LabelPolicy(label('garage'),{...base,width:390}));
  assert(!p.b32LabelPolicy(label('laundry-base'),{...base,width:390}));
  for(const key of ['stair1','shrine','storage','rear-bath'])assert(p.b32LabelPolicy(label(key),{...base,width:390}));
  for(const kind of ['entry','window','hvac','study'])assert(!p.b32LabelPolicy(label('storage',kind),base));
  assert.equal(p.b32LabelLimit(base),6);assert.equal(p.b32LabelLimit({...base,width:390}),4);
});
test('compact closeup has no floating text; full mode remains available',()=>{
  const p=policy(),context={mode:'compact',focused:true,selected:'B:floor-1:rear-bath',width:390};
  for(const kind of ['room','entry','window','hvac'])assert(!p.b32LabelPolicy(label('rear-bath',kind),context));
  for(const kind of ['room','entry','window','hvac'])assert(p.b32LabelPolicy(label('rear-bath',kind),{...context,mode:'all'}));
  assert.equal(p.b32LabelLimit({...context,mode:'all'}),Infinity);
});
test('upper-floor key functions and selected spaces are not dropped',()=>{
  const p=policy(),context={mode:'compact',focused:false,selected:'',width:390};
  for(const kind of ['bedroom','bath','stair'])assert(p.b32LabelPolicy(label('upper','room',kind,'floor-2'),context));
  const e=label('laundry-front');assert(p.b32LabelPolicy(e,{...context,selected:e.mesh.userData.cell.id}));
});
test('short names never rewrite full room names or metadata',()=>{
  const p=policy(),c={...cell('rear-bath'),name:'後右有窗公衛（乾轉位／淋浴分區）'},before=JSON.stringify(c);
  assert.equal(p.b32ShortRoomText(c),'後右公衛');assert.equal(JSON.stringify(c),before);
  assert(p.b32ShortRoomText({...c,key:'other',name:'非常長的原始房間名稱保留在完整資訊內'}).length<=12);
});
function controls(href='file:///project/3d.html?labels=compact'){
  const elements={},handlers={},events=[],classes=new Set(['panel-collapsed']);
  function element(id){return elements[id] ||= {id,value:'compact',dataset:{},textContent:'',hidden:false,scrollTop:0,
    style:{},offsetTop:0,offsetHeight:30,classList:{toggle(){}},setAttribute(){},appendChild(){},
    addEventListener(name,fn){handlers[id+':'+name]=fn;},getBoundingClientRect(){return {top:id==='b32-room-details-panel'?300:0};},
    click(){events.push('click:'+id);if(id==='mobile-panel-toggle'){if(classes.has('panel-collapsed'))classes.delete('panel-collapsed');else classes.add('panel-collapsed');}},
    focus(){events.push('focus:'+id);}};}
  const c={Number,URL,location:{href},history:{replaceState(a,b,url){events.push('url:'+url);}},stage:{clientWidth:390},
    roomCameraFocused:true,presentation:'tour',viewState:{room:'B:floor-1:rear-bath'},meshById:{},featuresOf:()=>({doors:[opening]}),
    window:{requestAnimationFrame:fn=>fn(),matchMedia:()=>({matches:true})},
    document:{body:{dataset:{}},getElementById:element,querySelectorAll:()=>[],createElement:()=>element('created')},
    facadeIsActive:()=>false,exteriorAngle:'front',facadeGroups:[]};
  c.stage.classList={toggle(){}};
  c.meshById[c.viewState.room]={userData:{cell:cell('rear-bath')}};
  element('app').classList={contains:name=>classes.has(name)};
  new vm.Script(source).runInNewContext(c);return {c,elements,handlers,events,classes};
}
test('equipment detail and back buttons preserve selection without touching scene visibility',()=>{
  const v=controls(),before=JSON.stringify(v.c.viewState);v.handlers['b32-room-details:click']();
  assert(!v.classes.has('panel-collapsed'));assert(v.elements['b32-room-entry-status'].textContent.includes('已排門位，通行未核'));
  assert(v.events.includes('focus:b32-details-back'));assert(v.elements.panel.scrollTop>0);
  v.handlers['b32-details-back:click']();assert(v.classes.has('panel-collapsed'));assert(v.events.includes('focus:b32-room-details'));
  assert.equal(JSON.stringify(v.c.viewState),before);
});
test('density switch uses only DOM/history and does not rebuild or rescale geometry',()=>{
  const v=controls('file:///project/3d.html?labels=all');assert.equal(v.c.document.body.dataset.b32LabelMode,'all');
  assert.equal(v.elements['furniture-names'].disabled,false);
  v.elements['b32-label-mode'].value='compact';v.handlers['b32-label-mode:change']();
  assert.equal(v.c.document.body.dataset.b32LabelMode,'compact');assert(v.events.some(e=>e.includes('labels=compact')));
  assert.equal(v.elements['furniture-names'].disabled,true);
  assert(!/applyLayout\(|applyViewPreset\(|DATA\s*=|\.scale\./.test(source));
});
test('actual generated facade sync preserves compact/all checkbox rules after initialization and repeated syncs',()=>{
  const viewer=fs.readFileSync(path.join(__dirname,'../../structured/candidates/b32-rear-right-3d.html'),'utf8');
  const sync=viewer.match(/  function syncFacadeControls\(\) \{[\s\S]*?\n  \}/)?.[0];
  assert(sync,'Use the actual emitted facade control function, not a copy of its expected behavior');
  const v=controls();new vm.Script(sync).runInNewContext(v.c);
  for(const mode of ['compact','all','compact','all']){
    v.elements['b32-label-mode'].value=mode;v.handlers['b32-label-mode:change']();
    for(let n=0;n<3;n++){
      v.c.syncFacadeControls();
      assert.equal(v.elements['furniture-names'].disabled,mode!=='all','Facade synchronization must respect '+mode+' mode');
    }
  }
});
test('active exterior state cannot be re-enabled by changing label density',()=>{
  const v=controls('file:///project/3d.html?labels=all');v.c.facadeIsActive=()=>true;
  for(const mode of ['compact','all']){
    v.elements['b32-label-mode'].value=mode;v.handlers['b32-label-mode:change']();
    assert.equal(v.elements['furniture-names'].disabled,true,'Exterior lock still takes priority over '+mode);
  }
});
