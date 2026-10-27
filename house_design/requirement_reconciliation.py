"""Read-only, ID-based reconciliation of existing concept snapshots.

Never imports a renderer, executes layout.js, confirms requirements, borrows
another option's area, or treats a packing/area result as functional approval.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json

SCHEMA = "house-requirement-reconciliation-v1"
REGISTRY = "inputs/requirement-dispositions.json"
ALLOCATIONS = {
    "mapped": "有對應配置／功能未核", "partial": "部分配置／原功能或位置有差異",
    "shared": "併入共用組／不給獨立面積信用", "unaccommodated": "未容納／原需求保留",
    "separate-study": "另案研究／未容納", "unmapped": "缺明確映射／待補",
}
AREA_LABELS = {
    "below-minimum": "低於原下限", "below-target": "低於原目標",
    "discussion-only": "僅討論面積達數值／功能未核", "shared-not-independent": "共用，不計獨立面積",
    "unallocated": "未分配", "unknown": "資料不足",
}
WARNING = "需求已對帳不等於已確認或符合；所有面積是概念格位的假設內縮量，非法定／完成面淨面積。各案分開，不互借結果，也不加總共用面積。"


def _public_path(root: Path, name: str) -> Path:
    parts = Path(name).parts
    if (not parts or Path(name).is_absolute() or "\\" in name or ".." in parts
            or parts[0] not in {"inputs", "scripts", "house_design", "structured", "assets", "Docs"}
            or any(p.startswith(".") or "private" in p.lower() for p in parts)):
        raise ContractError(f"Not a public project-relative source: {name}")
    path = root / name
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ContractError(f"Source escapes project root: {name}")
    if any(p.startswith(".") or "private" in p.lower() for p in resolved.relative_to(root.resolve()).parts):
        raise ContractError(f"Source resolves to a nonpublic location: {name}")
    return path


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _rect(room: dict[str, Any]) -> tuple[float, float, float, float]:
    g = room.get("geometry") or {}
    values = [g.get(k) for k in ("x_mm", "y_mm", "w_mm", "h_mm")]
    if not all(_number(v) for v in values) or min(values[2:]) <= 0:
        raise ContractError("Room needs finite positive concept geometry")
    x, y, w, h = values
    return x, y, x + w, y + h


def _union_area(rects: list[tuple]) -> float:
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    result = 0.0
    for x0, x1 in zip(xs, xs[1:], strict=False):
        intervals = sorted((r[1], r[3]) for r in rects if r[0] < x1 and r[2] > x0)
        end, height = -math.inf, 0.0
        for y0, y1 in intervals:
            height += max(0, y1 - max(y0, end))
            end = max(end, y1)
        result += (x1 - x0) * height
    return result


def discussion_area(rooms: list[dict[str, Any]], inset: float) -> float:
    """Exact square erosion of a small orthogonal union, no CAD/runtime imports.

    This matches the comparison convention without double-insetting an open
    seam or summing overlapping rectangles. The inset is not a measured wall.
    """
    if not _number(inset) or inset < 0:
        raise ContractError("Discussion inset must be finite and nonnegative")
    rects = [_rect(r) for r in rooms]
    if not inset:
        return round(_union_area(rects) / 1e6, 4)
    xs = sorted({x + delta for r in rects for x in (r[0], r[2]) for delta in (-inset, inset)})
    ys = sorted({y + delta for r in rects for y in (r[1], r[3]) for delta in (-inset, inset)})
    total = 0.0
    for x0, x1 in zip(xs, xs[1:], strict=False):
        for y0, y1 in zip(ys, ys[1:], strict=False):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            cuts = [(max(cx-inset, r[0]), max(cy-inset, r[1]), min(cx+inset, r[2]), min(cy+inset, r[3])) for r in rects]
            cuts = [r for r in cuts if r[2] > r[0] and r[3] > r[1]]
            if abs(_union_area(cuts) - (2 * inset) ** 2) < 1e-5:
                total += (x1 - x0) * (y1 - y0)
    return round(total / 1e6, 4)


def _snapshot(path: Path, assignment: str, schema: str) -> dict:
    source = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", assignment):
        raise ContractError("Invalid data assignment name")
    prefix = f"window.{assignment} = "
    if not source.startswith(prefix) or not source.endswith(";"):
        raise ContractError("Expected JSON data assignment, never executable JavaScript")
    data = json.loads(source[len(prefix):-1])
    if not isinstance(data, dict) or data.get("schema") != schema:
        raise ContractError("Unexpected layout snapshot schema")
    return data


def _binding(value: dict) -> None:
    if (not isinstance(value, dict) or not isinstance(value.get("allocation"), str)
            or value["allocation"] not in ALLOCATIONS.keys() - {"unmapped"}):
        raise ContractError("Binding needs a non-approval allocation status")
    if not isinstance(value.get("note"), str) or not value["note"].strip():
        raise ContractError("Binding needs an explicit rationale")
    for key in ("rooms", "related_rooms"):
        refs = value.get(key, [])
        if not isinstance(refs, list) or any(not isinstance(r, str) or not r for r in refs) or len(refs) != len(set(refs)):
            raise ContractError("Binding room ids must be a unique array")
    if value["allocation"] in {"unaccommodated", "separate-study"} and value.get("rooms"):
        raise ContractError("Unaccommodated requirements may have related rooms, not credited allocations")
    if value["allocation"] in {"mapped", "partial", "shared"} and not value.get("rooms"):
        raise ContractError("Allocated requirements need explicit room ids")


def _index(buildings: list[dict], expected: list[str]) -> dict[str, dict]:
    if sorted(b["id"] for b in buildings) != sorted(expected):
        raise ContractError("Snapshot building scope does not match scenario")
    index = {}
    for building in buildings:
        seen = set()
        for floor in building["floors"]:
            if floor["id"] in seen:
                raise ContractError("Duplicate floor in snapshot")
            seen.add(floor["id"])
            for room in floor["rooms"]:
                if room["id"] in index or room["id"] != f"{building['id']}:{floor['id']}:{room['key']}":
                    raise ContractError("Duplicate or mismatched snapshot room id")
                index[room["id"]] = {**room, "floor_id": floor["id"], "building_id": building["id"], "plan_file": floor["plan_file"]}
    return index


def _row(req: dict, binding: dict | None, rooms: dict, aliases: dict, insets: list) -> dict:
    rid, scope = req["id"], req["applies_to"]
    flags = []
    if binding is None:
        binding = {"allocation": "unmapped", "rooms": [], "note": "新需求或缺映射仍列入，不能因面積表沒列就消失。"}
        flags.append("missing-binding")
    allocation = binding["allocation"]
    refs = binding.get("rooms", [])
    missing = [r for r in [*refs, *binding.get("related_rooms", [])] if r not in rooms]
    if missing:
        flags.append("missing-room-reference")
    found = [rooms[r] for r in refs if r in rooms]
    expected_floor = aliases.get(scope["floor_id"], scope["floor_id"])
    if any(rooms[r]["building_id"] != scope["building_id"] or rooms[r]["floor_id"] != expected_floor
           for r in [*refs, *binding.get("related_rooms", [])] if r in rooms):
        flags.append("room-scope-mismatch")
    if allocation != "shared" and any(r.get("requirement_id") not in {None, rid} for r in found):
        flags.append("snapshot-requirement-id-conflict")
    constraints = req.get("constraints") or {}
    minimum, target = constraints.get("min_sqm"), constraints.get("target_sqm")
    nominal, sensitivity, state = None, [], "unknown"
    if not refs:
        state = "unknown" if allocation == "unmapped" else "unallocated"
    elif not missing and not {"room-scope-mismatch", "snapshot-requirement-id-conflict"}.intersection(flags):
        if allocation == "shared":
            state = "shared-not-independent"
        else:
            try:
                nominal = discussion_area(found, 0)
                sensitivity = [{"inset_mm": inset, "area_sqm": discussion_area(found, inset)} for inset in insets]
                value = sensitivity[0]["area_sqm"]
                state = ("below-minimum" if _number(minimum) and value < minimum else
                         "below-target" if _number(target) and value < target else "discussion-only")
                if _number(minimum) and any(v["area_sqm"] < minimum for v in sensitivity[1:]):
                    flags.append("sensitivity-below-minimum")
                if _number(target) and value >= target and any(v["area_sqm"] < target for v in sensitivity[1:]):
                    flags.append("sensitivity-below-target")
            except ContractError:
                flags.append("invalid-room-geometry")
    if allocation == "partial":
        flags.append("original-function-or-location-pending")
    return {
        "requirement_id": rid, "title": req["title"], "building_id": scope["building_id"], "floor_id": scope["floor_id"],
        "requirement_status": req.get("status", "unknown"), "priority": req.get("priority"),
        "allocation": allocation, "allocation_label": ALLOCATIONS[allocation], "note": binding["note"],
        "room_ids": refs, "related_room_ids": binding.get("related_rooms", []), "missing_room_ids": missing,
        "rooms": [{k: r[k] for k in ("id", "name", "geometry", "plan_file")} for r in found],
        "area": {"nominal_union_sqm": nominal, "discussion_inset_sqm": sensitivity[0]["area_sqm"] if sensitivity else None,
                 "minimum_sqm": minimum, "target_sqm": target, "state": state, "state_label": AREA_LABELS[state],
                 "sensitivity": sensitivity, "finished_or_legal_sqm": None, "additive_across_requirements": False},
        "flags": flags, "functional_acceptance": "unknown", "professional_acceptance": "unknown",
    }


def build_reconciliation(root: Path = ROOT) -> dict:
    root = root.resolve()
    registry, requirements, project = (read_json(root / p) for p in (REGISTRY, "inputs/requirements.json", "inputs/project.json"))
    if registry.get("schema") != "house-requirement-dispositions-v1" or registry.get("project_id") != project.get("project_id"):
        raise ContractError("Disposition registry schema/project mismatch")
    if requirements.get("schema") != "house-requirements-v2":
        raise ContractError("Expected canonical house-requirements-v2")
    reqs = requirements["requirements"]
    ids = [r["id"] for r in reqs]
    if len(ids) != len(set(ids)):
        raise ContractError("Canonical requirement ids must be unique")
    insets = registry["discussion_insets_mm"]
    if not isinstance(insets, list) or insets != [80, 100, 115] or any(not _number(n) for n in insets):
        raise ContractError("Discussion sensitivity convention must be [80, 100, 115] mm")
    aliases = registry["floor_aliases"]
    if aliases != {"floor-rf": "floor-4"}:
        raise ContractError("Only explicit conceptual RF/floor-4 alias is supported")
    for profile in registry["profiles"].values():
        for value in profile.values():
            _binding(value)
    hashes: dict[str, str | None] = {}

    def digest(name: str) -> str | None:
        if name not in hashes:
            path = _public_path(root, name)
            hashes[name] = sha256_file(path) if path.is_file() else None
        return hashes[name]

    for name in (REGISTRY, "inputs/project.json", "inputs/requirements.json"):
        digest(name)
    anchored = registry.get("requirements_sha256") == digest("inputs/requirements.json")
    scenarios, seen_scenarios = [], set()
    for spec in registry["scenarios"]:
        sid, profile = spec["id"], registry["profiles"][spec["profile"]]
        if sid in seen_scenarios:
            raise ContractError("Scenario ids must be unique")
        seen_scenarios.add(sid)
        rooms, program, source_issues = {}, {}, []
        recorded = None
        try:
            digest(spec["path"])
            snapshot = _snapshot(_public_path(root, spec["path"]), spec["assignment"], spec["schema"])
            recorded = snapshot.get("source_hashes")
            if "buildings" in snapshot:
                buildings = snapshot["buildings"]
            else:
                selected = [o for o in snapshot["options"] if o["id"] == sid]
                if len(selected) != 1:
                    raise ContractError("Scenario option absent or ambiguous")
                buildings, program = [selected[0]["plans"]], selected[0]["review"]["program"]
            rooms = _index(buildings, spec["building_ids"])
            if recorded is not None:
                if not isinstance(recorded, dict) or not recorded:
                    raise ContractError("Invalid embedded source hashes")
                for path, expected in recorded.items():
                    if not isinstance(expected, str) or digest(path) != expected:
                        source_issues.append({"source": path, "issue": "recorded-source-mismatch-or-missing"})
        except (ContractError, OSError, ValueError, KeyError, TypeError) as exc:
            source_issues.append({"source": spec["path"], "issue": f"snapshot-unavailable-or-invalid: {exc}"})
        relevant = [r for r in reqs if r["applies_to"]["building_id"] in spec["building_ids"]]
        rows = [_row(r, profile.get(r["id"]), rooms, aliases, insets) for r in relevant]
        area_rows = {r["id"]: r for r in [*program.get("area_checks", []), *program.get("upper_area_checks", [])]}
        owners = defaultdict(list)
        for row in rows:
            for room in row["room_ids"]:
                owners[room].append(row["requirement_id"])
        for row in rows:
            if not anchored:
                row["flags"].append("requirements-changed-binding-needs-review")
            if source_issues:
                row["flags"].append("source-stale-or-incomplete")
            row["shared_with_requirement_ids"] = sorted({r for room in row["room_ids"] for r in owners[room] if r != row["requirement_id"]})
            if row["shared_with_requirement_ids"]:
                row["flags"].append("shared-room-not-additive")
            old = area_rows.get(row["requirement_id"])
            row["in_original_partial_area_table"] = old is not None
            row["context_metrics"] = {}
            if row["requirement_id"] == "B.floor-1.shrine" and program.get("shrine_after_passage_reserve_sqm") is not None:
                row["context_metrics"] = {key: program.get(key) for key in (
                    "shrine_whole_room_discussion_sqm", "shrine_after_passage_reserve_sqm",
                    "passage_reserve_clear_assumption_mm", "praying_people_and_capacity",
                )}
            if old:
                refs = old.get("room_ids") or [old.get("room_id")]
                value = row["area"]["discussion_inset_sqm"]
                if set(refs) != set(row["room_ids"]) or not _number(value) or abs(value - old["discussion_inset_sqm"]) > 0.00011:
                    row["flags"].append("existing-area-table-disagrees")
        supplements = []
        for extra in registry.get("supplementary", []):
            if extra["building_id"] not in spec["building_ids"]:
                continue
            binding = extra["profile_bindings"].get(spec["profile"])
            if binding:
                _binding(binding)
            extra_row = _row(
                {"id": extra["id"], "title": extra["title"], "applies_to": {k: extra[k] for k in ("building_id", "floor_id")}},
                binding, rooms, aliases, insets,
            )
            if source_issues:
                extra_row["flags"].append("source-stale-or-incomplete")
            supplements.append(extra_row)
        scenarios.append({
            **{k: spec[k] for k in ("id", "label", "profile", "building_ids", "path", "viewer")},
            "adopted": False, "rows": rows, "supplementary": supplements,
            "source_freshness": {"state": "stale-or-incomplete" if source_issues else "recorded-hashes-match" if recorded else "snapshot-only-not-regenerated",
                                 "issues": source_issues, "rendered_qa": "not-run"},
            "summary": {"requirements": len(rows), "disposition_rows": sum(r["allocation"] != "unmapped" for r in rows),
                        "original_partial_area_rows": len(area_rows), "supplementary_items": len(supplements),
                        "allocation_counts": dict(Counter(r["allocation"] for r in rows)),
                        "area_counts": dict(Counter(r["area"]["state"] for r in rows))},
        })
    profile_keys = {k for p in registry["profiles"].values() for k in p}
    report = {
        "schema": SCHEMA, "generated_at": utc_now(), "project_id": project["project_id"],
        "warning": WARNING, "registry_requirements_anchor_matches": anchored,
        "summary": {"canonical_requirements": len(reqs), "by_building": dict(Counter(r["applies_to"]["building_id"] for r in reqs)),
                    "scenario_count": len(scenarios), "scenario_rows": sum(len(s["rows"]) for s in scenarios),
                    "orphaned_binding_ids": sorted(profile_keys - set(ids)), "verified_requirements": 0},
        "requirements": [{k: r[k] for k in ("id", "title", "applies_to", "status")} for r in reqs],
        "scenarios": scenarios, "source_hashes": hashes, "generator_sha256": sha256_file(Path(__file__)),
    }
    report["report_hash"] = stable_hash({k: v for k, v in report.items() if k != "generated_at"})
    return report


def _cell(value: Any) -> str:
    return str(value).replace("|", "／").replace("\n", " ")


def reconciliation_markdown(report: dict, root: Path, directory: Path) -> str:
    summary = report["summary"]
    lines = ["# ABC 逐需求配置對帳（討論用）", "", report["warning"], "",
             f"原需求 {summary['canonical_requirements']} 項：" + "、".join(f"{k} {v}" for k, v in summary["by_building"].items()) + "。",
             f"{summary['scenario_count']} 個方案分開共 {summary['scenario_rows']} 列；獨立公衛／停車另列，未變更任何需求或採用方案。", "",
             "內縮80／100／115mm是敏感度假設，不是牆厚實測或法定淨面積。候選需求不會因有格位或達面積而自動確認。", ""]
    if not report["registry_requirements_anchor_matches"] or summary["orphaned_binding_ids"]:
        lines += ["注意：需求來源已變更或有失效映射；本次對帳須重核，不能沿用舊結論。", ""]
    for scenario in report["scenarios"]:
        view = urlsplit(scenario["viewer"])
        link = os.path.relpath(root / view.path, directory).replace(os.sep, "/") + ("?" + view.query if view.query else "")
        lines += [f"## {scenario['label']}", "", f"[開啟本案3D]({link})（本輪未驗瀏覽器畫面）", "",
                  f"來源：`{scenario['path']}`；狀態：`{scenario['source_freshness']['state']}`。",
                  f"逐需求 {len(scenario['rows'])} 列；原部分面積表僅 {scenario['summary']['original_partial_area_rows']} 列，未列面積不等於需求消失。", ""]
        if scenario["source_freshness"]["issues"]:
            lines += ["來源過期／不完整：以下只描述已讀快照，不代表目前生成器輸出。", ""]
            lines += [f"- `{_cell(i['source'])}`：{_cell(i['issue'])}" for i in scenario["source_freshness"]["issues"]]
            lines.append("")
        lines += ["| 需求ID／原狀態 | 處置 | 80mm討論m²／原下限／目標 | 風險／未解內容 |", "| --- | --- | --- | --- |"]
        for row in scenario["rows"]:
            a = row["area"]
            value = "未獨立計量" if a["discussion_inset_sqm"] is None else f"{a['discussion_inset_sqm']:.4f}"
            sensitivity = "；加大內縮的敏感度會低於原下限" if "sensitivity-below-minimum" in row["flags"] else ""
            if "sensitivity-below-target" in row["flags"]:
                sensitivity += "；加大內縮後低於原目標"
            if row.get("context_metrics"):
                sensitivity += f"；扣本案側緣通行暫留後約{row['context_metrics']['shrine_after_passage_reserve_sqm']:.4f}m²，祭拜人數／操作未核"
            broken = "；映射／來源需重核" if any(f in row["flags"] for f in (
                "missing-binding", "missing-room-reference", "room-scope-mismatch", "requirements-changed-binding-needs-review",
                "source-stale-or-incomplete", "existing-area-table-disagrees", "snapshot-requirement-id-conflict",
            )) else ""
            lines.append(f"| `{_cell(row['requirement_id'])}` {row['requirement_status']}<br>{_cell(row['title'])} | {_cell(row['allocation_label'])} | "
                         f"{value}／{a['minimum_sqm']}／{a['target_sqm']}<br>{a['state_label']} | {_cell(row['note'])}{sensitivity}{broken} |")
        lines += ["", "### 不在原面積需求清單內的補充追蹤", ""]
        lines += [f"- {r['title']}：{r['allocation_label']}；{r['note']}" for r in scenario["supplementary"]]
        lines += ["", "具體房間ID、幾何、原面積表覆蓋、共享對象及敏感度數值見同目錄 requirement-ledger.json。", ""]
    lines += ["## 來源與判定邊界", "", "本表不執行產圖器或JavaScript，不回寫需求／格局／封存。來源hash只證明讀到的檔案版本，不代表HTML／3D畫面或專業查核已通過。", "",
              f"Report hash：`{report['report_hash']}`", ""]
    return "\n".join(lines)


def write_reconciliation(report: dict, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    directory = output_root if output_root is not None else root / "structured/reconciliation"
    paths = {"json": directory / "requirement-ledger.json", "markdown": directory / "requirement-ledger.md"}
    write_json(paths["json"], report)
    paths["markdown"].write_text(reconciliation_markdown(report, root, directory), encoding="utf-8")
    return paths
