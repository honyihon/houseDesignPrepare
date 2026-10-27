"""Small coordinate/metadata tests only; no scene runtime or access approval."""
import copy

import export_b32_entry_options as export
import pytest


@pytest.fixture(scope="module")
def options():
    return export.build_study()["options"]


def first_cells(building):
    return {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}


def test_both_options_use_street_root_and_same_bathroom(options):
    for o in options:
        r = o["review"]["program"]["entry_access"]
        assert r["unresolved_room_ids"] == []
        assert r["rear_alley_used_as_public_root"] is False
        cells = first_cells(o["model"]["buildings"][0])
        for c in cells.values():
            if c["is_outdoor"]:
                continue
            a = c["tour_features"]["entry_access_review"]
            assert a["route_room_ids"][0] == "B:floor-1:shrine-front"
            assert a["route_room_ids"][-1] == c["id"]
            assert a["professional_acceptance"] == a["finished_clearance"] == "unknown"
            assert c["tour_features"]["access_pending"] is False
        bath = cells["bath1"]["tour_features"]["entry_access_review"]
        assert bath["route_room_ids"][-2:] == [cells["bath-extension"]["id"], cells["bath1"]["id"]]
        work = cells["work-reserve"]["tour_features"]["entry_access_review"]
        assert work["route_room_ids"][-2:] == [cells["storage"]["id"], cells["work-reserve"]["id"]]
        assert work["independent_work_access"] is False


@pytest.mark.parametrize("defect", ["unpaired", "shifted", "kind", "no-reserve", "short-reserve", "blocked-reserve", "no-street", "fake-street"])
def test_rear_door_or_room_label_never_replaces_a_real_conditional_path(options, defect):
    o = copy.deepcopy(options[0])  # Keep the rear storage opening: it cannot grant a public route.
    b = o["model"]["buildings"][0]
    c = first_cells(b)
    if defect in {"unpaired", "shifted", "kind"}:
        edges = c["corridor1"]["tour_features"]["open_connections"]
        seam = next(v for v in edges if v["neighbor"] == c["shrine"]["id"])
        if defect == "unpaired":
            edges.remove(seam)
        elif defect == "shifted":
            seam["ratio"] += .1
        else:
            edges.remove(seam)
            c["corridor1"]["tour_features"]["doors"].append(seam)
    elif defect in {"no-reserve", "short-reserve", "blocked-reserve"}:
        zones = c["shrine"]["tour_features"]["reserved_mm"]
        reserve = next(v for v in zones if v["kind"] == "circulation")
        if defect == "no-reserve":
            zones.remove(reserve)
        elif defect == "short-reserve":
            reserve["aabb"]["minY"] += 300
        else:
            next(iter(c["shrine"]["furniture_placements"]["tour_mm"].values()))["aabb"] = copy.deepcopy(reserve["aabb"])
    else:
        gates = c["shrine-front"]["tour_features"]["doors"]
        gate = next(d for d in gates if d.get("purpose") == "ritual-entry")
        if defect == "no-street":
            gates.remove(gate)
        else:
            gate["ratio"] = 2
    report = export.attach_entry_access(b, o)
    assert "B:floor-1:storage" in report["unresolved_room_ids"]
    assert report["rear_alley_used_as_public_root"] is False


@pytest.mark.parametrize("defect", ["bath-group", "bath-partition", "bath-unpaired", "private-shortcut"])
def test_bath_subzones_are_destinations_not_public_through_rooms(options, defect):
    o = copy.deepcopy(options[1])
    b = o["model"]["buildings"][0]
    c = first_cells(b)
    if defect == "bath-group":
        c["bath1"]["space_group"] = "another-bath"
    elif defect == "bath-partition":
        for key, other in [("bath1", "bath-extension"), ("bath-extension", "bath1")]:
            openings = c[key]["tour_features"]["open_connections"]
            seam = next(v for v in openings if v["neighbor"] == c[other]["id"])
            openings.remove(seam)
            c[key]["tour_features"]["doors"].append(seam)
    elif defect == "bath-unpaired":
        c["bath1"]["tour_features"]["open_connections"] = []
    else:
        # Even a real paired door cannot make a bathroom a public through-route.
        c["storage"]["tour_features"]["doors"] = [d for d in c["storage"]["tour_features"]["doors"] if d["neighbor"] != c["work-reserve"]["id"]]
        for key, other, face, ratio in [("bath1", "work-reserve", "rear", .48), ("work-reserve", "bath1", "front", .5)]:
            c[key]["tour_features"]["doors"].append({"neighbor": c[other]["id"], "face": face, "ratio": ratio, "width_mm": 1000})
    report = export.attach_entry_access(b, o)
    expected = "work-reserve" if defect == "private-shortcut" else "bath1"
    assert c[expected]["id"] in report["unresolved_room_ids"]
