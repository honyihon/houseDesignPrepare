"""Small frozen-data calculations; no scene generation or browser runtime."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_balcony_coordination as export
import pytest

from house_design.c_balcony_coordination import (
    CONFIG,
    _arcade_low_segments,
    _union_area,
    analyze,
    build,
    compare_sections,
)
from house_design.contracts import ContractError

ROOT = Path(__file__).resolve().parents[1]
SVG_DEFAULT_NAMESPACE = True


@pytest.fixture(scope="module")
def source():
    cfg = json.loads((ROOT/CONFIG).read_text())
    report = json.loads((ROOT/cfg["base_report"]).read_text())
    option = next(o for o in report["options"] if o["id"] == "c-split")
    return cfg, option["states"][0]["plans"]


def test_union_area_never_double_counts_a_cover_projection():
    assert _union_area([[0, 0, 2000, 2000], [1000, 0, 2000, 2000], [0, 0, 0, 9000]]) == 6
    assert _union_area([[0, 0, 1000, 1000], [2000, 2000, 1000, 1000]]) == 2
    assert _union_area([]) == 0


def test_cover_projection_still_cannot_approve_solid_cover_or_soil(source):
    cfg, plans = source
    original = copy.deepcopy(plans)
    result = analyze(plans, cfg)
    assert plans == original
    assert result["upper_projection"]["union_projected_sqm"] == 9
    assert result["upper_projection"]["actual_solid_cover_slab_and_legal_eligibility"] == "unknown"
    assert result["under_soil"]["overlap_sqm"] == pytest.approx(3.393)
    assert result["connected_living_room"]["nominal_sqm"] == pytest.approx(16.192)
    assert result["coordinate_margins_mm"] == {
        "sink_operation_to_garden": 135,
        "rack_operation_width": 900,
        "soil_rear_to_indoor_wall": 1235,
    }
    assert result["soil_depth_selected_mm"] is None
    assert result["professional_approval"] == "unknown"
    assert result["full_scheme_adopted"] is False


def test_low_arcade_span_is_detected_without_turning_it_into_a_legal_verdict(source):
    cfg, plans = source
    hvac = {u["id"]: u for u in analyze(plans, cfg)["hvac"]}
    ac01 = hvac["C-AC01"]
    assert ac01["estimated_routed_length_mm"] == 15335
    assert ac01["coordinate_lower_bound_with_same_allowance_mm"] == 11085
    assert ac01["excess_above_coordinate_lower_bound_mm"] == 4250
    assert ac01["low_arcade_proxy_segments"][0]["overlap_length_mm"] == 3900
    assert ac01["low_arcade_proxy_segments"][0]["centreline_z_mm"] == 2350
    assert not hvac["C-AC03"]["low_arcade_proxy_segments"]
    assert not hvac["C-AC07"]["low_arcade_proxy_segments"]
    assert all(u["fan_discharge_direction"] == "unknown" for u in hvac.values())
    assert all(u["model"] is None for u in hvac.values())


def test_horizontal_arcade_warning_has_positive_overlap_and_respects_height():
    arcade = [0, 0, 6000, 3900]
    assert not _arcade_low_segments([[5850, 3900, 2350], [5850, 8230, 2350]], arcade)
    assert not _arcade_low_segments([[5850, 0, 3500], [5850, 3900, 3500]], arcade)
    assert not _arcade_low_segments([[5850, 500, 2350], [5850, 500, 5950]], arcade)


def test_soil_section_and_water_calculations_remain_sensitivities(source):
    cfg, plans = source
    result = analyze(plans, cfg)
    soil = result["soil_load_sensitivity"]["cases"][0]
    assert soil["volume_m3"] == pytest.approx(1.0179)
    assert soil["soil_only_load_kN"] == pytest.approx(18.3222)
    assert soil["soil_only_mass_tonnes"] == pytest.approx(1.868344)
    assert result["ponding_sensitivity"]["over_garden_only_mass_tonnes"] == pytest.approx(.27)
    assert result["drain_fall_sensitivity"][1] == {
        "slope_percent": 1.5,
        "over_balcony_depth_mm": 58.5,
        "over_service_depth_mm": 24.75,
        "over_garden_depth_mm": 33.75,
    }
    section = result["section_sensitivity"]["cases"]
    assert section[0]["slab_underside_upper_bound_mm"] == 3150
    assert section[0]["remaining_for_other_layers_mm"] == -350
    assert section[3]["remaining_for_other_layers_mm"] == 50
    assert section[4]["remaining_for_other_layers_mm"] == -100
    assert result["actual_drain_outlets_and_diameters"] is None


def test_frozen_dependency_hash_change_is_rejected(monkeypatch):
    import house_design.c_balcony_coordination as coordination

    real = coordination.sha256_file
    monkeypatch.setattr(coordination, "sha256_file", lambda p:
        "0"*64 if p.name == "requirements.json" else real(p))
    with pytest.raises(ContractError, match="Frozen dependency changed"):
        build(ROOT)


def test_inconsistent_stored_route_length_is_rejected(source):
    cfg, plans = source
    changed = copy.deepcopy(plans)
    balcony = next(r for r in changed["floors"][1]["rooms"] if r["key"] == "balcony2f")
    balcony["features"]["hvac_units"][0]["route"]["estimated_routed_length_mm"] += 100
    with pytest.raises(ContractError, match="Stored HVAC length is inconsistent"):
        analyze(changed, cfg)


def test_standalone_outputs_are_fresh_and_keep_unknowns_visible():
    files = export.artifacts(ROOT)
    assert len(files) == 3
    assert all(name.startswith(export.OUT+"/") for name in files)
    for name, content in files.items():
        assert (ROOT/name).read_text() == content
    drawing = ET.fromstring(files[export.OUT+"/plan-section.svg"])
    assert drawing.get("viewBox") == "0 0 1200 1220"
    text = "".join(drawing.itertext())
    assert "非施工圖" in text and "D 未定" in text
    assert "2350高跨前騎樓" in text and "11.085m僅幾何下界" in text
    assert "不得完工後切板" in text
    options_drawing = ET.fromstring(files[export.OUT+"/section-options.svg"])
    assert int(options_drawing.get("width"))*int(options_drawing.get("height")) <= 1600000
    options_text = "".join(options_drawing.itertext())
    assert "最少加130；保留原140總預留則加270mm" in options_text
    assert "踏面減20" in options_text and "四案皆未選定" in options_text


def test_24_risers_never_hide_the_original_140mm_spare(source):
    cfg, plans = source
    options = {o["id"]: o for o in compare_sections(plans, cfg)["options"]}
    generous = options["c40-24-270"]
    assert generous["required_flight_and_landing_depth_mm"] == 4970
    assert generous["minimum_extension_using_all_existing_spare_mm"] == 130
    assert generous["extension_retaining_existing_spare_mm"] == 270
    assert generous["retained_front_and_rear_budget_mm"] == [70, 70]
    third = next(f for f in generous["front_extension_with_existing_spare"]["floors"] if f["floor"] == "floor-3")
    assert third["union_overlap_sqm"] == pytest.approx(.972)
    assert third["affected"][0]["nominal_remaining_depth_mm"] == 1090
    first = generous["front_extension_with_existing_spare"]["floors"][0]
    assert {r["room"].rsplit(":", 1)[-1] for r in first["affected"]} == {"living-hall", "living-right"}
    rear = generous["rear_extension_with_existing_spare"]["floors"][0]
    assert {r["room"].rsplit(":", 1)[-1] for r in rear["affected"]} == {"elder", "elder-bath"}


def test_compact_option_records_tread_and_spare_loss_without_approval(source):
    cfg, plans = source
    result = compare_sections(plans, cfg)
    compact = next(o for o in result["options"] if o["id"] == "c40-24-250")
    assert compact["required_flight_and_landing_depth_mm"] == 4750
    assert compact["remaining_in_existing_box_mm"] == 90
    assert compact["minimum_extension_using_all_existing_spare_mm"] == 0
    assert compact["extension_retaining_existing_spare_mm"] == 50
    assert compact["tread_change_vs_existing_mm"] == -20
    assert result["all_options_unselected"] is True
    assert all(o["construction_approval"] == "unknown" and o["selected"] is False for o in result["options"])


def test_all_upper_bases_shift_but_stair_arrivals_stay_unknown(source):
    cfg, plans = source
    for option in compare_sections(plans, cfg)["options"]:
        if option["first_storey_mm"] == 4000:
            assert option["floor_bases_mm"] == {"floor-1": 0, "floor-2": 4000, "floor-3": 7000, "floor-4": 10000}
            assert option["front_and_rear_gross_added_elevation_sqm"] == pytest.approx(4.8)
            assert option["soil_cases_with_other_layer_assumption"][0]["margin_to_conservative_target_mm"] == 0
        assert option["all_upper_stair_arrivals"] == "must-recheck-not-automatically-aligned-by-base-shift"


def test_odd_riser_count_cannot_sneak_into_two_equal_flights(source):
    cfg, plans = source
    bad = copy.deepcopy(cfg)
    bad["section_comparison"]["options"][1]["risers"] = 23
    with pytest.raises(ContractError, match="positive even riser counts"):
        compare_sections(plans, bad)
