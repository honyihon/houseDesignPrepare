"""Illustrative shared-laundry workloads, with mutually exclusive handling; no actual capacity approval."""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/abc-laundry-use.json"
OUT = "structured/coordination/abc-laundry-use-v1"
DOC = "Docs/abc-laundry-use-v1.md"
PARENT = "structured/coordination/abc-laundry-access-v1/review.json"
PARENT_SHA = "35437c6cf61759841d6c3b1640517300c8261bf5bb06c6ce48dbba1ed6e1bc6c"
PARENT_HASH = "cccb8e77b8ff54e162bc27746b1cef493f02e6fd53d43bb19ffe49e41db18730"
TIME_KEYS = {"available_window", "washer_loading", "washer_program", "washer_unloading_transfer",
    "dryer_program", "dryer_unloading", "combined_loading", "combined_program", "combined_unloading"}


def minute_values(values):
    if set(values) != TIME_KEYS | {"basis"} or values["basis"] != "illustrative-only-not-owner-data-or-product-performance":
        raise ContractError("Keep laundry illustrative assumptions distinct from actual conditions")
    if any(type(values[k]) is not int or not 1 <= values[k] <= 1440 for k in TIME_KEYS):
        raise ContractError("Illustrative laundry durations need bounded positive integer minutes, not blanks or booleans")


def phase(batch, resource, kind, start, duration):
    return {"batch": batch, "resource": resource, "kind": kind, "start_min": start, "end_min": start+duration}


def handling_conflicts(phases):
    manual = [p for p in phases if p["kind"] != "program"]
    return [(a["batch"], b["batch"]) for a, b in combinations(manual, 2)
        if max(a["start_min"], b["start_min"]) < min(a["end_min"], b["end_min"])]


def paired_phases(batches, values, interval):
    events = []
    for n in range(batches):
        start = n*interval
        events.append(phase(n+1, "washer", "load", start, values["washer_loading"]))
        start += values["washer_loading"]
        events.append(phase(n+1, "washer", "program", start, values["washer_program"]))
        start += values["washer_program"]
        events.append(phase(n+1, "washer", "transfer", start, values["washer_unloading_transfer"]))
        start += values["washer_unloading_transfer"]
        events.append(phase(n+1, "dryer", "program", start, values["dryer_program"]))
        start += values["dryer_program"]
        events.append(phase(n+1, "dryer", "unload", start, values["dryer_unloading"]))
    return events


def schedule(batches, values, mode):
    """A bounded, fixed-interval example; handling never overlaps in the shared operation area."""
    minute_values(values)
    if type(batches) is not int or not 1 <= batches <= 12:
        raise ContractError("Laundry examples need one to twelve explicit batches")
    wash = sum(values[k] for k in ["washer_loading", "washer_program", "washer_unloading_transfer"])
    dry = values["dryer_program"]+values["dryer_unloading"]
    combined = sum(values[k] for k in ["combined_loading", "combined_program", "combined_unloading"])
    events = []
    if mode == "wash-and-air":
        interval = wash
        for n in range(batches):
            start = n*wash
            for kind, key in [("load", "washer_loading"), ("program", "washer_program"), ("unload", "washer_unloading_transfer")]:
                events.append(phase(n+1, "washer", kind, start, values[key]))
                start += values[key]
        first = wash
    elif mode == "separate-dryer":
        # The preceding dry unloading must finish before the next washer transfer begins.
        lower = max(wash, dry+values["washer_unloading_transfer"])
        for interval in range(lower, wash+dry+1):
            # Check two consecutive intervals even in a one-batch example.
            if not handling_conflicts(paired_phases(max(3, batches), values, interval)):
                break
        else:
            raise ContractError("No shared-handling interval was found within the serial bound")
        events = paired_phases(batches, values, interval)
        first = wash+dry
    elif mode == "combined-machine":
        interval = combined
        for n in range(batches):
            start = n*combined
            for kind, key in [("load", "combined_loading"), ("program", "combined_program"), ("unload", "combined_unloading")]:
                events.append(phase(n+1, "combined", kind, start, values[key]))
                start += values[key]
        first = combined
    else:
        raise ContractError("Unknown illustrative laundry mode")
    if handling_conflicts(events):
        raise ContractError("Shared laundry handling cannot be simultaneous")
    for resource in {p["resource"] for p in events}:
        occupied = [p for p in events if p["resource"] == resource]
        if any(max(a["start_min"], b["start_min"]) < min(a["end_min"], b["end_min"])
                for a, b in combinations(occupied, 2)):
            raise ContractError("A laundry machine is double-booked")
    end = max(p["end_min"] for p in events)
    capacity = 0 if values["available_window"] < first else 1+(values["available_window"]-first)//interval
    return {"mode": mode, "batches": batches, "interval_min": interval, "elapsed_min": end, "phases": events,
        "window_min": values["available_window"], "example_overrun_min": max(0, end-values["available_window"]),
        "example_batches_in_window": capacity, "handling_overlap": False,
        "completion_scope": "wash-only-not-air-dried" if mode == "wash-and-air" else "assumed-one-cycle-per-batch-only",
        "real_dry_completion_verified": False, "actual_demand_satisfied": None, "global_optimum_claimed": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    if (cfg.get("schema") != "house-abc-laundry-use-v1" or cfg.get("adopted") is not False
            or cfg.get("parent_report") != PARENT or cfg.get("parent_sha256") != PARENT_SHA
            or cfg.get("parent_report_hash") != PARENT_HASH):
        raise ContractError("Laundry use must retain its immutable access basis and non-adoption scope")
    if digest(root, PARENT, cache) != PARENT_SHA:
        raise ContractError("Laundry use parent file changed")
    parent = read_public_json(root, PARENT)
    if (parent.get("report_hash") != PARENT_HASH
            or stable_hash({k: v for k, v in parent.items() if k != "report_hash"}) != PARENT_HASH
            or parent.get("adopted") is not False):
        raise ContractError("Laundry use parent report seal changed")
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Laundry use parent source changed: "+name)
    owner = read_public_json(root, cfg["owner_reference"])
    if owner != parent["owner_direction"]:
        raise ContractError("Laundry use cannot replace the confirmed owner direction")
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    if len(controls) != 149 or any(digest(root, n, cache) != h for n, h in controls.items()):
        raise ContractError("Laundry use must preserve protected original plans")
    if (parent["formal_requirement_statuses"] != {"candidate": 66} or parent["formal_register_statuses"] != {"unknown": 105}
            or not cfg.get("actual_conditions") or any(v is not None for v in cfg["actual_conditions"].values())):
        raise ContractError("Keep formal statuses and unreceived actual conditions unknown")
    specs = cfg["illustrative_scenarios"]
    if (any(type(s.get("batches_per_household")) is not int for s in specs)
            or [(s.get("id"), s.get("batches_per_household")) for s in specs] != [("daily-example", 1), ("bedding-example", 2)]):
        raise ContractError("Retain two explicit hypothetical workloads, not invented household demand")
    scenarios = [{**spec, "basis": "hypothetical-not-actual-demand", "households": ["A", "B", "C"],
        "batches": 3*spec["batches_per_household"],
        "modes": [schedule(3*spec["batches_per_household"], cfg["illustrative_minutes"], mode)
            for mode in ["wash-and-air", "separate-dryer", "combined-machine"]]} for spec in specs]
    rear = parent["rear_entry_screen"]
    report = {"schema": "house-abc-laundry-use-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report": PARENT, "parent_report_sha256": PARENT_SHA, "parent_report_hash": PARENT_HASH,
        "parent_sources_verified": len(parent["source_hashes"]), "owner_direction": owner,
        "recommendation": cfg["recommendation"], "scenarios": scenarios,
        "retained_space": {"machine_bays_mm": [i["rect_mm"] for i in rear["bodies"] if i["id"] != "lowered-drying-envelope"],
            "rack_envelope_mm": next(i["rect_mm"] for i in rear["bodies"] if i["id"] == "lowered-drying-envelope"),
            "rack_envelope_is_kg_capacity": False, "cart_parking_adopted": False,
            "shared_operation_bands": rear["shared_operation_bands"], "door_travel_gaps_mm": rear["leaf_travel_body_gaps_mm"],
            "rear_whole_route_approved": False, "C2_space_retained": parent["C2_space_retained"],
            "A2_reservation_retained": parent["A2_reservation_retained"], "B_source_states_retained": parent["B_source_states_retained"]},
        "actual_conditions": cfg["actual_conditions"], "actual_conditions_received": 0,
        "actual_laundry_capacity_sufficient": None, "air_drying_duration_min": None,
        "protected_controls_unchanged": 149, "formal_requirement_statuses": parent["formal_requirement_statuses"],
        "formal_register_statuses": parent["formal_register_statuses"], "host_building_adopted": False,
        "original_ABC_or_3d_changed": False, "accepted_storage_viewers_changed": False,
        "equipment_purchase_decided": False, "adopted": False, "professional_approval": "unknown", "rendered_qa": "not-run"}
    names = [CONFIG, DOC, PARENT, *parent["source_hashes"], cfg["owner_reference"],
        "house_design/abc_laundry_use.py", "scripts/export_abc_laundry_use.py"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report
