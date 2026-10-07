"""Read-only comparison of public drafts, legacy render data and revision seals."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from house_design.contracts import ROOT, ContractError, sha256_file, stable_hash, utc_now, write_json
from house_design.owner_workspace import SOURCE_FILES, _e, build_workspace, sources
from house_design.revision_integrity import verify_revision_integrity


def _check_shared_plans(root: Path, building: str, expected: dict, add: Any) -> None:
    from lib.model3d_facade import render_elevation
    from lib.model3d_plan import plan_data, render_plan

    relative = "structured/candidates/furniture-plans"
    directory = root / relative
    try:
        source = (directory / "layout.js").read_text(encoding="utf-8")
        prefix, suffix = "window.HOUSE_CONCEPT_LAYOUT = ", ";\n"
        if not source.startswith(prefix) or not source.endswith(suffix):
            raise ValueError("Expected generated offline plan data, not an executable data loader")
        actual = json.loads(source[len(prefix) : -len(suffix)])
        wanted = plan_data(expected)
        add(
            "consistent" if actual == wanted else "stale",
            "HTML／3D 共用家具配置資料",
            relative + "/layout.js",
            {
                "building": building,
                "fields": "全部房間尺寸、家具尺寸、中心、旋轉、靠牆、入口、梯段、操作帶與獨立外觀提案",
                "sha256": sha256_file(directory / "layout.js"),
                "limitation": "資料一致性，非配置／法規／專業驗收。",
            },
        )
        expected_building = next(b for b in wanted["buildings"] if b["id"] == building)
        for floor in expected_building["floors"]:
            svg = directory / floor["plan_file"]
            equal = svg.is_file() and svg.read_text(encoding="utf-8") == render_plan(building, floor)
            add(
                "consistent" if equal else "stale",
                "HTML 等比例圖是否使用當前共用配置",
                relative + "/" + floor["plan_file"],
                {
                    "building": building,
                    "floor": floor["id"],
                    "sha256": sha256_file(svg) if svg.is_file() else None,
                    "action": "共同重跑 scripts/export_model_3d.py；不可手改生成圖，也不代表圖面可施工。",
                },
            )
            if floor.get("frontage_study_file"):
                svg = directory / floor["frontage_study_file"]
                equal = svg.is_file() and svg.read_text(encoding="utf-8") == render_plan(
                    building, floor, show_frontage_study=True
                )
                add(
                    "consistent" if equal else "stale",
                    "HTML 前院待核比較是否使用當前 3D 虛框",
                    relative + "/" + floor["frontage_study_file"],
                    {
                        "building": building,
                        "floor": floor["id"],
                        "sha256": sha256_file(svg) if svg.is_file() else None,
                        "action": "共用重匯出；只是未施作比較，騎樓／公共退縮與私用權利仍未知。",
                    },
                )
        facade = wanted["facade"]
        record = next(b for b in facade["buildings"] if b["id"] == building)
        svg = directory / record["elevation_file"]
        equal = svg.is_file() and svg.read_text(encoding="utf-8") == render_elevation(facade, record)
        add(
            "consistent" if equal else "stale",
            "HTML 正立面是否使用當前 3D 外觀元件",
            relative + "/" + record["elevation_file"],
            {"building": building, "sha256": sha256_file(svg) if svg.is_file() else None,
             "action": "共同重跑 scripts/export_model_3d.py；外觀一致不等於開口、停車、結構或法規核准。"},
        )
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as exc:
        add("insufficient", "HTML 共用家具配置資料不可讀", relative + "/layout.js", str(exc))


def build_consistency_review(root: Path = ROOT) -> dict[str, Any]:
    workspace = build_workspace(root)
    src = sources(root)
    findings = []

    def add(status: str, title: str, source: str, detail: Any) -> None:
        findings.append({"status": status, "title": title, "source": source, "detail": detail})

    req_ids = {r["id"] for r in workspace["rooms"]}
    for item in workspace["physical_items"]:
        req = next((r for r in workspace["rooms"] if r["id"] == item.get("location", {}).get("requirement_id")), None)
        location = item.get("location", {})
        valid = req is not None and all(req["location"].get(k) == location.get(k) for k in ("building_id", "floor_id"))
        add("consistent" if valid else "conflict", "實物與需求棟層對應", SOURCE_FILES["physical"], item["id"])
        if not item.get("measurements"):
            add("insufficient", "實物仍為規劃估值", SOURCE_FILES["physical"], item["id"])
        if item.get("transport", {}).get("measurement_state") != "measured":
            add("insufficient", "組裝搬運外廓尚未實測", SOURCE_FILES["physical"], item["id"])
    for q in workspace["questions"]:
        invalid = set(q.get("requirement_ids", [])) - req_ids
        if invalid:
            add("conflict", "情境引用不存在需求", SOURCE_FILES["register"], {"id": q["id"], "missing": sorted(invalid)})
    add(
        "insufficient",
        "需求與歷史格位尚未有完整明確映射",
        "inputs/requirements.json / inputs/furniture-layout.json",
        "不得依相似房名套用家具或幾何；歷史容量與需求卡分開顯示。",
    )
    # Include the existing static HTML checks in the linked owner report. Do not
    # manufacture authoritative geometry or interpret setbacks as illegal.
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    from check_html_consistency import check_building_footprint, check_floor_geometry
    from lib.dimension_overrides import load_overrides
    from lib.standards import load_residential_defaults

    static_issues = []
    for building in "ABC":
        path = root / f"{building}buildingView.html"
        if not path.is_file():
            continue
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        envelopes = []
        for floor in soup.select(".floor-plan"):
            if not floor.select(".plan-cell"):
                continue
            envelope = check_floor_geometry(
                building_id=building,
                file_name=path.name,
                floor=floor,
                issues=static_issues,
                door_min_mm=700,
                door_max_mm=1400,
                window_min_mm=300,
                window_max_mm=3600,
                mode="draft",
                spatial_config=load_residential_defaults().get("spatial_metadata", {}),
                overrides=load_overrides(root / SOURCE_FILES["dimensions"]),
            )
            if envelope:
                envelopes.append(envelope)
        check_building_footprint(building, path.name, envelopes, static_issues)
    for issue in static_issues:
        if issue["level"] == "info":
            continue
        # The checker cannot distinguish deliberate floor setbacks/voids from
        # missing data. Those remain questions, not geometric fixes or failures.
        ambiguous = issue["code"] in {"FOOTPRINT_INCONSISTENT", "FLOOR_COVERAGE_VOID"}
        add(
            "insufficient" if ambiguous else "conflict",
            "HTML 靜態查核 · " + issue["code"],
            issue["file"],
            {
                "building": issue["building_id"],
                "floor": issue["floor_id"],
                "message": issue["message"],
                "evidence": issue.get("evidence"),
                "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。",
            },
        )
    a_html = root / "AbuildingView.html"
    combined = next((r for r in workspace["rooms"] if r["id"] == "A.floor-1.living"), None)
    if a_html.is_file() and combined and "客餐廳" in combined["title"]:
        soup = BeautifulSoup(a_html.read_text(encoding="utf-8"), "html.parser")
        if soup.select_one("#room-living") and soup.select_one("#room-dining"):
            add(
                "insufficient",
                "A 棟客餐廳提案與原 HTML 版本不同",
                "AbuildingView.html / inputs/requirements.json",
                "原 HTML 的分開客廳／餐廳保留在歷史對照；A 照護回補版共用圖與 3D 改前段客餐廳、後段孝親房與一樓淋浴。屋主同意回補功能，不等於正式採用前帶可建或停車取捨；前段位置與原需求表後帶條件不同，須比較。勿把歷史卡的位置或坪數套用到新提案。",
            )
    expected = None
    try:
        # Reuse the exact historical renderer, not a second furniture dimension resolver.
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from export_model_3d import build_payload

        expected = build_payload(
            src["program"],
            load_overrides(root / SOURCE_FILES["dimensions"]),
            "presentation",
            furniture_path=root / SOURCE_FILES["furniture"],
            physical_items_path=root / SOURCE_FILES["physical"],
            review_path=root / SOURCE_FILES["concept_review"],
            requirements_path=root / SOURCE_FILES["requirements"],
            facade_path=root / SOURCE_FILES["facade"],
        )
    except (ContractError, ValueError, KeyError, TypeError, OSError) as exc:
        care_regression = str(exc).startswith("A 1F care requirement:")
        add(
            "conflict" if care_regression else "insufficient",
            "A 棟一樓照護功能回歸缺漏" if care_regression else "無法建立當前家具容量比較資料",
            SOURCE_FILES["concept_review"] if care_regression else SOURCE_FILES["program"],
            str(exc),
        )
    if expected:
        facade = expected["facade"]
        add(
            "insufficient",
            "ABC 外觀提案的採光／結構／維修仍待專業核定",
            SOURCE_FILES["facade"],
            {"status": facade["status"], "pending_checks": facade["pending_checks"],
             "pending_by_building": {b["id"]: b["pending"] for b in facade["buildings"]}},
        )
        reference = facade["reference"]
        photo = root / "assets/references/facade-photo-v1.jpg"
        equal = photo.is_file() and sha256_file(photo) == reference.get("sha256")
        add(
            "consistent" if equal else "insufficient",
            "外觀參考照片的來源雜湊",
            "assets/references/facade-photo-v1.jpg",
            {"expected": reference.get("sha256"), "actual": sha256_file(photo) if photo.is_file() else None,
             "limitation": "只證明引用的照片位元組；不推定材質、尺寸、結構或合法性。"},
        )
        care = next(c for c in expected["layout_review"]["checks"] if c["id"] == "A-1F-care-functions")
        add(
            "insufficient",
            "A 棟一樓照護功能已回補，仍為有條件提案",
            "inputs/requirements.json / inputs/concept-layout-review.json",
            care,
        )
        cells = {c["id"]: c for b in expected["buildings"] for f in b["floors"] for c in f["cells"]}
        for b in "ABC":
            path = root / f"{b}buildingView.html"
            if not path.is_file():
                add("insufficient", "缺原始 HTML", path.name, "未檢查")
                continue
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
            if soup.select_one('script[src="structured/candidates/furniture-plans/layout.js"]'):
                _check_shared_plans(root, b, expected, add)
                continue  # old cells are room indexes, not duplicate furniture positions
            overlays = soup.select("[data-model-room-id][data-layout-source]")
            for overlay in overlays:
                cid = overlay.get("data-model-room-id")
                cell = cells.get(cid)
                if not cell:
                    add("conflict", "HTML 對應不存在格位", path.name, cid)
                    continue
                furniture = {i["id"]: i for i in cell.get("furniture", [])}
                nodes = overlay.select("[data-furniture-id]")
                if not nodes:
                    add("insufficient", "HTML 無可解析家具比例資料", path.name, cid)
                found = set()
                for node in nodes:
                    fid = node.get("data-furniture-id")
                    found.add(fid)
                    item = furniture.get(fid)
                    if item is None:
                        add("conflict", "HTML 家具不存在來源配置", path.name, fid)
                        continue
                    try:
                        attrs = {
                            k: float(node.get("data-" + k.replace("_", "-"), "nan"))
                            for k in ("width_mm", "depth_mm", "height_mm")
                        }
                        # Existing HTML overlays declare width/depth but may omit height.
                        tested = [k for k in attrs if node.has_attr("data-" + k.replace("_", "-"))]
                        equal = bool(tested) and all(abs(attrs[k] - item[k]) < 0.1 for k in tested)
                        add(
                            "consistent" if equal else "conflict",
                            "HTML／來源家具尺寸",
                            path.name,
                            {"id": fid, "axes_checked": tested},
                        )
                    except (ValueError, TypeError, KeyError):
                        add("insufficient", "HTML 家具尺寸不可解析", path.name, fid)
                    for attr, key in (
                        ("data-x-ratio", "x_ratio"),
                        ("data-y-ratio", "y_ratio"),
                        ("data-rotation-deg", "rotation_deg"),
                    ):
                        try:
                            equal = abs(float(node.get(attr, "nan")) - float(item[key])) < 0.001
                            add(
                                "consistent" if equal else "conflict",
                                "HTML／來源家具比例位置",
                                path.name,
                                {"id": fid, "field": attr},
                            )
                        except (ValueError, TypeError, KeyError):
                            add("insufficient", "HTML 家具位置不可解析", path.name, {"id": fid, "field": attr})
                if set(furniture) != found:
                    add(
                        "conflict",
                        "HTML 與來源家具清單不同",
                        path.name,
                        {"room": cid, "missing": sorted(set(furniture) - found)},
                    )
            if not overlays:
                add("insufficient", "原始 HTML 未提供完整家具映射", path.name, "無可解析家具比例覆層；不代表內容通過")
        viewer = root / "structured/candidates/model3d.html"
        if viewer.is_file():
            match = re.search(r"var DATA = (.*?);\s*\n", viewer.read_text(encoding="utf-8"), re.S)
            try:
                rendered = json.loads(match[1]) if match else None
                current = {c["id"]: c for b in rendered["buildings"] for f in b["floors"] for c in f["cells"]}

                def signature(values: dict[str, Any]) -> Any:
                    return {
                        key: {
                            "name": c["name"],
                            "declared_mm": c["declared_mm"],
                            "auto_mm": c.get("auto_mm"),
                            "tour_mm": c.get("tour_mm"),
                            "tour_features": c.get("tour_features"),
                            "space_group": c.get("space_group"),
                            "provenance": c["provenance"],
                            "furniture": c.get("furniture", []),
                            "furniture_placements": c.get("furniture_placements"),
                        }
                        for key, c in values.items()
                    }

                add(
                    "consistent" if stable_hash(signature(cells)) == stable_hash(signature(current)) else "stale",
                    "歷史 3D 是否使用當前格位與家具來源",
                    "structured/candidates/model3d.html",
                    "比較 ID、名稱、原格位／需求尺寸、靠牆擺位、梯廳分區及門窗／操作帶；非合規檢查",
                )
                add(
                    "consistent" if rendered.get("facade") == expected["facade"] else "stale",
                    "3D 是否使用當前獨立外觀來源",
                    "structured/candidates/model3d.html / inputs/facade-concept.json",
                    "比較完整元件、候選開口、色票、假設及待確認項目；不更動屋主需求或宣稱法規通過。",
                )
            except (TypeError, KeyError, json.JSONDecodeError):
                add("insufficient", "3D 內嵌資料不可解析", "structured/candidates/model3d.html", "未檢查")
        else:
            add("insufficient", "缺歷史 3D", "structured/candidates/model3d.html", "未檢查")
    for manifest in sorted((root / "inputs/revisions").glob("*/manifest.json")):
        try:
            result = verify_revision_integrity(manifest.parent.name, root / "inputs/revisions")
            add(
                "consistent" if result["valid"] else "conflict",
                "不可變圖版完整性",
                str(manifest.relative_to(root)),
                result,
            )
        except ContractError as exc:
            add("conflict", "圖版完整性無法檢查", str(manifest.relative_to(root)), str(exc))
    # Document the actual current bytes; never reseal a mutated legacy source.
    r000 = root / "inputs/revisions/R000/manifest.json"
    if r000.is_file():
        manifest = json.loads(r000.read_text(encoding="utf-8"))
        for source in manifest.get("sources", []):
            path = root / source["file"]
            actual = sha256_file(path) if path.is_file() else None
            if actual != source.get("sha256"):
                historical = None
                # Read a precise tracked path from HEAD; never restore the dirty working file.
                try:
                    git = subprocess.run(
                        ["git", "show", "HEAD:" + source["file"]], cwd=root, capture_output=True, timeout=10
                    )
                    if git.returncode == 0:
                        import hashlib

                        digest = hashlib.sha256(git.stdout).hexdigest()
                        historical = {
                            "reference": "git HEAD:" + source["file"],
                            "sha256": digest,
                            "matches_manifest": digest == source.get("sha256"),
                        }
                except (OSError, subprocess.TimeoutExpired):
                    pass
                add(
                    "conflict",
                    "R000 原來源已偏離封存雜湊",
                    "inputs/revisions/R000/manifest.json",
                    {
                        "file": source["file"],
                        "expected": source.get("sha256"),
                        "actual": actual,
                        "historical_candidate": historical,
                        "action": "保存現況；從可信歷史版本／備份比對原來源。若無法復原，保留異常，另經授權建立新版本；不得改 manifest。",
                    },
                )
    return {
        "schema": "house-owner-consistency-v1",
        "project_id": workspace["project_id"],
        "generated_at": utc_now(),
        "source_hashes": workspace["source_hashes"],
        "findings": findings,
        "warning": "一致性不等於設計可行、法規合規或專業驗收；資料不足不可當成通過。",
    }


def write_consistency_review(root: Path = ROOT, output_root: Path | None = None) -> dict[str, str]:
    report = build_consistency_review(root)
    out = output_root or root / "structured/predesign"
    write_json(out / "consistency-review.json", report)
    md = ["# 三棟資料一致性查核", "", report["warning"], ""]
    labels = {"consistent": "一致", "conflict": "矛盾", "insufficient": "資料不足", "stale": "版本過期"}
    articles = []
    for f in report["findings"]:
        detail = json.dumps(f["detail"], ensure_ascii=False, indent=2)
        md += [f"## {labels[f['status']]} · {f['title']}", f"來源：{f['source']}", "```json", detail, "```", ""]
        articles.append(
            f'<article data-status="{f["status"]}"><h2>{labels[f["status"]]} · {_e(f["title"])}</h2><p>{_e(f["source"])}</p><details><summary>檢查證據與限制</summary><pre>{_e(detail)}</pre></details></article>'
        )
    (out / "consistency-review.md").write_text("\n".join(md), encoding="utf-8")
    (out / "consistency-review.html").write_text(
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>三棟資料一致性查核</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:auto;padding:20px;color:#18334a}article{border-bottom:1px solid #ddd;padding:14px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}button,select{font:inherit;padding:8px}@media print{button,select{display:none}}</style><h1>三棟資料一致性查核</h1><p>'
        + _e(report["warning"])
        + '</p><a href="owner-workspace.html">屋主工作台</a><p><label>顯示 <select id="status"><option value="">全部</option>'
        + "".join(f'<option value="{k}">{v}</option>' for k, v in labels.items())
        + '</select></label> <button onclick="window.print()">列印</button></p>'
        + "".join(articles)
        + '<script>document.getElementById("status").onchange=e=>document.querySelectorAll("article").forEach(a=>a.hidden=!!e.target.value&&a.dataset.status!==e.target.value);window.addEventListener("beforeprint",()=>document.querySelectorAll("details").forEach(d=>d.open=true));</script></html>',
        encoding="utf-8",
    )
    return {k: str(out / f"consistency-review.{k}") for k in ("json", "md", "html")}
