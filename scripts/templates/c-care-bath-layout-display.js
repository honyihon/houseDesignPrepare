  // Independent layout identity only. No geometry, camera or visibility edits.
  function layoutShortLabel(id) {
    return id==="door-control"?"原門組":id==="side-basin"?"側盆比較":"方案未知";
  }
  function layoutLabelBadge(badge,choice,use) {
    var states={open:"門組全開",half:"半開不可通行",closed:"關門不可通行"};
    badge.textContent=layoutShortLabel(choice.id)+" · "+states[use.id]+" · 未採用／濕地分時／照護救援未核";
    badge.dataset.layoutOption=choice.id;
    badge.dataset.layoutDisplayRevision="1";
    document.body.dataset.layoutDisplayRevision="1";
  }
  function layoutSyncRoomTitle(mesh,name) {
    bathSyncRoomTitle(mesh,name);
    if (presentation!=="tour") { return; }
    var title=document.getElementById("stage-title"),label=layoutShortLabel(studyChoice.id);
    var subtitle=title.querySelector("small"),base=title.firstChild?title.firstChild.textContent:name;
    var compact=mesh&&mesh.userData.cell.key==="elder-bath"&&stage.clientWidth<=860;
    title.replaceChildren(document.createTextNode(compact?"C 1F · "+label+" · 套衛":label+" · "+base));
    if (subtitle) { title.appendChild(subtitle); }
    title.title=studyChoice.label+" · "+name;
    title.dataset.layoutOption=studyChoice.id;
    title.dataset.layoutDisplayRevision="1";
  }
