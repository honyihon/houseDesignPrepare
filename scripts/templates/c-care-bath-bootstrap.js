  // Independent bath-use comparison; select before creating any WebGL scene.
  var study=DATA.c_care_bath,studyUrl=new URL(location.href);
  var studyChoice=study.options.find(function(o){return o.id===studyUrl.searchParams.get("scheme");})||study.options.find(function(o){return o.id===study.default_option;});
  var useChoice=studyChoice.states.find(function(s){return s.id===studyUrl.searchParams.get("use");})||studyChoice.states[0];
  if(studyUrl.searchParams.get("scheme")!==studyChoice.id||studyUrl.searchParams.get("use")!==useChoice.id){
    studyUrl.searchParams.set("scheme",studyChoice.id);studyUrl.searchParams.set("use",useChoice.id);location.replace(studyUrl.href);return;
  }
  DATA=useChoice.model;
  document.body.classList.add("bc-study");document.body.dataset.studyKind="c-care-bath";
  document.body.dataset.studyOption=studyChoice.id;document.body.dataset.studyUse=useChoice.id;
  document.title=studyChoice.label+" · "+useChoice.label+" · 討論未採用";
  document.querySelector("h1").textContent="C 孝親套衛照護比較 · 未採用";
  document.getElementById("canvas").setAttribute("aria-label",document.title);
  document.getElementById("tour-notice").textContent="原ABC及已驗收動線版不動。原2.4×3m套衛比較零門檻開放淋浴、折椅與扶手；轉位借濕地分時使用。不是照護、濕滑、門組或救援核可。";
  document.getElementById("bc-study-tradeoffs").textContent=DATA.bc_option.tradeoffs.join(" ");
  var studySelect=document.getElementById("study-scheme"),useSelect=document.getElementById("study-use");
  study.options.forEach(function(o){var e=document.createElement("option");e.value=o.id;e.textContent=o.label;studySelect.appendChild(e);});
  studyChoice.states.forEach(function(s){var e=document.createElement("option");e.value=s.id;e.textContent=s.label;useSelect.appendChild(e);});
  studySelect.value=studyChoice.id;useSelect.value=useChoice.id;
  document.getElementById("study-plan-link").href="c-care-bath.html#"+studyChoice.id+"-"+useChoice.id;
  function navigateCareBath(){
    var choice=study.options.find(function(o){return o.id===studySelect.value;}),next=new URL(location.href);
    var state=choice.states.some(function(s){return s.id===useSelect.value;})?useSelect.value:choice.states[0].id;
    next.searchParams.set("scheme",choice.id);next.searchParams.set("use",state);
    next.hash="mode=tour&building=C&floor=floor-1&room=C%3Afloor-1%3Aelder-bath&focus=room&view=plan";location.assign(next.href);
  }
  studySelect.addEventListener("change",navigateCareBath);useSelect.addEventListener("change",navigateCareBath);
  var studyHash=new URLSearchParams(location.hash.replace(/^#/,""));studyHash.set("mode","tour");studyHash.set("building","C");
  if(!studyHash.get("floor"))studyHash.set("floor","floor-1");if(!studyHash.get("view"))studyHash.set("view","plan");
  history.replaceState(null,"","#"+studyHash.toString());
  var badge=document.createElement("div");badge.id="study-stage-note";badge.setAttribute("role","status");
  var shortStates={baseline:"上版控制",transfer:"轉位比較",shower:"折椅放下","rail-down":"扶手放下","door-closed":"套衛關門"};
  badge.textContent=shortStates[useChoice.id]+" · 未採用／濕地分時／照護救援未核";
  badge.title=studyChoice.label+" · "+useChoice.label;document.getElementById("stage").appendChild(badge);
  var bathEquipment=document.createElement("div");bathEquipment.id="bath-accessories";bathEquipment.hidden=true;
  var bathHeading=document.createElement("h3");bathHeading.textContent="衛浴工程配件候選（非已購實物）";bathEquipment.appendChild(bathHeading);
  var bathList=document.createElement("ul");bathList.id="bath-equipment-list";bathList.setAttribute("aria-label","本房衛浴工程配件候選");bathEquipment.appendChild(bathList);
  document.getElementById("b32-room-details-panel").appendChild(bathEquipment);
  document.getElementById("b32-room-details").addEventListener("click",function(){
    var mesh=meshById[viewState.room],specs=mesh?(featuresOf(mesh.userData.cell).care_bath_components||[]):[];
    bathList.replaceChildren();bathEquipment.hidden=!specs.length;
    specs.forEach(function(spec){var e=document.createElement("li");e.dataset.bathComponent=spec.id;e.textContent=spec.label+" · "+spec.state+"；產品、承重與錨定未核";bathList.appendChild(e);});
  });
