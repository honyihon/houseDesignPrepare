  // Door comparison only: visible option identity without changing any geometry.
  function doorShortLabel(id) {
    return id==="single-control"?"單片控制":id==="two-panel"?"兩片新案":"方案未知";
  }
  function doorLabelBadge(badge,choice,use) {
    var states={open:"門組全開",half:"半開不可通行",closed:"關門不可通行"};
    badge.textContent=doorShortLabel(choice.id)+" · "+states[use.id]+" · 未採用／濕地分時／照護救援未核";
    badge.dataset.doorOption=choice.id;
    badge.dataset.doorDisplayRevision="2";
    document.body.dataset.doorDisplayRevision="2";
  }
  function doorSyncRoomTitle(mesh,name) {
    bathSyncRoomTitle(mesh,name);
    if (presentation!=="tour") { return; }
    var title=document.getElementById("stage-title"),label=doorShortLabel(studyChoice.id);
    var subtitle=title.querySelector("small"),base=title.firstChild?title.firstChild.textContent:name;
    var compact=mesh&&mesh.userData.cell.key==="elder-bath"&&stage.clientWidth<=860;
    title.replaceChildren(document.createTextNode(compact?"C 1F · "+label+" · 套衛":label+" · "+base));
    if (subtitle) { title.appendChild(subtitle); }
    title.title=studyChoice.label+" · "+name;
    title.dataset.doorOption=studyChoice.id;
    title.dataset.doorDisplayRevision="2";
  }
