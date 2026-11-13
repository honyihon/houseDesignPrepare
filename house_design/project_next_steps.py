"""Derived next-step map: reads existing task/requirement/register IDs without deciding them."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import INDEX, digest, inspect_project, read_public_json

OUT = "structured/planning/project-next-steps"
REQUIREMENTS = "inputs/requirements.json"
REGISTER = "inputs/planning-register.json"
CONTROLS = "inputs/abc-next-protected-controls.json"
FOLLOWUP_KEYS = {"buildings", "register_ids", "requirement_ids", "recommendation", "prepare_now",
    "when_data_arrives", "decision_if_needed", "depends_on", "source_documents"}


def keyed(rows, label):
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("id"), str)
            or not r["id"] for r in rows):
        raise ContractError(label+" requires identified records")
    result = {r["id"]: r for r in rows}
    if len(result) != len(rows):
        raise ContractError(label+" IDs must be unique")
    return result


def strings(value, label, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value) or any(
            not isinstance(v, str) or not v.strip() for v in value) or len(set(value)) != len(value):
        raise ContractError("Expected distinct text values: "+label)


def validate_tasks(tasks, requirements, register):
    for task in tasks.values():
        f = task.get("followup")
        if not isinstance(f, dict) or set(f) != FOLLOWUP_KEYS:
            raise ContractError("Missing/unknown followup fields: "+task["id"])
        if (not isinstance(task.get("title"), str) or not task["title"].strip()
                or type(task.get("priority")) is not int or task["priority"] < 1
                or not isinstance(task.get("status"), str)):
            raise ContractError("Invalid navigation task metadata")
        for k in ["buildings", "register_ids", "requirement_ids", "prepare_now", "when_data_arrives", "depends_on", "source_documents"]:
            strings(f[k], task["id"]+"."+k, nonempty=k not in {"register_ids", "requirement_ids", "depends_on"})
        if set(f["buildings"])-set("ABC"):
            raise ContractError("Unknown task building")
        if not isinstance(f["recommendation"], str) or not f["recommendation"].strip():
            raise ContractError("Recommendation must explain a provisional next step")
        if f["decision_if_needed"] is not None and (not isinstance(f["decision_if_needed"], str) or not f["decision_if_needed"].strip()):
            raise ContractError("Deferred question is a text prompt or null, not a decision result")
        for k, known in [("register_ids", register), ("requirement_ids", requirements), ("depends_on", tasks)]:
            if set(f[k])-set(known):
                raise ContractError("Unknown followup reference: "+task["id"]+"."+k)
        for rid in f["requirement_ids"]:
            if requirements[rid].get("applies_to", {}).get("building_id") not in f["buildings"]:
                raise ContractError("Requirement reference points to another building")
        for rid in f["register_ids"]:
            if not set(register[rid].get("building_ids", [])) & set(f["buildings"]):
                raise ContractError("Register reference points to another building")
    visited, active = set(), set()

    def visit(key):
        if key in active:
            raise ContractError("Next-step dependency cycle; do not hide unresolved mutual decisions")
        if key in visited:
            return
        active.add(key)
        for dep in tasks[key]["followup"]["depends_on"]:
            visit(dep)
        active.remove(key)
        visited.add(key)

    for key in tasks:
        visit(key)


def build(root):
    root = Path(root)
    index = read_public_json(root, INDEX)
    if index.get("work_mode") != "conditional-preplanning-real-data-integration-later":
        raise ContractError("Preserve the owner's preplanning-only working mode")
    requirements = keyed(read_public_json(root, REQUIREMENTS).get("requirements"), "Requirements")
    register = keyed(read_public_json(root, REGISTER).get("items"), "Planning register")
    tasks = keyed(index.get("work_items"), "Navigation tasks")
    validate_tasks(tasks, requirements, register)
    cache = {}
    controls = read_public_json(root, CONTROLS)
    for name, expected in controls["hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original design/reference changed: "+name)
    status = inspect_project(root)
    observed = {p["document"]: p for p in index["packages"]}
    package_states = {p["id"]: p for p in status["packages"]}
    rows, names = [], [INDEX, REQUIREMENTS, REGISTER, CONTROLS]
    for task in sorted(tasks.values(), key=lambda t: (t["priority"], list(tasks).index(t["id"]))):
        f = task["followup"]
        source_refs = []
        for name in f["source_documents"]:
            digest(root, name, cache)
            names.append(name)
            package = observed.get(name)
            state = package_states[package["id"]] if package else None
            source_refs.append({"path": name, "sha256": cache[name],
                "indexed_package_scope": state["check_scope"] if state else "document-reference-only",
                "indexed_source_state": state["source_state"] if state else "not-a-package-acceptance"})
        rows.append({"id": task["id"], "title": task["title"], "priority": task["priority"],
            "navigation_task_status": task["status"], "building_ids": f["buildings"],
            "recommendation": f["recommendation"], "prepare_now": f["prepare_now"],
            "when_data_arrives": f["when_data_arrives"], "decision_if_needed": f["decision_if_needed"],
            "decision_result": None, "depends_on": f["depends_on"], "sources": source_refs,
            "formal_requirements": [{"id": key, "title": requirements[key]["title"],
                "status": requirements[key]["status"]} for key in f["requirement_ids"]],
            "formal_register_items": [{"id": key, "title": register[key]["title"],
                "status": register[key]["status"]} for key in f["register_ids"]],
            "planning_ready_does_not_mean_requirement_confirmed": True,
            "actual_conditions_received_here": False, "design_adopted": False, "professional_approval": "unknown"})
    used_register = {r["id"] for row in rows for r in row["formal_register_items"]}
    used_requirements = {r["id"] for row in rows for r in row["formal_requirements"]}
    report = {"schema": "house-project-next-steps-v1", "date": index["updated_at"],
        "authority": "derived-navigation-only-not-requirement-decisions-or-approval", "rows": rows,
        "summary": {"navigation_tasks": len(rows), "by_building_nonexclusive": {b: sum(b in r["building_ids"] for r in rows) for b in "ABC"},
            "deferred_choice_topics": sum(r["decision_if_needed"] is not None for r in rows),
            "formal_requirement_count": len(requirements), "formal_register_count": len(register),
            "requirement_statuses": dict(Counter(r["status"] for r in requirements.values())),
            "register_statuses": dict(Counter(r["status"] for r in register.values()))},
        "not_represented_in_this_focus_map": {
            "requirement_ids": sorted(set(requirements)-used_requirements),
            "register_ids": sorted(set(register)-used_register),
            "meaning": "只集中本階段優先議題，其他原需求與情境仍留原清單，沒有刪除、降級或完成率推定。"},
        "observed_packages": [{k: p[k] for k in ["id", "check_scope", "source_state", "artifact_state"]} for p in status["packages"]],
        "design_or_primary_3d_changed": False, "formal_requirements_or_register_written": False,
        "protected_controls_unchanged": len(controls["hashes"]), "actual_conditions_received_here": 0,
        "adopted": False, "professional_approval": "unknown", "browser_qa": "not-run",
        "notes": ["現在可準備、等資料後要做與屆時要取捨同列，不將缺實測當現在工作的阻擋。",
            "此表建議是研究方向，不是使用者已採用；候選需求仍按原狀態列出。",
            "工程／家規／照護／搬運的證據和採用仍須各自核對，不能拼用不同版本的有利數字。",
            "此表不寫正式清單、不生成新格局、不更新舊預期hash、不啟動瀏覽器。"]}
    names.extend(["house_design/project_next_steps.py", "house_design/project_status.py",
        "scripts/export_project_next_steps.py", "scripts/export_abc_next_improvements.py", "Docs/project-next-steps-v1.md"])
    for package in index["packages"]:
        for k in ["report", "manifest"]:
            if package.get(k):
                names.append(package[k])
        if package.get("report"):
            names.extend(read_public_json(root, package["report"]).get("source_hashes", {}))
    report["file_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report
