'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const THREE=require(path.join(root,'assets/vendor/three/three.min.js'));
const html=fs.readFileSync(path.join(root,'structured/candidates/model3d.html'),'utf8');
const source=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];

// Full production IIFE with real Three.js scene math, DOM contract doubles and
// ONLY the WebGLRenderer replaced. No WebGL, browser, screenshot or CSS proof.
class Node {
  constructor(tag='div',id=''){
    this.tagName=tag;this.id=id;this.children=[];this.attrs={};this.style={};this.events={};
    this.className='';this.checked=false;this.disabled=false;this.hidden=false;this.value='on';
    this.clientWidth=1080;this.clientHeight=900;this._text='';this._html='';
    this.classList={contains:name=>this.className.split(' ').includes(name),toggle:(name,on)=>{
      const set=new Set(this.className.split(' ').filter(Boolean));on=on??!set.has(name);
      if(on)set.add(name);else set.delete(name);this.className=[...set].join(' ');return on;
    },add:name=>{this.classList.toggle(name,true);},remove:name=>{this.classList.toggle(name,false);}};
  }
  set innerHTML(value){this._html=value;this.children=[];}
  get innerHTML(){return this._html;}
  set textContent(value){this._text=value;this.children=[];}
  get textContent(){return this._text;}
  setAttribute(key,value){this.attrs[key]=String(value);}
  getAttribute(key){return this.attrs[key]??null;}
  appendChild(child){child.parent=this;this.children.push(child);return child;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
  addEventListener(event,callback){(this.events[event]??=[]).push(callback);}
  dispatchEvent(event){for(const cb of this.events[event.type]||[])cb({target:this,...event});}
  click(){assert.ok(!this.disabled,'control is not disabled: '+this.id);this.dispatchEvent({type:'click'});}
  getContext(){return {fillRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){}};}
  get offsetWidth(){return Math.min(350,String(this._text||this._html).length*6+16);}
  get offsetHeight(){return this.id==='stage-title'?55:this.id==='orientation'?46:36;}
  get offsetTop(){return this.style.top?Number.parseFloat(this.style.top):this.id==='stage-title'?58:0;}
  getBoundingClientRect(){return {left:0,top:this.offsetTop,width:this.offsetWidth,height:this.offsetHeight,
    right:this.offsetWidth,bottom:this.offsetTop+this.offsetHeight};}
}
function descendants(node){return node.children.flatMap(c=>[c,...descendants(c)]);}
function runtime(hash='',width=1080,height=900){
  const nodes={};
  for(const m of html.split('<script>')[0].matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const node=nodes[m[3]]=new Node(m[1],m[3]), attrs=m[2];
    node.checked=/\bchecked(?:\s|\/|>)/.test(attrs);node.hidden=/\bhidden(?:\s|\/|>)/.test(attrs);
    for(const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){node.setAttribute(a[1],a[2]);if(['value','max','min'].includes(a[1]))node[a[1]]=a[2];}
  }
  nodes.stage.clientWidth=width;nodes.stage.clientHeight=height;
  for(const [id,key,values] of [['presentation-mode','data-presentation',['tour','interior','diagnostic']],
    ['geom-source','data-geom',['auto','declared']],['color-mode','data-mode',['kind','provenance']]]){
    for(const value of values){const button=new Node('button');button.setAttribute(key,value);nodes[id].appendChild(button);}
  }
  const document={getElementById:id=>{assert.ok(nodes[id],'known DOM ID '+id);return nodes[id];},
    createElement:tag=>new Node(tag),createElementNS:(_ns,tag)=>new Node(tag),createTextNode:text=>{const n=new Node('#text');n.textContent=text;return n;},
    querySelectorAll:selector=>selector.split(',').flatMap(css=>{
      const m=css.trim().match(/^#([\w-]+) (button|input|\[data-mode="kind"\])$/);assert.ok(m,'known selector '+css);
      return descendants(nodes[m[1]]).filter(n=>m[2].startsWith('[')?n.getAttribute('data-mode')==='kind':n.tagName===m[2]);
    }),querySelector:selector=>document.querySelectorAll(selector)[0]||null};
  const windowEvents={},window={devicePixelRatio:1,addEventListener:(event,cb)=>{(windowEvents[event]??=[]).push(cb);},setTimeout:cb=>{cb();}};
  const location={hash},history={replaceState:(_s,_t,value)=>{location.hash=value;}};
  class Renderer {
    constructor(){this.shadowMap={};}setPixelRatio(){}setClearColor(){}setSize(w,h){nodes.canvas.width=w;nodes.canvas.height=h;}
    render(scene){scene.updateMatrixWorld(true);}
  }
  vm.runInNewContext(source,{THREE:{...THREE,WebGLRenderer:Renderer},document,window,location,history,
    URLSearchParams,requestAnimationFrame(){},console,Event:class{constructor(type){this.type=type;}}});
  return {debug:()=>JSON.parse(JSON.stringify(window.__htmlModel3dDebug())),nodes,
    click:(id)=>nodes[id].click(),
    button:(parent,attribute,value)=>descendants(nodes[parent]).find(n=>n.getAttribute(attribute)===value).click(),
    control:(id,value)=>{const node=nodes[id];if(typeof value==='boolean'){node.checked=value;node.dispatchEvent({type:'change'});}
      else{node.value=String(value);node.dispatchEvent({type:'input'});}},
    hash:value=>{location.hash=value;for(const cb of windowEvents.hashchange||[])cb();},
    resize:(w,h)=>{nodes.stage.clientWidth=w;nodes.stage.clientHeight=h;for(const cb of windowEvents.resize||[])cb();}};
}

test('C1F frontage comparison is off by default, scoped, reversible and preserves indoor furniture at desktop/mobile sizes',()=>{
  for(const [width,height] of [[1080,900],[390,790]]){
    const r=runtime('#mode=tour&building=C&floor=floor-1&room=C:floor-1:garage&view=plan',width,height);
    const before=r.debug();
    assert.equal(r.nodes['frontage-study'].disabled,false);
    assert.deepEqual(before.frontageStudy.visible,[]);
    r.control('frontage-study',true);
    const after=r.debug();
    assert.deepEqual(after.frontageStudy.visible.map(z=>z.id),['clear-route','garden-pocket','waiting-bench']);
    const study=after.tour.rooms.find(room=>room.id==='C:floor-1:garage').features.frontage_study;
    assert.equal(study.status,'conditional-not-installed');assert.equal(study.active_option,'keep-full-clear');
    assert.equal(study.site_use_status,'unknown');
    for(const item of after.frontageStudy.visible){
      const expected=item.id==='clear-route'?study.route_mm:study.zones.find(z=>z.id===item.id).geometry;
      assert.deepEqual(item.geometry,expected);
      assert.equal(item.status,'conditional-not-installed');
      const b=item.renderedBounds;
      assert.ok(Math.abs((b.max[0]-b.min[0])*1000-expected.w_mm)<.01);
      assert.ok(Math.abs((b.max[2]-b.min[2])*1000-expected.h_mm)<.01);
      assert.ok(Math.abs((b.max[1]-b.min[1])*1000-item.height_mm)<.01);
    }
    assert.deepEqual(after.furniture.shapes,before.furniture.shapes);
    assert.deepEqual(after.visibleRooms,before.visibleRooms);
    r.control('architecture',false);assert.deepEqual(r.debug().frontageStudy.visible,[]);
    r.control('architecture',true);assert.equal(r.debug().frontageStudy.visible.length,3);
    r.click('view-exterior');assert.deepEqual(r.debug().frontageStudy.visible,[]);
    r.click('exterior-return');assert.equal(r.debug().frontageStudy.visible.length,3);
    r.button('scope-floors','data-floor','floor-2');
    assert.equal(r.nodes['frontage-study'].disabled,true);assert.deepEqual(r.debug().frontageStudy.visible,[]);
    r.hash('#mode=tour&building=A&floor=floor-1&view=plan');assert.deepEqual(r.debug().frontageStudy.visible,[]);
    r.hash('#mode=tour&building=C&floor=floor-1&view=plan');
    r.control('frontage-study',false);assert.deepEqual(r.debug().frontageStudy.visible,[]);
    assert.deepEqual(r.debug().furniture.shapes,before.furniture.shapes);
  }
});

test('full offline viewer initialization, exterior UI events and return preserve the real indoor scene',()=>{
  const r=runtime('#mode=tour&building=A&floor=floor-2&room=A:floor-2:master-bath&view=front&focus=room');
  const before=r.debug();assert.equal(before.roomCloseup,true);assert.equal(before.roomCutaway.active,true);
  r.control('architecture',false);r.control('navigation',false);r.control('cut',900);r.control('explode',600);
  const custom=r.debug();r.click('view-exterior');
  const exterior=r.debug();assert.deepEqual(exterior.state,{building:'A',floor:'',room:'',view:'exterior'});
  assert.equal(exterior.facade.componentIds.length>200,true);assert.equal(exterior.furniture.visibleItems,0);
  assert.ok(exterior.tour.rooms.every(r=>!r.architectureVisible));assert.equal(r.nodes['facade-review'].hidden,false);
  assert.equal(r.nodes['cut'].disabled,true);assert.equal(r.nodes['exterior-return'].hidden,false);
  r.button('scope-buildings','data-building','B');assert.equal(r.debug().facade.allFloors.length,4);
  r.click('exterior-oblique');assert.equal(r.debug().facade.angle,'oblique');
  r.button('scope-buildings','data-building','overview');assert.equal(r.debug().visibleRooms.length,105);
  assert.equal(r.debug().facade.equipment.length,17);
  r.click('exterior-return');const after=r.debug();
  assert.deepEqual(after.state,custom.state);assert.deepEqual(after.facade.controls,custom.facade.controls);
  assert.deepEqual(after.furniture.pendingItems,custom.furniture.pendingItems);
  assert.deepEqual(after.furniture.shapes,custom.furniture.shapes);
  assert.equal(after.roomCloseup,true);assert.equal(after.facade.active,false);
  assert.equal(r.nodes['cut'].disabled,false);assert.equal(r.nodes['facade-review'].hidden,true);
});

test('direct exterior sharing fits mobile, ignores room scope, and returns actual care/shrine floor controls',()=>{
  const r=runtime('#mode=diagnostic&building=C&floor=floor-1&room=A:floor-2:master-bath&view=exterior&angle=oblique',390,790);
  let d=r.debug();assert.deepEqual(d.state,{building:'C',floor:'',room:'',view:'exterior'});
  assert.equal(d.presentation,'tour');assert.equal(d.facade.allFloors.length,4);
  assert.ok(d.facade.screenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
  r.click('exterior-return');d=r.debug();assert.equal(d.state.floor,'floor-1');assert.equal(d.state.building,'C');
  assert.ok(d.visibleRooms.includes('C:floor-1:elder'));assert.equal(d.facade.controls.navigation.checked,true);
  r.click('view-exterior');r.button('scope-buildings','data-building','B');r.button('scope-floors','data-floor','floor-1');
  d=r.debug();assert.ok(d.visibleRooms.includes('B:floor-1:shrine'));assert.ok(d.visibleRooms.includes('B:floor-1:storage'));
  assert.equal(d.facade.active,false);assert.equal(d.facade.controls['full-walls'].checked,false);
  r.click('view-exterior');r.hash('#mode=tour&building=A&floor=floor-2&room=A:floor-2:master-bath&view=front&focus=room');
  d=r.debug();assert.equal(d.facade.active,false);assert.equal(d.roomCloseup,true);assert.equal(d.roomCutaway.active,true);
  assert.equal(d.furniture.pendingItems.length,2);assert.ok(d.furniture.pendingItems.every(id=>id.startsWith('A:floor-2:walkin:')));
  r.click('view-exterior');r.resize(390,450);assert.ok(r.debug().facade.screenBounds.every(([x,y])=>Math.abs(x)<1&&Math.abs(y)<1));
});

test('exterior return restores an explicit legacy auto-source selection instead of the declared-room default',()=>{
  const r=runtime('#mode=interior&building=A&floor=floor-1&room=A:floor-1:living&view=plan');
  r.button('geom-source','data-geom','auto');const before=r.debug();assert.equal(before.geomSource,'auto');
  r.control('furniture',false);r.click('view-exterior');assert.equal(r.debug().presentation,'tour');
  r.click('exterior-return');const after=r.debug();
  assert.equal(after.presentation,'interior');assert.equal(after.geomSource,'auto');assert.deepEqual(after.state,before.state);
  assert.equal(after.furniture.visible,false);assert.equal(r.nodes.furniture.checked,false);
  assert.deepEqual(after.tour.rooms.map(r=>r.geometry),before.tour.rooms.map(r=>r.geometry));
});
