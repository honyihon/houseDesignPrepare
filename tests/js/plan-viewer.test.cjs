'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const api=require('../../assets/plan_viewer.js');
const source=fs.readFileSync(path.join(__dirname,'../../assets/plan_viewer.js'),'utf8');
const close=(a,b)=>assert.ok(Math.abs(a-b)<.001,`${a} != ${b}`);

// DOM contract only. Sizes are supplied, not measured by a CSS/browser engine.
function events(node){
  node.handlers={};node.addEventListener=(type,fn)=>(node.handlers[type]??=[]).push(fn);
  node.dispatch=(type,extra={})=>{const event={target:node,prevented:false,preventDefault(){this.prevented=true;},...extra};
    for(const fn of node.handlers[type]||[])fn(event);return event;};return node;
}
function fixture(width=360,height=500){
  const plan=events({style:{width:'660px',height:String(660*19030/6600)+'px'},complete:false,naturalWidth:0});
  const buttons=['in','out','readable','overview'].map(name=>events({dataset:{planAction:name},disabled:false,attrs:{},
    setAttribute(name,value){this.attrs[name]=value;},click(){if(!this.disabled)this.dispatch('click');}}));
  const controls={hidden:true,querySelectorAll:()=>buttons},status={textContent:''},error={hidden:true};
  let left=0,top=0;
  const viewport=events({clientWidth:width,clientHeight:height,
    get scrollWidth(){return Math.max(this.clientWidth,parseFloat(plan.style.width));},
    get scrollHeight(){return Math.max(this.clientHeight,parseFloat(plan.style.height));},
    get scrollLeft(){return left;},set scrollLeft(value){left=Math.max(0,Math.min(this.scrollWidth-this.clientWidth,value));},
    get scrollTop(){return top;},set scrollTop(value){top=Math.max(0,Math.min(this.scrollHeight-this.clientHeight,value));}});
  const nodes={'[data-plan-viewport]':viewport,'[data-plan-content]':plan,'[data-plan-controls]':controls,'[data-plan-state]':status,'[data-plan-error]':error};
  const root={dataset:{sourceWidth:'6600',sourceHeight:'19030',readableWidth:'660'},querySelector:s=>nodes[s]};
  return {root,viewport,plan,controls,status,error,buttons,button:name=>buttons.find(b=>b.dataset.planAction===name)};
}

test('dimensions preserve source aspect, responsive fit and bounded vector width',()=>{
  for(const [w,h] of [[1080,640],[390,548],[844,280]]){
    const d=api.dimensions(6600,19030,w,h,660);
    close(d.width,660);close(d.height/d.width,19030/6600);
    const fit=api.dimensions(6600,19030,w,h,660,.1);
    assert.ok(fit.width<=w&&fit.height<=h+.001);
    assert.equal(api.dimensions(6600,19030,w,h,660,100000).width,2640);
  }
  for(const bad of [0,-1,NaN,Infinity])assert.throws(()=>api.dimensions(bad,19030,390,548,660));
});
test('each viewer starts readable, zoom really changes both object dimensions and reset restores origin',()=>{
  const r=fixture(),v=api.attach(r.root);
  assert.equal(r.controls.hidden,false);assert.equal(r.root.dataset.planMode,'readable');assert.match(r.status.textContent,/100%.*非工程比例/);
  r.viewport.scrollLeft=100;r.viewport.scrollTop=1000;const before=v.state();
  r.button('in').click();close(v.state().width,before.width*1.35);close(v.state().height,before.height*1.35);
  close(r.viewport.scrollLeft,(100+180)*1.35-180);close(r.viewport.scrollTop,(1000+250)*1.35-250);
  r.button('out').click();close(v.state().width,660);
  r.button('overview').click();assert.equal(r.root.dataset.planMode,'overview');assert.match(r.status.textContent,/文字較小/);
  assert.equal(r.button('overview').attrs['aria-pressed'],'true');assert.equal(r.button('out').disabled,true);
  r.button('readable').click();assert.equal(v.state().width,660);assert.equal(r.viewport.scrollLeft,0);assert.equal(r.viewport.scrollTop,0);
  assert.equal(r.button('readable').attrs['aria-pressed'],'true');assert.equal(r.button('overview').attrs['aria-pressed'],'false');
});
test('zoom bounds disable controls and resizing recomputes only overview',()=>{
  const r=fixture(1000,640),v=api.attach(r.root);
  for(let n=0;n<30;n++)r.button('in').click();assert.equal(v.state().width,2640);assert.equal(r.button('in').disabled,true);
  for(let n=0;n<50;n++)r.button('out').click();close(v.state().width,v.state().fitWidth);assert.equal(r.button('out').disabled,true);
  r.button('overview').click();r.viewport.clientWidth=390;r.viewport.clientHeight=844;v.resize();
  close(v.state().width,Math.min(390,844*6600/19030));
  r.button('readable').click();r.viewport.clientWidth=314;r.viewport.clientHeight=500;v.resize();close(v.state().width,660);
});
test('zooming a centered overview preserves the horizontal center when wider than the viewport',()=>{
  const r=fixture(800,640),v=api.attach(r.root);r.button('overview').click();
  while(v.state().width<=800)r.button('in').click();
  close(r.viewport.scrollLeft,(v.state().width-800)/2);
});
test('keyboard scrolling is scoped, and Tab, SVG links and browser zoom are not trapped',()=>{
  const r=fixture();api.attach(r.root);
  assert.equal(r.viewport.dispatch('keydown',{key:'End'}).prevented,true);assert.ok(r.viewport.scrollTop>0);
  r.viewport.dispatch('keydown',{key:'ArrowRight'});assert.equal(r.viewport.scrollLeft,80);
  r.viewport.dispatch('keydown',{key:'Home'});assert.equal(r.viewport.scrollTop,0);assert.equal(r.viewport.scrollLeft,0);
  r.viewport.dispatch('keydown',{key:'PageDown'});assert.equal(r.viewport.scrollTop,400);
  for(const data of [{key:'Tab'},{key:'+'},{key:'ArrowDown',ctrlKey:true},{key:'ArrowDown',altKey:true},{key:'ArrowDown',target:r.plan}]){
    const old=r.viewport.scrollTop;assert.equal(r.viewport.dispatch('keydown',data).prevented,false);assert.equal(r.viewport.scrollTop,old);
  }
  assert.ok(!r.viewport.handlers.wheel&&!r.viewport.handlers.touchmove);
});
test('two browser instances initialize independently, observe resize, and expose honest loading failures',()=>{
  const rear=fixture(),front=fixture(),observers=[];
  const window={document:{querySelectorAll:()=>[rear.root,front.root]},ResizeObserver:class{constructor(callback){this.callback=callback;observers.push(this);}observe(node){this.node=node;}}};
  vm.runInNewContext(source,{window});assert.equal(observers.length,2);
  const old=front.plan.style.width;rear.button('in').click();assert.equal(front.plan.style.width,old);
  rear.button('overview').click();rear.viewport.clientHeight=300;observers[0].callback();close(parseFloat(rear.plan.style.height),300);
  rear.plan.dispatch('load');assert.equal(rear.root.dataset.planLoaded,'true');
  front.plan.dispatch('error');assert.equal(front.root.dataset.planLoaded,'false');assert.equal(front.error.hidden,false);
  assert.equal(api.attach({dataset:{},querySelector:()=>null}),null);
});
test('cached images are recognized and deferred image loads cannot falsely pass',()=>{
  const ready=fixture();ready.plan.complete=true;ready.plan.naturalWidth=6600;
  api.attach(ready.root);assert.equal(ready.root.dataset.planLoaded,'true');
  const pending=fixture();api.attach(pending.root);assert.equal(pending.root.dataset.planLoaded,undefined);
  pending.plan.dispatch('load');assert.equal(pending.root.dataset.planLoaded,'true');
});
