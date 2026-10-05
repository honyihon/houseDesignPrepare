"""Offline owner drafts and append-only public meeting records. Never a signoff."""

from __future__ import annotations

import copy
import html
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from house_design.contracts import ROOT, ContractError, read_json, stable_hash, utc_now, write_json
from house_design.physical_items import DIMENSION_KEYS, active_dimensions, validate_physical_items
from house_design.rendering import encode_html_json

RECORDS_PATH = ROOT / "inputs/owner-records.json"
DRAFT_SCHEMA = "house-owner-draft-v1"
RECORD_SCHEMA = "house-owner-records-v1"
SOURCE_FILES = {
    "project": "inputs/project.json",
    "requirements": "inputs/requirements.json",
    "register": "inputs/planning-register.json",
    "physical": "inputs/physical-items.json",
    "furniture": "inputs/furniture-layout.json",
    "program": "structured/room_program.json",
    "dimensions": "inputs/dimensions.json",
}
KINDS = {"answer", "room", "meeting", "change", "measurement", "proposal"}
FIELDS = {
    "answer": {"answer", "alternative", "reason", "questions", "reference"},
    "room": {"people", "storage", "equipment", "cleaning", "acceptance", "reference"},
    "meeting": {
        "date",
        "roles",
        "topic",
        "proposal",
        "conclusion",
        "professional_questions",
        "responsible",
        "deadline",
        "reference",
        "stage",
    },
    "change": {
        "old",
        "new",
        "reason",
        "area_impact",
        "cost_impact",
        "schedule_impact",
        "equipment_impact",
        "building_impact",
        "reference",
    },
    "measurement": {
        "width_mm",
        "depth_mm",
        "height_mm",
        "transport_width_mm",
        "transport_depth_mm",
        "transport_height_mm",
        "measured_by",
        "measured_at",
        "method",
        "reference",
        "removable",
        "operation",
        "weight",
        "note",
    },
    "proposal": {"label", "building", "floor", "quantity", "note", "reference"},
}
WARNING = "草稿與屋主回覆不是需求確認、法規簽證或專業驗收。禁止填姓名、健康細節、精確預算及電腦絕對路徑。"


def sources(root: Path = ROOT) -> dict[str, Any]:
    return {key: read_json(root / path) if (root / path).is_file() else None for key, path in SOURCE_FILES.items()}


def load_records(project_id: str, path: Path = RECORDS_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": RECORD_SCHEMA, "project_id": project_id, "entries": []}
    value = read_json(path)
    if (
        value.get("schema") != RECORD_SCHEMA
        or value.get("project_id") != project_id
        or not isinstance(value.get("entries"), list)
    ):
        raise ContractError("Owner records schema/project mismatch")
    previous = None
    seen = set()
    for entry in value["entries"]:
        if not isinstance(entry, dict) or entry.get("previous_hash") != previous:
            raise ContractError("Owner records chain broken")
        if entry.get("entry_hash") != stable_hash({k: v for k, v in entry.items() if k != "entry_hash"}):
            raise ContractError("Owner records hash mismatch")
        if not entry.get("id") or entry["id"] in seen:
            raise ContractError("Duplicate owner record")
        seen.add(entry["id"])
        previous = entry["entry_hash"]
    return value


def owner_summary(project_id: str, path: Path = RECORDS_PATH) -> dict[str, Any]:
    records = load_records(project_id, path)
    current_sources = {k: stable_hash(v) for k, v in sources(path.parent.parent).items()}
    # Explicit field allowlist: no arbitrary keys from an imported ledger reach reports.
    entries = []
    for e in records["entries"]:
        if e.get("kind") not in KINDS or not isinstance(e.get("data"), dict):
            raise ContractError("Invalid owner record kind/data")
        entry = {k: e.get(k) for k in ("id", "kind", "target", "supersedes", "recorded_at")}
        entry["data"] = {k: v for k, v in e["data"].items() if k in FIELDS[e["kind"]] and isinstance(v, str)}
        entry["source_status"] = "current" if e.get("source_hashes") == current_sources else "needs_review"
        entries.append(entry)
    return {"record_hash": stable_hash(records), "entries": entries, "warning": WARNING}


def build_workspace(root: Path = ROOT) -> dict[str, Any]:
    src = sources(root)
    if not all(src[k] for k in ("project", "requirements", "register", "physical")):
        raise ContractError("Workspace needs project, requirements, planning register and physical inventory")
    project_id = src["project"]["project_id"]
    if src["register"]["project_id"] != project_id:
        raise ContractError("Planning project mismatch")
    records = load_records(project_id, root / "inputs/owner-records.json")
    reqs = src["requirements"]["requirements"]
    physical = src["physical"]["items"]
    cards = []
    for req in reqs:
        linked = [i for i in physical if i.get("location", {}).get("requirement_id") == req["id"]]
        cards.append(
            {
                "id": req["id"],
                "title": req["title"],
                "location": req.get("applies_to", {}),
                "status": req.get("status"),
                "rationale": req.get("rationale"),
                "constraints": req.get("constraints", {}),
                "source": req.get("source"),
                "relationships": req.get("relationships", []),
                "physical_items": linked,
                "checks": [
                    i["question"] for i in src["register"]["items"] if req["id"] in i.get("requirement_ids", [])
                ],
                "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測",
            }
        )
    # Historical furniture assignments have their own stable IDs; do not conflate with requirements.
    furniture = src["furniture"] or {}
    history = [
        {
            "id": key,
            **assignment,
            "furniture": [
                {**(furniture.get("catalog", {}).get(item.get("catalog"), {})), **item}
                for item in [
                    *furniture.get("profiles", {}).get(assignment.get("profile"), []),
                    *assignment.get("items", []),
                ]
            ],
        }
        for key, assignment in furniture.get("rooms", {}).items()
    ]
    physical_map = {i["id"]: i for i in physical}
    for historical_room in history:
        for item in historical_room["furniture"]:
            if item.get("physical_item_id") in physical_map:
                dimensions, state = active_dimensions(physical_map[item["physical_item_id"]])
                item.update(dimensions)
                item["dimension_source"] = state
    phase_order = [
        "owner_brief",
        "finance",
        "site_search",
        "site_due_diligence",
        "design",
        "tender",
        "construction",
        "handover",
    ]
    stage = src["project"].get("stage", "site_search")
    questions = [
        {**i, "due": phase_order.index(i["due_phase"]) <= phase_order.index(stage)} for i in src["register"]["items"]
    ]
    return {
        "schema": "house-owner-workspace-v1",
        "project_id": project_id,
        "warning": WARNING,
        "source_hashes": {k: stable_hash(v) for k, v in src.items()},
        "record_hash": stable_hash(records),
        "questions": questions,
        "rooms": cards,
        "historical_rooms": history,
        "physical_items": physical,
        "records": owner_summary(project_id, root / "inputs/owner-records.json")["entries"],
    }


def validate_draft(draft: dict[str, Any], workspace: dict[str, Any]) -> list[dict[str, Any]]:
    if draft.get("schema") != DRAFT_SCHEMA or draft.get("project_id") != workspace["project_id"]:
        raise ContractError("Draft schema/project mismatch")
    if draft.get("source_hashes") != workspace["source_hashes"] or draft.get("record_hash") != workspace["record_hash"]:
        raise ContractError("Draft sources or records are stale; export a fresh workspace and review answers")
    rows = draft.get("rows")
    if not isinstance(rows, list):
        raise ContractError("Draft rows must be an array")
    targets = {
        "answer": {i["id"] for i in workspace["questions"]},
        "room": {i["id"] for i in workspace["rooms"]},
        "measurement": {i["id"] for i in workspace["physical_items"]},
    }
    old_ids = {i["id"] for i in workspace["records"]}
    seen = set()
    cleaned = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "kind", "target", "supersedes", "data"}:
            raise ContractError("Invalid draft row fields")
        kind, rid, target, data = row.get("kind"), row.get("id"), row.get("target"), row.get("data")
        if kind not in KINDS or not isinstance(rid, str) or not rid.strip() or rid in seen or rid in old_ids:
            raise ContractError("Unknown kind, duplicate or replayed row id")
        seen.add(rid)
        if not isinstance(target, str) or not target.strip() or (kind in targets and target not in targets[kind]):
            raise ContractError("Unknown target id")
        if row.get("supersedes") and row["supersedes"] not in old_ids:
            raise ContractError("Correction must reference an existing record")
        if row.get("supersedes"):
            old = next(e for e in workspace["records"] if e["id"] == row["supersedes"])
            if old["kind"] != kind or old["target"] != target:
                raise ContractError("Correction kind/target must match the original record")
        if not isinstance(data, dict) or set(data) - FIELDS[kind] or any(not isinstance(v, str) for v in data.values()):
            raise ContractError("Invalid draft data; only known text fields allowed")
        if not any(v.strip() for v in data.values()):
            continue
        for value in data.values():
            if len(value) > 10000 or re.search(r"(?:file://|[A-Za-z]:[\\/]|(?:^|\s)/(?:mnt|root|home|Users)/)", value):
                raise ContractError("Text too long or contains private absolute file path")
        if kind == "meeting":
            if data.get("stage", "proposal") not in {"proposal", "owner_conclusion", "professional_pending"}:
                raise ContractError("Meeting cannot certify professional acceptance")
            for key in ("date", "deadline"):
                if data.get(key):
                    _date(data[key])
        cleaned.append(
            {
                "id": rid,
                "kind": kind,
                "target": target,
                "supersedes": row.get("supersedes"),
                "data": {k: v.strip() for k, v in data.items()},
            }
        )
    return cleaned


def _date(value: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.+)?", value):
        raise ContractError("Invalid ISO date")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("Invalid ISO date") from exc


def import_owner_records(file: Path, *, root: Path = ROOT, apply: bool = False) -> dict[str, Any]:
    workspace = build_workspace(root)
    rows = validate_draft(read_json(file), workspace)
    result = {"mode": "apply" if apply else "preview", "rows": rows, "count": len(rows), "warning": WARNING}
    if apply and rows:
        path = root / "inputs/owner-records.json"
        ledger = load_records(workspace["project_id"], path)
        for row in rows:
            entry = {
                **row,
                "recorded_at": utc_now(),
                "source_hashes": workspace["source_hashes"],
                "previous_hash": ledger["entries"][-1]["entry_hash"] if ledger["entries"] else None,
            }
            entry["entry_hash"] = stable_hash(entry)
            ledger["entries"].append(entry)
        write_json(path, ledger)
    return result


def apply_measurements(file: Path, *, root: Path = ROOT, apply: bool = False) -> dict[str, Any]:
    workspace = build_workspace(root)
    rows = validate_draft(read_json(file), workspace)
    if any(r["kind"] != "measurement" for r in rows):
        raise ContractError("Export measurements only for physical-measurements-import")
    payload = copy.deepcopy(read_json(root / SOURCE_FILES["physical"]))
    by_id = {i["id"]: i for i in payload["items"]}
    seen = set()
    for row in rows:
        if row["target"] in seen:
            raise ContractError("Only one measurement per item in a batch")
        seen.add(row["target"])
        data = row["data"]

        def dims(prefix: str, data: dict[str, str] = data) -> dict[str, float]:
            try:
                result = {k: float(data.get(prefix + k, "")) for k in DIMENSION_KEYS}
            except ValueError as exc:
                raise ContractError("Complete width/depth/height required") from exc
            if any(not math.isfinite(v) or v <= 0 for v in result.values()):
                raise ContractError("Positive finite millimetres required")
            return result

        if not all(data.get(k) for k in ("measured_by", "measured_at", "method", "reference")):
            raise ContractError("Measurement needs verifier, ISO date, method and reference")
        _date(data["measured_at"])
        item = by_id[row["target"]]
        if any(m.get("draft_row_id") == row["id"] for m in item["measurements"]):
            raise ContractError("Measurement draft has already been applied")
        item["measurements"].append(
            {
                "sequence": len(item["measurements"]) + 1,
                "dimensions": dims(""),
                **{k: data[k] for k in ("measured_by", "measured_at", "method")},
                "note": data.get("note", ""),
                "reference": data["reference"],
                "draft_row_id": row["id"],
            }
        )
        if any(data.get("transport_" + k) for k in DIMENSION_KEYS):
            transport = item.setdefault("transport", {})
            previous = {k: copy.deepcopy(v) for k, v in transport.items() if k != "measurement_history"}
            transport.setdefault("measurement_history", []).append(previous)
            transport.update(
                assembled_dimensions=dims("transport_"),
                measurement_state="measured",
                evidence={
                    "verified_by": data["measured_by"],
                    "verified_at": data["measured_at"],
                    "reference": data["reference"],
                },
            )
        if data.get("removable"):
            if data["removable"] not in {"true", "false"}:
                raise ContractError("removable must be true/false or blank")
            item.setdefault("transport", {})["carrying_poles_removable"] = data["removable"] == "true"
        item.setdefault("operation_records", []).append(
            {
                "operation": data.get("operation", ""),
                "weight": data.get("weight", ""),
                "reference": data["reference"],
                "measured_at": data["measured_at"],
            }
        )
    if validate_physical_items(payload):
        raise ContractError("Invalid physical inventory; no measurements written")
    if apply and rows:
        payload["updated_at"] = utc_now()
        write_json(root / SOURCE_FILES["physical"], payload)
    return {
        "mode": "apply" if apply else "preview",
        "items": sorted(seen),
        "count": len(rows),
        "next": "Regenerate HTML/3D capacity views and risk reports; measurement is not transport acceptance",
    }


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else "待補"))


def records_html(summary: dict[str, Any]) -> str:
    if not summary.get("entries"):
        return "<p>尚無已匯入屋主回覆／會議紀錄。</p>"
    return (
        "<h2>屋主回覆與未解事項（非驗收）</h2><p>"
        + _e(WARNING)
        + "</p>"
        + "".join(
            "<details><summary>"
            + _e(e["kind"])
            + " · "
            + _e(e["target"])
            + (" · 來源已變更，回覆待複核" if e.get("source_status") == "needs_review" else "")
            + "</summary><pre>"
            + _e("紀錄 " + str(e.get("id", "")) + ((" · 修正 " + str(e["supersedes"])) if e.get("supersedes") else ""))
            + "\n"
            + _e(json.dumps(e["data"], ensure_ascii=False, indent=2))
            + "</pre></details>"
            for e in summary["entries"]
        )
    )


def records_markdown(summary: dict[str, Any]) -> str:
    lines = ["", "## 屋主回覆與未解事項（非驗收）", "", WARNING, ""]
    for entry in summary.get("entries", []):
        lines += [
            f"### {entry['kind']} · {entry['target']}",
            "",
            "```json",
            json.dumps(entry["data"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        if entry.get("source_status") == "needs_review":
            lines += ["來源已變更，回覆待複核。", ""]
    if not summary.get("entries"):
        lines += ["尚無已匯入紀錄。", ""]
    return "\n".join(lines)


def tool_links(document: str, directory: Path, *, prefix: str = "") -> str:
    """Only local generated pages link the tools; sealed handoff renders stay self-contained."""
    if not (directory / "owner-workspace.html").is_file():
        return document
    nav = f'<p><a href="{prefix}owner-workspace.html">屋主填答／房間卡／量測與會議工作台</a>'
    if (directory / "consistency-review.html").is_file():
        nav += f' · <a href="{prefix}consistency-review.html">資料一致性查核</a>'
    return document.replace("</h1>", "</h1>" + nav + "</p>", 1)


def write_workspace(root: Path = ROOT, output_root: Path | None = None) -> dict[str, str]:
    workspace = build_workspace(root)
    out = output_root or root / "structured/predesign"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "owner-workspace.json", workspace)
    template = (ROOT / "house_design/templates/owner-workspace.html").read_text(encoding="utf-8")
    (out / "owner-workspace.html").write_text(
        template.replace("__DATA__", encode_html_json(workspace)), encoding="utf-8"
    )
    for name, rows in (("room-cards", workspace["rooms"]), ("measurement-sheet", workspace["physical_items"])):
        md = [f"# {'三棟房間需求卡' if name == 'room-cards' else '實物量測表'}", "", WARNING, ""]
        for row in rows:
            md += [
                f"## {row['id']} · {row.get('title', row.get('label'))}",
                "",
                "```json",
                json.dumps(row, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
            kind = "room" if name == "room-cards" else "measurement"
            md += ["### 待填", ""] + [f"- {key}：________________" for key in sorted(FIELDS[kind])] + [""]
        (out / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
    return {
        "html": str(out / "owner-workspace.html"),
        "json": str(out / "owner-workspace.json"),
        "room_cards": str(out / "room-cards.md"),
        "measurement_sheet": str(out / "measurement-sheet.md"),
    }
