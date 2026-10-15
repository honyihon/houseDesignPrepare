"""Unadopted B/C comparisons: actual rooms, full products, explicit costs."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_bc_options as export
import pytest
from bs4 import BeautifulSoup
from lib.furniture_layout import FurnitureLayoutError
from lib.model3d_placement import _issues, overlaps

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def option(study, id):
    return next(o for o in study["options"] if o["id"] == id)


def rooms(study, id):
    return {r["id"]: r for f in option(study, id)["plans"]["floors"] for r in f["rooms"]}


def cells(study, id):
    return {
        c["id"]: c
        for f in option(study, id)["model"]["buildings"][0]["floors"]
        for c in f["cells"]
        if c.get("tour_active")
    }


def test_comparison_does_not_write_or_adopt_main_and_baselines_match(study):
    files = [
        ROOT / p
        for p in [
            "inputs/concept-layout-review.json",
            "inputs/furniture-layout.json",
            "inputs/requirements.json",
            "structured/candidates/model3d.html",
            "structured/candidates/furniture-plans/layout.js",
        ]
    ]
    before = [p.read_bytes() for p in files]
    export.build_study()
    assert [p.read_bytes() for p in files] == before
    main = json.loads(files[-1].read_text().removeprefix("window.HOUSE_CONCEPT_LAYOUT = ").rstrip(";\n"))
    assert study["status"] == export.STATUS and study["active_design"] == "baseline"
    for id, bid in [("b-baseline", "B"), ("c-baseline", "C")]:
        baseline = copy.deepcopy(option(study, id)["plans"])
        for f in baseline["floors"]:
            f["plan_file"] = f"{bid}_{f['id']}.svg"
        frozen = export.model3d.build_payload(json.loads(export.model3d.PROGRAM_FILE.read_text()),
                                             export.load_overrides(), "presentation", review_path=ROOT / study["baseline_reference"])
        assert baseline == next(b for b in export.plan_data(frozen)["buildings"] if b["id"] == bid)
    assert sum(len(f["rooms"]) for b in main["buildings"] for f in b["floors"]) == 112
    assert sum(len(r["furniture"]) for b in main["buildings"] for f in b["floors"] for r in f["rooms"]) == 127


def test_all_options_are_bounded_clear_and_unapproved(study):
    for o in study["options"]:
        assert set(o["professional_status"]) == export.PROFESSIONAL_KEYS
        assert set(o["professional_status"].values()) == {"unknown"}
        assert len(o["model"]["buildings"]) == 1
        assert o["model"]["layout_review"]["status"] == export.STATUS
        assert o["model"]["compare"] == {"available": False}
        assert "mdf_study" not in o["model"]["layout_review"]
        total = 0
        for f in o["plans"]["floors"]:
            assert (f["width_mm"], f["depth_mm"]) == (6000, 17630)
            assert sum(r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in f["rooms"]) == 6000 * 17630
            for i, r in enumerate(f["rooms"]):
                assert not any(
                    overlaps(export.aabb(r["geometry"]), export.aabb(other["geometry"]))
                    for other in f["rooms"][i + 1 :]
                )
            total += len(f["rooms"])
        assert total == o["model"]["provenance"]["total"]
        frontage = next(r for r in o["plans"]["floors"][0]["rooms"] if r["key"] == "garage")
        assert frontage["outdoor"] and not frontage["furniture"]
        assert frontage["geometry"] == {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}


def test_b_strict_checks_whole_rooms_real_backing_routes_and_full_size_products(study):
    old, new = option(study, "b-baseline"), option(study, "b-strict")
    assert old["geometry_review"]["prohibited_backing"] == ["B:floor-1:stair1"]
    assert old["geometry_review"]["sleep_rooms_above_whole_shrine"] == ["B:floor-3:guest3"]
    review = new["geometry_review"]
    assert review["backing_room_ids"] == ["B:floor-1:altar-backing"]
    assert not review["prohibited_backing"] and not review["stair_or_hall_in_rear_axis"]
    assert not review["sleep_rooms_above_whole_shrine"] and review["street_facing_axial_door"]
    assert review["shrine_assumed_clear_sqm"] == 22.3136
    assert review["public_stair_path"] == ["public-entry", "rear-hall", "stair1"]
    assert review["master_long_side_body_gaps_mm"] == {"front": 661, "rear": 665}
    assert not new["unresolved_furniture"]
    source = cells(study, "b-strict")
    entrances = [c for c in source.values() if c["is_entry"]]
    assert {c["key"] for c in entrances} == {"entry", "public-entry"}
    assert all(any(d["neighbor"] is None for d in c["tour_features"]["doors"]) for c in entrances)
    cores = [c for c in source.values() if c["kind"] == "stair"]
    assert len(cores) == 4 and len({tuple(c["tour_mm"].values()) for c in cores}) == 1
    for c in cores:
        features = c["tour_features"]
        assert features["stair_geometry"]["fits_reserved_box"]
        assert features["stair_geometry"]["flight_width_mm"] == 1000
        assert all(
            d["neighbor"] == features["shared_landing_mm"]["space"]
            for d in features["doors"] + features["open_connections"]
        )
    transport = review["transport"]
    assert transport["assembled_dimensions"] is None and transport["transport_acceptance"] == "unknown"
    assert transport["status"] == "storage-body-sweep-only-not-transport-approval"
    assert transport["bottleneck_assumed_width_mm"] == 1440
    assert [s["room_id"].split(":")[-1] for s in transport["segments"]] == ["garage", "entry", "corridor1", "storage"]


def test_original_brief_shortfalls_are_not_erased_or_summed(study):
    screen = option(study, "b-strict")["geometry_review"]["program_screen"]
    areas = {a["requirement_id"]: a for a in screen["areas"]}
    assert areas["B.floor-1.palanquin"]["assumed_clear_sqm"] == 8.6688 < areas["B.floor-1.palanquin"]["minimum_sqm"]
    assert areas["B.floor-2.master_b"]["nominal_sqm"] == 15.48
    assert areas["B.floor-2.master_b"]["assumed_clear_sqm"] == 14.2416 >= 14
    assert areas["B.floor-2.master_b"]["state"] == "area-only-not-function-approval"
    assert areas["B.floor-2.master_b"]["target_sqm"] == 20
    assert areas["B.floor-2.master_b"]["target_state"] == "below-brief-target"
    assert areas["B.floor-1.bath_acc"]["state"] == "brief-area-shortfall"
    assert screen["unaccommodated_requirement_ids"] == ["B.floor-2.tea", "B.floor-3.ktv", "B.floor-1.balcony_b"]
    assert screen["owner_tradeoffs_accepted"] is screen["legal_area_sqm"] is None
    guest = option(study, "c-wet-stack")["geometry_review"]["program_screen"]["areas"][0]
    assert guest["minimum_sqm"] == 9 and guest["assumed_clear_sqm"] == 8.2208
    assert guest["state"] == "brief-area-shortfall" and guest["legal_area_sqm"] is None


def test_c_small_change_preserves_care_suite_window_and_other_floors(study):
    old, new = rooms(study, "c-baseline"), rooms(study, "c-side-bed")
    for id, r in new.items():
        if id != "C:floor-1:elder":
            if id in {"C:floor-2:bath2f", "C:floor-3:bath3f"}:
                assert r["geometry"] == {"x_mm": 0, "y_mm": 13800, "w_mm": 2400, "h_mm": 2000}
                assert [(i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"]) for i in r["furniture"]] == [
                    (i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"]) for i in old[id]["furniture"]
                ]
                assert all(not i["placement"]["issues"] and i["front_clearance_mm"] == 700 for i in r["furniture"])
                continue
            if id in {"C:floor-2:rear-service", "C:floor-3:rear-service"}:
                assert r["geometry"] == {"x_mm": 0, "y_mm": 15800, "w_mm": 2400, "h_mm": 1830}
                assert r["outdoor"] and not r["furniture"]
                continue
            if id == "C:floor-1:sliding-door":
                assert {k: v for k, v in r.items() if k != "features"} == {
                    k: v for k, v in old[id].items() if k != "features"
                }
                assert not r["features"]["doors"]  # same doorway closes on both adjoining rooms
            else:
                expected = copy.deepcopy(old[id])
                expected["features"].pop("fengshui_review", None)  # different comparison contract, not moved geometry
                if id in {"C:floor-2:guestroom2f", "C:floor-3:fitness3f"}:
                    expected["features"]["hvac_units"] = r["features"][
                        "hvac_units"
                    ]  # paired rear unit / pipe route recomputed
                assert r == expected, id
    elder = new["C:floor-1:elder"]
    assert elder["geometry"] == old[elder["id"]]["geometry"]
    assert elder["features"]["window_mm"] == 2300
    assert len(elder["features"]["doors"]) == 2  # main bedroom entry plus ensuite
    assert {d["neighbor"] for d in elder["features"]["doors"]} == {"C:floor-1:stair1f", "C:floor-1:elder-bath"}
    assert not option(study, "c-side-bed")["unresolved_furniture"]
    review = option(study, "c-side-bed")["geometry_review"]
    assert not review["wet_rooms_over_bed"] and len(review["wet_rooms_over_bedroom"]) == 2
    assert review["wet_room_to_bed_nominal_gap_mm"] == 230
    assert all(a["assumed_clear_sqm"] == 4.1216 and a["minimum_sqm"] == 3.6 for a in review["program_screen"]["areas"])
    assert review["bathroom_turning_and_rescue"] == "unknown" and review["visitor_public_bath"] == "not-provided"
    assert all(
        route["compliance"] == "unknown"
        for route in option(study, "c-side-bed")["model"]["layout_review"]["hvac_routes"]
    )


def test_c_wet_stack_retains_declared_pending_wardrobe_and_area_change(study):
    o = option(study, "c-wet-stack")
    assert not o["geometry_review"]["wet_rooms_over_bedroom"]
    assert [i["item_id"] for i in o["unresolved_furniture"]] == ["C:floor-2:guestroom2f:furniture:wardrobe"]
    old, new = rooms(study, "c-baseline"), rooms(study, "c-wet-stack")
    assert old["C:floor-3:rear-hall"]["outdoor"]
    bath = new["C:floor-3:bath3f"]
    assert not bath["outdoor"] and bath["geometry"]["w_mm"] * bath["geometry"]["h_mm"] == 5280000
    assert any("衣櫃" in t and "衝突" in t for t in o["tradeoffs"])
    assert any("戶外" in t and "5.28" in t for t in o["tradeoffs"])


@pytest.mark.parametrize(
    "bad",
    [
        "adopt",
        "rule",
        "approval",
        "missing-approval",
        "building",
        "resize",
        "drop-bed",
        "missing-share-mode",
        "approved-share-mode",
        "entry-width",
        "entry-face",
        "duplicate-entry",
        "entry-interior",
    ],
)
def test_source_contract_rejects_false_adoption_products_and_entries(bad):
    raw = json.loads(export.SOURCE.read_text())
    b = raw["options"][1]
    if bad == "adopt":
        raw["active_design"] = "b-strict"
    elif bad == "rule":
        raw["confirmed_b_rules"]["no_sleep_above_whole_shrine"] = False
    elif bad == "approval":
        b["professional_status"]["religious_acceptance"] = "verified"
    elif bad == "missing-approval":
        b["professional_status"].pop("religious_acceptance")
    elif bad == "building":
        b["building"] = "A"
    elif bad == "resize":
        raw["profiles"]["study-bc-b-master"][0]["width_mm"] = 800
    elif bad == "drop-bed":
        raw["profiles"]["study-bc-b-master"].pop(0)
    elif bad == "missing-share-mode":
        raw["profiles"]["study-bc-c-side-elder"][0].pop("shared_operation_mode")
    elif bad == "approved-share-mode":
        raw["profiles"]["study-bc-c-side-elder"][0]["shared_operation_mode"] = "simultaneous-approved"
    else:
        floor = b["patch"]["replace_building"]["floors"]["floor-1"]
        entry = floor["additional_entries"][0]
        if bad == "entry-width":
            entry[2] = -1
        elif bad == "entry-face":
            entry[1] = "north"
        elif bad == "duplicate-entry":
            floor["additional_entries"].append(copy.deepcopy(entry))
        elif bad == "entry-interior":
            entry[1:] = ["right", 900, 5500]
    with pytest.raises(ValueError):
        export.build_study(raw=raw)


@pytest.mark.parametrize("bad", ["fake-back", "wet-back", "sleep-room", "rename-bedroom", "bed-product", "tiny-altar"])
def test_actual_geometry_independent_checks_reject_disguised_conflicts(study, bad):
    b = copy.deepcopy(option(study, "b-strict")["model"]["buildings"][0])
    by_id = {c["id"]: c for f in b["floors"] for c in f["cells"]}
    if bad == "fake-back":
        by_id["B:floor-1:altar-backing"]["furniture"] = []
    elif bad == "wet-back":
        by_id["B:floor-1:altar-backing"]["kind"] = "bath"
    elif bad == "sleep-room":
        by_id["B:floor-2:living2"]["kind"] = "bedroom"
    elif bad == "rename-bedroom":
        by_id["B:floor-3:guest3"]["kind"] = "other"
        by_id["B:floor-3:guest3"]["name"] = "乾式閱讀"
    elif bad == "bed-product":
        by_id["B:floor-3:quiet-study"]["furniture"][0]["shape"] = "sofa-bed"
    elif bad == "tiny-altar":
        by_id["B:floor-1:shrine"]["furniture"][0]["width_mm"] = 800
    with pytest.raises(ValueError):
        export.essential_products(b, "b-strict")
        export.review_geometry(b, "b-strict")


def test_sequential_sharing_never_excuses_a_body_rear_or_side_obstruction(study):
    c = cells(study, "c-side-bed")["C:floor-1:elder"]
    item = next(i for i in c["furniture"] if i["shape"] == "bed")
    p = c["furniture_placements"]["tour_mm"][item["id"]]
    for zone_kind in ["care-route", "care-turn"]:
        for field in ["operation_mm", "aabb", "rear_operation_mm", "side_operation_mm"]:
            candidate = copy.deepcopy(p)
            zone = copy.deepcopy(p["operation_mm"])
            if field == "aabb":
                zone = copy.deepcopy(p["aabb"])
            elif field == "rear_operation_mm":
                candidate[field] = zone
            elif field == "side_operation_mm":
                candidate[field] = [{"aabb": zone}]
            features = {
                "reserved_mm": [{"kind": zone_kind, "aabb": zone}],
                "open_connections": [],
                "doors": [],
                "window_face": None,
            }
            issues = _issues(item, candidate, c["tour_mm"], features, [])
            assert (zone_kind in issues) is (field != "operation_mm")
    raw = json.loads(export.SOURCE.read_text())
    profile = raw["profiles"]["study-bc-c-side-elder"]
    profile[0]["note"] = ""
    with pytest.raises(FurnitureLayoutError, match="explicit limitation"):
        export.build_study(raw=raw)


def test_generated_manifest_svg_and_viewer_are_fresh_same_data_and_unadopted(study):
    directory = ROOT / "structured/candidates/bc-options"
    manifest = json.loads(
        (directory / "layout.js").read_text().removeprefix("window.HOUSE_BC_OPTIONS = ").rstrip(";\n")
    )
    expected = {**study, "options": [{k: v for k, v in o.items() if k != "model"} for o in study["options"]]}
    assert manifest == expected
    for path, digest in study["source_hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    for o in study["options"]:
        for f in o["plans"]["floors"]:
            svg = (directory / f["plan_file"]).read_text()
            assert svg == export.render_study_plan(o, f)
            tree = ET.fromstring(svg)
            assert tree.get("data-study-option") == o["id"] and tree.get("data-study-status") == export.STATUS
            groups = {g.get("data-room-id"): g for g in tree.findall("s:g[@data-room-id]", NS)}
            assert set(groups) == {r["id"] for r in f["rooms"]}
            for r in f["rooms"]:
                assert all(
                    float(groups[r["id"]].get(f"data-{k}-mm")) == r["geometry"][k + "_mm"] for k in ["x", "y", "w", "h"]
                )
                for i in r["furniture"]:
                    node = groups[r["id"]].find(f"s:g[@data-furniture-id='{i['id']}']", NS)
                    assert node is not None and float(node.get("data-width-mm")) == i["width_mm"]
                    assert node.get("data-status") == i["placement"]["status"]
    viewer = (ROOT / "structured/candidates/bc-options-3d.html").read_text()
    assert "DATA.bc_options" in viewer and "bc-options.html#" in viewer
    models = {
        "bc_options": {
            "default_option": study["default_option"],
            "options": [
                {"id": o["id"], "label": o["label"], "building": o["building"], "model": o["model"]}
                for o in study["options"]
            ],
        }
    }
    stored = json.JSONDecoder().raw_decode(viewer.split("var DATA = ", 1)[1])[0]
    for fresh, saved in zip(models["bc_options"]["options"], stored["bc_options"]["options"], strict=True):
        assert fresh["id"] == saved["id"]
        fresh["model"]["generated_at"] = saved["model"]["generated_at"]  # only volatile export timestamp differs
    expected_viewer = export.model3d.render_html(
        models,
        export.model3d.three_source()[0],
        study_controls=(ROOT / "scripts/templates/bc-options-controls.html").read_text(),
        study_bootstrap=(ROOT / "scripts/templates/bc-options-bootstrap.js").read_text(),
    )
    assert hashlib.sha256(viewer.encode()).hexdigest() == hashlib.sha256(expected_viewer.encode()).hexdigest()
    assert 'src="bc-options/layout.js"' in (ROOT / "structured/candidates/bc-options.html").read_text()


def test_comparison_display_controls_are_scoped_and_keep_full_tradeoffs():
    # Markup/CSS source contracts only; actual viewport placement is Windows QA.
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text()
    document = BeautifulSoup(controls, "html.parser")
    card = document.select_one("#bc-study-controls")
    assert card and "未採用" in card["aria-label"]
    assert "未採用／未核" in card.select_one(".bc-study-warning").text
    assert card.select_one('label[for="study-scheme"] select#study-scheme')
    assert card.select_one('a#study-plan-link[href="bc-options.html"]')
    assert card.select_one('a[href="model3d.html"]')
    assert card.select_one("details summary").text == "本案取捨與未解需求"
    assert card.select_one("details #bc-study-tradeoffs") is not None
    css = document.style.text
    badge_rule = css.split("body.bc-study #study-stage-note{", 1)[1].split("}", 1)[0]
    for declaration in ["position:absolute", "z-index:4", "max-width:calc(100% - 28px)", "overflow-wrap:anywhere"]:
        assert declaration in badge_rule
    for selector in [
        "#tour-actions",
        "#furniture-start",
        "#presentation-mode",
        "#geom-source",
        "#facade-actions",
        "#compare",
        "label:has(#mdf-study)",
        "label:has(#frontage-study)",
        "label:has(#ghost)",
        "h2:has(+label #ghost)",
    ]:
        assert "body.bc-study " + selector in css
    assert not re.search(r":has\([^)]*:has\(", css), "CSS forbids nested :has(); it invalidates the entire hide rule"
    assert "min-height:44px" in css and "focus-visible" in css
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text()
    assert 'classList.add("bc-study")' in bootstrap
    assert 'studyBadge.setAttribute("role","status")' in bootstrap
    assert 'studyBadge.setAttribute("aria-live","polite")' in bootstrap
    main = (ROOT / "structured/candidates/model3d.html").read_text()
    headings = BeautifulSoup(main, "html.parser").select("h2:has(+label #ghost)")
    assert len(headings) == 1 and headings[0].text == "與舊版參數化情境對照"
    assert 'id="bc-study-controls"' not in main and "body.bc-study #study-stage-note" not in main
