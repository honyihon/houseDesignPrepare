  // Select data before any meshes exist. Switching reloads this one renderer,
  // so alternatives never accumulate canvases or mutate the active ABC design.
  var study = DATA.c1f_options;
  var studyUrl = new URL(location.href);
  var studyChoice = study.options.find(function (o) { return o.id === studyUrl.searchParams.get("scheme"); }) || study.options[0];
  // File URLs only permit hash changes through history.replaceState in some
  // browsers. Normalize a missing/invalid query with real navigation, before
  // creating a renderer, rather than leaving double-click entry blank.
  if (studyUrl.searchParams.get("scheme") !== studyChoice.id) {
    studyUrl.searchParams.set("scheme", studyChoice.id);
    location.replace(studyUrl.href);
    return;
  }
  DATA = studyChoice.model;
  document.body.classList.add("c1f-study");
  document.body.setAttribute("data-study-option", studyChoice.id);
  document.title = "C 1F 公衛／採光比較 · " + studyChoice.label + "（未採用）";
  document.querySelector("h1").textContent = "C 一樓公衛／採光 · 比較用 3D";
  document.getElementById("canvas").setAttribute("aria-label", "C 一樓公衛／採光 · " + studyChoice.label + "（比較用，未採用）");
  document.getElementById("tour-notice").textContent = "比較案尚未採用，不取代 ABC 主案。" + studyChoice.label + "；保留孝親房、套衛、同軸樓梯與前方通行帶。新增濕區、完成面淨空、採光／通風及冷氣安裝均未專業核准。";
  var studySelect = document.getElementById("study-scheme");
  study.options.forEach(function (o) {
    var el = document.createElement("option"); el.value = o.id; el.textContent = o.label; studySelect.appendChild(el);
  });
  studySelect.value = studyChoice.id;
  document.getElementById("study-plan-link").href = "c1f-options.html#scheme=" + studyChoice.id;
  studySelect.addEventListener("change", function () {
    var next = new URL(location.href);
    next.searchParams.set("scheme", studySelect.value);
    next.hash = "mode=tour&building=C&floor=floor-1&view=front";
    location.assign(next.href);
  });
  var studyHash = new URLSearchParams(location.hash.replace(/^#/, ""));
  studyHash.set("mode", "tour"); studyHash.set("building", "C");
  if (!studyHash.get("floor")) studyHash.set("floor", "floor-1");
  if (!studyHash.get("view")) studyHash.set("view", "front");
  history.replaceState(null, "", "#" + studyHash.toString());
  var studyBadge = document.createElement("div");
  studyBadge.id = "study-stage-note"; studyBadge.textContent = studyChoice.label + " · 比較用，未採用／未核准";
  document.getElementById("stage").appendChild(studyBadge);
