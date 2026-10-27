"""Non-circular, reproducible drawing evidence shared by review and planning.

The hash binds data, not a professional signature. Validation reloads the sealed
revision and re-evaluates its overlay; a self-consistent hash alone is not proof.
No planning status, generated timestamp, signoff or release decision belongs here.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from house_design.contracts import ContractError, stable_hash
from house_design.coordination import coordination_review
from house_design.drawings import load_revision

SCHEMA = "house-drawing-evidence-v1"
_KEYS = {
    "schema", "project_id", "project_hash", "requirements_hash", "revision", "model_hash",
    "coordination", "evidence_hash",
}


def build_drawing_evidence(
    *, project: dict[str, Any], requirements: dict[str, Any], manifest: dict[str, Any],
    model: dict[str, Any], coordination: dict[str, Any],
) -> dict[str, Any]:
    snapshot = {
        "schema": SCHEMA,
        "project_id": project.get("project_id"),
        "project_hash": stable_hash(project),
        "requirements_hash": stable_hash(requirements),
        "revision": {"revision_id": manifest.get("revision_id"), "content_hash": manifest.get("content_hash")},
        "model_hash": stable_hash(model),
        "coordination": copy.deepcopy(coordination),
    }
    snapshot["evidence_hash"] = stable_hash(snapshot)
    return snapshot


def validate_drawing_evidence(
    snapshot: Any, *, project: dict[str, Any], requirements: dict[str, Any], revision_root: Path,
    expected_revision_id: str | None = None,
) -> bool:
    """Fail closed on stale, foreign, malformed or non-reproducible evidence."""
    try:
        if not isinstance(snapshot, dict) or set(snapshot) != _KEYS or snapshot.get("schema") != SCHEMA:
            return False
        if (
            not project.get("project_id") or snapshot["project_id"] != project["project_id"]
            or snapshot["project_hash"] != stable_hash(project)
            or snapshot["requirements_hash"] != stable_hash(requirements)
            or stable_hash({k: v for k, v in snapshot.items() if k != "evidence_hash"}) != snapshot["evidence_hash"]
        ):
            return False
        revision = snapshot["revision"]
        if not isinstance(revision, dict) or set(revision) != {"revision_id", "content_hash"}:
            return False
        revision_id = revision["revision_id"]
        if not isinstance(revision_id, str) or (expected_revision_id is not None and revision_id != expected_revision_id):
            return False
        manifest, model = load_revision(revision_id, revision_root)
        if (
            revision["content_hash"] != manifest["content_hash"] or model.get("revision_id") != revision_id
            or snapshot["model_hash"] != stable_hash(model)
        ):
            return False
        coordination = snapshot["coordination"]
        if not isinstance(coordination, dict):
            return False
        actual = coordination_review(model, coordination.get("overlay"), manifest["content_hash"], requirements)
        return stable_hash(actual) == stable_hash(coordination)
    except (ContractError, OSError, KeyError, TypeError, ValueError, AttributeError):
        return False


def check_scope_matches(item: dict[str, Any], check: dict[str, Any], requirements: dict[str, Any]) -> bool:
    """A B/1F item cannot borrow an unrelated A/2F result with the same id.

    Unscoped numeric checks remain usable for compound-wide scenarios, but not
    as evidence for a particular building or floor. Scenario approval remains
    a separate, named human evidence requirement in planning.
    """
    scope = check.get("applies_to") or {}
    requirement_id = scope.get("requirement_id")
    requirement = next((r for r in requirements.get("requirements", []) if r.get("id") == requirement_id), {})
    req_scope = requirement.get("applies_to") or {}
    if any(scope.get(k) and req_scope.get(k) and scope[k] != req_scope[k] for k in ("building_id", "floor_id")):
        return False
    location = {**req_scope, **{k: v for k, v in scope.items() if v is not None}}
    buildings = item.get("building_ids") or []
    building, floor = location.get("building_id"), location.get("floor_id")
    if buildings and building and building not in buildings:
        return False
    if len(buildings) == 1 and not building:
        return False
    if item.get("floor_id") and item["floor_id"] != floor:
        return False
    return not (item.get("requirement_ids") and requirement_id and requirement_id not in item["requirement_ids"])
