  // Select an independent discussion layout/state before allocating WebGL.
  var study=DATA.current_design_basis,studyUrl=new URL(location.href);
  var studyChoice=study.options.find(function(o){return o.id===studyUrl.searchParams.get("scheme");})||study.options.find(function(o){return o.id===study.default_option;});
  var useChoice=studyChoice.states.find(function(s){return s.id===studyUrl.searchParams.get("use");})||studyChoice.states[0];
  if(studyUrl.searchParams.get("scheme")!==studyChoice.id||studyUrl.searchParams.get("use")!==useChoice.id){
    studyUrl.searchParams.set("scheme",studyChoice.id);studyUrl.searchParams.set("use",useChoice.id);location.replace(studyUrl.href);return;
  }
  DATA=useChoice.model;
  document.body.classList.add("bc-study");document.body.dataset.studyKind="current-design-basis";
  document.body.dataset.studyOption=studyChoice.id;document.body.dataset.studyUse=useChoice.id;
  document.title=studyChoice.label+" · "+useChoice.label+" · 討論未採用";
  document.querySelector("h1").textContent="ABC目前討論基準 · 未採用";
  document.getElementById("canvas").setAttribute("aria-label",document.title);
  document.getElementById("tour-notice").textContent="不是ABC主案。"+DATA.bc_option.label+"；原需求、法規、風水、後巷／外窗、照護及真人搬運均未核。新A套衛與收納取捨待屋主選擇。";
  document.getElementById("bc-study-tradeoffs").textContent=DATA.bc_option.tradeoffs.join(" ");
  var studySelect=document.getElementById("study-scheme"),useSelect=document.getElementById("study-use");
  study.options.forEach(function(o){var e=document.createElement("option");e.value=o.id;e.textContent=o.label;studySelect.appendChild(e);});
  studyChoice.states.forEach(function(s){var e=document.createElement("option");e.value=s.id;e.textContent=s.label;useSelect.appendChild(e);});
  studySelect.value=studyChoice.id;useSelect.value=useChoice.id;
  document.getElementById("study-plan-link").href="current-design-basis.html#"+studyChoice.id+"-"+useChoice.id;
  function navigateBasis(){
    var choice=study.options.find(function(o){return o.id===studySelect.value;}),next=new URL(location.href);
    var state=choice.states.some(function(s){return s.id===useSelect.value;})?useSelect.value:choice.states[0].id;
    next.searchParams.set("scheme",choice.id);next.searchParams.set("use",state);
    next.hash="mode=tour&building="+choice.building+"&floor=floor-1&view=plan";location.assign(next.href);
  }
  studySelect.addEventListener("change",navigateBasis);useSelect.addEventListener("change",navigateBasis);
  var studyHash=new URLSearchParams(location.hash.replace(/^#/,""));studyHash.set("mode","tour");studyHash.set("building",studyChoice.building);
  if(!studyHash.get("floor"))studyHash.set("floor","floor-1");if(!studyHash.get("view"))studyHash.set("view","plan");
  history.replaceState(null,"","#"+studyHash.toString());
  var badge=document.createElement("div");badge.id="study-stage-note";badge.setAttribute("role","status");
  badge.textContent=studyChoice.label+" · "+useChoice.label+" · 討論未採用／專業未核";document.getElementById("stage").appendChild(badge);
