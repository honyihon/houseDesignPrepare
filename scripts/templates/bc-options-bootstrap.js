  // Normalize file-protocol navigation BEFORE any renderer is allocated.
  var study = DATA.bc_options;
  var studyUrl = new URL(location.href);
  var studyChoice = study.options.find(function(o){return o.id === studyUrl.searchParams.get("scheme");}) ||
    study.options.find(function(o){return o.id === study.default_option;});
  if (studyUrl.searchParams.get("scheme") !== studyChoice.id) {
    studyUrl.searchParams.set("scheme", studyChoice.id);
    location.replace(studyUrl.href);
    return;
  }
  DATA = studyChoice.model;
  document.body.classList.add("bc-study");
  document.body.setAttribute("data-study-kind", "bc-constraints");
  document.body.setAttribute("data-study-option", studyChoice.id);
  document.title = studyChoice.label + " · 比較用 3D（未採用）";
  document.querySelector("h1").textContent = "B 家規／C 照護 · 比較用 3D";
  document.getElementById("canvas").setAttribute("aria-label", studyChoice.label + "（比較用，未採用）");
  document.getElementById("tour-notice").textContent = "本頁不是 ABC 主案。" + studyChoice.label +
    "；專業、宗教與原需求取捨未核。不得以同源圖或家具初篩取代完成面、救援與結構查核。";
  document.getElementById("bc-study-tradeoffs").textContent = DATA.bc_option.tradeoffs.join(" ");
  var studySelect = document.getElementById("study-scheme");
  study.options.forEach(function(o){var el=document.createElement("option");el.value=o.id;el.textContent=o.label;studySelect.appendChild(el);});
  studySelect.value=studyChoice.id;
  document.getElementById("study-plan-link").href="bc-options.html#"+studyChoice.id;
  studySelect.addEventListener("change",function(){
    var choice=study.options.find(function(o){return o.id===studySelect.value;});
    var next=new URL(location.href);next.searchParams.set("scheme",choice.id);
    next.hash="mode=tour&building="+choice.building+"&floor=floor-1&view=front";
    location.assign(next.href);
  });
  var studyHash=new URLSearchParams(location.hash.replace(/^#/,""));
  studyHash.set("mode","tour");studyHash.set("building",studyChoice.building);
  if(!studyHash.get("floor"))studyHash.set("floor","floor-1");
  if(!studyHash.get("view"))studyHash.set("view","front");
  history.replaceState(null,"","#"+studyHash.toString());
  var studyBadge=document.createElement("div");studyBadge.id="study-stage-note";
  studyBadge.setAttribute("role","status");studyBadge.setAttribute("aria-live","polite");
  studyBadge.textContent=studyChoice.label+" · 比較，未採用／未核";
  document.getElementById("stage").appendChild(studyBadge);
