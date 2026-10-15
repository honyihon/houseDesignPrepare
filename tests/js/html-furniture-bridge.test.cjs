const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root=path.resolve(__dirname,'../..');
const source=fs.readFileSync(path.join(root,'assets/html_design_bridge.js'),'utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/furniture-plans/layout.js'),'utf8')
  .replace(/^window.HOUSE_CONCEPT_LAYOUT = /,'').replace(/;\n$/,''));
const proposalLabelDefinition=source.match(/    function proposalLabel\([\s\S]*?(?=    function link\()/)[0];

// Minimal DOM contract harness. It does not replace rendered browser QA.
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.events={};this.style={};this.dataset={};this.className='';this.textContent='';this.classList={add:(name)=>{this.className+=' '+name;}};}
  setAttribute(k,v){this.attrs[k]=String(v);}
  getAttribute(k){return this.attrs[k]??null;}
  replaceChildren(){this.children=[];}
  focus(){this.focused=true;}
  appendChild(child){if(child.parent)child.parent.children.splice(child.parent.children.indexOf(child),1);child.parent=this;this.children.push(child);return child;}
  insertAdjacentElement(where,child){assert.ok(['beforebegin','afterend'].includes(where));child.parent=this.parent;this.parent.children.splice(this.parent.children.indexOf(this)+(where==='afterend'?1:0),0,child);}
  closest(selector){assert.equal(selector,'.visual-plan');return this.parent;}
  addEventListener(type,callback){this.events[type]=callback;}
  dispatchEvent(event){this.events[event.type]?.(event);}
  querySelectorAll(selector){return selector.split(',').flatMap(part=>{
    const direct=part.trim().startsWith(':scope > '), css=part.trim().replace(/^:scope > /,'');
    return (direct?this.children:descendants(this)).filter(n=>css.startsWith('.')?n.className.split(' ').includes(css.slice(1)):n.tagName===css);
  });}
  querySelector(selector){return this.querySelectorAll(selector)[0] || null;}
}
function descendants(node){return node.children.flatMap(child=>[child,...descendants(child)]);}

test('HTML facade panel preserves exact shared material/pending evidence and links to all storeys',()=>{
  const definitions=source.match(/    function link\([\s\S]*?(?=    function installOverview\()/)[0];
  for(const record of data.facade.buildings){
    const container=new Element('main'),bridge=new Element('aside');bridge.className='design-bridge';container.appendChild(bridge);
    const document={baseURI:`file:///project/${record.id}buildingView.html`,createElement:tag=>new Element(tag),
      querySelector:selector=>container.querySelector(selector)};
    vm.runInNewContext(definitions+';installFacadeProposal();',{document,buildingId:record.id,
      viewerPath:'structured/candidates/model3d.html',window:{HOUSE_CONCEPT_LAYOUT:data},URL,URLSearchParams});
    const panel=container.querySelector('.shared-facade-proposal'),nodes=descendants(panel);
    assert.equal(panel.attrs['data-facade-id'],data.facade.id);assert.equal(panel.attrs['data-geometry-source'],'tour_mm');
    assert.equal(nodes.filter(n=>n.attrs['data-facade-pending-id']).length,record.pending.length);
    assert.equal(nodes.filter(n=>n.attrs['data-facade-check-id']).length,data.facade.pending_checks.length);
    assert.equal(nodes.find(n=>n.tagName==='img').src,`file:///project/structured/candidates/furniture-plans/${record.elevation_file}`);
    const link=nodes.find(n=>n.className.includes('facade-exterior-link'));
    const hash=new URLSearchParams(new URL(link.href).hash.slice(1));
    assert.equal(hash.get('mode'),'tour');assert.equal(hash.get('view'),'exterior');assert.equal(hash.get('building'),record.id);
    assert.equal(hash.get('floor'),null);assert.equal(hash.get('room'),null);
    for(const material of Object.values(data.facade.palette))assert.ok(nodes.some(n=>n.textContent.includes(material.note)));
    assert.ok(nodes.some(n=>n.textContent===data.facade.assumption_note));
  }
});

test('HTML bridge installs every floor, exact numbered furniture list and tour links offline',()=>{
  let rooms=0,items=0;
  for(const building of data.buildings){
    const floors=Object.fromEntries(building.floors.map(f=>{
      const host=new Element('div'),visual=new Element('div'),grid=new Element('div');
      grid.className='plan-grid-visual';visual.className='visual-plan';host.appendChild(visual);visual.appendChild(grid);
      return [f.id,host];
    }));
    const document={baseURI:`file:///project/${building.id}buildingView.html`,
      createElement:(tag)=>new Element(tag),createTextNode:text=>{const node=new Element('#text');node.textContent=text;return node;},getElementById:(id)=>floors[id]};
    const definitions=[
      source.match(/    function viewerUrl\([\s\S]*?(?=    function link\()/)[0],
      source.match(/    function link\([\s\S]*?(?=    function installOverview\()/)[0],
      source.match(/    var placementIssues[\s\S]*?(?=    function roomIdsFromPlan\()/)[0],
    ].join('\n');
    vm.runInNewContext(`${definitions};installSharedPlans();`,{document,buildingId:building.id,
      viewerPath:'structured/candidates/model3d.html',window:{HOUSE_CONCEPT_LAYOUT:data},URL,URLSearchParams});
    for(const floor of building.floors){
      const nodes=descendants(floors[floor.id]);
      assert.equal(nodes.filter(n=>n.className==='shared-furniture-plan').length,1);
      const img=nodes.find(n=>n.tagName==='img');
      assert.equal(img.src,`file:///project/structured/candidates/furniture-plans/${floor.plan_file}`);
      const reader=nodes.find(n=>n.attrs['data-plan-viewer']==='');
      assert.ok(reader);
      assert.equal(reader.attrs['data-source-width'],String(floor.width_mm+600));
      assert.equal(reader.attrs['data-source-height'],String(floor.depth_mm+1400));
      assert.equal(reader.attrs['data-readable-width'],'660');
      assert.equal(nodes.filter(n=>n.attrs['data-plan-action']).length,4);
      assert.equal(img.style.width,'660px');
      const entries=nodes.filter(n=>n.attrs['data-furniture-id']);
      const optionsLinks=nodes.filter(n=>n.className.split(' ').includes('c1f-options-link'));
      assert.equal(optionsLinks.length,building.id==='C' && floor.id==='floor-1'?1:0);
      if(optionsLinks.length){
        assert.ok(optionsLinks[0].href.endsWith('structured/candidates/c1f-options.html'));
        assert.ok(optionsLinks[0].textContent.includes('未採用'));
      }
      const toggle=nodes.find(n=>n.attrs['data-frontage-study-toggle']);
      if(building.id==='C' && floor.id==='floor-1'){
        assert.ok(toggle);
        const panel=nodes.find(n=>n.className==='shared-furniture-plan');
        const candidateNodes=nodes.filter(n=>n.attrs['data-frontage-study-zone']);
        const study=floor.rooms.find(r=>r.key==='garage').features.frontage_study;
        assert.equal(panel.attrs['data-frontage-study-visible'],'false');
        assert.equal(candidateNodes.length,2);
        for(const zone of study.zones)assert.ok(candidateNodes.some(n=>n.textContent.includes(zone.note)));
        const before=JSON.stringify(floor);
        toggle.checked=true;toggle.dispatchEvent({type:'change'});
        assert.equal(img.src,'file:///project/structured/candidates/furniture-plans/'+floor.frontage_study_file);
        assert.equal(panel.attrs['data-frontage-study-visible'],'true');
        assert.equal(panel.querySelector('.shared-plan-open').href,img.src);
        toggle.checked=false;toggle.dispatchEvent({type:'change'});
        assert.equal(img.src,'file:///project/structured/candidates/furniture-plans/'+floor.plan_file);
        assert.equal(panel.attrs['data-frontage-study-visible'],'false');
        assert.equal(JSON.stringify(floor),before,'conditional overlay must not install furniture or approve frontage use');
      }else assert.equal(toggle,undefined,'no conditional frontage toggle on other floors');
      const expected=floor.rooms.flatMap(r=>r.furniture);
      const mdfToggle=nodes.find(n=>n.attrs['data-mdf-study-toggle']);
      if(building.id==='A' && floor.id==='floor-1'){
        assert.ok(mdfToggle);
        const panel=nodes.find(n=>n.className==='shared-furniture-plan'),before=JSON.stringify(data);
        assert.equal(panel.attrs['data-mdf-study-visible'],'false');
        mdfToggle.checked=true;mdfToggle.dispatchEvent({type:'change'});
        assert.ok(img.src.endsWith(data.layout_review.mdf_study.plan_file));
        assert.equal(panel.querySelector('.shared-plan-open').href,img.src);
        assert.equal(panel.attrs['data-mdf-study-visible'],'true');
        const mdfLink=nodes.find(n=>n.className.includes('mdf-study-link'));
        const params=new URLSearchParams(new URL(mdfLink.href).hash.slice(1));
        assert.equal(params.get('mdf'),'study');assert.equal(params.get('room'),'A:floor-1:stair-door');
        assert.ok(nodes.some(n=>n.tagName==='img' && n.src.endsWith(data.layout_review.mdf_study.section_file)));
        assert.ok(nodes.some(n=>n.textContent.includes('機櫃仍只計1台')));
        mdfToggle.checked=false;mdfToggle.dispatchEvent({type:'change'});
        assert.ok(img.src.endsWith(floor.plan_file));
        assert.equal(panel.attrs['data-mdf-study-visible'],'false');
        assert.equal(JSON.stringify(data),before,'MDF comparison cannot install a second rack or release the backup');
      }else assert.equal(mdfToggle,undefined,'MDF overlay is scoped to the current A1F');
      assert.equal(entries.length,expected.length);
      entries.forEach((node,index)=>{
        const item=expected[index];
        assert.equal(node.attrs['data-furniture-id'],item.id);
        assert.ok(node.textContent.startsWith(`${index+1}. ${item.label}`));
        assert.ok(node.textContent.includes(`${item.width_mm} × ${item.depth_mm} × ${item.height_mm}mm`));
        assert.equal(node.attrs['data-placement-status'],item.placement.status);
        items++;
      });
      for(const node of nodes.filter(n=>n.href && n.href.includes('model3d.html'))){
        const hash=new URLSearchParams(new URL(node.href).hash.slice(1));
        assert.equal(hash.get('mode'),'tour');assert.equal(hash.get('building'),building.id);assert.equal(hash.get('floor'),floor.id);
      }
      for(const room of floor.rooms){
        const details=nodes.find(n=>n.attrs['data-model-room-id']===room.id);
        const sliding=room.features.doors.filter(d=>d.operation==='sliding');
        const notes=details.children.filter(n=>n.tagName==='p' && n.textContent.startsWith('滑門提案：'));
        assert.equal(notes.length,sliding.length?1:0);
        if(sliding.length)assert.ok(notes[0].textContent.includes('門寬暫估'+sliding.map(d=>d.width_mm).join('／')+'mm'),
          room.id+' must display its actual proposed door width, not a hard-coded care-door width');
      }
      rooms+=nodes.filter(n=>n.attrs['data-model-room-id']).length;
    }
    // Calling again must not duplicate lists or figures.
    vm.runInNewContext(`${definitions};installSharedPlans();`,{document,buildingId:building.id,
      viewerPath:'structured/candidates/model3d.html',window:{HOUSE_CONCEPT_LAYOUT:data},URL,URLSearchParams});
    assert.equal(Object.values(floors).flatMap(descendants).filter(n=>n.className==='shared-furniture-plan').length,4);
  }
  assert.equal(rooms,data.buildings.flatMap(b=>b.floors).flatMap(f=>f.rooms).length);
  assert.equal(items,data.buildings.flatMap(b=>b.floors).flatMap(f=>f.rooms).flatMap(r=>r.furniture).length);
});

function flatStudy(hash='',missing=false,capacity=false){
  const name=capacity?'arcade-capacity':'c1f-options',globalName=capacity?'HOUSE_ARCADE_CAPACITY':'HOUSE_C1F_OPTIONS';
  const html=fs.readFileSync(path.join(root,'structured/candidates/'+name+'.html'),'utf8');
  const script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
  const data=JSON.parse(fs.readFileSync(path.join(root,'structured/candidates/'+name+'/layout.js'),'utf8')
    .replace('window.'+globalName+' = ','').replace(/;\s*$/,''));
  const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element('div')]));
  const events={},window={addEventListener:(type,callback)=>{events[type]=callback;}};
  if(!missing)window[globalName]=data;
  const location={href:'file:///project/structured/candidates/'+name+'.html'+hash,hash};
  const document={body:new Element('body'),createElement:tag=>new Element(tag),getElementById:id=>{
    assert.ok(nodes[id],'known flat study DOM ID '+id);return nodes[id];
  }};
  const history={replaceState:(_state,_title,url)=>{
    const next=new URL(url,location.href);location.href=next.href;location.hash=next.hash;
  }};
  vm.runInNewContext(script,{window,document,location,history,URLSearchParams});
  return {data,nodes,window,document,location,hash:value=>{location.hash=value;events.hashchange();},
    select:id=>{nodes.scheme.value=id;nodes.scheme.dispatchEvent({type:'change'});},
    selectField:(key,value)=>{nodes[key].value=value;nodes[key].dispatchEvent({type:'change'});}};
}

test('ABC capacity HTML owns one SVG and retains option/building/floor, ordinary envelopes, care caveats and reset',()=>{
  const r=flatStudy('#scheme=arcade32&building=A&floor=floor-1',false,true),before=JSON.stringify(r.data);
  for(const option of r.data.options){
    r.select(option.id);
    for(const b of option.plans.buildings){
      r.selectField('building',b.id);
      for(const f of b.floors){
        r.selectField('floor',f.id);const d=r.window.__arcadeCapacityDebug();
        assert.equal(d.id,option.id);assert.equal(d.building,b.id);assert.equal(d.floor,f.id);assert.equal(d.activeDesign,'main-a32-arcade-v1');
        assert.equal(r.nodes.plan.attrs.data,'arcade-capacity/'+f.plan_file);
        assert.equal(r.nodes['svg-link'].href,r.nodes.plan.attrs.data);assert.equal(r.nodes['plan-fallback-link'].href,r.nodes.plan.attrs.data);
        assert.ok(r.nodes['open-3d'].href.includes('?scheme='+option.id+'#mode=tour&building='+b.id+'&floor='+f.id));
        assert.equal(r.nodes.furniture.children.length,f.rooms.flatMap(v=>v.furniture).length);
        assert.equal(r.nodes.pending.children.filter(p=>p.dataset.pendingItem).length,option.capacity[b.id].pending_furniture.length);
        assert.equal(r.nodes.unmet.children.length,option.capacity[b.id].unmet.length);
        assert.ok(r.location.hash.includes('scheme='+option.id+'&building='+b.id+'&floor='+f.id));
        if(b.id==='C')assert.ok(r.nodes.care.children.some(p=>p.textContent.includes('尚無150cm轉位暫留')));
      }
    }
  }
  r.nodes.reset.dispatchEvent({type:'click'});assert.equal(r.nodes.scheme.value,'arcade32');assert.equal(r.nodes.building.value,'A');assert.equal(r.nodes.floor.value,'floor-1');
  r.hash('#scheme=bad&building=other&floor=bad');assert.equal(r.window.__arcadeCapacityDebug().id,'arcade32');
  assert.equal(JSON.stringify(r.data),before,'capacity UI cannot adopt, approve or mutate the dataset');
  const missing=flatStudy('',true,true);assert.equal(missing.window.__arcadeCapacityDebug,undefined);
  assert.ok(missing.nodes['selection-status'].textContent.includes('不要據此判定任何方案通過'));
});

test('all main HTML comparison links preserve their own building and label the unadopted capacity study',()=>{
  const definitions=source.match(/    function installOverview\([\s\S]*?(?=    var placementIssues)/)[0];
  for(const id of ['A','B','C']){
    const host=new Element('main'),header=new Element('div');host.appendChild(header);
    const document={baseURI:'file:///project/'+id+'buildingView.html',querySelector:()=>header,createElement:tag=>new Element(tag)};
    vm.runInNewContext(proposalLabelDefinition+definitions+';installOverview();',{document,buildingId:id,window:{HOUSE_CONCEPT_LAYOUT:data},URL,URLSearchParams,viewerUrl:()=>'',
      walkthroughPath:'structured/parametric/walkthrough.html',link:(css,text,href)=>{const el=new Element('a');el.className=css;el.textContent=text;el.href=href;return el;}});
    const link=host.querySelector('.arcade-capacity-link');assert.ok(link.textContent.includes('未採用'));
    assert.equal(new URL(link.href).pathname,'/project/structured/candidates/arcade-capacity.html');
    assert.equal(new URLSearchParams(new URL(link.href).hash.slice(1)).get('building'),id);
  }
});

test('flat C1F comparison keeps SVG, fallback, catalogue list and share state in the selected unadopted scheme',()=>{
  const r=flatStudy('#scheme=bath-front'),before=JSON.stringify(r.data);
  assert.equal(r.window.__c1fOptionsDebug().id,'bath-front');
  assert.equal(r.nodes.scheme.children.length,3);assert.equal(r.nodes.compare.children.length,7);
  for(const option of r.data.options){
    r.select(option.id);
    assert.equal(r.location.hash,'#scheme='+option.id);assert.equal(r.document.body.dataset.scheme,option.id);
    assert.equal(r.nodes.plan.attrs.data,'c1f-options/'+option.id+'.svg');
    assert.equal(r.nodes['svg-link'].href,r.nodes.plan.attrs.data);
    assert.equal(r.nodes['plan-fallback-link'].href,r.nodes.plan.attrs.data);
    assert.ok(r.nodes['open-3d'].href.includes('?scheme='+option.id));
    const items=option.floor.rooms.flatMap(room=>room.furniture);
    assert.equal(r.nodes.furniture.children.length,items.length);
    for(const [index,item] of items.entries())assert.ok(r.nodes.furniture.children[index].textContent
      .includes(item.width_mm/10+'×'+item.depth_mm/10+'×'+item.height_mm/10+'cm'));
    assert.ok(r.nodes['selection-status'].textContent.includes('主案與需求決定未變更'));
    assert.equal(r.window.__c1fOptionsDebug().activeDesign,'baseline');
  }
  r.nodes.reset.dispatchEvent({type:'click'});assert.equal(r.nodes.scheme.value,'baseline');assert.ok(r.nodes.scheme.focused);
  r.hash('#scheme=front-living');assert.equal(r.nodes.scheme.value,'front-living');
  r.hash('#scheme=not-a-scheme');assert.equal(r.nodes.scheme.value,'baseline');
  assert.equal(JSON.stringify(r.data),before,'flat selector must not adopt a plan or update its facts');
});

test('flat comparison survives a missing data script with an explicit caution and static SVG fallback',()=>{
  const r=flatStudy('',true);
  assert.equal(r.window.__c1fOptionsDebug,undefined);
  assert.ok(r.nodes['selection-status'].textContent.includes('比較資料未載入'));
  assert.ok(r.nodes['selection-status'].textContent.includes('不要據此判定其他方案'));
  assert.equal(r.nodes.scheme.children.length,0);
});

test('actual archive code keeps current plan and header outside old claims, including overview panels',()=>{
  const building=data.buildings[1],floor=new Element('section');floor.id='floor-1';
  const oldHeader=new Element('div');oldHeader.className='floor-header';oldHeader.textContent='前帶武轎、後帶神明廳';
  const floorLink=new Element('a');floorLink.className='design-bridge-floor-link';oldHeader.appendChild(floorLink);
  const content=new Element('div');content.className='floor-content';
  const shared=new Element('section');shared.className='shared-furniture-plan';content.appendChild(shared);
  const directions=new Element('div');directions.className='direction-grid';
  floor.appendChild(oldHeader);floor.appendChild(directions);floor.appendChild(content);
  const overview=new Element('section');overview.id='floor-overview';
  const overviewHeader=new Element('div');overviewHeader.className='floor-header';
  const overviewContent=new Element('div');overviewContent.className='floor-content';overviewContent.textContent='兩車＋機車／緊急設備位置';
  overview.appendChild(overviewHeader);overview.appendChild(overviewContent);
  const document={querySelectorAll:()=>[floor,overview],createElement:tag=>new Element(tag)};
  const code=source.match(/    function archiveLegacyPlans\([\s\S]*?(?=    function installRoomLinks\()/)[0];
  vm.runInNewContext(`${proposalLabelDefinition}${code};archiveLegacyPlans();`,{document,buildingId:'B',window:{HOUSE_CONCEPT_LAYOUT:{buildings:[building]}},
    reviewNote:()=>{}});
  const archive=floor.querySelector('.legacy-layout');
  assert.ok(archive && !archive.open);
  assert.equal(shared.parent,floor);
  assert.equal(content.parent,archive);
  assert.equal(oldHeader.parent,archive);
  assert.equal(directions.parent,archive);
  assert.equal(floorLink.parent,floor.querySelector(':scope > .floor-header'));
  assert.ok(floor.querySelector(':scope > .floor-header').children[0].textContent.includes('中軸祭祀門'));
  assert.equal(overviewContent.parent,overview.querySelector('.legacy-layout'));
  assert.ok(!overview.querySelector('.legacy-layout').open);
  vm.runInNewContext(`${proposalLabelDefinition}${code};archiveLegacyPlans();`,{document,buildingId:'B',window:{HOUSE_CONCEPT_LAYOUT:{buildings:[building]}}});
  assert.equal(floor.querySelectorAll('.legacy-layout').length,1);
});

test('old header and statistics are archived instead of presenting stairs-under-IDF or old capacity as current',()=>{
  const container=new Element('main'),oldHeader=new Element('div'),stats=new Element('div'),bridge=new Element('aside');
  oldHeader.className='header';oldHeader.textContent='IDF樓梯下／四衣櫃';stats.className='stats-bar';stats.textContent='32坪／360cm衣櫃';bridge.className='design-bridge';
  container.appendChild(oldHeader);container.appendChild(bridge);container.appendChild(stats);
  const document={createElement:tag=>new Element(tag),querySelector:css=>{
    if(css.startsWith('.container > '))return container.querySelector(':scope > '+css.slice(13));
    return container.querySelector(css);
  }};
  const definition=source.match(/    function archiveTopMetadata\([\s\S]*?(?=    function installRoomLinks\()/)[0];
  vm.runInNewContext(`${proposalLabelDefinition}${definition};archiveTopMetadata();`,{document,buildingId:'C',window:{HOUSE_CONCEPT_LAYOUT:data}});
  const archive=container.querySelector('.legacy-metadata');
  assert.ok(archive && !archive.open);
  assert.equal(stats.parent,archive);assert.equal(oldHeader.parent,archive);
  assert.equal(container.children[0].className,'header proposal-header');
  assert.ok(container.children[0].children[0].textContent.includes('開放客餐廳'));
  assert.equal(container.children[1],bridge);
});
