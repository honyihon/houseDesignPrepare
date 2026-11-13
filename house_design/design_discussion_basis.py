"""Source-bound discussion references and a static handout; no layout or decision writes."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from house_design.abc_laundry_access import build as build_laundry_access
from house_design.abc_laundry_roughin import build as build_laundry_roughin
from house_design.abc_laundry_use import build as build_laundry_use
from house_design.abc_meeting_followup import build as build_meeting_followup
from house_design.ac_storage_preview import ARCHIVE as AC_STORAGE_ARCHIVE
from house_design.ac_storage_preview import OUT as AC_STORAGE_OUT
from house_design.ac_storage_preview import build as build_ac_storage_preview
from house_design.b_front_drop_reply_routes import build as build_drainage_routes
from house_design.b_upper_storage_sync import ARCHIVE as B_STORAGE_ARCHIVE
from house_design.b_upper_storage_sync import OUT as B_STORAGE_OUT
from house_design.b_upper_storage_sync import build as build_b_storage_sync
from house_design.b_upper_storage_viewer import ARCHIVE as B_VIEWER_ARCHIVE
from house_design.b_upper_storage_viewer import OUT as B_VIEWER_OUT
from house_design.b_upper_storage_viewer import build as build_b_storage_viewer
from house_design.builder_communication import PLAN as BUILDER_PLAN
from house_design.contracts import ContractError, stable_hash
from house_design.plan_readability import readable_svg
from house_design.project_next_steps import CONTROLS, REGISTER, REQUIREMENTS, keyed, strings, validate_tasks
from house_design.project_status import (
    INDEX,
    digest,
    inspect_project,
    public_path,
    read_public_json,
    source_checks_current,
)
from house_design.upper_floor_storage_viewer import build as build_storage_viewer
from scripts.export_ac_storage_preview import render as render_ac_storage_preview
from scripts.export_b_upper_storage_sync import render as render_b_storage_sync
from scripts.export_b_upper_storage_viewer import render as render_b_storage_viewer
from scripts.export_upper_floor_storage_viewer import render as render_storage_viewer

PLAN = "inputs/design-discussion-basis.json"
AC_STORAGE_QA = "inputs/references/ac-storage-rendered-review-20261112.json"
B_STORAGE_QA = "inputs/references/b-upper-storage-rendered-review-20261113.json"
SCENARIOS = "inputs/abc-use-scenarios.json"
OUT = "structured/planning/design-discussion-basis"
AUTHORITY = "discussion-basis-and-handoff-only-not-adopted-or-professionally-approved"
BASIS_LABELS = {"owner-confirmed-direction": "屋主已確認方向", "original-goal-not-adopted": "原需求目標／未採用配置",
    "study-only": "研究建議／未採用", "pending-owner-choice": "待條件齊備後由屋主取捨"}
MAX_SVG_BYTES = 2*1024*1024


def static_svg(data):
    """Preserve vector geometry/text, removing navigation that would leave the handout."""
    if len(data) > MAX_SVG_BYTES or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ContractError("SVG exceeds static attachment scope")
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ContractError("Malformed static SVG") from exc
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ContractError("Expected SVG drawing")
    removed = 0
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject", "image", "iframe"}:
            raise ContractError("Active or externally loaded SVG content is outside the static handout")
        css = (node.text or "") if tag == "style" else ""
        css += node.attrib.get("style", "")
        if re.search(r"@import|url\(\s*['\"]?(?!#)[^\s'\"]", css, re.I):
            raise ContractError("SVG contains a nonlocal stylesheet resource")
        for name, value in list(node.attrib.items()):
            local = name.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or (local in {"href", "src"} and not value.startswith("#")):
                del node.attrib[name]
                removed += 1
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)+b"\n", removed


def validate(plan, tasks, register, scenarios):
    if plan.get("schema") != "house-design-discussion-basis-v1" or plan.get("authority") != AUTHORITY:
        raise ContractError("Discussion basis cannot adopt designs or assign professional approval")
    assets = plan.get("assets")
    if not isinstance(assets, dict) or not assets or any(not re.fullmatch(r"[A-Za-z0-9-]+", k) for k in assets):
        raise ContractError("Attachment IDs must be distinct safe filenames")
    rows = keyed(plan.get("floor_versions"), "Floor versions")
    expected = {(b, f) for b in "ABC" for f in ["floor-1", "floor-2", "floor-3", "floor-rf"]}
    if len(rows) != 12 or {(r.get("building"), r.get("floor")) for r in rows.values()} != expected:
        raise ContractError("Version map requires exactly ABC 1F/2F/3F/RF; RF is not a fourth residential floor")
    for row in rows.values():
        for key in ["base_assets", "task_ids"]:
            strings(row.get(key), row["id"]+"."+key)
        strings(row.get("supplement_assets"), row["id"]+".supplement_assets", nonempty=False)
        if set(row["base_assets"]+row["supplement_assets"])-set(assets) or set(row["task_ids"])-set(tasks):
            raise ContractError("Unknown floor attachment or work item")
        if row["building"] == "B" and row.get("integration") != "local-research-not-merged-in-main-3d":
            raise ContractError("Do not claim the latest B research is merged into the old main 3D")
    docs = set(plan.get("source_documents", []))
    for name in ["a_brief", "bc_comparisons", "systems", "extra_walkthroughs"]:
        keyed(plan.get(name), name)
        for row in plan[name]:
            if set(row.get("source_refs", []))-docs:
                raise ContractError("Unbound source reference")
            if set(row.get("task_ids", []))-set(tasks) or set(row.get("register_ids", []))-set(register):
                raise ContractError("Unknown work item or original register item")
            if set(row.get("assets", []))-set(assets):
                raise ContractError("Unknown comparison attachment")
    if any(row.get("basis") not in BASIS_LABELS for row in plan["a_brief"]):
        raise ContractError("A brief must distinguish owner directions, original goals, studies and deferred choices")
    if set(plan.get("scenario_overrides", {}))-set(scenarios):
        raise ContractError("Scenario context correction must cite an existing ID")
    if set(scenarios) & {r["id"] for r in plan["extra_walkthroughs"]}:
        raise ContractError("Extra walkthrough must not shadow an original scenario")
    observations = plan.get("paper_observations", {})
    if set(observations) != set(scenarios) | {r["id"] for r in plan["extra_walkthroughs"]}:
        raise ContractError("Every walkthrough needs a source-bound paper observation")
    for row in observations.values():
        if not row.get("state") or not row.get("finding") or not row.get("source_refs") or set(row["source_refs"])-docs:
            raise ContractError("Paper observation requires a finding and bound sources")
    strings(plan.get("a_requested_deliverables"), "Suggested A designer deliverables")


def readable_copy(data):
    cleaned, removed = static_svg(data)
    content, entries = readable_svg(cleaned)
    return content, removed, entries


def storage_owner_review(plan, storage):
    """Reuse all frozen storage cases; owner feedback remains in the existing walkthrough."""
    guide = plan.get("storage_owner_review", {})
    if (set(guide) != {"purpose", "source", "feedback_scenario_id", "items"}
            or guide["source"] != "inputs/upper-floor-storage.json"
            or guide["source"] not in plan["source_documents"]
            or guide["feedback_scenario_id"] != "ABC-DAILY-CHAIN"
            or guide["feedback_scenario_id"] not in plan["paper_observations"]
            or not isinstance(guide["purpose"], str) or not guide["purpose"].strip()):
        raise ContractError("Storage owner review must reuse the bound source and existing feedback scenario")
    cases = keyed(storage["cases"], "Storage cases")
    items = guide["items"]
    if not isinstance(items, list) or [r.get("case") for r in items] != list(cases):
        raise ContractError("Storage owner review must retain all source cases, including both B roofs")
    rows = []
    for item in items:
        if set(item) != {"case", "access", "recommendation", "check"} or any(
                not isinstance(item[k], str) or not item[k].strip() for k in ["access", "recommendation", "check"]):
            raise ContractError("Storage owner review contains reading guidance, not choices, dimensions or approvals")
        source = cases[item["case"]]
        asset = "ST-"+source["id"]
        if asset not in plan["assets"]:
            raise ContractError("Storage owner review lacks its matching plan attachment")
        rows.append({**item, "building": source["building"], "floor": source["floor"],
            "label": source["label"], "rect_mm": source["rect_mm"], "height_mm": source["height_mm"],
            "operation_mm": source["operation_mm"], "source_note": source["note"], "asset": asset,
            "viewer_archive": B_VIEWER_ARCHIVE if source["building"] == "B" else AC_STORAGE_ARCHIVE,
            "owner_choice": None, "adopted": False, "professional_approval": "unknown"})
    return {"purpose": guide["purpose"], "source": guide["source"],
        "feedback_scenario_id": guide["feedback_scenario_id"], "items": rows}


def laundry_preplanning_basis(root, plan, cache):
    """Carry the new owner direction separately from unchanged older washer drawings."""
    name = plan.get("laundry_preplanning")
    if name != "structured/coordination/abc-ground-laundry-v1/review.json" or name not in plan["source_documents"]:
        raise ContractError("Bind the latest laundry preplanning report")
    study = read_public_json(root, name)
    owner = study.get("owner_direction", {}).get("confirmed", {})
    if (study.get("schema") != "house-abc-ground-laundry-report-v1"
            or study.get("report_hash") != stable_hash({k: v for k, v in study.items() if k != "report_hash"})
            or study.get("adopted") is not False or study.get("host_building_adopted") is not False
            or study.get("original_ABC_or_3d_changed") is not False
            or study.get("actual_conditions_received") != 0
            or owner.get("shared_group_at_ground_floor") != 1
            or owner.get("A_upper_floor_washer_space_required") is not True
            or owner.get("C_floor2_initial_washer_use") != "temporarily-inactive-reserve-space"):
        raise ContractError("Laundry preplanning cannot adopt a host, change originals or lose the latest owner direction")
    for source, expected in study["source_hashes"].items():
        if digest(root, source, cache) != expected:
            raise ContractError("Laundry preplanning source changed: "+source)
    return study, [name, *study["source_hashes"]]


def laundry_access_basis(root, plan, cache):
    """Bind the independent access geometry without extending it to the unknown exterior."""
    name = plan.get("laundry_access")
    if name != "structured/coordination/abc-laundry-access-v1/review.json" or name not in plan["source_documents"]:
        raise ContractError("Bind the independent laundry access report")
    study = read_public_json(root, name)
    if (study.get("schema") != "house-abc-laundry-access-report-v1"
            or study.get("report_hash") != stable_hash({k: v for k, v in study.items() if k != "report_hash"})
            or study.get("adopted") is not False or study.get("host_building_adopted") is not False
            or study.get("original_ABC_or_3d_changed") is not False
            or study.get("actual_conditions_received") != 0
            or study.get("rear_entry_screen", {}).get("whole_route_or_care_approved") is not False
            or study.get("front_entry_screen", {}).get("global_front_replanning_impossible") is not False
            or study.get("parent_report") != plan["laundry_preplanning"]):
        raise ContractError("Laundry access cannot adopt a host or claim whole-route approval or global impossibility")
    for source, expected in study["source_hashes"].items():
        if digest(root, source, cache) != expected:
            raise ContractError("Laundry access source changed: "+source)
    if study["report_hash"] != build_laundry_access(root)["report_hash"]:
        raise ContractError("Laundry access report differs from its current scoped geometry")
    return study, [name, *study["source_hashes"]]


def laundry_use_basis(root, plan, cache):
    """Carry hypothetical demand separately from unreceived actual capacity and product data."""
    name = plan.get("laundry_use")
    if name != "structured/coordination/abc-laundry-use-v1/review.json" or name not in plan["source_documents"]:
        raise ContractError("Bind the laundry use report")
    study = read_public_json(root, name)
    if (study.get("schema") != "house-abc-laundry-use-report-v1"
            or study.get("report_hash") != stable_hash({k: v for k, v in study.items() if k != "report_hash"})
            or study.get("adopted") is not False or study.get("equipment_purchase_decided") is not False
            or study.get("host_building_adopted") is not False or study.get("original_ABC_or_3d_changed") is not False
            or study.get("actual_conditions_received") != 0 or study.get("actual_laundry_capacity_sufficient") is not None
            or study.get("air_drying_duration_min") is not None or study.get("parent_report") != plan["laundry_access"]):
        raise ContractError("Laundry use cannot turn an illustrative workload into actual capacity or purchases")
    for source, expected in study["source_hashes"].items():
        if digest(root, source, cache) != expected:
            raise ContractError("Laundry use source changed: "+source)
    if study["report_hash"] != build_laundry_use(root)["report_hash"]:
        raise ContractError("Laundry use report differs from the current illustrative schedules")
    return study, [name, *study["source_hashes"]]


def laundry_roughin_basis(root, plan, cache):
    """Reuse original builder questions without treating interface planning as construction design."""
    name = plan.get("laundry_roughin")
    if name != "structured/coordination/abc-laundry-roughin-v1/review.json" or name not in plan["source_documents"]:
        raise ContractError("Bind the laundry rough-in report")
    study = read_public_json(root, name)
    if (study.get("schema") != "house-abc-laundry-roughin-report-v1"
            or study.get("report_hash") != stable_hash({k: v for k, v in study.items() if k != "report_hash"})
            or any(study.get(k) is not False for k in ["adopted", "construction_release", "equipment_purchase_decided",
                "point_coordinates_decided", "pipe_sizes_decided", "electrical_ratings_decided", "exterior_openings_authorized"])
            or study.get("dryer_type_selected") is not None or study.get("actual_conditions_received") != 0
            or study.get("parent_report") != plan["laundry_use"]):
        raise ContractError("Laundry rough-in cannot authorize points, ratings, purchases or construction")
    for source, expected in study["source_hashes"].items():
        if digest(root, source, cache) != expected:
            raise ContractError("Laundry rough-in source changed: "+source)
    if study["report_hash"] != build_laundry_roughin(root)["report_hash"]:
        raise ContractError("Laundry rough-in report differs from current source-bound interfaces")
    return study, [name, *study["source_hashes"]]


def validate_workflow(plan, tasks, builder):
    """Validate timing references without making a schedule or approving a choice."""
    if plan.get("workflow_revision") != 1:
        raise ContractError("Expected the discussion sequencing revision")
    if not isinstance(plan.get("workflow_scope"), str) or not plan["workflow_scope"].strip():
        raise ContractError("Sequencing must explain per-building and per-work scope")
    sequence = keyed(plan.get("decision_sequence"), "Decision sequence")
    stages = keyed(builder.get("stages"), "Builder stages")
    known = {"task_ids": tasks, "question_ids": keyed(builder["questions"], "Builder questions"),
        "a_interface_ids": keyed(builder["a_interfaces"], "A interfaces"),
        "brief_ids": keyed(plan["a_brief"], "A brief"), "comparison_ids": keyed(plan["bc_comparisons"], "BC comparisons"),
        "system_ids": keyed(plan["systems"], "Systems"), "lock_after": sequence, "coordinate_with": sequence}
    rank = {key: n for n, key in enumerate(stages)}
    for row in sequence.values():
        if row.get("stage") not in stages:
            raise ContractError("Unknown sequencing stage")
        strings(row.get("building_ids"), "Sequencing buildings")
        if set(row["building_ids"])-set("ABC"):
            raise ContractError("Unknown sequencing building")
        for field, values in known.items():
            strings(row.get(field), row["id"]+"."+field, nonempty=field == "task_ids")
            if set(row[field])-set(values):
                raise ContractError("Unknown sequencing reference: "+field)
        if row["id"] in row["lock_after"]+row["coordinate_with"]:
            raise ContractError("Sequence cannot depend or coordinate with itself")
        for dependency in row["lock_after"]:
            if rank[sequence[dependency]["stage"]] > rank[row["stage"]]:
                raise ContractError("A sequencing prerequisite cannot belong to a later stage")
        for field in ["title", "proposed_lead", "first_action", "before_lock", "defer_strategy", "decision_when"]:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ContractError("Missing sequencing text: "+field)
        strings(row.get("required_reply"), row["id"]+".required_reply")
    active, visited = set(), set()

    def visit(key):
        if key in active:
            raise ContractError("Finalization prerequisite cycle; parallel coordination belongs in coordinate_with")
        if key in visited:
            return
        active.add(key)
        for dependency in sequence[key]["lock_after"]:
            visit(dependency)
        active.remove(key)
        visited.add(key)

    for key in sequence:
        visit(key)
    meeting = plan.get("a_first_meeting", {})
    for key in ["duration", "purpose", "opening_message"]:
        if not isinstance(meeting.get(key), str) or not meeting[key].strip():
            raise ContractError("Missing A first-meeting text")
    questions = keyed(meeting.get("questions"), "A first-meeting questions")
    for row in questions.values():
        for field, ids in [("brief_ids", known["brief_ids"]), ("a_interface_ids", known["a_interface_ids"]), ("sequence_ids", sequence)]:
            strings(row.get(field), row["id"]+"."+field)
            if set(row[field])-set(ids):
                raise ContractError("Unknown A meeting reference: "+field)
        if any("A" not in sequence[key]["building_ids"] for key in row["sequence_ids"]):
            raise ContractError("A first meeting cannot decide a B/C-only sequence item")
        for field in ["topic", "ask", "deliver"]:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ContractError("Missing A first-meeting question")
    strings(meeting.get("finish_with"), "A meeting outputs")
    if not isinstance(meeting.get("agenda"), list) or not meeting["agenda"]:
        raise ContractError("A first meeting requires an agenda")
    for row in meeting["agenda"]:
        if not row.get("minutes") or not row.get("topic"):
            raise ContractError("Missing A meeting agenda item")
    records = {"drawing-register.csv", "builder-replies.csv", "a-interface-matrix.csv", "bc-comparison-replies.csv",
        "life-walkthrough.csv", "systems-replies.csv", "same-scope-quotes.csv", "change-log.csv", "decision-sequence.csv",
        "meeting-decisions.csv", "inspection-log.csv", "a-first-meeting-replies.csv", "b-review-replies.csv",
        "abc-coordination-actions.csv"}
    for row in keyed(plan.get("reply_workflow"), "Reply review steps").values():
        for field in ["title", "action", "outcome"]:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ContractError("Missing reply review step")
        strings(row.get("records"), "Reply record links")
        if set(row["records"])-records:
            raise ContractError("Unknown reply record file")
    validate_b_route(plan, sequence, known["question_ids"])


def validate_b_route(plan, sequence, questions):
    route = plan.get("b_review_route", {})
    if (not isinstance(route, dict) or route.get("revision") != 1 or route.get("sequence_id") != "SEQ-04"
            or route.get("comparison_id") != "BC-CMP-07" or route.get("capacity_gate_id") != "BQG-07"):
        raise ContractError("B reply routing must retain its existing decision/comparison and capacity gate")
    comparison = keyed(plan["bc_comparisons"], "B comparison route").get(route["comparison_id"])
    step = sequence.get(route["sequence_id"])
    if (step is None or step["building_ids"] != ["B"] or comparison is None or comparison["building"] != "B"):
        raise ContractError("B reply routing cannot decide another building's work")
    strings(route.get("question_ids"), "B reply question IDs")
    if any(k not in questions or "B" not in questions[k]["buildings"] for k in route["question_ids"]):
        raise ContractError("B reply routing needs existing B meeting questions")
    if (route.get("engineering_report") not in plan["source_documents"]
            or not isinstance(route.get("engineering_report_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", route["engineering_report_sha256"])):
        raise ContractError("Bind the B engineering report to a public source and exact SHA-256")
    if not isinstance(route.get("purpose"), str) or not route["purpose"].strip():
        raise ContractError("Explain the B reply routing scope")
    for key in ["preserve", "meeting_order"]:
        strings(route.get(key), "B reply "+key)
    alternatives = keyed(route.get("fallbacks"), "B reply fallback routes")
    if list(alternatives) != [f"B-ROUTE-{i:02d}" for i in range(1, 6)]:
        raise ContractError("Keep all five B conditional routes; none is an adopted fallback")
    for row in alternatives.values():
        if set(row) != {"id", "title", "trigger", "action", "limits", "cost_scope", "assets"}:
            raise ContractError("B fallback routes contain discussion fields, not approval or choice fields")
        for key in ["title", "trigger", "action", "limits", "cost_scope"]:
            if not isinstance(row[key], str) or not row[key].strip():
                raise ContractError("Missing B fallback consequence or cost boundary")
        strings(row["assets"], "B fallback assets", nonempty=False)
        if set(row["assets"])-set(plan["assets"]):
            raise ContractError("Unknown B fallback drawing")


def b_review_basis(root, plan, cache):
    """Read the pinned engineering findings; never turn reply text into adoption."""
    route = plan["b_review_route"]
    name = route["engineering_report"]
    if digest(root, name, cache) != route["engineering_report_sha256"]:
        raise ContractError("B engineering basis changed; review the new revision before handoff")
    engineering = read_public_json(root, name)
    if (engineering.get("schema") != "house-b-q3-engineering-gates-report-v1" or engineering.get("adopted") is not False
            or engineering.get("report_hash") != stable_hash({k: v for k, v in engineering.items() if k != "report_hash"})):
        raise ContractError("B engineering basis requires an intact independent study report")
    sources = engineering.get("source_hashes")
    if not isinstance(sources, dict) or not sources:
        raise ContractError("Missing B engineering source bindings")
    for source, expected in sources.items():
        if digest(root, source, cache) != expected:
            raise ContractError("B engineering source changed: "+source)
    gates = engineering["engineering_gates"]
    if [r["id"] for r in gates] != [f"BQG-{i:02d}" for i in range(1, 10)]:
        raise ContractError("B reply routing needs the complete nine engineering questions")
    capacity = engineering["capacity_boundary"]
    target, upper = capacity["original_target_sqm"], capacity["fixed_front_upper_bound_before_equipment_sqm"]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in [target, upper]):
        raise ContractError("Invalid B capacity basis")
    shortfall = round(max(0, target-upper), 6)
    return {"source_report": name, "source_sha256": route["engineering_report_sha256"],
        "source_report_hash": engineering["report_hash"], "original_RF_target_sqm": target,
        "fixed_front_optimistic_upper_bound_sqm": upper, "known_RF_shortfall_sqm": shortfall,
        "known_capacity_conflict": shortfall > 0,
        "current_next_action": "continue-independent-research-not-whole-design-adoption",
        "gates": [{**r, "basis_status": "known-capacity-conflict" if r["id"] == route["capacity_gate_id"] and shortfall > 0 else "pending-evidence",
            "received_reply": None, "owner_choice": None, "professional_review": "unknown", "construction_drawing_issued": False} for r in gates],
        "fallbacks": [{**r, "owner_choice": None, "adopted": False, "all_original_goals_met": False} for r in route["fallbacks"]],
        "all_positive_reply_text_would_resolve_capacity": False, "actual_replies_imported": 0,
        "whole_design_adoption_allowed_here": False, "construction_release_allowed_here": False}, [name, *sources]


def b_drainage_basis(root, plan, cache):
    """Include only the pinned blank public interface; never load private conditions into handouts."""
    basis = plan.get("b_drainage_intake", {})
    name = basis.get("report")
    expected = "structured/coordination/b-front-drop-conditions-v1/review.json"
    if (name != expected or name not in plan["source_documents"]
            or [basis.get(k) for k in ["sequence_id", "comparison_id", "task_id"]] != ["SEQ-04", "BC-CMP-01", "B-WET-001"]
            or digest(root, name, cache) != basis.get("report_sha256")):
        raise ContractError("G4D intake must bind the reviewed public template and existing B decision identities")
    report = read_public_json(root, name)
    if (report.get("schema") != "house-b-front-drop-conditions-report-v1" or report.get("adopted") is not False
            or report.get("report_hash") != stable_hash({k:v for k,v in report.items() if k != "report_hash"})
            or report.get("condition_values_received") != 0 or report.get("condition_document_hash") is not None
            or report.get("received_conditions") != report.get("condition_template")):
        raise ContractError("Discussion package can include only an intact blank G4D interface, not private replies")
    groups = report["condition_template"]["groups"]
    if (any(v is not None for g in groups for v in g["values"].values())
            or any(g["reference"] for g in groups) or any(report["condition_template"]["basis"].values())
            or [g["id"] for g in report["engineering_gates"]] != [f"BFD-{i:02d}" for i in range(1,9)]):
        raise ContractError("Do not publish actual G4D values or replace the eight builder questions")
    sources = report.get("source_hashes", {})
    if not sources:
        raise ContractError("G4D intake source bindings missing")
    for source, expected_hash in sources.items():
        if digest(root, source, cache) != expected_hash:
            raise ContractError("G4D intake source drift: "+source)
    return report, [name, *sources]


def b_drainage_routes_basis(root,plan,cache):
    basis=plan.get("b_drainage_reply_routes",{})
    name=basis.get("report")
    if (name!="structured/planning/b-front-drop-reply-routes/review.json" or name not in plan["source_documents"]
            or digest(root,name,cache)!=basis.get("report_sha256")):
        raise ContractError("G4D handoff routes require the pinned public research-only routing report")
    report=read_public_json(root,name)
    if (report.get("condition_report_imported") is not False or report.get("condition_values_received")!=0
            or report.get("active_action_ids")!=["BFR-07"] or report!=build_drainage_routes(root)):
        raise ContractError("Only current blank reply routes belong in handouts, never private results or edited statuses")
    return report,[name,*report["source_hashes"]]


def validate_coordination_agenda(agenda,plan,tasks,builder):
    root_fields={"schema","date","duration_minutes","authority","title","purpose","participants","opening_message",
        "before_meeting","finish_with","source_refs","slots"}
    if (not isinstance(agenda,dict) or set(agenda)!=root_fields
            or agenda.get("schema")!="house-abc-coordination-agenda-v1"
            or agenda.get("authority")!="meeting-preparation-only-no-design-adoption-or-professional-approval"
            or type(agenda.get("duration_minutes")) is not int or agenda["duration_minutes"]!=90):
        raise ContractError("ABC agenda is a90-minute preparation guide without meeting results or approvals")
    for key in ["title","purpose","opening_message","date"]:
        if not isinstance(agenda.get(key),str) or not agenda[key].strip():
            raise ContractError("Missing ABC agenda text: "+key)
    for key in ["participants","before_meeting","finish_with","source_refs"]:
        strings(agenda.get(key),"ABC agenda "+key)
    if set(agenda["source_refs"])-set(plan["source_documents"]):
        raise ContractError("ABC agenda requires public source bindings")
    slots=keyed(agenda.get("slots"),"ABC coordination slots")
    if list(slots)!=[f"COORD-{i:02d}" for i in range(1,7)]:
        raise ContractError("Keep six ordered ABC coordination blocks")
    known={"task_ids":tasks,"question_ids":keyed(builder["questions"],"Builder questions"),
        "floor_ids":keyed(plan["floor_versions"],"Floor versions"),"asset_ids":plan["assets"],
        "comparison_ids":keyed(plan["bc_comparisons"],"BC comparisons"),"a_brief_ids":keyed(plan["a_brief"],"A brief"),
        "a_interface_ids":keyed(builder["a_interfaces"],"A interfaces"),"system_ids":keyed(plan["systems"],"Systems"),
        "sequence_ids":keyed(plan["decision_sequence"],"Sequence")}
    text_fields={"title","proposed_lead","objective","request","retain","decision_when"}
    slot_fields={"id","start_minute","end_minute","buildings","ask",*text_fields,*known}
    start=0
    for slot in slots.values():
        if (set(slot)!=slot_fields or type(slot.get("start_minute")) is not int or type(slot.get("end_minute")) is not int
                or slot["start_minute"]!=start or not start<slot["end_minute"]<=agenda["duration_minutes"]):
            raise ContractError("ABC meeting time blocks must be continuous, bounded and not imply decisions")
        start=slot["end_minute"]
        for key in text_fields:
            if not isinstance(slot.get(key),str) or not slot[key].strip():
                raise ContractError("Missing ABC coordination text: "+key)
        strings(slot["buildings"],"ABC agenda buildings")
        strings(slot["ask"],"ABC agenda questions")
        if set(slot["buildings"])-set("ABC"):
            raise ContractError("Unknown building in ABC agenda")
        for key,values in known.items():
            strings(slot[key],slot["id"]+"."+key,nonempty=key in {"task_ids","question_ids","sequence_ids"})
            if set(slot[key])-set(values):
                raise ContractError("Unknown ABC agenda reference: "+key)
        buildings=set(slot["buildings"])
        available={b for key in slot["task_ids"] for b in tasks[key]["followup"]["buildings"]}
        if (any(not set(known["question_ids"][q]["buildings"])<=buildings for q in slot["question_ids"])
                or not buildings<=available
                or any(not buildings.intersection(tasks[key]["followup"]["buildings"]) for key in slot["task_ids"])
                or any(known["floor_ids"][f]["building"] not in buildings for f in slot["floor_ids"])
                or any(known["comparison_ids"][c]["building"] not in buildings for c in slot["comparison_ids"])
                or any(not set(known["sequence_ids"][s]["building_ids"])<=buildings for s in slot["sequence_ids"])
                or any(a[0] not in buildings for a in slot["asset_ids"])
                or (slot["a_brief_ids"] or slot["a_interface_ids"]) and "A" not in buildings):
            raise ContractError("ABC agenda cannot borrow another building's questions, drawings or decisions")
    if start!=agenda["duration_minutes"] or [r["buildings"] for r in slots.values()]!=[["A","B","C"],["B"],["C"],["A"],["A","B","C"],["A","B","C"]]:
        raise ContractError("Preserve common/B/C/A/systems/close sequence and the separate A designer interface")


def meeting_followup_basis(root,plan,cache):
    basis=plan.get("meeting_followup",{})
    name=basis.get("report")
    if (name!="structured/planning/abc-meeting-followup/review.json" or name not in plan["source_documents"]
            or digest(root,name,cache)!=basis.get("report_sha256")):
        raise ContractError("Meeting follow-up handout requires its reviewed blank public report")
    report=read_public_json(root,name)
    if (report.get("actual_record_imported") is not False or report.get("record_document_hash") is not None
            or report.get("meeting_reported") is not False or report.get("replies_reported")!=0
            or report!=build_meeting_followup(root)):
        raise ContractError("Do not publish private meeting notes, choices or edited follow-up statuses in the blank handout")
    return report,[name,*report["source_hashes"]]


def validate_drawing_return_review(plan,tasks,builder):
    guide=plan.get("drawing_return_review",{})
    if (guide.get("schema")!="house-drawing-return-review-v1"
            or guide.get("authority")!="receipt-and-change-review-guide-only-no-design-adoption-or-release"):
        raise ContractError("Returned drawing guide cannot adopt or release drawings")
    for key in ["format_rules","formal_workflow_refs"]:
        strings(guide.get(key),"Drawing return "+key)
    if set(guide["formal_workflow_refs"])-set(plan["source_documents"]) or not guide.get("purpose"):
        raise ContractError("Returned drawing instructions need existing public workflow sources")
    questions=keyed(builder["questions"],"Builder questions")
    sequence=keyed(plan["decision_sequence"],"Decision sequence")
    rows=keyed(guide.get("steps"),"Drawing return review")
    if list(rows)!=[f"RETURN-{i:02d}" for i in range(1,9)]:
        raise ContractError("Keep the eight receiving and impact review instructions")
    for row in rows.values():
        if set(row)!={"id","buildings","topic","check","recheck","question_ids","task_ids","sequence_ids"}:
            raise ContractError("Returned drawing guide contains instructions, not received evidence or decisions")
        for key in ["topic","check","recheck"]:
            if not isinstance(row[key],str) or not row[key].strip():
                raise ContractError("Missing returned drawing instruction")
        strings(row["buildings"],"Drawing return buildings")
        if set(row["buildings"])-set("ABC"):
            raise ContractError("Unknown returned drawing building")
        for key,known in [("question_ids",questions),("task_ids",tasks),("sequence_ids",sequence)]:
            strings(row[key],"Drawing return "+key)
            if set(row[key])-set(known):
                raise ContractError("Unknown returned drawing reference")
        if (any(not set(row["buildings"]).intersection(questions[q]["buildings"]) for q in row["question_ids"])
                or any(not set(row["buildings"]).intersection(tasks[q]["followup"]["buildings"]) for q in row["task_ids"])
                or any(not set(row["buildings"]).intersection(sequence[q]["building_ids"]) for q in row["sequence_ids"])):
            raise ContractError("Returned drawing reference belongs to another building")


def validate_quote_review(plan, builder):
    guide = plan.get("quote_review", {})
    if set(guide) != {"purpose", "principles", "steps", "package_checks"} or not guide["purpose"]:
        raise ContractError("Quote review contains instructions only, not actual quotes or choices")
    strings(guide["principles"], "Quote review principles")
    if not isinstance(guide["steps"], list) or len(guide["steps"]) != 6:
        raise ContractError("Keep the six same-scope quote review steps")
    for step in guide["steps"]:
        if set(step) != {"title", "check"} or any(not isinstance(v, str) or not v.strip() for v in step.values()):
            raise ContractError("Missing quote review instruction")
    packages = keyed(builder["quote_packages"], "Existing quote topics")
    questions = keyed(builder["questions"], "Builder questions")
    interfaces = keyed(builder["a_interfaces"], "A interfaces")
    rows = guide["package_checks"]
    if not isinstance(rows, list) or [r.get("package_id") for r in rows] != list(packages):
        raise ContractError("Quote notes must follow the existing twelve topics without new packages")
    for row in rows:
        if set(row) != {"package_id", "question_ids", "a_interface_ids", "risk", "ask"}:
            raise ContractError("Quote notes cannot publish actual prices, choices or approvals")
        for field in ["risk", "ask"]:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ContractError("Quote topic needs an overlap risk and requested basis")
        buildings = set(packages[row["package_id"]]["buildings"])
        for field, known in [("question_ids", questions), ("a_interface_ids", interfaces)]:
            strings(row[field], "Quote review "+field, nonempty=field == "question_ids")
            if set(row[field])-set(known):
                raise ContractError("Unknown quote review reference")
        if (any(not buildings.intersection(questions[q]["buildings"]) for q in row["question_ids"])
                or (row["a_interface_ids"] and "A" not in buildings)):
            raise ContractError("Quote reference belongs to another building")


def validate_inspection_review(plan, builder):
    guide = plan.get("inspection_review", {})
    if (set(guide) != {"purpose", "principles", "checkpoints"}
            or not isinstance(guide["purpose"], str) or not guide["purpose"].strip()):
        raise ContractError("Inspection guide contains instructions, not actual inspections or releases")
    strings(guide["principles"], "Inspection principles")
    rows = keyed(guide["checkpoints"], "Inspection reminders")
    if list(rows) != [f"INS-{i:02d}" for i in range(1, 10)]:
        raise ContractError("Keep the nine existing-workflow inspection and handoff reminders")
    questions = keyed(builder["questions"], "Builder questions")
    interfaces = keyed(builder["a_interfaces"], "A interfaces")
    sequence = keyed(plan["decision_sequence"], "Decision sequence")
    for row in rows.values():
        if set(row) != {"id", "buildings", "title", "before", "check", "evidence", "question_ids", "a_interface_ids", "sequence_ids"}:
            raise ContractError("Inspection reminder cannot contain actual results, thresholds or approvals")
        for field in ["title", "before", "check", "evidence"]:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ContractError("Missing inspection instruction")
        strings(row["buildings"], "Inspection buildings")
        buildings = set(row["buildings"])
        if buildings-set("ABC"):
            raise ContractError("Unknown inspection building")
        for field, known in [("question_ids", questions), ("a_interface_ids", interfaces), ("sequence_ids", sequence)]:
            strings(row[field], "Inspection "+field, nonempty=field != "a_interface_ids")
            if set(row[field])-set(known):
                raise ContractError("Unknown inspection reference")
        if (any(not buildings.intersection(questions[q]["buildings"]) for q in row["question_ids"])
                or any(not buildings.intersection(sequence[q]["building_ids"]) for q in row["sequence_ids"])
                or (row["a_interface_ids"] and "A" not in buildings)):
            raise ContractError("Inspection reference belongs to another building")


def ac_storage_rendered_qa(root, preview, files, cache):
    """Accept only the separate display review bound to this exact frozen ZIP."""
    qa = read_public_json(root, AC_STORAGE_QA)
    automatic, visual = qa.get("automated", {}), qa.get("visual_review", {})
    artifacts = {n: hashlib.sha256(data).hexdigest() for n, data in files.items()}
    if (qa.get("schema") != "house-ac-storage-rendered-review-v1"
            or qa.get("status") != "passed-for-comparison-display-scope"
            or qa.get("display_revision") != preview["display_revision"]
            or qa.get("report_hash") != preview["report_hash"]
            or qa.get("source_hashes") != preview["source_hashes"]
            or qa.get("viewer_artifacts_sha256") != artifacts
            or qa.get("raw_evidence", {}).get("tested_preview_zip_sha256") != artifacts[AC_STORAGE_ARCHIVE]
            or automatic.get("status") != "passed" or automatic.get("checks") != 188
            or automatic.get("failed") != 0 or automatic.get("cases") != 24
            or automatic.get("console_errors") != [] or automatic.get("closed") is not True
            or visual.get("status") != "completed-with-minor-display-limitations"
            or visual.get("screenshots_reviewed") != 36 or visual.get("blocking_findings") != []
            or qa.get("constraints", {}).get("adopted") is not False
            or qa.get("constraints", {}).get("professional_approval") != "unknown"):
        raise ContractError("A/C display review does not match the current frozen preview")
    for name, expected in artifacts.items():
        if digest(root, AC_STORAGE_OUT+"/"+name, cache) != expected:
            raise ContractError("A/C display review artifact changed: "+name)
    return {"status": qa["status"], "source": AC_STORAGE_QA, "sha256": digest(root, AC_STORAGE_QA, cache),
        "checks": 188, "cases": 24, "screenshots_reviewed": 36,
        "minor_limitations": visual["minor_limitations"], "adopted": False, "professional_approval": "unknown"}


def b_storage_rendered_qa(root, viewer, files, cache):
    """Bind the later owner-run display review without rewriting the accepted viewer."""
    qa = read_public_json(root, B_STORAGE_QA)
    automatic, visual = qa.get("automated", {}), qa.get("visual_review", {})
    artifacts = {n: hashlib.sha256(data).hexdigest() for n, data in files.items()}
    if (qa.get("schema") != "house-b-upper-storage-rendered-review-v1"
            or qa.get("status") != "passed-for-comparison-display-scope"
            or qa.get("display_revision") != viewer["display_revision"]
            or qa.get("report_hash") != viewer["report_hash"]
            or qa.get("source_hashes") != viewer["source_hashes"]
            or qa.get("viewer_artifacts_sha256") != artifacts
            or qa.get("raw_evidence", {}).get("tested_viewer_zip_sha256") != artifacts[B_VIEWER_ARCHIVE]
            or automatic.get("status") != "passed" or automatic.get("checks") != 127
            or automatic.get("failed") != 0 or automatic.get("cases") != 16
            or automatic.get("console_errors") != [] or automatic.get("closed") is not True
            or visual.get("status") != "completed-with-minor-display-limitations"
            or visual.get("screenshots_reviewed") != 32 or visual.get("blocking_findings") != []
            or len(qa.get("screenshots_sha256", {})) != 32 or len(qa.get("cases", [])) != 16
            or qa.get("constraints", {}).get("adopted") is not False
            or qa.get("constraints", {}).get("professional_approval") != "unknown"
            or qa.get("constraints", {}).get("construction_release") is not False):
        raise ContractError("B display review does not match the current frozen viewer")
    for name, expected in artifacts.items():
        if digest(root, B_VIEWER_OUT+"/"+name, cache) != expected:
            raise ContractError("B display review artifact changed: "+name)
    return {"status": qa["status"], "source": B_STORAGE_QA, "sha256": digest(root, B_STORAGE_QA, cache),
        "checks": 127, "cases": 16, "screenshots_reviewed": 32,
        "minor_limitations": visual["minor_limitations"], "adopted": False, "professional_approval": "unknown"}


def build(root):
    root = Path(root)
    plan, index = read_public_json(root, PLAN), read_public_json(root, INDEX)
    if index.get("work_mode") != "conditional-preplanning-real-data-integration-later":
        raise ContractError("Preserve conditional preplanning")
    requirements = keyed(read_public_json(root, REQUIREMENTS)["requirements"], "Requirements")
    register = keyed(read_public_json(root, REGISTER)["items"], "Register")
    tasks = keyed(index["work_items"], "Tasks")
    validate_tasks(tasks, requirements, register)
    scenarios = keyed(read_public_json(root, SCENARIOS)["scenarios"], "Scenarios")
    validate(plan, tasks, register, scenarios)
    builder = read_public_json(root, BUILDER_PLAN)
    validate_workflow(plan, tasks, builder)
    validate_drawing_return_review(plan,tasks,builder)
    validate_quote_review(plan, builder)
    validate_inspection_review(plan, builder)
    agenda_name=plan.get("coordination_agenda")
    if agenda_name!="inputs/abc-coordination-agenda.json" or agenda_name not in plan["source_documents"]:
        raise ContractError("Bind the ABC coordination agenda to its public source")
    agenda=read_public_json(root,agenda_name)
    validate_coordination_agenda(agenda,plan,tasks,builder)
    status = inspect_project(root)
    if not source_checks_current(status):
        raise ContractError("Current indexed sources changed; resolve before preparing a new handout")
    cache = {}
    controls = read_public_json(root, CONTROLS)["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original design changed: "+name)
    b_review, b_sources = b_review_basis(root, plan, cache)
    b_drainage, drainage_sources = b_drainage_basis(root, plan, cache)
    drainage_routes, route_sources = b_drainage_routes_basis(root, plan, cache)
    meeting_followup, followup_sources = meeting_followup_basis(root,plan,cache)
    viewer_name = "structured/coordination/upper-floor-storage-viewer-v1/review.json"
    storage_viewer = read_public_json(root,viewer_name)
    if storage_viewer != build_storage_viewer(root):
        raise ContractError("Storage 3D must match current source-bound independent viewer")
    archive_name = "upper-floor-storage-3d.zip"
    archive_source = "structured/coordination/upper-floor-storage-viewer-v1/"+archive_name
    archive_bytes = render_storage_viewer(root,storage_viewer)[archive_name]
    if public_path(root,archive_source).read_bytes() != archive_bytes:
        raise ContractError("Storage 3D archive differs from its reviewed source")
    ac_preview = build_ac_storage_preview(root)
    ac_files = render_ac_storage_preview(root, ac_preview)
    ac_archive_source = AC_STORAGE_OUT+"/"+AC_STORAGE_ARCHIVE
    for filename in ["review.json", "artifact-manifest.json", AC_STORAGE_ARCHIVE]:
        if public_path(root, AC_STORAGE_OUT+"/"+filename).read_bytes() != ac_files[filename]:
            raise ContractError("A/C storage preview differs from its same-source comparison: "+filename)
    ac_qa = ac_storage_rendered_qa(root, ac_preview, ac_files, cache)
    b_sync = build_b_storage_sync(root)
    b_sync_files = render_b_storage_sync(b_sync)
    b_archive_source = B_STORAGE_OUT+"/"+B_STORAGE_ARCHIVE
    for filename, content in b_sync_files.items():
        if public_path(root, B_STORAGE_OUT+"/"+filename).read_bytes() != content:
            raise ContractError("B upper-floor synchronization is stale: "+filename)
    b_viewer = build_b_storage_viewer(root)
    b_viewer_files = render_b_storage_viewer(root, b_viewer)
    b_viewer_archive_source = B_VIEWER_OUT+"/"+B_VIEWER_ARCHIVE
    for filename, content in b_viewer_files.items():
        if public_path(root, B_VIEWER_OUT+"/"+filename).read_bytes() != content:
            raise ContractError("B source-height 3D viewer is stale: "+filename)
    b_viewer_qa = b_storage_rendered_qa(root, b_viewer, b_viewer_files, cache)
    storage_review = storage_owner_review(plan, read_public_json(root, "inputs/upper-floor-storage.json"))
    laundry_study, laundry_sources = laundry_preplanning_basis(root, plan, cache)
    laundry_access, laundry_access_sources = laundry_access_basis(root, plan, cache)
    laundry_use, laundry_use_sources = laundry_use_basis(root, plan, cache)
    laundry_roughin, laundry_roughin_sources = laundry_roughin_basis(root, plan, cache)
    names = [PLAN, INDEX, REQUIREMENTS, REGISTER, CONTROLS, SCENARIOS, BUILDER_PLAN,
        "house_design/design_discussion_basis.py", "scripts/export_design_discussion_basis.py", "house_design/plan_readability.py",
        "house_design/project_next_steps.py", "house_design/project_status.py", "house_design/contracts.py",
        "scripts/export_builder_communication.py", "scripts/export_abc_next_improvements.py",
        "Docs/design-discussion-basis-v1.md", *plan["source_documents"], *b_sources, *drainage_sources, *route_sources, *followup_sources,
        viewer_name, archive_source, *storage_viewer["source_hashes"],
        AC_STORAGE_OUT+"/review.json", ac_archive_source, *ac_preview["source_hashes"], AC_STORAGE_QA,
        B_STORAGE_OUT+"/review.json", b_archive_source, *b_sync["source_hashes"],
        B_VIEWER_OUT+"/review.json", b_viewer_archive_source, *b_viewer["source_hashes"], B_STORAGE_QA,
        *laundry_sources, *laundry_access_sources, *laundry_use_sources, *laundry_roughin_sources]
    package_states = {p["id"]: p for p in status["packages"]}
    packages = {p["id"]: p for p in index["packages"]}
    attachments = []
    for key, asset in plan["assets"].items():
        source_hash = digest(root, asset["source"], cache)
        content, removed, entries = readable_copy(public_path(root, asset["source"]).read_bytes())
        package = package_states.get(asset["package_id"])
        attachments.append({"id": key, **asset, "source_sha256": source_hash,
            "attachment": "drawings/"+key+".svg", "attachment_sha256": hashlib.sha256(content).hexdigest(),
            "navigation_attributes_removed": removed,
            "visible_equipment_legend": entries,
            "package_source_state": package["source_state"] if package else "local-study-file-hash-only",
            "package_scope": package["check_scope"] if package else "unindexed-local-study",
            "rendered_qa": "not-verified-here", "adopted": False})
        names.append(asset["source"])
    for key in sorted({a["package_id"] for a in attachments} & set(packages)):
        package = packages[key]
        for field in ["report", "manifest"]:
            if package.get(field):
                names.append(package[field])
        if package.get("report"):
            names.extend(read_public_json(root, package["report"]).get("source_hashes", {}))
    walks = [{"id": s["id"], "building": s["building"], "scenario": s["scenario"],
        "expectation": plan["scenario_overrides"].get(s["id"], s["expectation"]),
        "original_expectation": s["expectation"], "context_updated_here": s["id"] in plan["scenario_overrides"],
        "original_status": s["status"], "evidence_needed": s["evidence_needed"], "result": None,
        "approved": False} for s in scenarios.values()]
    walks += [{**s, "original_expectation": None, "context_updated_here": False, "original_status": "new-discussion-only",
        "evidence_needed": "同版圖面／完整產品／使用與專業核對，尚未演練。", "result": None, "approved": False}
        for s in plan["extra_walkthroughs"]]
    for row in walks:
        row["paper_observation"] = plan["paper_observations"][row["id"]]
    report = {"schema": "house-design-discussion-report-v1", "date": plan["date"], "authority": AUTHORITY,
        "plan": plan, "attachments": attachments, "walkthroughs": walks, "b_review": b_review,
        "b_drainage_intake": b_drainage,
        "b_drainage_reply_routes": drainage_routes,
        "coordination_agenda": agenda,
        "coordination_followup": meeting_followup,
        "storage_owner_review": storage_review,
        "laundry_preplanning": laundry_study,
        "laundry_access": laundry_access,
        "laundry_use": laundry_use,
        "laundry_roughin": laundry_roughin,
        "storage_3d_archive": {"source":archive_source,"filename":archive_name,"sha256":hashlib.sha256(archive_bytes).hexdigest(),
            "report_hash":storage_viewer["report_hash"],"scope":storage_viewer["display_scope"],"rendered_qa":storage_viewer["rendered_qa"]},
        "ac_storage_3d_archive": {"source":ac_archive_source,"filename":AC_STORAGE_ARCHIVE,
            "sha256":hashlib.sha256(ac_files[AC_STORAGE_ARCHIVE]).hexdigest(),
            "report_hash":ac_preview["report_hash"],"rendered_qa":ac_qa["status"],"display_review":ac_qa,
            "scope":ac_preview["scope"],"new_cabinets":6,"adopted":False},
        "b_upper_storage_archive": {"source": b_archive_source, "filename": B_STORAGE_ARCHIVE,
            "sha256": hashlib.sha256(b_sync_files[B_STORAGE_ARCHIVE]).hexdigest(),
            "report_hash": b_sync["report_hash"], "scope": b_sync["config"]["scope"],
            "summary": b_sync["summary"], "rendered_qa": b_sync["rendered_qa"], "adopted": False},
        "b_upper_storage_3d_archive": {"source": b_viewer_archive_source, "filename": B_VIEWER_ARCHIVE,
            "sha256": hashlib.sha256(b_viewer_files[B_VIEWER_ARCHIVE]).hexdigest(),
            "report_hash": b_viewer["report_hash"], "summary": b_viewer["summary"],
            "rendered_qa": b_viewer_qa["status"], "display_review": b_viewer_qa, "adopted": False},
        "coordination_meeting_status": {"meeting_held":False,"actual_date":None,"actual_participants":[],"received_replies":0,
            "owner_choices_received":0,"professional_approval":"unknown","construction_release":False},
        "a_original_requirement_references": [{"id": r["id"], "title": r["title"], "status": r["status"]}
            for r in requirements.values() if r["applies_to"]["building_id"] == "A"],
        "system_register_references": {r: {"title": register[r]["title"], "status": register[r]["status"]}
            for s in plan["systems"] for r in s["register_ids"]},
        "builder_meeting_plan": builder,
        "decision_execution": [{**row, "actual_deadline": None, "agreed_lead": None, "owner_choice": None,
            "received_evidence": [], "professional_review": "unknown", "construction_drawing_issued": False}
            for row in plan["decision_sequence"]],
        "summary": {"floors": len(plan["floor_versions"]), "drawings": len(attachments), "a_topics": len(plan["a_brief"]),
            "bc_comparisons": len(plan["bc_comparisons"]), "walkthroughs": len(walks), "systems": len(plan["systems"]),
            "decision_items": len(plan["decision_sequence"]), "a_meeting_questions": len(plan["a_first_meeting"]["questions"]),
            "reply_review_steps": len(plan["reply_workflow"]),
            "formal_requirement_statuses": dict(Counter(r["status"] for r in requirements.values())),
            "formal_register_statuses": dict(Counter(r["status"] for r in register.values()))},
        "protected_controls_unchanged": len(controls), "layout_or_primary_3d_changed": False,
        "formal_requirements_or_register_written": False, "new_measured_values_received": 0,
        "owner_or_builder_responses_received_here": 0, "adopted": False,
        "professional_approval": "unknown", "browser_qa": "not-run", "new_geometry_generated": False,
        "paper_review_method": "existing-documents-and-static-plan-review-not-rehearsal-or-new-geometry-computation",
        "notes": ["版本對照不等於各局部已併成同一棟；B及C缺口仍明列。",
            "附件保留現有SVG設計幾何與原文字；去除離包導覽／事件，編號家具另在原畫布下方附可見名稱圖例，未轉點陣圖。新增儲藏圖為獨立提案，尚未併主3D。",
            "來源相符只表示檔案狀態；歷史來源漂移及未驗畫面不會升格為通過。",
            "確認方向與正式candidate／unknown狀態分開保留，本包不回寫、不採購、不送出文件。"],
        "source_hashes": {name: digest(root, name, cache) for name in dict.fromkeys(names)}}
    report["report_hash"] = stable_hash(report)
    return report
