from __future__ import annotations

import html
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from house_design.brief import BRIEF_SCHEMA, design_brief_hash, design_brief_html, design_brief_markdown
from house_design.contracts import (
    ROOT,
    ContractError,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)
from house_design.drawings import import_revision, load_revision, revision_model3d_readiness
from house_design.revision_integrity import revision_dir

HANDOFF_SCHEMA = "house-architect-handoff-v1"
DELIVERY_SCHEMA = "house-architect-delivery-v1"
PREFLIGHT_SCHEMA = "house-architect-delivery-preflight-v1"
PREDECESSOR_FILES = (
    "index.html",
    "AbuildingView.html",
    "BbuildingView.html",
    "CbuildingView.html",
)
DEFAULT_PREDECESSOR_ROOT = Path("/mnt/d/Desktop/houseDesign")
DEFAULT_HANDOFF_ROOT = ROOT / "structured/architect_handoffs"
PLACEHOLDERS = {"", "__FILL__", "TBD", "TODO", "待填", "待確認", "unknown"}


def _filled(value: Any) -> bool:
    return isinstance(value, str) and value.strip() not in PLACEHOLDERS


def _floor_key(value: str) -> tuple[int, str]:
    order = {"floor-1": 1, "floor-2": 2, "floor-3": 3, "floor-rf": 99}
    return order.get(value, 50), value


def _expected_scope(requirements: dict[str, Any]) -> dict[str, Any]:
    records = [item for item in requirements.get("requirements", []) if isinstance(item, dict)]
    locations = {
        (
            str(item.get("applies_to", {}).get("building_id") or ""),
            str(item.get("applies_to", {}).get("floor_id") or ""),
        )
        for item in records
        if isinstance(item.get("applies_to"), dict)
    }
    locations.discard(("", ""))
    buildings = sorted({building for building, _floor in locations if building})
    requirement_statuses = Counter(str(item.get("status") or "unknown") for item in records)
    requirement_priorities = Counter(str(item.get("priority") or "unknown") for item in records)
    return {
        "buildings": buildings,
        "storeys": [
            {"building_id": building, "floor_id": floor}
            for building, floor in sorted(locations, key=lambda item: (item[0], _floor_key(item[1])))
        ],
        "requirement_ids": [str(item["id"]) for item in records if item.get("id")],
        "confirmed_must_requirement_ids": [
            str(item["id"])
            for item in records
            if item.get("id") and item.get("status") == "confirmed" and item.get("priority") == "must"
        ],
        "requirement_status_counts": dict(sorted(requirement_statuses.items())),
        "requirement_priority_counts": dict(sorted(requirement_priorities.items())),
        "relationship_count": sum(
            len(item["relationships"]) for item in records if isinstance(item.get("relationships"), list)
        ),
    }


def _verified_design_brief(brief_path: Path, *, project_path: Path, requirements_path: Path) -> dict[str, Any]:
    """Refuse a brief that was edited by hand or describes other project or requirement files."""

    if not brief_path.is_file():
        raise ContractError(f"design brief not found: {brief_path}; run predesign brief first")
    brief = read_json(brief_path)
    if brief.get("schema") != BRIEF_SCHEMA:
        raise ContractError(f"design brief schema must be {BRIEF_SCHEMA}")
    if brief.get("brief_hash") != design_brief_hash(brief):
        raise ContractError("design brief content does not match its brief_hash; rerun predesign brief")
    sources = {str(item.get("key")): item for item in brief.get("sources") or [] if isinstance(item, dict)}
    stale = [
        key
        for key, source_path in (("project", project_path), ("requirements", requirements_path))
        if sources.get(key, {}).get("sha256") != sha256_file(source_path)
    ]
    if stale:
        raise ContractError(f"design brief is stale ({', '.join(stale)} changed); rerun predesign brief")
    return brief


def _mapping_template(scope: dict[str, Any]) -> dict[str, Any]:
    storeys = []
    for item in scope["storeys"]:
        floor_id = item["floor_id"]
        nominal_elevation = {
            "floor-1": 0,
            "floor-2": None,
            "floor-3": None,
            "floor-rf": None,
        }.get(floor_id)
        storeys.append(
            {
                **item,
                "name": floor_id,
                "elevation_mm": nominal_elevation,
                "height_mm": None,
                "verified_by": "__FILL__",
                "verified_at": "__FILL__",
                "evidence": {"type": "drawing_note", "reference": "__FILL__"},
            }
        )
    return {
        "schema": "house-drawing-mapping-v2",
        "coordinate_system": {
            "status": "draft",
            "unit": "mm",
            "axis": {"x": "__FILL__", "y": "__FILL__", "z": "up"},
            "verified_by": "__FILL__",
            "verified_at": "__FILL__",
            "method": "__FILL__",
            "reference_points": [
                {"id": "P1", "source_mm": None, "project_mm": None, "evidence": "__FILL__"},
                {"id": "P2", "source_mm": None, "project_mm": None, "evidence": "__FILL__"},
            ],
        },
        "dxf_unit_scale_to_mm": 1.0,
        "storeys": storeys,
        "layers": {},
        "entities": {},
        "ifc_entities": {},
        "walkthrough_scope": {
            "equipment": {
                "status": "draft",
                "verified_by": "__FILL__",
                "verified_at": "__FILL__",
                "evidence": "__FILL__",
            }
        },
        "examples_do_not_import": {
            "space_layer": {
                "ROOM-A-1F": {
                    "kind": "space",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "name": "客廳",
                    "requirement_id": "A.floor-1.living",
                }
            },
            "door_entity": {
                "2A7": {
                    "kind": "door",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "height_mm": 2100,
                    "opening_width": {
                        "value_mm": 900,
                        "measurement": "finished_clear",
                        "verified_by": "__FILL__",
                        "verified_at": "__FILL__",
                        "evidence": {"type": "door_schedule", "reference": "D01"},
                    },
                }
            },
        },
    }


def _delivery_template(revision_id: str, label: str) -> dict[str, Any]:
    return {
        "schema": DELIVERY_SCHEMA,
        "revision_id": revision_id,
        "label": label,
        "prepared_by": "__FILL__",
        "prepared_at": "__FILL__",
        "files": {
            "pdf": None,
            "ifc": None,
            "dxf": None,
            "mapping": "mapping.json",
        },
        "declarations": {
            "building_ids": ["A", "B", "C"],
            "source_files_are_final_for_this_revision": False,
            "coordinate_system_reviewed": False,
            "storey_elevations_reviewed": False,
            "room_boundaries_reviewed": False,
            "openings_include_position_and_height": False,
            "equipment_scope_reviewed": False,
        },
        "notes": [],
    }


def _render_request_markdown(manifest: dict[str, Any]) -> str:
    revision_id = manifest["revision_id"]
    scope = manifest["expected_scope"]
    storeys = "、".join(f"{item['building_id']} {item['floor_id']}" for item in scope["storeys"])
    site_note = (
        "目前土地尚未選定；本包是未來圖面交付契約，不是開始定案或施工授權。"
        if not manifest["project_gate"]["site_selected"]
        else "基地已在 project snapshot 中標記為選定，仍須以正式地籍與專業預檢為準。"
    )
    brief = manifest["snapshots"].get("design_brief")
    brief_section = (
        f"""
## 設計需求

- 先閱讀 `design-brief.html`（或 `design-brief.md`）：棟別定位、需求分段、空間關係、大型實物與開會待問問題；任務書雜湊 `{brief['brief_hash']}`。
- 「待屋主決定」的項目只是討論起點，不是硬需求；面積與樓層沿用舊版配置，請依實際基地重新推導。
- 任務書與 `owner-requirements.snapshot.json` 出自同一份需求登錄；內容有疑義時以需求快照及其決策紀錄為準。
"""
        if brief
        else ""
    )
    return f"""# {revision_id} 建築師圖面交付需求

> {site_note}
{brief_section}
## 必交檔案

- 同一版次的 PDF 圖冊。
- 優先提供 IFC；若只有 DWG，請另存 DXF。IFC 與 DXF 可同時提供，但跨格式合併只接受明確 IFC GlobalId。
- 填妥 `delivery.json` 與 `mapping.json`；所有檔案應放在本目錄內並使用相對路徑。
- 前身 A／B／C HTML 位於 `legacy-reference/`，只用來討論房間需求與名稱，不是基地、權威幾何或合規證據。

## 必須可追溯的模型資料

- 棟別只使用：{', '.join(scope['buildings'])}。
- 預期棟層：{storeys}。
- 每個 IfcSpace 或 DXF 閉合空間需有棟別、樓層、名稱；能對應屋主需求時填 `requirement_id`。
- 座標需寫明單位、軸向、查核人、日期、方法及至少兩個共同基準點。
- 樓層需提供 `elevation_mm`、層高、查核人、日期及圖號證據；1F 也要明列 0 mm 基準。
- 走入式模型另需：精確空間 polygon、牆、樓梯、門窗位置與高度、固定設備位置或經查核的不適用聲明。
- 門窗幾何外框不可自動當成完工淨寬；淨寬必須標示量測型態並附門窗表／圖號證據。

## 交回前檢查

將檔案放入本包並更新 `delivery.json` 後，在專案根目錄執行：

```bash
.venv/bin/python -m house_design drawings preflight --package {manifest['package_path']}
```

preflight 使用暫存目錄試匯入，不會建立或覆寫 `inputs/revisions/{revision_id}`。通過後才執行正式不可變匯入；若要修改圖面，使用新的 revision id，不得覆寫既有版次。

## 狀態解讀

- `ready_for_import`：檔案格式、mapping 與語意足以建立正常版次。
- `ready_for_space_block`：可產生有來源追溯的空間量體 3D。
- `ready_for_walkthrough`：牆、開口、樓梯、高度及設備範圍也完整；仍不等於法規或施工簽證。
"""


def _render_request_html(manifest: dict[str, Any], markdown_text: str) -> str:
    scope = manifest["expected_scope"]
    rows = "".join(
        f"<tr><td>{html.escape(item['building_id'])}</td><td>{html.escape(item['floor_id'])}</td>"
        "<td>□ 標高　□ 層高　□ 圖號證據</td></tr>"
        for item in scope["storeys"]
    )
    site_warning = (
        "土地尚未選定：這是未來交付規格，不是開始定案或施工授權。"
        if not manifest["project_gate"]["site_selected"]
        else "基地仍須以正式文件與專業預檢確認。"
    )
    brief = manifest["snapshots"].get("design_brief")
    brief_html = (
        '<h2>設計需求</h2><p>請先閱讀 <a href="design-brief.html">設計任務書</a>'
        f"（任務書雜湊 <code>{html.escape(brief['brief_hash'])}</code>）。「待屋主決定」的項目只是討論起點，"
        "不是硬需求；面積與樓層沿用舊版配置，請依實際基地重新推導。</p>"
        if brief
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(manifest['revision_id'])} 建築師交付需求</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;color:#17212b;max-width:960px;margin:32px auto;padding:0 20px}}h1,h2{{line-height:1.25}}.warn{{border-left:5px solid #b45309;background:#fff7ed;padding:14px 16px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #b8c2cc;padding:8px;text-align:left}}code{{background:#eef2f6;padding:2px 5px}}@media print{{body{{margin:0;max-width:none}}}}</style></head>
<body><h1>{html.escape(manifest['revision_id'])} 建築師圖面交付需求</h1><p class="warn">{html.escape(site_warning)}</p>{brief_html}
<h2>檔案</h2><ul><li>PDF ＋ IFC（優先），或 PDF ＋ DXF。</li><li>填妥 <code>delivery.json</code> 與 <code>mapping.json</code>。</li><li>前身 HTML 只供需求對照，不是權威幾何。</li></ul>
<h2>預期棟層</h2><table><thead><tr><th>棟</th><th>樓層</th><th>必要證據</th></tr></thead><tbody>{rows}</tbody></table>
<h2>模型內容</h2><ul><li>空間閉合邊界、棟層位置與 requirement_id。</li><li>已驗證座標、至少兩個基準點及各層標高。</li><li>walkthrough 另需牆、樓梯、門窗位置／高度、設備範圍。</li><li>完工門淨寬需獨立量測型態與圖號證據。</li></ul>
<h2>交回前</h2><p>執行 <code>house-design drawings preflight --package {html.escape(manifest['package_path'])}</code>；此步只在暫存目錄試匯入，不建立 R001。</p>
<details><summary>Markdown 原文</summary><pre>{html.escape(markdown_text)}</pre></details></body></html>"""


def create_handoff_package(
    *,
    revision_id: str = "R001",
    label: str = "初步設計",
    output_root: Path = DEFAULT_HANDOFF_ROOT,
    predecessor_root: Path = DEFAULT_PREDECESSOR_ROOT,
    project_path: Path = ROOT / "inputs/project.json",
    requirements_path: Path = ROOT / "inputs/requirements.json",
    brief_path: Path | None = None,
) -> dict[str, Any]:
    """Create a future architect-delivery contract without creating a revision."""

    revision_dir(revision_id, Path("."))  # Reuse the public revision-id validation contract.
    target = output_root / revision_id
    if target.exists() and any(target.iterdir()):
        raise ContractError(f"handoff package already exists and is not empty: {target}")
    missing = [name for name in PREDECESSOR_FILES if not (predecessor_root / name).is_file()]
    if missing:
        raise ContractError(f"predecessor HTML source is incomplete: {', '.join(missing)}")

    brief = (
        _verified_design_brief(brief_path, project_path=project_path, requirements_path=requirements_path)
        if brief_path is not None
        else None
    )
    planning_report = None
    if brief is not None and brief.get("planning") and brief_path is not None:
        planning_report = read_json(brief_path.parent / "risk-review.json")
        digest = stable_hash({k: v for k, v in planning_report.items() if k not in {"generated_at", "report_hash"}})
        if (planning_report.get("schema") != "house-planning-review-v1"
                or digest != planning_report.get("report_hash")
                or digest != brief["planning"].get("report_hash")):
            raise ContractError("Risk review and design brief disagree; regenerate risk-review then brief before handoff")

    project = read_json(project_path)
    requirements = read_json(requirements_path)
    scope = _expected_scope(requirements)
    target.mkdir(parents=True, exist_ok=True)
    reference_dir = target / "legacy-reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    predecessor_records = []
    for name in PREDECESSOR_FILES:
        source = predecessor_root / name
        destination = reference_dir / name
        shutil.copy2(source, destination)
        predecessor_records.append(
            {
                "file": f"legacy-reference/{name}",
                "source_path": str(source.resolve()),
                "sha256": sha256_file(destination),
                "size_bytes": destination.stat().st_size,
                "authority": "historical_requirement_reference_only",
            }
        )

    write_json(target / "project.snapshot.json", project)
    write_json(target / "owner-requirements.snapshot.json", requirements)
    write_json(target / "delivery.json", _delivery_template(revision_id, label))
    write_json(target / "mapping.json", _mapping_template(scope))
    snapshots: dict[str, dict[str, Any]] = {
        "project": {
            "file": "project.snapshot.json",
            "sha256": sha256_file(target / "project.snapshot.json"),
        },
        "requirements": {
            "file": "owner-requirements.snapshot.json",
            "sha256": sha256_file(target / "owner-requirements.snapshot.json"),
        },
    }
    if planning_report is not None:
        from house_design.planning import write_risk_review

        paths = write_risk_review(planning_report, target)
        for kind, path in paths.items():
            snapshots[f"risk_review_{kind}"] = {"file": path.name, "sha256": sha256_file(path)}
    if brief is not None and brief_path is not None:
        # The JSON keeps its exact bytes; the readable copies are re-rendered from the verified JSON
        # so a stale design-brief.md or .html next to it can never enter the package.
        shutil.copy2(brief_path, target / "design-brief.snapshot.json")
        (target / "design-brief.md").write_text(design_brief_markdown(brief), encoding="utf-8", newline="\n")
        (target / "design-brief.html").write_text(design_brief_html(brief), encoding="utf-8", newline="\n")
        snapshots["design_brief"] = {
            "file": "design-brief.snapshot.json",
            "sha256": sha256_file(target / "design-brief.snapshot.json"),
            "brief_hash": brief["brief_hash"],
        }
        snapshots["design_brief_markdown"] = {
            "file": "design-brief.md",
            "sha256": sha256_file(target / "design-brief.md"),
        }
        snapshots["design_brief_html"] = {
            "file": "design-brief.html",
            "sha256": sha256_file(target / "design-brief.html"),
        }
    selected_site = project.get("site_search", {}).get("selected_site")
    manifest = {
        "schema": HANDOFF_SCHEMA,
        "revision_id": revision_id,
        "label": label,
        "generated_at": utc_now(),
        "package_path": target.as_posix(),
        "state": "request_template",
        "immutable_revision_created": False,
        "project_gate": {
            "stage": project.get("stage"),
            "site_selected": selected_site is not None,
            "note": "A technical delivery may be preflighted, but design release remains subject to project gates.",
        },
        "predecessor": {
            "source_root": str(predecessor_root.resolve()),
            "files": predecessor_records,
            "policy": "Historical HTML is a room-discussion reference, never authoritative site or drawing geometry.",
        },
        "expected_scope": scope,
        "snapshots": snapshots,
    }
    request_markdown = _render_request_markdown(manifest)
    (target / "README.md").write_text(request_markdown, encoding="utf-8", newline="\n")
    (target / "architect-request.html").write_text(
        _render_request_html(manifest, request_markdown), encoding="utf-8", newline="\n"
    )
    write_json(target / "handoff-manifest.json", manifest)
    return {
        "schema": HANDOFF_SCHEMA,
        "revision_id": revision_id,
        "package": str(target),
        "manifest": str(target / "handoff-manifest.json"),
        "request_markdown": str(target / "README.md"),
        "request_html": str(target / "architect-request.html"),
        "predecessor_files": len(predecessor_records),
        "expected_storeys": len(scope["storeys"]),
        "design_brief": str(target / "design-brief.html") if brief is not None else None,
        "brief_hash": brief["brief_hash"] if brief is not None else None,
        "site_selected": selected_site is not None,
        "immutable_revision_created": False,
    }


def _package_file(package: Path, reference: Any) -> Path | None:
    if not _filled(reference):
        return None
    candidate = (package / str(reference)).resolve()
    try:
        candidate.relative_to(package.resolve())
    except ValueError as exc:
        raise ContractError(f"delivery file escapes the handoff package: {reference}") from exc
    return candidate


def _looks_like(path: Path, kind: str) -> bool:
    sample = path.read_bytes()[:8192]
    if kind == "pdf":
        return sample.startswith(b"%PDF-")
    text = sample.decode("utf-8", errors="ignore").upper()
    if kind == "ifc":
        return "ISO-10303-21" in text and "FILE_SCHEMA" in text
    if kind == "dxf":
        return "SECTION" in text and ("HEADER" in text or "ENTITIES" in text)
    return True


def _valid_iso_date(value: Any) -> bool:
    if not _filled(value):
        return False
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def preflight_handoff_package(package: Path) -> dict[str, Any]:
    """Preview-import an architect delivery without creating an immutable revision."""

    package = package.resolve()
    checks: list[dict[str, Any]] = []

    def add(
        code: str,
        status: str,
        message: str,
        *,
        blocks: tuple[str, ...] = (),
        next_action: str | None = None,
        **details: Any,
    ) -> None:
        item: dict[str, Any] = {"code": code, "status": status, "message": message, "blocks": list(blocks)}
        if next_action:
            item["next_action"] = next_action
        if details:
            item["details"] = details
        checks.append(item)

    if not package.is_dir():
        add(
            "PACKAGE_MISSING",
            "fail",
            f"交付包目錄不存在：{package}",
            blocks=("import", "space_block", "walkthrough"),
            next_action="確認 --package 路徑。",
        )
        return _finish_preflight(package, None, checks, None, None, None)

    manifest: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None
    try:
        manifest = read_json(package / "handoff-manifest.json")
        valid = manifest.get("schema") == HANDOFF_SCHEMA
        add(
            "HANDOFF_MANIFEST",
            "pass" if valid else "fail",
            "交付包 manifest 格式正確。" if valid else "handoff-manifest.json schema 不正確。",
            blocks=() if valid else ("import", "space_block", "walkthrough"),
        )
    except ContractError as exc:
        add(
            "HANDOFF_MANIFEST",
            "fail",
            str(exc),
            blocks=("import", "space_block", "walkthrough"),
            next_action="重新執行 drawings prepare-handoff 建立交付包。",
        )
    try:
        delivery = read_json(package / "delivery.json")
        valid = delivery.get("schema") == DELIVERY_SCHEMA
        add(
            "DELIVERY_MANIFEST",
            "pass" if valid else "fail",
            "delivery.json 格式正確。" if valid else "delivery.json schema 不正確。",
            blocks=() if valid else ("import", "space_block", "walkthrough"),
        )
    except ContractError as exc:
        add(
            "DELIVERY_MANIFEST",
            "fail",
            str(exc),
            blocks=("import", "space_block", "walkthrough"),
            next_action="填妥交付包內的 delivery.json。",
        )
    if manifest is None or delivery is None:
        return _finish_preflight(package, None, checks, None, None, None)

    revision_id = str(manifest.get("revision_id") or "")
    revision_match = bool(revision_id and delivery.get("revision_id") == revision_id)
    add(
        "REVISION_ID_MATCH",
        "pass" if revision_match else "fail",
        "交付版次 id 一致。" if revision_match else "delivery.json 與 handoff manifest 的 revision id 不一致。",
        blocks=() if revision_match else ("import", "space_block", "walkthrough"),
    )
    prepared = _filled(delivery.get("prepared_by")) and _valid_iso_date(delivery.get("prepared_at"))
    add(
        "PREPARER_EVIDENCE",
        "pass" if prepared else "fail",
        "交付人與日期已記錄。" if prepared else "prepared_by 或 prepared_at 尚未填妥。",
        blocks=() if prepared else ("import", "space_block", "walkthrough"),
        next_action=None if prepared else "填入可追溯的交付人與 ISO 日期。",
    )

    declarations = delivery.get("declarations") if isinstance(delivery.get("declarations"), dict) else {}
    required_declarations = (
        "source_files_are_final_for_this_revision",
        "coordinate_system_reviewed",
        "storey_elevations_reviewed",
        "room_boundaries_reviewed",
    )
    missing_declarations = [name for name in required_declarations if declarations.get(name) is not True]
    add(
        "DELIVERY_DECLARATIONS",
        "pass" if not missing_declarations else "fail",
        "必要交付聲明已確認。" if not missing_declarations else "仍有必要交付聲明未確認。",
        blocks=() if not missing_declarations else ("import", "space_block", "walkthrough"),
        next_action=None if not missing_declarations else "由交付人逐項查核 delivery.json declarations。",
        missing=missing_declarations,
    )
    expected_buildings = set(manifest.get("expected_scope", {}).get("buildings", []))
    declared_buildings = {
        str(item) for item in declarations.get("building_ids", []) if isinstance(item, str) and item
    }
    missing_buildings = sorted(expected_buildings - declared_buildings)
    add(
        "BUILDING_SCOPE_DECLARATION",
        "pass" if not missing_buildings else "fail",
        "交付聲明涵蓋所有預期棟別。" if not missing_buildings else "交付聲明缺少預期棟別。",
        blocks=() if not missing_buildings else ("import", "space_block", "walkthrough"),
        next_action=None if not missing_buildings else "在 delivery.json declarations.building_ids 補齊棟別。",
        missing=missing_buildings,
    )
    walkthrough_declarations = (
        declarations.get("openings_include_position_and_height") is True
        and declarations.get("equipment_scope_reviewed") is True
    )
    add(
        "WALKTHROUGH_DECLARATIONS",
        "pass" if walkthrough_declarations else "warning",
        "走入式模型聲明已確認。" if walkthrough_declarations else "門窗或設備範圍聲明尚未確認。",
        blocks=() if walkthrough_declarations else ("walkthrough",),
        next_action=None if walkthrough_declarations else "若要 walkthrough，補齊門窗位置／高度與設備範圍聲明。",
    )

    files = delivery.get("files") if isinstance(delivery.get("files"), dict) else {}
    resolved: dict[str, Path | None] = {}
    for kind in ("pdf", "ifc", "dxf", "mapping"):
        try:
            resolved[kind] = _package_file(package, files.get(kind))
        except ContractError as exc:
            resolved[kind] = None
            add(
                f"{kind.upper()}_PATH",
                "fail",
                str(exc),
                blocks=("import", "space_block", "walkthrough"),
            )

    pdf_exists = resolved["pdf"] is not None and resolved["pdf"].is_file()
    add(
        "PDF_SOURCE",
        "pass" if pdf_exists else "fail",
        "PDF 圖冊存在。" if pdf_exists else "缺少 PDF 圖冊。",
        blocks=() if pdf_exists else ("import", "space_block", "walkthrough"),
        next_action=None if pdf_exists else "將同版 PDF 放入包內並更新 delivery.json files.pdf。",
    )
    machine_kinds = [kind for kind in ("ifc", "dxf") if resolved[kind] is not None and resolved[kind].is_file()]
    add(
        "MACHINE_SOURCE",
        "pass" if machine_kinds else "fail",
        f"可機讀來源：{', '.join(machine_kinds)}。" if machine_kinds else "缺少 IFC 或 DXF。",
        blocks=() if machine_kinds else ("import", "space_block", "walkthrough"),
        next_action=None if machine_kinds else "提供 IFC；若只有 DWG，另存 DXF。",
    )
    for kind in ("pdf", *machine_kinds):
        path = resolved[kind]
        if path is None or not path.is_file():
            continue
        valid_signature = _looks_like(path, kind)
        add(
            f"{kind.upper()}_SIGNATURE",
            "pass" if valid_signature else "fail",
            f"{kind.upper()} 檔頭符合格式。" if valid_signature else f"{kind.upper()} 副檔名或檔頭不符。",
            blocks=() if valid_signature else ("import", "space_block", "walkthrough"),
        )

    mapping: dict[str, Any] | None = None
    mapping_path = resolved["mapping"]
    if mapping_path is None or not mapping_path.is_file():
        add(
            "MAPPING_SOURCE",
            "fail",
            "缺少 mapping.json。",
            blocks=("import", "space_block", "walkthrough"),
            next_action="填妥 mapping.json 並在 delivery.json 指向它。",
        )
    else:
        try:
            mapping = read_json(mapping_path)
            valid_schema = mapping.get("schema") == "house-drawing-mapping-v2"
            add(
                "MAPPING_SCHEMA",
                "pass" if valid_schema else "fail",
                "mapping v2 schema 正確。" if valid_schema else "mapping 必須使用 house-drawing-mapping-v2。",
                blocks=() if valid_schema else ("import", "space_block", "walkthrough"),
            )
        except ContractError as exc:
            add(
                "MAPPING_SOURCE",
                "fail",
                str(exc),
                blocks=("import", "space_block", "walkthrough"),
            )

    if mapping is not None:
        coordinate = mapping.get("coordinate_system") if isinstance(mapping.get("coordinate_system"), dict) else {}
        reference_points = coordinate.get("reference_points")
        coordinate_ready = (
            coordinate.get("status") in {"verified", "verified_aligned", "georeferenced"}
            and bool(coordinate.get("axis"))
            and _filled(coordinate.get("verified_by"))
            and _valid_iso_date(coordinate.get("verified_at"))
            and _filled(coordinate.get("method"))
            and isinstance(reference_points, list)
            and len(reference_points) >= 2
            and all(isinstance(point, dict) and _filled(point.get("id")) for point in reference_points[:2])
        )
        add(
            "COORDINATE_EVIDENCE",
            "pass" if coordinate_ready else "fail",
            "座標與兩個基準點證據完整。" if coordinate_ready else "座標驗證或基準點證據不完整。",
            blocks=() if coordinate_ready else ("space_block", "walkthrough"),
            next_action=None if coordinate_ready else "補單位、軸向、查核人／日期／方法及至少兩個基準點。",
        )
        expected_storeys = {
            (str(item.get("building_id")), str(item.get("floor_id")))
            for item in manifest.get("expected_scope", {}).get("storeys", [])
            if isinstance(item, dict)
        }
        verified_storeys = {
            (str(item.get("building_id")), str(item.get("floor_id")))
            for item in mapping.get("storeys", [])
            if isinstance(item, dict)
            and isinstance(item.get("elevation_mm"), (int, float))
            and not isinstance(item.get("elevation_mm"), bool)
            and _filled(item.get("verified_by"))
            and _valid_iso_date(item.get("verified_at"))
            and isinstance(item.get("evidence"), dict)
            and _filled(item["evidence"].get("reference"))
        }
        missing_storeys = sorted(expected_storeys - verified_storeys)
        add(
            "STOREY_EVIDENCE",
            "pass" if not missing_storeys else "fail",
            "所有預期棟層都有標高證據。" if not missing_storeys else "部分棟層缺少標高或圖號證據。",
            blocks=() if not missing_storeys else ("space_block", "walkthrough"),
            next_action=None if not missing_storeys else "補齊每一棟層 elevation_mm、查核人、日期及 evidence.reference。",
            missing=[{"building_id": item[0], "floor_id": item[1]} for item in missing_storeys],
        )
        if "dxf" in machine_kinds:
            has_semantic_mapping = bool(mapping.get("layers") or mapping.get("entities"))
            add(
                "DXF_SEMANTIC_MAPPING",
                "pass" if has_semantic_mapping else "fail",
                "DXF 已提供圖層或 entity 語意 mapping。" if has_semantic_mapping else "DXF 沒有語意 mapping。",
                blocks=() if has_semantic_mapping else ("import", "space_block", "walkthrough"),
                next_action=None if has_semantic_mapping else "將實際 DXF layer 或 handle 對應到 space／wall／door 等種類。",
            )

    blocking_before_preview = any(item["status"] == "fail" and "import" in item["blocks"] for item in checks)
    import_preview: dict[str, Any] | None = None
    space_readiness: dict[str, Any] | None = None
    walkthrough_readiness: dict[str, Any] | None = None
    if not blocking_before_preview and delivery is not None:
        try:
            with tempfile.TemporaryDirectory(prefix="house-design-handoff-") as temp_name:
                preview_root = Path(temp_name) / "revisions"
                import_preview = import_revision(
                    revision_id=revision_id,
                    label=str(delivery.get("label") or manifest.get("label") or revision_id),
                    pdf=resolved["pdf"],
                    ifc=resolved["ifc"] if "ifc" in machine_kinds else None,
                    dxf=resolved["dxf"] if "dxf" in machine_kinds else None,
                    mapping_path=mapping_path,
                    root=preview_root,
                )
                _preview_manifest, preview_model = load_revision(revision_id, preview_root)
                space_readiness = revision_model3d_readiness(revision_id, preview_root, "space_block")
                walkthrough_readiness = revision_model3d_readiness(revision_id, preview_root, "walkthrough")
                actual_locations = {
                    (str(item.get("building_id")), str(item.get("floor_id")))
                    for item in preview_model.get("entities", {}).get("spaces", [])
                    if isinstance(item, dict) and item.get("building_id") and item.get("floor_id")
                }
                expected_locations = {
                    (str(item.get("building_id")), str(item.get("floor_id")))
                    for item in manifest.get("expected_scope", {}).get("storeys", [])
                    if isinstance(item, dict)
                }
                missing_locations = sorted(expected_locations - actual_locations)
                add(
                    "SPACE_SCOPE_COVERAGE",
                    "pass" if not missing_locations else "fail",
                    "所有預期棟層都有空間語意。" if not missing_locations else "部分預期棟層沒有任何空間。",
                    blocks=() if not missing_locations else ("space_block", "walkthrough"),
                    next_action=None if not missing_locations else "在 IFC 提供 IfcSpace，或以 DXF mapping 建立各棟層閉合空間。",
                    missing=[{"building_id": item[0], "floor_id": item[1]} for item in missing_locations],
                )
                known_requirements = set(manifest.get("expected_scope", {}).get("requirement_ids", []))
                actual_requirements = {
                    str(item.get("requirement_id"))
                    for item in preview_model.get("entities", {}).get("spaces", [])
                    if isinstance(item, dict) and item.get("requirement_id")
                }
                unknown_requirements = sorted(actual_requirements - known_requirements)
                add(
                    "REQUIREMENT_REFERENCES",
                    "pass" if not unknown_requirements else "fail",
                    "圖面 requirement_id 都能回溯屋主需求。" if not unknown_requirements else "圖面含未知 requirement_id。",
                    blocks=() if not unknown_requirements else ("space_block", "walkthrough"),
                    next_action=None if not unknown_requirements else "改用 owner-requirements.snapshot.json 中的 id。",
                    unknown=unknown_requirements,
                )
                required_must = set(
                    manifest.get("expected_scope", {}).get("confirmed_must_requirement_ids", [])
                )
                missing_must = sorted(required_must - actual_requirements)
                add(
                    "CONFIRMED_MUST_COVERAGE",
                    "pass" if not missing_must else "fail",
                    "所有 confirmed must 需求都有圖面對應。" if not missing_must else "部分 confirmed must 沒有圖面對應。",
                    blocks=() if not missing_must else ("space_block", "walkthrough"),
                    next_action=None if not missing_must else "將 confirmed must requirement_id 綁到對應空間。",
                    missing=missing_must,
                )
        except (ContractError, ValueError, OSError) as exc:
            add(
                "PREVIEW_IMPORT",
                "fail",
                f"暫存試匯入失敗：{exc}",
                blocks=("import", "space_block", "walkthrough"),
                next_action="依錯誤修正來源檔或 mapping；不要先建立正式 revision。",
            )
    else:
        add(
            "PREVIEW_IMPORT",
            "warning",
            "必要檔案尚未通過，因此未執行暫存試匯入。",
            blocks=("import", "space_block", "walkthrough"),
        )

    if import_preview is not None:
        preview_ready = import_preview.get("status") == "ready"
        add(
            "PREVIEW_IMPORT",
            "pass" if preview_ready else "fail",
            "暫存試匯入為 ready。" if preview_ready else f"暫存試匯入狀態為 {import_preview.get('status')}。",
            blocks=() if preview_ready else ("import", "space_block", "walkthrough"),
            next_action=None if preview_ready else "處理 import preview 的 blocking issues。",
            issue_codes=[str(item.get("code")) for item in import_preview.get("issues", [])],
        )

    return _finish_preflight(
        package,
        revision_id or None,
        checks,
        import_preview,
        space_readiness,
        walkthrough_readiness,
        project_gate=manifest.get("project_gate") if isinstance(manifest.get("project_gate"), dict) else None,
    )


def _finish_preflight(
    package: Path,
    revision_id: str | None,
    checks: list[dict[str, Any]],
    import_preview: dict[str, Any] | None,
    space_readiness: dict[str, Any] | None,
    walkthrough_readiness: dict[str, Any] | None,
    *,
    project_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def has_block(level: str) -> bool:
        return any(item["status"] == "fail" and level in item.get("blocks", []) for item in checks)

    ready_for_import = bool(import_preview and import_preview.get("status") == "ready" and not has_block("import"))
    ready_for_space_block = bool(
        ready_for_import
        and space_readiness
        and space_readiness.get("eligible") is True
        and not has_block("space_block")
    )
    ready_for_walkthrough = bool(
        ready_for_space_block
        and walkthrough_readiness
        and walkthrough_readiness.get("eligible") is True
        and not has_block("walkthrough")
    )
    status_counts = Counter(item["status"] for item in checks)
    return {
        "schema": PREFLIGHT_SCHEMA,
        "revision_id": revision_id,
        "checked_at": utc_now(),
        "package": str(package),
        "ready_for_import": ready_for_import,
        "ready_for_space_block": ready_for_space_block,
        "ready_for_walkthrough": ready_for_walkthrough,
        "project_ready_for_design": bool(project_gate and project_gate.get("site_selected")),
        "policy": "Technical preflight never replaces site due diligence, professional review or immutable import.",
        "summary": {
            "checks": len(checks),
            "pass": status_counts.get("pass", 0),
            "fail": status_counts.get("fail", 0),
            "warning": status_counts.get("warning", 0),
        },
        "checks": checks,
        "import_preview": (
            {
                "status": import_preview.get("status"),
                "normalized_entity_count": import_preview.get("normalized_entity_count"),
                "normalized_space_count": import_preview.get("normalized_space_count"),
                "issues": import_preview.get("issues", []),
            }
            if import_preview
            else None
        ),
        "model3d_readiness": {
            "space_block": space_readiness,
            "walkthrough": walkthrough_readiness,
        },
    }


def write_preflight_report(report: dict[str, Any], output: Path) -> Path:
    write_json(output, report)
    return output
