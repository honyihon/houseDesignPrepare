"""Pre-land comparisons: dimensional evidence, not professional approval."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_preparation_review as export
import pytest
from lib.model3d_placement import overlaps

ROOT = Path(__file__).resolve().parents[1]
IDS = ["c-window-3000", "c-window-3600", "c-window-4000", "b-fixed-3000",
       "b-program-3000", "b-program-3600", "b-program-4000"]


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def option(study, key):
    return next(o for o in study["options"] if o["id"] == key)


def cells(o):
    return {c["id"]: c for f in o["model"]["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}


def test_main_archives_and_sources_are_read_only(study):
    before = {p: export.digest(ROOT / p) for p in export.PROTECTED}
    export.build_study()
    assert before == {p: export.digest(ROOT / p) for p in export.PROTECTED}
    assert study["protected_main_hashes"] == before
    assert study["status"] == export.STATUS and study["active_design"] == "baseline"
    assert [o["id"] for o in study["options"]] == IDS
    main = json.loads((ROOT / "structured/candidates/furniture-plans/layout.js").read_text().split(" = ", 1)[1].rstrip(";\n"))
    assert sum(len(f["rooms"]) for b in main["buildings"] for f in b["floors"]) == 112
    assert sum(len(r["furniture"]) for b in main["buildings"] for f in b["floors"] for r in f["rooms"]) == 128


@pytest.mark.parametrize("key", IDS)
def test_floor_coverage_levels_stair_cores_and_products(study, key):
    o = option(study, key)
    frame = [6000, 20530] if key.startswith("b-program") else [6000, 17630]
    assert o["frame_mm"] == frame
    assert len(o["model"]["buildings"]) == 1
    assert set(o["review"]["professional_status"].values()) == {"unknown"}
    bases, cores, body_count = [], [], 0
    previous = 0
    for f in o["plans"]["floors"]:
        assert f["base_mm"] == previous
        previous += f["height_mm"]
        bases.append(f["base_mm"])
        assert [f["width_mm"], f["depth_mm"]] == frame
        assert sum(r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in f["rooms"]) == frame[0] * frame[1]
        for index, r in enumerate(f["rooms"]):
            assert not any(overlaps(export.box(r["geometry"]), export.box(s["geometry"])) for s in f["rooms"][index + 1:])
            assert not r["features"]["stairs"] or r["features"]["stair_geometry"]["fits_reserved_box"]
            if r["kind"] == "stair":
                cores.append(r["geometry"])
                stair = r["features"]["stair_geometry"]
                assert stair["middle_landing_mm"] >= 1000
                assert stair["run_mm"] == (stair["risers"] // 2 - 1) * 270
                assert stair["riser_mm"] == round(f["height_mm"] / stair["risers"], 2)
                assert stair["run_mm"] + stair["middle_landing_mm"] + stair["departure_offset_mm"] == r["features"]["stair_footprint_mm"]["h_mm"]
            for i in r["furniture"]:
                p = i["placement"]
                width, depth = (i["width_mm"], i["depth_mm"]) if p["rotation_deg"] % 180 == 0 else (i["depth_mm"], i["width_mm"])
                assert p["aabb"]["maxX"] - p["aabb"]["minX"] == pytest.approx(width)
                assert p["aabb"]["maxY"] - p["aabb"]["minY"] == pytest.approx(depth)
                body_count += 1
        assert f["plan_file"] == key + "_" + f["id"] + ".svg"
    assert all(g == cores[0] for g in cores)
    assert bases == [0, o["height_mm"], o["height_mm"] + 3000, o["height_mm"] + 6000]
    screen = o["review"]["coordinate_screen"]
    assert screen["fixed_body_failures"] == screen["pending_solver_items"] == screen["operation_limits"] == []
    assert not any(r["issue"] == "operation-vs-body" for r in screen["operation_sharing"])
    assert screen["operation_sharing"] and screen["full_human_door_sweeps"] == "unknown"
    assert body_count == o["model"]["furniture"]["items"]
    assert o["model"]["compare"] == {"available": False}
    assert "mdf_study" not in o["model"]["layout_review"]


@pytest.mark.parametrize("height,public", [(3000, 25.272), (3600, 23.328), (4000, 22.356)])
def test_c_real_window_visitor_path_bed_projection_and_unshrunk_products(study, height, public):
    o = option(study, f"c-window-{height}")
    c, brief = cells(o), o["review"]["program"]
    assert brief["visitor_route"] == ["dining", "entrance", "public-bath"]
    assert brief["wet_rooms_over_bed"] == []
    assert brief["living_dining_nominal_sqm"] == public
    assert brief["kitchen_discussion_inset_sqm"] == 6.5184
    wc = c["C:floor-1:public-bath"]
    f = wc["tour_features"]
    assert (f["window_face"], f["window_mm"], f["window_height_mm"], f["window_sill_mm"]) == ("front", 600, 500, 2100)
    assert f["window_operable"] == "proposed-not-selected" and f["moisture_control"]
    assert brief["ventilation_effective_area"] is None
    expected = {"living:sofa": (1800, 900), "living:coffee-table": (1100, 600),
                "dining:dining-set": (1800, 1800), "entrance:shoe-cabinet": (1200, 350),
                "elder:bed": (1520, 1880), "elder:wardrobe": (1200, 600),
                "elder-bath:accessible-shower": (1200, 1200), "kitchen:counter": (2400, 600),
                "kitchen:fridge": (750, 700)}
    for name, size in expected.items():
        key, local = name.split(":")
        item = next(i for i in c["C:floor-1:" + key]["furniture"] if i["id"].endswith(":" + local))
        assert (item["width_mm"], item["depth_mm"]) == size
    couch = c["C:floor-1:living"]["furniture_placements"]["tour_mm"]["C:floor-1:living:furniture:sofa"]
    assert couch["rotation_deg"] == 90  # faces its TV on the left, not the shared hall
    assert couch["operation_mm"]["maxX"] == couch["aabb"]["minX"]
    for key in ("living-hall", "elder"):
        room = c["C:floor-1:" + key]
        turn = next(z["aabb"] for z in room["tour_features"]["reserved_mm"] if z["kind"] == "care-turn")
        assert turn["maxX"] - turn["minX"] == turn["maxY"] - turn["minY"] == 1500
        allowed = [r for r in c.values() if r["id"].startswith("C:floor-1:") and
                   (r is room or room["space_group"] and r["space_group"] == room["space_group"])]
        assert export.union_covers(turn, allowed)
        assert not any(overlaps(turn, wall) for r in allowed for wall in export.wall_strips(r))
    unit = c["C:floor-1:living-right"]["tour_features"]["hvac_units"][0]
    route = unit["route"]
    assert route["estimated_routed_length_mm"] == pytest.approx(sum(export.math.dist(a, b) for a, b in zip(route["polyline_mm"], route["polyline_mm"][1:])) + route["bend_service_allowance_mm"])
    assert route["compliance"] == "unknown"


def test_b_fixed_gaps_and_conditional_example_not_false_32_ping_approval(study):
    fixed = option(study, "b-fixed-3000")["review"]["program"]
    assert fixed["master_discussion_inset_sqm"] == 14.2416
    assert fixed["master_target_sqm"] == 20
    assert not fixed["first_floor_shower_body_present"]
    for height in (3000, 3600, 4000):
        o = option(study, f"b-program-{height}")
        r, c = o["review"]["program"], cells(o)
        assert r["street_facing_axial_door"] and not r["stair_or_hall_behind_altar"] and not r["sleep_above_whole_shrine"]
        assert r["public_stair_route"] == ["public-entry", "rear-hall", "stair1"]
        assert r["carry_route"] == ["entry", "corridor1", "storage"]
        assert r["storage_discussion_inset_sqm"] == 10.8016
        assert r["master_discussion_inset_sqm"] == 20.0208
        assert r["master_bath_discussion_inset_sqm"] == 6.2496
        assert r["first_floor_shower_body_present"]
        bed = next(i for i in c["B:floor-2:master2"]["furniture"] if i["shape"] == "bed")
        assert (bed["width_mm"], bed["depth_mm"]) == (1800, 2000)
        assert any(i["width_mm"] == i["depth_mm"] == 1200 for i in c["B:floor-1:bath1"]["furniture"])
        areas = {a["id"]: a for a in r["area_checks"]}
        assert areas["B.floor-1.bath_acc"]["target_state"] == "below-target"
        assert areas["B.floor-1.shrine"]["target_state"] == "below-target"
        assert not r["transport"]["assembled_envelope_measured"]
        assert any("KTV" in x for x in r["unaccommodated"])
        assert any("不是32坪" in x for x in o["tradeoffs"])


@pytest.mark.parametrize("defect", ["fixed-overlap", "overflow", "door", "operation", "unsupported-wall"])
def test_independent_screen_catches_post_solver_errors(study, defect):
    b = copy.deepcopy(option(study, "c-window-3000")["model"]["buildings"][0])
    c = next(c for c in b["floors"][0]["cells"] if c["key"] == "public-bath")
    if defect == "fixed-overlap":
        export.set_product(c, "vanity", [5470, 5050, 450, 600], 90, "right")
    elif defect == "overflow":
        export.set_product(c, "vanity", [6000, 4950, 450, 600], 90, "right")
    elif defect == "door":
        export.set_product(c, "vanity", [4400, 4900, 600, 450], 0)
    elif defect == "operation":
        export.set_product(c, "toilet", [4120, 4000, 700, 450], 90)
    else:
        export.set_product(c, "vanity", [4100, 5170, 600, 450], 0, "rear")
    result = export.body_screen(b)
    assert result["fixed_body_failures"] or result["pending_solver_items"] or result["operation_limits"] or any(
        i["issue"] == "operation-vs-body" for i in result["operation_sharing"])


def test_generated_svg_html_3d_parity_and_sources_current(study):
    source = (ROOT / "structured/candidates/preparation-review-3d.html").read_text()
    data = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", source, re.M).group(1))["bc_options"]
    for o in study["options"]:
        m = next(m["model"] for m in data["options"] if m["id"] == o["id"])
        for index, f in enumerate(o["plans"]["floors"]):
            active = {c["id"]: c for c in m["buildings"][0]["floors"][index]["cells"] if c.get("tour_active")}
            tree = ET.parse(ROOT / "structured/candidates/preparation-review" / f["plan_file"])
            assert tree.getroot().get("data-study-option") == o["id"]
            for r in f["rooms"]:
                assert active[r["id"]]["tour_mm"] == r["geometry"]
                assert active[r["id"]]["tour_features"] == r["features"]
                for item in r["furniture"]:
                    svg = tree.find('.//*[@data-furniture-id="' + item["id"] + '"]')
                    assert svg is not None
                    assert float(svg.get("data-width-mm")) == item["width_mm"]
                    assert float(svg.get("data-center-x-mm")) == item["placement"]["center_x_mm"]
                    assert active[r["id"]]["furniture_placements"]["tour_mm"][item["id"]] == item["placement"]
    assert 'htmlHref="bc-options.html#"' not in source
    assert 'htmlHref="preparation-review.html#"' in source
    for p, sha in study["source_hashes"].items():
        assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
    packet = json.loads((ROOT / "structured/discussions/abc-preparation-meeting.json").read_text())
    assert len(packet["scenarios"]) == 22 and packet["professional_approval"] == "unknown"
    assert all(s["status"] == "unknown" and s["evidence"] is None for s in packet["scenarios"])


def test_single_run_not_doubled_and_c_public_area_is_not_recredited(study):
    for bid, prefix in [("C", "c-window"), ("B", "b-program")]:
        rows = [r for r in export.sensitivity(study) if r["option"].startswith(prefix)]
        assert [r["parallel_flight_run_mm"] for r in rows] == [2160, 2700, 2970]
        assert rows[1]["well_depth_mm"] - rows[0]["well_depth_mm"] == 540
        assert rows[2]["well_depth_mm"] - rows[0]["well_depth_mm"] == 810
        assert all(r["legal_arcade_height"] is None and r["beam_and_stair_headroom"] is None for r in rows)


def test_generator_does_not_publish_known_coordinate_defects(monkeypatch):
    monkeypatch.setattr(export, "body_screen", lambda _: {
        "fixed_body_failures": [{"issue": "fixed-body-overlap"}], "pending_solver_items": [],
        "operation_limits": [], "operation_sharing": [],
    })
    with pytest.raises(ValueError, match="coordinate defects"):
        export.build_study()


def test_changed_frame_is_not_silently_ignored(monkeypatch, tmp_path):
    settings = json.loads(export.SOURCE.read_text())
    settings["b_conditional_frame_mm"][1] = 17630
    source = tmp_path / "changed.json"
    source.write_text(json.dumps(settings))
    monkeypatch.setattr(export, "SOURCE", source)
    with pytest.raises(ValueError, match="coordinated redraw"):
        export.build_study()


@pytest.mark.parametrize("height", [3000, 3600, 4000])
def test_c_v2_clear_operations_and_real_size_public_seating(study, height):
    o = option(study, f"c-window-{height}")
    c, r = cells(o), o["review"]["program"]["revision_checks"]
    assert study["revision"] == 2
    assert not r["wash_shares_door_approach"] and not r["shoe_shares_door_approach"]
    assert r["sofa_coffee_gap_mm"] == 600
    assert r["front_window_door_nominal_separation_mm"] == 300
    assert r["visitor_door_nominal_mm"] == 900
    assert r["toilet_entry_use"] == r["chair_dining_use"] == "sequential-not-verified"
    assert r["sliding_leaf_track_handle_and_rescue"] == "unknown"
    living = c["C:floor-1:living"]
    chair = next(i for i in living["furniture"] if i["id"].endswith(":reading-chair"))
    assert (chair["width_mm"], chair["depth_mm"]) == (900, 850)
    assert chair["rotation_deg"] == 0 and "可移" in chair["label"]
    assert not c["C:floor-1:living-right"]["furniture"]
    band = next(z["aabb"] for z in c["C:floor-1:living-hall"]["tour_features"]["reserved_mm"] if z["kind"] == "care-route")
    assert band["maxX"] - band["minX"] == 1200
    for room in c.values():
        if room["id"].startswith("C:floor-1:"):
            for item in room["furniture"]:
                if item["mount_height_mm"] < 2100:
                    assert not overlaps(band, room["furniture_placements"]["tour_mm"][item["id"]]["aabb"])
    interfaces = o["review"]["program"]["public_wc_interfaces"]
    assert interfaces["door_nominal_mm"] == 900 and interfaces["finished_door_clear_mm"] is None
    assert interfaces["proposed_external_window"] and interfaces["effective_ventilation"] == "unknown"


@pytest.mark.parametrize("height", [3000, 3600, 4000])
def test_b_v2_shrine_transport_and_wet_zone_are_coordinated(study, height):
    o = option(study, f"b-program-{height}")
    c, r = cells(o), o["review"]["program"]
    assert c["B:floor-1:shrine"]["tour_mm"] == export.rect(1200, 3900, 3120, 7700)
    assert r["dry_altar_backing"] and not r["wet_above_whole_shrine"]
    assert not r["sleep_above_whole_shrine"] and not r["stair_or_hall_behind_altar"]
    assert c["B:floor-4:shrine-buffer-rf"]["tour_mm"] == c["B:floor-1:shrine"]["tour_mm"]
    for key in ("B:floor-2:bath2", "B:floor-2:master-bath2", "B:floor-3:bath3"):
        assert c[key]["tour_mm"]["y_mm"] == 11600
    budget = r["transport"]["clearance_budget"]
    assert budget["minimum_discussion_clear_mm"] == 1500
    assert [s["discussion_clear_mm"] for s in budget["segments"]] == [1520, 1520, 1500, 1500]
    assert all(s["finished_clear_mm"] is None and s["target_state"] == "nominal-budget-only" for s in budget["segments"])
    assert budget["frame_product"] == budget["columns_handles_tracks"] == budget["people_poles_rehearsal"] == "unknown"
    p = c["B:floor-1:storage"]["furniture_placements"]["tour_mm"]["B:floor-1:storage:furniture:ceremonial-storage"]
    assert p["center_x_mm"] == 5160
    for key in ("entry", "corridor1"):
        g = c["B:floor-1:" + key]["tour_mm"]
        assert g["x_mm"] + 80 <= p["aabb"]["minX"] < p["aabb"]["maxX"] <= g["x_mm"] + g["w_mm"] - 80
    areas = {a["id"]: a for a in r["area_checks"]}
    assert areas["B.floor-1.shrine"]["discussion_inset_sqm"] == 22.3184
    assert areas["B.floor-1.bath_acc"]["discussion_inset_sqm"] == 6.4592
    assert areas["B.floor-2.bath_g"]["discussion_inset_sqm"] == areas["B.floor-3.bath_b3"]["discussion_inset_sqm"] == 3.6736
    assert areas["B.floor-2.bath_g"]["target_state"] == "below-target"
    interfaces = r["first_floor_bath_interfaces"]
    assert interfaces["door_nominal_mm"] == 1060 and interfaces["finished_door_clear_mm"] is None
    assert not interfaces["proposed_external_window"]
    assert interfaces["door_leaf_track_handle_and_rescue"] == "unknown"
    shower = next(i for i in c["B:floor-1:bath1"]["furniture"] if i["shape"] == "shower")
    assert "無障礙" not in shower["label"] and "未核" in shower["label"]


@pytest.mark.parametrize("defect", ["wash", "shoe", "coffee", "window"])
def test_c_v2_screen_rejects_regressions(study, defect):
    c = copy.deepcopy(cells(option(study, "c-window-3000")))
    if defect == "wash":
        export.set_product(c["C:floor-1:public-bath"], "vanity", [5470, 4950, 450, 600], 90, "right")
    elif defect == "shoe":
        export.set_product(c["C:floor-1:entrance"], "shoe-cabinet", [5570, 6300, 350, 1200], 90, "right")
    elif defect == "coffee":
        export.set_product(c["C:floor-1:living"], "coffee-table", [480, 7730, 600, 1100], 270)
    else:
        c["C:floor-1:dining"]["tour_features"]["window_ratio"] = 0.4
    with pytest.raises(ValueError, match="C v2"):
        export.c_revision_screen(c)


@pytest.mark.parametrize("defect", ["gate", "corridor", "shrine", "wet", "backing"])
def test_b_v2_screen_rejects_regressions(study, defect):
    o = option(study, "b-program-3000")
    b = copy.deepcopy(o["model"]["buildings"][0])
    c = {c["id"]: c for f in b["floors"] for c in f["cells"] if c.get("tour_active")}
    if defect == "gate":
        next(d for d in c["B:floor-1:entry"]["tour_features"]["doors"] if d["neighbor"] is None)["width_mm"] = 1500
    elif defect == "corridor":
        c["B:floor-1:corridor1"]["tour_mm"]["w_mm"] = 1600
    elif defect == "shrine":
        c["B:floor-1:shrine"]["tour_mm"]["w_mm"] = 3000
    elif defect == "wet":
        c["B:floor-2:bath2"]["tour_mm"]["y_mm"] -= 20
    else:
        c["B:floor-1:altar-backing"]["tour_mm"]["y_mm"] += 100
    with pytest.raises(ValueError, match="B v2|family rules"):
        export.program_screen(b, o, {})


def test_fixed_32_ping_gaps_not_hidden_by_new_transport_budget(study):
    fixed = option(study, "b-fixed-3000")["review"]["program"]
    assert not fixed["first_floor_shower_body_present"]
    budget = fixed["transport"]["clearance_budget"]
    assert budget["minimum_discussion_clear_mm"] == 1340
    assert all(s["target_state"] == "below-target" for s in budget["segments"])
