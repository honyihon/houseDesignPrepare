  // Pick one unadopted dataset BEFORE allocating the sole WebGL renderer.
  var study = DATA.arcade_capacity, studyUrl = new URL(location.href);
  var studyChoice = study.options.find(function(o){return o.id===studyUrl.searchParams.get("scheme");}) || study.options[1];
  if(studyUrl.searchParams.get("scheme")!==studyChoice.id){studyUrl.searchParams.set("scheme",studyChoice.id);location.replace(studyUrl.href);return;}
  DATA = studyChoice.model;
  document.body.classList.add("capacity-study");document.body.setAttribute("data-study-option",studyChoice.id);
  document.title="ABC32地坪含騎樓容量 · "+studyChoice.label+"（未採用）";
  document.querySelector("h1").textContent="ABC · 騎樓容量比較3D";
  document.getElementById("canvas").setAttribute("aria-label","ABC "+studyChoice.label+"（未採用／非核准）");
  document.getElementById("tour-notice").textContent="歷史骨架比較、未採用；現行A主案已另重排，本頁不是現行A。"+(studyChoice.id==="baseline"?
    "舊骨架全棟層高3m、A前帶仍作室內，不能直接沿用作騎樓。":studyChoice.id==="room-first"?
    "加深對照：A約40.71坪、B／C各約33.63坪，不是最小基地解；1F層高暫估4m，A樓上衣櫃仍待排。":
    "32坪含前3.9m、1F層高暫估4m；這個保留原骨架的排法，A客餐廳／C客廳有容量衝突，不可採用。")+
    "梁下淨高／建蔽未知。正常家具放不下就列待調整，不縮放。孝親房與洗澡仍在；C套衛轉位、停車／搬轎／法規未核。";
  var studySelect=document.getElementById("study-scheme");
  study.options.forEach(function(o){var n=document.createElement("option");n.value=o.id;n.textContent=o.label;studySelect.appendChild(n);});studySelect.value=studyChoice.id;
  function planUrl(){var h=new URLSearchParams(location.hash.slice(1));return "arcade-capacity.html#scheme="+studyChoice.id+"&building="+(h.get("building")||"A")+"&floor="+(h.get("floor")||"floor-1");}
  function syncStudyLink(){DATA.study_option.plan_url=planUrl();document.getElementById("study-plan-link").href=planUrl();var link=document.querySelector("#renderer-fallback a");if(link)link.href=planUrl();}
  studySelect.addEventListener("change",function(){var next=new URL(location.href);next.searchParams.set("scheme",studySelect.value);var h=new URLSearchParams(location.hash.slice(1));h.set("mode","tour");h.delete("room");h.set("view","front");next.hash=h.toString();location.assign(next.href);});
  var studyHash=new URLSearchParams(location.hash.slice(1));studyHash.set("mode","tour");
  if(!["A","B","C"].includes(studyHash.get("building")))studyHash.set("building","A");
  if(!["floor-1","floor-2","floor-3","floor-4"].includes(studyHash.get("floor")))studyHash.set("floor","floor-1");
  if(!studyHash.get("view"))studyHash.set("view","front");history.replaceState(null,"","#"+studyHash.toString());syncStudyLink();window.addEventListener("hashchange",syncStudyLink);
  var studyBadge=document.createElement("div");studyBadge.id="study-stage-note";
  studyBadge.textContent=studyChoice.label+" · 未採用／未核准；放不下項目見平面清單";document.getElementById("stage").appendChild(studyBadge);
