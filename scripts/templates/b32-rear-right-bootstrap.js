  // Select BOTH the independent wall layout and furniture use state before
  // allocating a renderer. A route never inherits another state's furniture.
  var study=DATA.b32_rear_right, studyUrl=new URL(location.href);
  var studyChoice=study.options.find(function(o){return o.id===studyUrl.searchParams.get("scheme");}) ||
    study.options.find(function(o){return o.id===study.default_option;});
  var useChoice=studyChoice.states.find(function(s){return s.id===studyUrl.searchParams.get("use");}) ||
    studyChoice.states.find(function(s){return s.id===study.default_state;});
  if(studyUrl.searchParams.get("scheme")!==studyChoice.id || studyUrl.searchParams.get("use")!==useChoice.id){
    studyUrl.searchParams.set("scheme",studyChoice.id);studyUrl.searchParams.set("use",useChoice.id);
    location.replace(studyUrl.href);return;
  }
  DATA=useChoice.model;
  document.body.classList.add("bc-study");
  document.body.dataset.studyKind="b32-rear-right";
  document.body.dataset.studyOption=studyChoice.id;
  document.body.dataset.studyUse=useChoice.id;
  document.body.dataset.studyDisplayRevision=String(study.display_revision);
  document.title=studyChoice.label+" · "+useChoice.label+" · 深化3D（未採用）";
  document.querySelector("h1").textContent="B32後右公衛／後左武轎庫 · 兩版深化";
  document.getElementById("canvas").setAttribute("aria-label",document.title);
  document.getElementById("tour-notice").textContent="不是ABC主案。"+DATA.bc_option.label+"；後巷、外窗、法規、家規、照護及真人搬轎未核。日常家具不等於已完成搬轎整備。";
  document.getElementById("bc-study-tradeoffs").textContent=DATA.bc_option.tradeoffs.join(" ");
  var studySelect=document.getElementById("study-scheme"),useSelect=document.getElementById("study-use");
  study.options.forEach(function(o){var el=document.createElement("option");el.value=o.id;el.textContent=o.label;studySelect.appendChild(el);});
  studyChoice.states.forEach(function(s){var el=document.createElement("option");el.value=s.id;el.textContent=s.label;useSelect.appendChild(el);});
  studySelect.value=studyChoice.id;useSelect.value=useChoice.id;
  document.getElementById("study-plan-link").href="b32-rear-right.html#"+studyChoice.id+"-"+useChoice.id;
  function navigateStudy(){
    var next=new URL(location.href);next.searchParams.set("scheme",studySelect.value);next.searchParams.set("use",useSelect.value);
    next.hash="mode=tour&building=B&floor=floor-1&view=plan";location.assign(next.href);
  }
  studySelect.addEventListener("change",navigateStudy);useSelect.addEventListener("change",navigateStudy);
  var studyHash=new URLSearchParams(location.hash.replace(/^#/,""));
  studyHash.set("mode","tour");studyHash.set("building","B");
  if(!studyHash.get("floor"))studyHash.set("floor","floor-1");
  if(!studyHash.get("view"))studyHash.set("view","plan");
  history.replaceState(null,"","#"+studyHash.toString());
  var badge=document.createElement("div");badge.id="study-stage-note";badge.setAttribute("role","status");
  badge.textContent=studyChoice.label+" · "+useChoice.label+" · 深化未採用／未核";
  document.getElementById("stage").appendChild(badge);
