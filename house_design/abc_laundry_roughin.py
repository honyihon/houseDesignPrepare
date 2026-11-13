"""Laundry rough-in discussion interfaces; no point design, system sizing or construction release."""
from __future__ import annotations

from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/abc-laundry-roughin.json"
OUT = "structured/coordination/abc-laundry-roughin-v1"
DOC = "Docs/abc-laundry-roughin-v1.md"
PARENT = "structured/coordination/abc-laundry-use-v1/review.json"
PARENT_SHA = "df5c49acba569405b75ba1245e07a698c1e5b8cd4eb1de06c2462e9c91dc31c7"
PARENT_HASH = "5c4d2c47ac309a04d9be0d7eb45abaea9bc179fc28d8e531e89621d2eb0f2d74"
BUILDER = "inputs/builder-communication-plan.json"
BUILDER_SHA = "dd3334da200ee8e0a09e83fd8d0d2390d6b0225d3364d51b84123790a18f8595"
INTERFACES = ["siting", "water", "wastewater", "power", "air", "waterproof", "vibration", "maintenance"]
ACTUAL_KEYS = {"shared_host_and_legal_site_plan", "products_and_installation_revision", "finished_wall_column_and_door_plan",
    "washer_supply_pressure_and_valve_location", "washer_wastewater_design_and_legal_terminal", "dryer_type_and_condensate_detail",
    "electrical_load_panel_and_protection", "socket_coordinates_height_and_splash_protection", "air_inlet_exhaust_and_moisture_design",
    "door_threshold_levels_and_rain_detail", "waterproofing_and_floor_drainage_detail", "machine_support_vibration_and_noise_targets",
    "rack_fixing_load_and_reach", "machine_opening_service_replacement_envelope", "existing_filter_and_HVAC_service_envelope",
    "A_upper_inactive_stub_safeguards", "C2_temporary_inactivity_and_reactivation_method", "agreed_scope_quote_programme_and_warranty",
    "concealed_work_photos_and_test_records", "professional_review_and_drawing_issue"}


def validate(cfg, builder):
    if (cfg.get("schema") != "house-abc-laundry-roughin-v1" or cfg.get("adopted") is not False
            or cfg.get("parent_report") != PARENT or cfg.get("parent_sha256") != PARENT_SHA
            or cfg.get("parent_report_hash") != PARENT_HASH
            or cfg.get("builder_plan") != BUILDER or cfg.get("builder_plan_sha256") != BUILDER_SHA):
        raise ContractError("Laundry rough-in must preserve source seals and discussion-only scope")
    if set(cfg.get("actual_conditions", {})) != ACTUAL_KEYS or any(v is not None for v in cfg["actual_conditions"].values()):
        raise ContractError("Laundry rough-in actual conditions must remain complete and unknown")
    if [r.get("id") for r in cfg.get("interfaces", [])] != INTERFACES:
        raise ContractError("Laundry rough-in requires all distinct system interfaces")
    questions, a_interfaces = ({r["id"] for r in builder[k]} for k in ["questions", "a_interfaces"])
    for row in cfg["interfaces"]:
        if (not row.get("question_ids") or not row.get("a_interface_ids")
                or set(row["question_ids"])-questions or set(row["a_interface_ids"])-a_interfaces
                or not row.get("laundry_ids") or set(row["laundry_ids"])-{f"LAU-0{n}" for n in range(1, 9)}):
            raise ContractError("Laundry rough-in must reuse existing builder, A designer and laundry topics")
        if any(not isinstance(row.get(k), str) or not row[k].strip()
                for k in ["label", "before", "prepare", "required", "proposed_window"]):
            raise ContractError("Laundry rough-in requires concrete timing, preparation and evidence")
    if [r.get("id") for r in cfg.get("dryer_alternatives", [])] != ["heatpump-condensing", "electric-vented"]:
        raise ContractError("Preserve dryer alternatives without silently selecting a product")


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    builder = read_public_json(root, BUILDER)
    validate(cfg, builder)
    for name, expected in [(PARENT, PARENT_SHA), (BUILDER, BUILDER_SHA)]:
        if digest(root, name, cache) != expected:
            raise ContractError("Laundry rough-in frozen input changed: "+name)
    parent = read_public_json(root, PARENT)
    if (parent.get("report_hash") != PARENT_HASH
            or stable_hash({k: v for k, v in parent.items() if k != "report_hash"}) != PARENT_HASH
            or parent.get("adopted") is not False or len(parent.get("source_hashes", {})) != 30):
        raise ContractError("Laundry rough-in parent seal or scope changed")
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Laundry rough-in parent source changed: "+name)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    if len(controls) != 149 or any(digest(root, n, cache) != h for n, h in controls.items()):
        raise ContractError("Laundry rough-in cannot change protected originals")
    if parent["formal_requirement_statuses"] != {"candidate": 66} or parent["formal_register_statuses"] != {"unknown": 105}:
        raise ContractError("Keep the existing formal statuses")
    space = parent["retained_space"]
    report = {"schema": "house-abc-laundry-roughin-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report": PARENT, "parent_report_sha256": PARENT_SHA, "parent_report_hash": PARENT_HASH,
        "parent_sources_verified": 30, "owner_direction": parent["owner_direction"], "recommendation": cfg["recommendation"],
        "locations": [
            {"id": "shared-ground", "label": "1F共用候選／A1原陽台先研究", "mode": "host-not-adopted",
                "rects_mm": space["machine_bays_mm"],
                "preserve": "原兩個850×750mm安裝預算、洗曬與門路；先核合法共享到達和完整產品，機位能放不等已選主位置。"},
            {"id": "A-upper", "label": "A上層備位／先研究A2後陽台", "mode": "reserve-no-machine-decided",
                "rects_mm": [space["A2_reservation_retained"]["bodies"][0]["rect_mm"]],
                "preserve": "留原備位及水電排水檢修條件，不買機。未啟用的支管／端口安全防漏防臭由設計與工班核；仍須穿書房，門前操作共用。"},
            {"id": "C2-retain", "label": "C2原機位／暫不用保恢復使用", "mode": "temporarily-inactive-reserve-space",
                "rects_mm": [space["C2_space_retained"]["rect_mm"]],
                "preserve": "原650×650mm來源機位及恢復操作空間不放固定櫃。長期停用的止水、端口與存水彎防臭由工班核，保通氣及必要公共排水，不自動拆機。"}],
        "retained_space": space,
        "interfaces": [{**r, "actual_reply": None, "agreed_window": None, "professional_approval": "unknown",
            "construction_release": False} for r in cfg["interfaces"]],
        "actual_conditions": cfg["actual_conditions"], "actual_conditions_received": 0,
        "point_coordinates_decided": False, "pipe_sizes_decided": False, "electrical_ratings_decided": False,
        "dryer_type_selected": None, "exterior_openings_authorized": False, "equipment_purchase_decided": False,
        "host_building_adopted": False, "original_ABC_or_3d_changed": False, "accepted_storage_viewers_changed": False,
        "protected_controls_unchanged": 149, "formal_requirement_statuses": parent["formal_requirement_statuses"],
        "formal_register_statuses": parent["formal_register_statuses"], "adopted": False,
        "professional_approval": "unknown", "construction_release": False, "rendered_qa": "not-run"}
    names = [CONFIG, DOC, PARENT, *parent["source_hashes"], BUILDER,
        "house_design/abc_laundry_roughin.py", "scripts/export_abc_laundry_roughin.py"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report
