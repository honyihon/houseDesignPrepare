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
                "原 HTML 客廳與餐廳分開；需求 A.floor-1.living 為合併客餐廳提案，仍待確認。保留兩版，不自動合併、移動或匹配家具。",
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
        )
    except (ContractError, ValueError, KeyError, TypeError, OSError) as exc:
        add("insufficient", "無法建立當前家具容量比較資料", SOURCE_FILES["program"], str(exc))
    if expected:
        cells = {c["id"]: c for b in expected["buildings"] for f in b["floors"] for c in f["cells"]}
        for b in "ABC":
            path = root / f"{b}buildingView.html"
            if not path.is_file():
                add("insufficient", "缺原始 HTML", path.name, "未檢查")
                continue
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
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
                            "provenance": c["provenance"],
                            "furniture": c.get("furniture", []),
                        }
                        for key, c in values.items()
                    }

                add(
                    "consistent" if stable_hash(signature(cells)) == stable_hash(signature(current)) else "stale",
                    "歷史 3D 是否使用當前格位與家具來源",
                    "structured/candidates/model3d.html",
                    "比較 ID、名稱、格位尺寸、來源狀態及家具配置；非合規檢查",
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
