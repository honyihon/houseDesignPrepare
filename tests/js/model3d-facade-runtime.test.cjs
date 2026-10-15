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
  // Declared layout measurements, not browser/CSS evidence. Stage-relative
  // positions must be realistic or the production safe-area fit is untested.
  get stage(){return this.layout?.stage||this.parent?.stage;}
  get landscape(){return this.stage?.clientWidth<=860 && this.stage?.clientHeight<=400;}
  get offsetWidth(){
    if(this.id==='stage')return this.clientWidth;
    if(this.id==='stage-title')return Math.min(this.landscape?600:350,this.stage.clientWidth-90);
    if(this.id==='room-view-actions')return Math.min(450,this.stage.clientWidth-28);
    if(this.id==='study-stage-note'||this.id==='orientation')return this.landscape?330:Math.min(350,this.stage.clientWidth-28);
    if(this.id==='mdf-study-note')return this.landscape?this.stage.clientWidth/2-28:Math.min(650,this.stage.clientWidth-28);
    return Math.min(350,String(this._text||this._html).length*6+16);
  }
  get offsetHeight(){
    if(this.id==='stage')return this.clientHeight;
    if(this.id==='stage-title')return this.landscape?36:55;
    if(this.id==='room-view-actions')return this.landscape?44:(this.layout.nodes['room-cutaway-status'].hidden?44:76);
    if(this.id==='mdf-study-note')return this.stage.clientWidth<=860?70:46;
    return this.id==='orientation'||this.id==='study-stage-note'?46:this.id==='compass'?54:36;
  }
  get offsetTop(){
    if(this.style.top)return Number.parseFloat(this.style.top);
    if(this.id==='stage-title')return this.landscape?12:this.stage.clientWidth<=860?62:58;
    if(this.id==='orientation')return this.stage.clientHeight-this.offsetHeight-8;
    if(this.id==='study-stage-note')return this.stage.clientHeight-this.offsetHeight-
      (this.style.bottom?Number.parseFloat(this.style.bottom):this.landscape?8:56);
    if(this.id==='mdf-study-note')return this.stage.clientHeight-this.offsetHeight-
      (this.style.bottom?Number.parseFloat(this.style.bottom):this.landscape?8:58);
    return ['hud','compass','facade-actions'].includes(this.id)?14:0;
  }
  getBoundingClientRect(){
    const left=this.id==='stage'?0:this.id==='study-stage-note'&&this.landscape?
      this.stage.clientWidth-this.offsetWidth-14:14;
    return {left,top:this.offsetTop,width:this.offsetWidth,height:this.offsetHeight,
      right:left+this.offsetWidth,bottom:this.offsetTop+this.offsetHeight};
  }
  getClientRects(){
    const hidden=this.hidden||(this.id==='hud'&&this.stage.clientWidth<=860)||
      (this.id==='facade-actions'&&['capacity-study','c1f-study','bc-study'].some(name=>this.layout.body.classList.contains(name)));
    return hidden?[]:[this.getBoundingClientRect()];
  }
}
function descendants(node){return node.children.flatMap(c=>[c,...descendants(c)]);}
function runtime(hash='',width=1080,height=900,options={}){
  const studyName=options.bc?'bc-options':options.capacity?'arcade-capacity':options.study?'c1f-options':null;
  const runtimeHtml=studyName?fs.readFileSync(path.join(root,'structured/candidates/'+studyName+'-3d.html'),'utf8'):html;
  const runtimeSource=studyName?[...runtimeHtml.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1]:source;
  const nodes={};
  for(const m of runtimeHtml.split('<script>')[0].matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const node=nodes[m[3]]=new Node(m[1],m[3]), attrs=m[2];
    node.checked=/\bchecked(?:\s|\/|>)/.test(attrs);node.hidden=/\bhidden(?:\s|\/|>)/.test(attrs);
    for(const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){node.setAttribute(a[1],a[2]);if(['value','max','min'].includes(a[1]))node[a[1]]=a[2];}
  }
  nodes.stage.clientWidth=width;nodes.stage.clientHeight=height;
  for(const [id,key,values] of [['presentation-mode','data-presentation',['tour','interior','diagnostic']],
    ['geom-source','data-geom',['auto','declared']],['color-mode','data-mode',['kind','provenance']]]){
    for(const value of values){const button=new Node('button');button.setAttribute(key,value);nodes[id].appendChild(button);}
  }
  const documentEvents={},body=new Node('body'),heading=new Node('h1');
  for(const node of Object.values(nodes))node.layout={stage:nodes.stage,nodes,body};
  const find=id=>nodes[id]||Object.values(nodes).flatMap(descendants).find(n=>n.id===id);
  const document={body,hidden:false,addEventListener:(event,callback)=>{(documentEvents[event]??=[]).push(callback);},
    getElementById:id=>{const node=find(id);assert.ok(node||id==='study-stage-note','known DOM ID '+id);return node||null;},
    createElement:tag=>new Node(tag),createElementNS:(_ns,tag)=>new Node(tag),createTextNode:text=>{const n=new Node('#text');n.textContent=text;return n;},
    querySelectorAll:selector=>selector.split(',').flatMap(css=>{
      const m=css.trim().match(/^#([\w-]+) (button|input|\[data-mode="kind"\])$/);assert.ok(m,'known selector '+css);
      return descendants(nodes[m[1]]).filter(n=>m[2].startsWith('[')?n.getAttribute('data-mode')==='kind':n.tagName===m[2]);
    }),querySelector:selector=>selector==='h1'?heading:selector==='#renderer-fallback a'?
      find('renderer-fallback')?.children.find(n=>n.tagName==='a')||null:document.querySelectorAll(selector)[0]||null};
  const windowEvents={},window={devicePixelRatio:1,addEventListener:(event,cb)=>{(windowEvents[event]??=[]).push(cb);},setTimeout:cb=>{cb();}};
  const assigned=[],frames=new Map();let frameId=0,renderCount=0;
  const location={hash,href:'file:///project/structured/candidates/'+(studyName?studyName+'-3d.html'+
    (options.bare?'':'?scheme='+options.scheme):'model3d.html')+hash,
    assign:value=>assigned.push(value),replace:value=>assigned.push(value),reload:()=>assigned.push('reload')},history={replaceState:(_s,_t,value)=>{
      const url=new URL(value,location.href),current=new URL(location.href);
      assert.equal(url.pathname,current.pathname,'file history cannot change the document path');
      assert.equal(url.search,current.search,'file history cannot change its query; use real navigation');
      location.href=url.href;location.hash=url.hash;
    }};
  class Renderer {
    constructor(){if(options.noWebGL)throw new Error('WebGL unavailable');this.shadowMap={};}setPixelRatio(){}setClearColor(){}setSize(w,h){nodes.canvas.width=w;nodes.canvas.height=h;}
    render(scene){renderCount++;scene.updateMatrixWorld(true);}
  }
  vm.runInNewContext(runtimeSource,{THREE:{...THREE,WebGLRenderer:Renderer},document,window,location,history,
    URL,URLSearchParams,requestAnimationFrame:cb=>{frames.set(++frameId,cb);return frameId;},cancelAnimationFrame:id=>frames.delete(id),console,
    Event:class{constructor(type){this.type=type;}}});
  return {debug:()=>JSON.parse(JSON.stringify(window.__htmlModel3dDebug())),nodes,find,body,location,assigned,frames,
    get renderCount(){return renderCount;},
    hidden:value=>{document.hidden=value;for(const cb of documentEvents.visibilitychange||[])cb();},
    frame:()=>{const [id,cb]=frames.entries().next().value;frames.delete(id);cb();},
    click:(id)=>nodes[id].click(),
    button:(parent,attribute,value)=>descendants(nodes[parent]).find(n=>n.getAttribute(attribute)===value).click(),
    control:(id,value)=>{const node=nodes[id];if(typeof value==='boolean'){node.checked=value;node.dispatchEvent({type:'change'});}
      else{node.value=String(value);node.dispatchEvent({type:'input'});}},
    hash:value=>{location.hash=value;for(const cb of windowEvents.hashchange||[])cb();},
    resize:(w,h)=>{nodes.stage.clientWidth=w;nodes.stage.clientHeight=h;for(const cb of windowEvents.resize||[])cb();}};
}

test('BC real scene math matches all twenty unadopted floor plans and retains declared pending items',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  function checkBcOption\(option, floor, debug\) \{[\s\S]*?\n  }/)?.[0];
  assert.ok(definition,'production Windows BC checker is exercised');
  const check=vm.runInNewContext(definition+'\ncheckBcOption',{assert:(condition,message)=>assert.ok(condition,message)});
  const study=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/bc-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_BC_OPTIONS = /,'').replace(/;\s*$/,''));
  for(const option of study.options) {
    const r=runtime('#mode=tour&building='+option.building+'&floor=floor-1&view=plan',1080,900,{bc:true,scheme:option.id});
    assert.equal(r.body.getAttribute('data-study-option'),option.id);
    assert.ok(r.body.classList.contains('bc-study'),'display styles have their own comparison scope');
    assert.ok(!r.body.classList.contains('c1f-study'));
    assert.equal(r.find('study-stage-note').getAttribute('role'),'status');
    assert.equal(r.find('study-stage-note').getAttribute('aria-live'),'polite');
    assert.equal(r.find('study-stage-note').textContent,option.label+' · 比較，未採用／未核');
    assert.equal(r.nodes['study-plan-link'].href,'bc-options.html#'+option.id);
    for(const floor of option.plans.floors) {
      r.button('scope-floors','data-floor',floor.id);r.frame();
      const debug=r.debug();
      check(option,floor,debug);
      assert.equal(debug.layoutReview.status,'comparison-only-not-adopted');
      assert.equal(debug.bcOption.geometry_review.religious_acceptance,'unknown');
      const item=floor.rooms.find(room=>room.furniture.length);
      if(item) {
        r.button('scope-rooms','data-room',item.id);
        assert.match(r.nodes.info.innerHTML,new RegExp('bc-options.html#'+option.id));
        assert.match(r.nodes.info.innerHTML,/取捨未定/);
      }
    }
  }
});

test('BC file query normalization occurs before allocation; switching reloads only comparison',()=>{
  for(const options of [{bc:true,bare:true},{bc:true,scheme:'invalid'}]) {
    const r=runtime('#building=C&floor=floor-1',1080,900,options);
    assert.equal(r.renderCount,0);
    assert.equal(r.assigned.length,1);
    assert.match(r.assigned[0],/bc-options-3d.html\?scheme=b-strict/);
  }
  const r=runtime('#building=C&floor=floor-1',1080,900,{bc:true,scheme:'b-strict'});
  assert.equal(r.debug().state.building,'B');
  r.nodes['study-scheme'].value='c-side-bed';r.nodes['study-scheme'].dispatchEvent({type:'change'});
  assert.equal(r.assigned.length,1);
  assert.match(r.assigned[0],/bc-options-3d.html\?scheme=c-side-bed#mode=tour&building=C/);
  assert.equal(r.debug().bcOption.id,'b-strict','existing scene is not mutably replaced or adopted');
  assert.equal(runtime('#mode=tour&building=B&floor=floor-1').debug().bcOption,null);
  assert.ok(!runtime('#mode=tour&building=B&floor=floor-1').body.classList.contains('bc-study'));
});

test('BC mobile camera fits comparison overlay and full furniture without masking whole rooms',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  const check=vm.runInNewContext(definition+'\ncheckCameraFraming',{assert:(condition,message)=>assert.ok(condition,message)});
  for(const [scheme,bid,key] of [['b-strict','B','shrine'],['c-side-bed','C','elder']]) {
    const id=bid+':floor-1:'+key;
    for(const [width,height] of [[390,790],[844,336]]) {
      const r=runtime('#mode=tour&building='+bid+'&floor=floor-1&room='+encodeURIComponent(id)+'&focus=room&view=front',width,height,{bc:true,scheme});
      r.click('mobile-panel-toggle');r.frame();
      const debug=r.debug();
      check(debug,id);
      assert.ok(debug.cameraFraming.overlays.some(o=>o.id==='study-stage-note'));
      assert.ok(!debug.cameraFraming.overlays.some(o=>o.id==='facade-actions'),'unrelated facade controls do not reserve comparison camera space');
      assert.equal(debug.visibleRooms.length,11,'closeup retains the entire eleven-room floor');
    }
  }
});

test('minimal fengshui real scene transforms retain full worktops, original products and unadopted decisions',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  function checkMinimalFengshui\(building, floor, debug\) \{[\s\S]*?\n  }/)?.[0];
  const fitDefinition=checkPages.toString().match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);assert.ok(fitDefinition);
  const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  const sharedFloors=Object.fromEntries(shared.buildings.flatMap(b=>b.floors.map(f=>[b.id+':'+f.id,f])));
  const check=vm.runInNewContext(definition+'\ncheckMinimalFengshui',{
    sharedFloors,assert:(condition,message)=>assert.ok(condition,message)});
  const checkFit=vm.runInNewContext(fitDefinition+'\ncheckCameraFraming',{
    assert:(condition,message)=>assert.ok(condition,message)});
  for(const [b,f,key] of [['A','floor-1','kitchen'],['B','floor-2','living2'],['B','floor-3','guest3'],
    ['C','floor-3','master3f'],['B','floor-1',null],['C','floor-1',null]]){
    for(const [w,h] of [[1080,900],[390,790],[844,336]]){
      const prefix='#mode=tour&building='+b+'&floor='+f+'&view=front';
      const r=runtime(prefix,w,h),floor=sharedFloors[b+':'+f],before=r.debug();
      // Box3 is evaluated from real Three.js meshes, not a copied placement fixture.
      check(b,floor,before);
      if(!key)continue;
      const id=b+':'+f+':'+key;
      r.hash(prefix+'&room='+id+'&focus=room');
      const focused=r.debug();check(b,floor,focused);checkFit(focused,id);
      assert.ok(focused.roomCloseup);
      assert.deepEqual(focused.visibleRooms,before.visibleRooms,'closeup preserves the whole floor');
      assert.deepEqual(focused.furniture.shapes,before.furniture.shapes,'camera never repositions or resizes furniture');
      assert.ok(r.nodes.info.innerHTML.includes('風水最小修改／待決'),'room info retains partial/pending scope');
      r.click('room-overview');check(b,floor,r.debug());
    }
  }
});

test('capacity study real scene math retains all four levels, normal products and honest failure across desktop/mobile',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/    const checkCapacityOption = \(option, building, floor, debug\) => \{[\s\S]*?\n    };/)?.[0];
  assert.ok(definition,'shared Windows capacity QA definition');
  const check=vm.runInNewContext(definition+'\ncheckCapacityOption',{assert:(condition,message)=>assert.ok(condition,message)});
  const fitDefinition=checkPages.toString().match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(fitDefinition,'serialized camera-framing QA');
  const checkFit=vm.runInNewContext(fitDefinition+'\ncheckCameraFraming',{assert:(condition,message)=>assert.ok(condition,message)});
  const study=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/arcade-capacity/layout.js'),'utf8')
    .replace(/^window.HOUSE_ARCADE_CAPACITY = /,'').replace(/;\s*$/,''));
  for(const option of study.options){
    for(const building of option.plans.buildings){
      for(const [width,height] of [[1080,900],[390,790],[844,336]]){
        const r=runtime('#mode=tour&building='+building.id+'&floor=floor-1&view=front',width,height,{capacity:true,scheme:option.id});
        assert.equal(r.body.attrs['data-study-option'],option.id);
        for(const floor of building.floors){
          r.button('scope-floors','data-floor',floor.id);
          check(option,building,floor,r.debug());
          checkFit(r.debug());
          const footer=r.debug().cameraFraming.overlays.filter(rect=>['orientation','study-stage-note'].includes(rect.id));
          assert.equal(footer.length,2);
          assert.ok(footer[0].right<=footer[1].left||footer[1].right<=footer[0].left||
            footer[0].bottom<=footer[1].top||footer[1].bottom<=footer[0].top,'study badge never covers the direction note');
          assert.ok(r.find('study-plan-link').href.includes('scheme='+option.id+'&building='+building.id+'&floor='+floor.id));
        }
        r.nodes['study-scheme'].value='arcade32';r.nodes['study-scheme'].dispatchEvent({type:'change'});
        const next=new URL(r.assigned.at(-1));assert.equal(next.searchParams.get('scheme'),'arcade32');
        assert.equal(new URLSearchParams(next.hash.slice(1)).get('building'),building.id);
        assert.equal(new URLSearchParams(next.hash.slice(1)).get('floor'),'floor-4');
        assert.equal(r.frames.size,1,'single renderer loop (no real WebGL/browser evidence)');
      }
    }
  }
});

test('capacity file entry redirects before scene allocation; fallback and context loss retain exact scheme/building/floor',()=>{
  for(const options of [{capacity:true,scheme:'invalid'},{capacity:true,bare:true}]){
    const r=runtime('#building=C&floor=floor-1',390,790,options);
    assert.equal(new URL(r.assigned.at(-1)).searchParams.get('scheme'),'arcade32');assert.equal(r.frames.size,0);
  }
  const unavailable=runtime('#building=B&floor=floor-2',390,790,{capacity:true,scheme:'room-first',noWebGL:true});
  assert.equal(unavailable.find('renderer-fallback').hidden,false);assert.equal(unavailable.frames.size,0);
  assert.equal(unavailable.find('renderer-fallback').children.find(n=>n.tagName==='a').href,
    'arcade-capacity.html#scheme=room-first&building=B&floor=floor-2');
  const r=runtime('#building=A&floor=floor-1&view=front',390,790,{capacity:true,scheme:'arcade32'});
  r.hidden(true);r.frame();assert.equal(r.frames.size,0);r.hidden(false);assert.equal(r.frames.size,1);
  let prevented=false;r.nodes.canvas.dispatchEvent({type:'webglcontextlost',preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,true);assert.equal(r.frames.size,0);assert.equal(r.find('renderer-fallback').hidden,false);
  r.nodes.canvas.dispatchEvent({type:'webglcontextrestored'});assert.equal(r.find('renderer-fallback').hidden,true);
  assert.equal(r.frames.size,1);assert.ok(r.debug().visibleRooms.includes('A:floor-1:flex1'));
});

test('isolated C1F study initializes each scheme with exact shared geometry, query state and reversible controls',()=>{
  const study=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/c1f-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_C1F_OPTIONS = /,'').replace(/;\s*$/,''));
  for(const option of study.options){
    const r=runtime('#mode=tour&building=C&floor=floor-1&view=plan',390,790,{study:true,scheme:option.id});
    const d=r.debug();assert.equal(r.body.attrs['data-study-option'],option.id);
    assert.equal(d.state.building,'C');assert.equal(d.visibleRooms.length,option.floor.rooms.length);
    assert.equal(d.layoutReview.status,'comparison-only-not-adopted');
    assert.ok(d.visibleRooms.every(id=>id.startsWith('C:floor-1:')));
    for(const room of option.floor.rooms){
      const actual=d.tour.rooms.find(c=>c.id===room.id);assert.deepEqual(actual.geometry,room.geometry);assert.deepEqual(actual.features,room.features);
    }
    const id=option.public_bath_key?'C:floor-1:public-bath':'C:floor-1:elder-bath';
    r.button('scope-rooms','data-room',id);r.click('focus-room');
    assert.equal(r.debug().roomCloseup,true);assert.equal(r.debug().roomCutaway.active,true);
    assert.ok(r.location.href.includes('?scheme='+option.id));
    r.click('room-overview');assert.equal(r.debug().visibleRooms.length,option.floor.rooms.length);
    r.nodes['study-scheme'].value='baseline';r.nodes['study-scheme'].dispatchEvent({type:'change'});
    const next=new URL(r.assigned.at(-1));assert.equal(next.searchParams.get('scheme'),'baseline');
    assert.equal(new URLSearchParams(next.hash.slice(1)).get('room'),null);
  }
  for(const options of [{study:true,scheme:'invalid'},{study:true,bare:true}]){
    const invalid=runtime('',1080,900,options);
    assert.equal(new URL(invalid.assigned.at(-1)).searchParams.get('scheme'),'baseline');
    assert.equal(invalid.frames.size,0,'missing/invalid query redirects before a renderer is created');
  }
  const encoded=runtime('',1080,900,{study:true,scheme:'bath%2Dfront'});
  assert.equal(encoded.body.attrs['data-study-option'],'bath-front');
  assert.ok(encoded.location.href.includes('scheme=bath%2Dfront'),'valid encoded queries survive hash-only file history');
});

test('C1F study real scene math meets serialized floor and ordinary WC cutaway contracts in all viewports',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const extract=name=>{
    const expression=new RegExp('  const '+name+' = \\([^]*?\\) => \\{[^]*?\\n  };');
    const definition=checkPages.toString().match(expression)?.[0];assert.ok(definition,name+' definition');
    return vm.runInNewContext(definition+'\n'+name,{assert:(condition,message)=>assert.ok(condition,message)});
  };
  const checkOption=extract('checkCOption'),checkCutaway=extract('checkRoomCutaway'),checkFit=extract('checkCameraFraming');
  const study=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/c1f-options/layout.js'),'utf8')
    .replace(/^window.HOUSE_C1F_OPTIONS = /,'').replace(/;\s*$/,''));
  for(const option of study.options){
    for(const [width,height] of [[1080,900],[390,790],[844,336]]){
      const r=runtime('#mode=tour&building=C&floor=floor-1&view=front',width,height,{study:true,scheme:option.id});
      checkOption(option,r.debug());
      if(!option.public_bath_key)continue;
      r.button('scope-rooms','data-room','C:floor-1:public-bath');r.click('focus-room');
      checkCutaway(r.debug(),'C:floor-1:public-bath',2);
      checkFit(r.debug(),'C:floor-1:public-bath');
      assert.ok(r.debug().focusedScreenBounds.every(p=>Math.abs(p[0])<1 && Math.abs(p[1])<1),
        option.id+' WC focus fits the '+width+'×'+height+' stage (scene math, not pixel evidence)');
      r.resize(844,336);checkCutaway(r.debug(),'C:floor-1:public-bath',2);checkFit(r.debug(),'C:floor-1:public-bath');
      r.click('room-overview');checkOption(option,r.debug());
    }
  }
});

test('ABC selected body framing uses measured overlays without remote HVAC-route inflation or geometry changes',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition);
  const check=vm.runInNewContext(definition+'\ncheckCameraFraming',{assert:(condition,message)=>assert.ok(condition,message)});
  const cutawayDefinition=checkPages.toString().match(/  const checkRoomCutaway = \(debug, roomId, fixtureCount\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(cutawayDefinition);
  const checkCutaway=vm.runInNewContext(cutawayDefinition+'\ncheckRoomCutaway',{assert:(condition,message)=>assert.ok(condition,message)});
  const stable=d=>({rooms:d.tour.rooms.map(r=>({id:r.id,geometry:r.geometry,features:r.features})),
    ids:d.visibleRooms,shapes:d.furniture.shapes,pending:d.furniture.pendingItems});
  const floors=[['A','floor-1',['arcade','living','flex1','bath1']],['A','floor-2',['master-bath','hall2']],
    ['B','floor-1',['shrine']],['B','floor-2',['bath2','master-bath2']],['C','floor-1',['dining','living','kitchen','elder']]];
  for(const [b,f,keys] of floors)for(const [w,h] of [[1080,900],[390,790],[844,336]]){
    const prefix='#mode=tour&building='+b+'&floor='+f+'&view=front',r=runtime(prefix,w,h),before=stable(r.debug());
    for(const key of keys){
      const id=b+':'+f+':'+key;r.hash(prefix+'&room='+id+'&focus=room');
      const d=r.debug();check(d,id);
      assert.deepEqual(stable(d),before,id+' focus is a camera/material change, never a room/product edit');
      if(id==='A:floor-1:living')checkCutaway(d,id,4);
      if(id==='A:floor-1:living' && w/h>=1.8){
        assert.equal(d.cameraFraming.autoFit.theta,.85,'landscape closeup looks toward the real side-wall TV');
        const tv=d.furniture.shapes.find(item=>item.id===id+':furniture:tv');
        assert.deepEqual([tv.width,tv.depth,tv.height],[1230,80,710],'readability never inflates the 55-inch screen');
      }
      if(id==='C:floor-1:living'){
        const room=d.tour.rooms.find(r=>r.id===id),unit=room.features.hvac_units.find(u=>u.id==='C-AC01');
        const route=d.cameraFraming.routes.find(r=>r.id===unit.id);
        assert.ok(route.visible);assert.equal(route.cameraFit,false);
        const points=unit.route.polyline_mm.flatMap(p=>[p[0]/1000,p[2]/1000,-p[1]/1000]);
        assert.equal(route.points.length,points.length,'all real route vertices remain in the scene');
        assert.ok(route.points.every((v,i)=>Math.abs(v-points[i])<.00001));
        const bounds=d.cameraFraming.worldBounds;
        assert.ok(bounds.max[2]-bounds.min[2]<=room.geometry.h_mm/1000+.3,'remote route no longer enlarges room bounds');
      }
      r.click('room-overview');assert.deepEqual(stable(r.debug()),before,'return retains the whole original floor');
    }
  }
});

test('B ritual gate and all four actual transport lines retain source vertices across desktop/mobile',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const definition=checkPages.toString().match(/  const checkBFirstFloor = \(floor, debug\) => \{[\s\S]*?\n  };/)?.[0];
  assert.ok(definition,'actual Windows B flow verifier');
  const check=vm.runInNewContext(definition+'\ncheckBFirstFloor',{assert:(condition,message)=>assert.ok(condition,message)});
  const fitDefinition=checkPages.toString().match(/  const checkCameraFraming = \(debug, roomId = ''\) => \{[\s\S]*?\n  };/)?.[0];
  const checkFit=vm.runInNewContext(fitDefinition+'\ncheckCameraFraming',{assert:(condition,message)=>assert.ok(condition,message)});
  const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  for(const [width,height] of [[1080,900],[390,790],[844,336]]){
    const r=runtime('#mode=tour&building=B&floor=floor-1&view=front',width,height);
    check(shared.buildings[1].floors[0],r.debug());
    const before=r.debug().furniture.shapes;
    for(const key of ['shrine','entry','storage']){
      r.button('scope-rooms','data-room','B:floor-1:'+key);r.click('focus-room');
      const d=r.debug();check(shared.buildings[1].floors[0],d);
      if(key==='storage'){
        // Desktop/portrait cover every real product body. A 35x30cm device
        // is still small in the shallow landscape viewport: verify the room
        // fit and route, but do not mislabel that as all-product readability.
        if(width/height<1.8) checkFit(d,'B:floor-1:storage');
        else {
          const frame=d.cameraFraming,area=frame.safeArea;
          assert.ok(frame.ready && area.usable && d.focusedScreenBounds.length===8);
          for(const point of d.focusedScreenBounds){
            const x=(point[0]+1)*width/2,y=(1-point[1])*height/2;
            assert.ok(x>=area.left-1 && x<=area.right+1 && y>=area.top-1 && y<=area.bottom+1,
              'landscape storage room fits the measured safe rectangle; small-device readability remains pending');
          }
        }
        assert.equal(d.furniture.shapes.find(i=>i.id==='B:floor-1:storage:furniture:dehumidifier').width,350);
      }
      assert.deepEqual(d.furniture.shapes,before,'route annotations and closeups never install or shrink furniture');
      assert.ok(r.nodes.info.innerHTML.includes(key==='shrine'?'屋主家規':'裝桿'));
      r.click('room-overview');
    }
    r.control('architecture',false);assert.deepEqual(r.debug().transportRoutes,[]);
    r.control('architecture',true);check(shared.buildings[1].floors[0],r.debug());
    r.hash('#mode=tour&building=C&floor=floor-1&view=front');assert.deepEqual(r.debug().transportRoutes,[]);
  }
});

test('no-WebGL study fallback retains the exact option and context-loss/hidden-tab stops scene work',()=>{
  const unavailable=runtime('',390,790,{study:true,scheme:'bath-front',noWebGL:true});
  assert.equal(unavailable.find('renderer-fallback').hidden,false);assert.equal(unavailable.nodes.canvas.hidden,true);
  assert.equal(unavailable.find('renderer-fallback').children.find(n=>n.tagName==='a').href,'c1f-options.html#scheme=bath-front');
  assert.equal(unavailable.frames.size,0);
  const r=runtime('#mode=tour&building=C&floor=floor-1&view=plan',390,790,{study:true,scheme:'front-living'});
  assert.equal(r.find('renderer-fallback').hidden,true);const rendered=r.renderCount;
  r.hidden(true);r.frame();assert.equal(r.frames.size,0);assert.equal(r.renderCount,rendered);
  r.hidden(false);assert.equal(r.frames.size,1);assert.equal(r.renderCount,rendered+1);
  let prevented=false;r.nodes.canvas.dispatchEvent({type:'webglcontextlost',preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,true);assert.equal(r.frames.size,0);assert.equal(r.find('renderer-fallback').hidden,false);
  r.nodes.canvas.dispatchEvent({type:'webglcontextrestored'});assert.equal(r.find('renderer-fallback').hidden,true);assert.equal(r.frames.size,1);
  assert.ok(r.debug().visibleRooms.includes('C:floor-1:elder'));
});

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

test('MDF under-stair comparison retains a single original rack, honest side-width conflict and bounded reuse',()=>{
  const {checkPages}=require('../../scripts/check_windows_playwright.cjs');
  const extract=name=>{
    const definition=checkPages.toString().match(new RegExp('  const '+name+' = \\([^]*?\\) => \\{[^]*?\\n  };'))?.[0];
    assert.ok(definition,name);
    return vm.runInNewContext(definition+'\n'+name,{assert:(condition,message)=>assert.ok(condition,message),
      expectedCounts:{floors:12,rooms:112,items:128}});
  };
  const check=extract('checkMdfStudy'),fit=extract('checkCameraFraming');
  const shared=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
    .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\s*$/,''));
  const floor=shared.buildings[0].floors[0];
  for(const [w,h] of [[1080,900],[390,790],[844,336]]){
    const hash='#mode=tour&building=A&floor=floor-1&room=A:floor-1:stair-door&view=front&focus=room';
    const r=runtime(hash,w,h),before=r.debug();
    assert.equal(before.mdfStudy.active,false);assert.equal(before.mdfStudy.visible.length,0);
    r.control('mdf-study',true);
    const d=r.debug();check(d,floor);fit(d,'A:floor-1:stair-door');
    assert.deepEqual(d.furniture.shapes,before.furniture.shapes);
    assert.deepEqual(d.tour.rooms,before.tour.rooms);
    assert.equal(r.nodes['mdf-study-note'].hidden,false);
    assert.equal(new URLSearchParams(r.location.hash.slice(1)).get('mdf'),'study');
    const reloaded=runtime(r.location.hash,w,h);check(reloaded.debug(),floor);
    r.click('view-exterior');assert.equal(r.debug().mdfStudy.active,false);
    assert.equal(r.nodes['mdf-study-note'].hidden,true);
    r.click('exterior-return');check(r.debug(),floor);
    r.button('scope-floors','data-floor','floor-2');assert.equal(r.nodes['mdf-study'].disabled,true);
    assert.equal(r.debug().mdfStudy.visible.length,0);
    r.hash(hash+'&mdf=study');check(r.debug(),floor);
    r.control('architecture',false);assert.equal(r.debug().mdfStudy.visible.length,0);
    assert.equal(r.nodes['mdf-study-note'].hidden,true);
    r.control('architecture',true);check(r.debug(),floor);
    r.control('mdf-study',false);assert.equal(r.debug().mdfStudy.visible.length,0);
    assert.deepEqual(r.debug().furniture.shapes,before.furniture.shapes);
    assert.equal(r.nodes['mdf-study-note'].hidden,true);
    r.hash('#mode=tour&building=C&floor=floor-1&mdf=study&view=front');
    assert.equal(r.debug().mdfStudy.active,false);assert.equal(r.debug().mdfStudy.visible.length,0);
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
  r.button('scope-buildings','data-building','overview');assert.equal(r.debug().visibleRooms.length,112);
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
  assert.deepEqual(d.furniture.pendingItems.slice().sort(),[]);
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
