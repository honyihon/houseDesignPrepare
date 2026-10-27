  // Independent C-only comparison; select before allocating any WebGL scene.
  var study=DATA.c_care_entry,studyUrl=new URL(location.href);
  var studyChoice=study.options.find(function(o){return o.id===studyUrl.searchParams.get("scheme");})||study.options.find(function(o){return o.id===study.default_option;});
  var useChoice=studyChoice.states.find(function(s){return s.id===studyUrl.searchParams.get("use");})||studyChoice.states[0];
  if(studyUrl.searchParams.get("scheme")!==studyChoice.id||studyUrl.searchParams.get("use")!==useChoice.id){
    studyUrl.searchParams.set("scheme",studyChoice.id);studyUrl.searchParams.set("use",useChoice.id);location.replace(studyUrl.href);return;
  }
  DATA=useChoice.model;
  document.body.classList.add("bc-study");document.body.dataset.studyKind="c-care-entry";
  document.body.dataset.studyOption=studyChoice.id;document.body.dataset.studyUse=useChoice.id;
  document.title=studyChoice.label+" · "+useChoice.label+" · 討論未採用";
  document.querySelector("h1").textContent="C 孝親房入口比較 · 未採用";
  document.getElementById("canvas").setAttribute("aria-label",document.title);
  document.getElementById("tour-notice").textContent="原C與ABC主案未改。兩道120cm名義滑門只作比較，原900mm目標保留；不是實測或全程無障礙。上游770mm門缺口、照護救援與門組未核。";
  document.getElementById("bc-study-tradeoffs").textContent=DATA.bc_option.tradeoffs.join(" ");
  var studySelect=document.getElementById("study-scheme"),useSelect=document.getElementById("study-use");
  study.options.forEach(function(o){var e=document.createElement("option");e.value=o.id;e.textContent=o.label;studySelect.appendChild(e);});
  studyChoice.states.forEach(function(s){var e=document.createElement("option");e.value=s.id;e.textContent=s.label;useSelect.appendChild(e);});
  studySelect.value=studyChoice.id;useSelect.value=useChoice.id;
  document.getElementById("study-plan-link").href="c-care-entry.html#"+studyChoice.id+"-"+useChoice.id;
  function navigateCareEntry(){
    var choice=study.options.find(function(o){return o.id===studySelect.value;}),next=new URL(location.href);
    var state=choice.states.some(function(s){return s.id===useSelect.value;})?useSelect.value:choice.states[0].id;
    next.searchParams.set("scheme",choice.id);next.searchParams.set("use",state);
    next.hash="mode=tour&building=C&floor=floor-1&view=plan";location.assign(next.href);
  }
  studySelect.addEventListener("change",navigateCareEntry);useSelect.addEventListener("change",navigateCareEntry);
  var studyHash=new URLSearchParams(location.hash.replace(/^#/,""));studyHash.set("mode","tour");studyHash.set("building","C");
  if(!studyHash.get("floor"))studyHash.set("floor","floor-1");if(!studyHash.get("view"))studyHash.set("view","plan");
  history.replaceState(null,"","#"+studyHash.toString());
  var badge=document.createElement("div");badge.id="study-stage-note";badge.setAttribute("role","status");
  badge.textContent=studyChoice.label+" · "+useChoice.label+" · 未採用／門組與照護未核";document.getElementById("stage").appendChild(badge);
