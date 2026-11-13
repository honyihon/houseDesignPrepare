"""Prepare staged builder discussions without assigning contracts or adopting designs."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_next_steps import (
    CONTROLS,
    REGISTER,
    REQUIREMENTS,
    keyed,
    strings,
    validate_tasks,
)
from house_design.project_status import INDEX, digest, read_public_json

PLAN = "inputs/builder-communication-plan.json"
OUT = "structured/planning/builder-communication"
AUTHORITY = "communication-preparation-only-not-contract-design-adoption-or-approval"


def validate(plan, tasks):
    if plan.get("schema") != "house-builder-communication-plan-v1" or plan.get("authority") != AUTHORITY:
        raise ContractError("Expected a communication preparation plan, not a design or contract decision")
    direction = plan.get("owner_direction", {})
    if direction.get("actual_site_data_received") is not False or not direction.get("a_interior"):
        raise ContractError("Preserve separate A designer discussion and no actual site data")
    brief = plan.get("building_brief")
    if (not isinstance(brief, list) or [b.get("building") for b in brief] != list("ABC")
            or any(not b.get("known_use") or not b.get("early_topics") for b in brief)
            or not plan.get("shared_brief")):
        raise ContractError("Keep separate ABC use summaries, with unlisted uses retained")
    stages = keyed(plan.get("stages"), "Meeting stages")
    questions = keyed(plan.get("questions"), "Builder questions")
    interfaces = keyed(plan.get("a_interfaces"), "A interfaces")
    quotes = keyed(plan.get("quote_packages"), "Quote packages")
    if list(stages) != [f"S{i:02d}" for i in range(1, 7)]:
        raise ContractError("Keep the six ordered stages from feasibility through handover")
    required = {
        "stage": ["title", "timing", "participants", "hold"],
        "question": ["title", "ask", "evidence"],
        "interface": ["topic", "builder", "designer", "joint", "evidence"],
        "quote": ["buildings", "topic", "boundary"],
    }
    for kind, rows in [("stage", stages), ("question", questions), ("interface", interfaces), ("quote", quotes)]:
        for row in rows.values():
            for field in required[kind]:
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ContractError("Missing communication text: "+row["id"]+"."+field)
            if kind in {"question", "interface"} and row.get("stage") not in stages:
                raise ContractError("Unknown meeting stage: "+row["id"])
            if kind in {"stage", "question"}:
                strings(row.get("task_ids"), row["id"]+".task_ids")
                if set(row["task_ids"])-set(tasks):
                    raise ContractError("Unknown existing work item: "+row["id"])
            if kind == "stage":
                for field in ["prepare", "deliver"]:
                    strings(row.get(field), row["id"]+"."+field)
            if kind == "question":
                strings(row.get("buildings"), row["id"]+".buildings")
                if set(row["buildings"])-set("ABC"):
                    raise ContractError("Unknown building in question")
                available = {b for tid in row["task_ids"] for b in tasks[tid]["followup"]["buildings"]}
                if not set(row["buildings"]) <= available:
                    raise ContractError("Question references another building's task")
    first = plan.get("first_meeting", {})
    strings(first.get("question_ids"), "First meeting question IDs")
    if any(q not in questions or questions[q]["stage"] != "S01" for q in first["question_ids"]):
        raise ContractError("First meeting questions must exist and belong to S01")
    if len(first["question_ids"]) > 5:
        raise ContractError("Keep the first meeting focused on at most five questions")
    strings(plan.get("operating_rules"), "Operating rules")
    return stages, questions, interfaces, quotes


def build(root):
    root = Path(root)
    plan = read_public_json(root, PLAN)
    index = read_public_json(root, INDEX)
    if index.get("work_mode") != "conditional-preplanning-real-data-integration-later":
        raise ContractError("Preserve conditional preplanning, with actual integration later")
    requirements = keyed(read_public_json(root, REQUIREMENTS).get("requirements"), "Requirements")
    register = keyed(read_public_json(root, REGISTER).get("items"), "Planning register")
    tasks = keyed(index.get("work_items"), "Navigation tasks")
    validate_tasks(tasks, requirements, register)
    validate(plan, tasks)
    cache = {}
    controls = read_public_json(root, CONTROLS)["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    names = [PLAN, INDEX, REQUIREMENTS, REGISTER, CONTROLS,
        "house_design/builder_communication.py", "scripts/export_builder_communication.py",
        "house_design/project_next_steps.py", "house_design/project_status.py", "house_design/contracts.py",
        "scripts/export_abc_next_improvements.py", "Docs/builder-communication-v1.md"]
    task_ids = set(t for group in [plan["stages"], plan["questions"]] for row in group for t in row["task_ids"])
    task_refs = []
    for task in tasks.values():
        if task["id"] not in task_ids:
            continue
        f = task["followup"]
        names.extend(f["source_documents"])
        task_refs.append({"id": task["id"], "title": task["title"], "recommendation": f["recommendation"],
            "requirement_references": [{"id": v, "status": requirements[v]["status"]} for v in f["requirement_ids"]],
            "register_references": [{"id": v, "status": register[v]["status"]} for v in f["register_ids"]],
            "source_documents": f["source_documents"]})
    names.extend(ref["path"] for ref in plan["references"])
    report = {"schema": "house-builder-communication-report-v1", "date": plan["date"], "authority": AUTHORITY,
        "plan": plan, "task_references": task_refs,
        "summary": {"stages": len(plan["stages"]), "questions": len(plan["questions"]),
            "a_interfaces": len(plan["a_interfaces"]), "quote_packages": len(plan["quote_packages"]),
            "first_meeting_questions": len(plan["first_meeting"]["question_ids"]),
            "formal_requirement_statuses": dict(Counter(r["status"] for r in requirements.values())),
            "formal_register_statuses": dict(Counter(r["status"] for r in register.values()))},
        "protected_controls_unchanged": len(controls), "builder_responses_received": 0,
        "actual_conditions_received_here": 0, "contractual_responsibilities_agreed": False,
        "formal_requirements_or_register_written": False, "design_or_primary_3d_changed": False,
        "adopted": False, "professional_approval": "unknown", "browser_qa": "not-run",
        "source_hashes": {name: digest(root, name, cache) for name in dict.fromkeys(names)}}
    report["report_hash"] = stable_hash(report)
    return report
