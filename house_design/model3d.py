from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from house_design.contracts import ContractError, ROOT, read_json
from house_design.drawings import REVISION_ROOT, assess_model3d_readiness, load_revision
from house_design.rendering import encode_html_json


THREE_PATH = ROOT / "assets/vendor/three/three.min.js"


def _model_payload(manifest: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    entities = model.get("entities") if isinstance(model.get("entities"), dict) else {}
    storeys = [item for item in entities.get("storeys", []) if isinstance(item, dict)]
    elevations = {
        (str(item.get("building_id")), str(item.get("floor_id"))): float(item["elevation_mm"])
        for item in storeys
        if item.get("building_id")
        and item.get("floor_id")
        and isinstance(item.get("elevation_mm"), (int, float))
    }
    storey_heights: dict[tuple[str, str], tuple[float, str]] = {}
    for storey in storeys:
        key = (str(storey.get("building_id")), str(storey.get("floor_id")))
        if isinstance(storey.get("height_mm"), (int, float)) and float(storey["height_mm"]) > 0:
            storey_heights[key] = (float(storey["height_mm"]), "verified_storey_height")
            continue
        elevation = elevations.get(key)
        if elevation is None:
            storey_heights[key] = (2800.0, "display_only_default")
            continue
        higher = sorted(
            value for location, value in elevations.items() if location[0] == key[0] and value > elevation
        )
        if higher:
            storey_heights[key] = (higher[0] - elevation, "derived_from_adjacent_elevations")
        else:
            storey_heights[key] = (2800.0, "display_only_default")

    spaces: list[dict[str, Any]] = []
    for item in entities.get("spaces", []):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox_mm")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        key = (str(item.get("building_id")), str(item.get("floor_id")))
        height, height_source = storey_heights.get(key, (2800.0, "display_only_default"))
        if isinstance(item.get("height_mm"), (int, float)) and float(item["height_mm"]) > 0:
            height, height_source = float(item["height_mm"]), "verified_space_height"
        spaces.append(
            {
                "id": str(item.get("id")),
                "name": str(item.get("name") or item.get("id") or "未命名空間"),
                "building_id": key[0],
                "floor_id": key[1],
                "bbox_mm": [float(value) for value in bbox],
                "elevation_mm": elevations.get(key, 0.0),
                "display_height_mm": height,
                "height_source": height_source,
                "area_sqm": item.get("area_sqm"),
                "requirement_id": item.get("requirement_id"),
                "geometry_method": item.get("geometry_method") or "bounding_box",
                "geometry_provenance": item.get("geometry_provenance"),
            }
        )
    return {
        "schema": "house-space-block-viewer-v1",
        "revision": {
            "revision_id": manifest.get("revision_id"),
            "label": manifest.get("label"),
            "content_hash": manifest.get("content_hash"),
        },
        "coordinate_system": model.get("coordinate_system"),
        "spaces": spaces,
    }


def render_space_block_html(payload: dict[str, Any], three_source: str) -> str:
    revision = payload.get("revision") or {}
    revision_id = html.escape(str(revision.get("revision_id") or "unknown"))
    label = html.escape(str(revision.get("label") or "未命名版次"))
    data = encode_html_json(payload)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>空間量體模型 · {revision_id}</title>
  <style>
    :root {{ color-scheme: light; --ink:#102a43; --muted:#627d98; --line:#d9e2ec; --blue:#2d6cdf; --panel:#f7fafc; }}
    * {{ box-sizing:border-box; }}
    html,body,#app {{ width:100%; height:100%; margin:0; overflow:hidden; font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif; color:var(--ink); }}
    #app {{ display:grid; grid-template-columns:320px minmax(0,1fr); background:#e8eef3; }}
    #panel {{ background:white; border-right:1px solid var(--line); overflow:auto; padding:20px; z-index:3; }}
    h1 {{ font-size:20px; margin:0 0 5px; }}
    .eyebrow,.note,.meta {{ color:var(--muted); font-size:12px; line-height:1.55; }}
    .warning {{ margin:14px 0; padding:10px 12px; background:#fff8e6; border:1px solid #f2d28b; border-radius:7px; font-size:12px; line-height:1.55; }}
    .group {{ margin-top:17px; }}
    .group h2 {{ font-size:12px; margin:0 0 7px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    button {{ font:inherit; }}
    .chip,.room {{ border:1px solid var(--line); background:white; color:var(--ink); border-radius:6px; cursor:pointer; }}
    .chip {{ min-height:34px; padding:0 11px; }}
    .chip[aria-pressed="true"],.room[aria-pressed="true"] {{ color:white; border-color:var(--blue); background:var(--blue); }}
    .room-list {{ display:grid; gap:6px; }}
    .room {{ padding:9px 10px; text-align:left; }}
    .room small {{ display:block; color:inherit; opacity:.75; margin-top:2px; }}
    #info {{ border-top:1px solid var(--line); margin-top:16px; padding-top:13px; font-size:12px; line-height:1.65; }}
    #stage {{ position:relative; min-width:0; min-height:0; }}
    #canvas {{ display:block; width:100%; height:100%; outline:none; }}
    #canvas:focus-visible,button:focus-visible {{ outline:3px solid rgba(45,108,223,.35); outline-offset:2px; }}
    #orientation {{ position:absolute; right:14px; top:14px; padding:8px 10px; background:rgba(255,255,255,.9); border:1px solid var(--line); border-radius:6px; font-size:12px; }}
    #panel-toggle {{ display:none; position:absolute; left:12px; top:12px; z-index:5; min-height:42px; padding:0 12px; border:1px solid var(--line); border-radius:7px; background:white; color:var(--ink); }}
    @media (max-width:760px) {{
      #app {{ grid-template-columns:1fr; }}
      #panel {{ position:absolute; inset:0 0 45% 0; border:0; border-bottom:1px solid var(--line); padding:58px 16px 14px; transition:transform .2s ease; }}
      #app.panel-collapsed #panel {{ transform:translateY(calc(-100% + 52px)); }}
      #stage {{ grid-area:1/1; }}
      #panel-toggle {{ display:block; }}
    }}
  </style>
</head>
<body>
<div id="app">
  <button id="panel-toggle" type="button" aria-controls="panel" aria-expanded="true">收合控制</button>
  <aside id="panel" aria-label="空間量體篩選">
    <div class="eyebrow">現行圖面版次 · {revision_id}</div>
    <h1>空間量體模型</h1>
    <div class="meta">{label}</div>
    <div class="warning"><strong>用途界線：</strong>這是依可追溯房間平面與樓層標高建立的量體定位圖，不是施工精度 walkthrough；bbox 與頂層顯示高度不得拿來下料或碰撞檢核。</div>
    <section class="group"><h2>棟別</h2><div id="buildings" class="chips"></div></section>
    <section class="group"><h2>樓層</h2><div id="floors" class="chips"></div></section>
    <section class="group"><h2>空間 <span id="room-count"></span></h2><div id="room-list" class="room-list"></div></section>
    <div id="info" aria-live="polite">選擇一個空間可查看來源與量體限制。</div>
  </aside>
  <main id="stage">
    <canvas id="canvas" role="img" tabindex="0" aria-label="{revision_id} 空間量體三維模型；可用棟別、樓層與房間控制高亮區塊"></canvas>
    <div id="orientation">北向／原點依已驗證 mapping</div>
  </main>
</div>
<script>{three_source}</script>
<script id="model-data" type="application/json">{data}</script>
<script>
(() => {{
  const payload = JSON.parse(document.getElementById('model-data').textContent);
  const app = document.getElementById('app');
  const canvas = document.getElementById('canvas');
  const stage = document.getElementById('stage');
  const state = {{ building:'all', floor:'all', room:'' }};
  const colors = {{ A:0x4e79a7, B:0x59a14f, C:0xe15759 }};
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0xe8eef3);
  const camera = new THREE.PerspectiveCamera(45,1,.1,1000);
  const renderer = new THREE.WebGLRenderer({{canvas,antialias:true}}); renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  scene.add(new THREE.HemisphereLight(0xffffff,0x61758a,2.2));
  const light = new THREE.DirectionalLight(0xffffff,1.5); light.position.set(12,18,8); scene.add(light);
  const group = new THREE.Group(); scene.add(group);
  const meshes = new Map();
  const extents = {{minX:Infinity,maxX:-Infinity,minZ:Infinity,maxZ:-Infinity,maxY:0}};
  payload.spaces.forEach((space,index) => {{
    const b=space.bbox_mm, w=Math.max(100,b[2]-b[0])/1000, d=Math.max(100,b[3]-b[1])/1000, h=Math.max(300,space.display_height_mm)/1000;
    const geometry = new THREE.BoxGeometry(w,h,d);
    const material = new THREE.MeshStandardMaterial({{color:colors[space.building_id]||0x7b8794,transparent:true,opacity:.72,roughness:.72}});
    const mesh = new THREE.Mesh(geometry,material); mesh.position.set((b[0]+b[2])/2000,space.elevation_mm/1000+h/2,-(b[1]+b[3])/2000);
    mesh.userData=space; group.add(mesh); meshes.set(space.id,mesh);
    extents.minX=Math.min(extents.minX,mesh.position.x-w/2); extents.maxX=Math.max(extents.maxX,mesh.position.x+w/2);
    extents.minZ=Math.min(extents.minZ,mesh.position.z-d/2); extents.maxZ=Math.max(extents.maxZ,mesh.position.z+d/2); extents.maxY=Math.max(extents.maxY,mesh.position.y+h/2);
  }});
  const grid = new THREE.GridHelper(100,100,0x9fb3c4,0xcbd5df); scene.add(grid);
  let yaw=.7,pitch=.55,distance=20,target=new THREE.Vector3();
  function home() {{
    const span=Math.max(8,extents.maxX-extents.minX,extents.maxZ-extents.minZ,extents.maxY); distance=span*1.65;
    target.set((extents.minX+extents.maxX)/2,extents.maxY*.35,(extents.minZ+extents.maxZ)/2); updateCamera();
  }}
  function updateCamera() {{ camera.position.set(target.x+Math.sin(yaw)*Math.cos(pitch)*distance,target.y+Math.sin(pitch)*distance,target.z+Math.cos(yaw)*Math.cos(pitch)*distance); camera.lookAt(target); }}
  let dragging=false,lastX=0,lastY=0;
  canvas.addEventListener('pointerdown',e=>{{dragging=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId);}});
  canvas.addEventListener('pointermove',e=>{{if(!dragging)return;yaw-=(e.clientX-lastX)*.008;pitch=Math.max(.12,Math.min(1.35,pitch+(e.clientY-lastY)*.006));lastX=e.clientX;lastY=e.clientY;updateCamera();}});
  canvas.addEventListener('pointerup',()=>dragging=false); canvas.addEventListener('wheel',e=>{{e.preventDefault();distance=Math.max(3,distance*Math.exp(e.deltaY*.001));updateCamera();}},{{passive:false}});
  function unique(key) {{ return [...new Set(payload.spaces.map(x=>x[key]))].sort(); }}
  function chip(container,value,label,key) {{ const b=document.createElement('button');b.type='button';b.className='chip';b.dataset[key]=value;b.textContent=label;b.setAttribute('aria-pressed',String(state[key]===value));b.onclick=()=>{{state[key]=value;state.room='';if(key==='building'&&value!=='all'&&!visibleFloors().includes(state.floor))state.floor='all';render();}};container.appendChild(b); }}
  function visibleFloors() {{ return unique('floor_id').filter(f=>state.building==='all'||payload.spaces.some(s=>s.building_id===state.building&&s.floor_id===f)); }}
  function selectedSpaces() {{ return payload.spaces.filter(s=>(state.building==='all'||s.building_id===state.building)&&(state.floor==='all'||s.floor_id===state.floor)); }}
  function render() {{
    const buildings=document.getElementById('buildings');buildings.innerHTML='';chip(buildings,'all','全部','building');unique('building_id').forEach(x=>chip(buildings,x,`${{x}} 棟`,'building'));
    const floors=document.getElementById('floors');floors.innerHTML='';chip(floors,'all','全部','floor');visibleFloors().forEach(x=>chip(floors,x,x.replace('floor-','').toUpperCase(),'floor'));
    const rooms=selectedSpaces(), list=document.getElementById('room-list'); list.innerHTML='';document.getElementById('room-count').textContent=`(${{rooms.length}})`;
    rooms.forEach(space=>{{const b=document.createElement('button');b.type='button';b.className='room';b.dataset.room=space.id;b.setAttribute('aria-pressed',String(state.room===space.id));b.innerHTML=`${{escapeText(space.name)}}<small>${{escapeText(space.building_id)}} · ${{escapeText(space.floor_id)}}</small>`;b.onclick=()=>{{state.room=space.id;render();}};list.appendChild(b);}});
    meshes.forEach((mesh,id)=>{{const s=mesh.userData,visible=(state.building==='all'||s.building_id===state.building)&&(state.floor==='all'||s.floor_id===state.floor);mesh.visible=visible;mesh.material.opacity=state.room?(id===state.room?1:.12):.72;mesh.material.emissive.setHex(id===state.room?0x223344:0x000000);}});
    const selected=payload.spaces.find(s=>s.id===state.room);document.getElementById('info').innerHTML=selected?`<strong>${{escapeText(selected.name)}}</strong><br>${{escapeText(selected.building_id)}}棟 · ${{escapeText(selected.floor_id)}} · ${{Number(selected.area_sqm||0).toFixed(2)}} m²<br>平面：${{escapeText(selected.geometry_method)}}<br>高度：${{escapeText(selected.height_source)}}<br>來源：${{escapeText(selected.geometry_provenance||'unknown')}}`:'選擇一個空間可查看來源與量體限制。';
  }}
  function escapeText(value) {{ return String(value??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
  function resize() {{const r=stage.getBoundingClientRect();renderer.setSize(r.width,r.height,false);camera.aspect=r.width/Math.max(1,r.height);camera.updateProjectionMatrix();}};
  new ResizeObserver(resize).observe(stage); document.getElementById('panel-toggle').onclick=()=>{{app.classList.toggle('panel-collapsed');const collapsed=app.classList.contains('panel-collapsed');const button=document.getElementById('panel-toggle');button.textContent=collapsed?'展開控制':'收合控制';button.setAttribute('aria-expanded',String(!collapsed));}};
  home();render();resize();(function loop(){{renderer.render(scene,camera);requestAnimationFrame(loop);}})();
  window.__spaceBlockDebug=()=>({{state:{{...state}},visible:[...meshes.values()].filter(x=>x.visible).map(x=>x.userData.id),spaces:payload.spaces.length}});
}})();
</script>
</body></html>"""


def export_revision_model3d(
    *,
    revision_id: str,
    root: Path = REVISION_ROOT,
    output: Path | None = None,
    output_root: Path = ROOT / "structured/reviews",
) -> dict[str, Any]:
    manifest, model = load_revision(revision_id, root)
    readiness = assess_model3d_readiness(manifest, model, "space_block")
    if not readiness["eligible"]:
        codes = ", ".join(str(item["code"]) for item in readiness["blockers"])
        raise ContractError(f"revision {revision_id} is not ready for a space-block model: {codes}")
    if not THREE_PATH.is_file():
        raise ContractError(f"Missing bundled Three.js runtime: {THREE_PATH}")
    target = output or output_root / revision_id / "model3d.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _model_payload(manifest, model)
    target.write_text(render_space_block_html(payload, THREE_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    report_path = target.parent / "report.json"
    if target.name == "model3d.html" and report_path.is_file():
        # Keep the sibling dashboard link honest: it appears only after both
        # readiness and the actual artifact have been verified.
        from house_design.dashboard import write_dashboard

        write_dashboard(read_json(report_path), target.parent)
    return {
        "schema": "house-model3d-export-v1",
        "revision_id": revision_id,
        "level": "space_block",
        "label": "空間量體模型",
        "output": str(target),
        "spaces": len(payload["spaces"]),
        "self_contained": True,
    }
