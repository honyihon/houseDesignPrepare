from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

import house_design.abc_fresh_air_planning as planning
import scripts.export_abc_fresh_air_planning as exporter
from house_design.abc_fresh_air_planning import (
    CONFIG,
    CSV_FIELDS,
    OUT,
    box_comparison,
    build,
    context,
    evaluate,
    input_template,
    load_input,
    normalize,
    parse_json,
    sections,
)
from house_design.contracts import ContractError, read_json, sha256_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def base():
    return context(ROOT)


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def empty(base):
    cfg, parent, fields = base
    return input_template(parent, fields, cfg["input_schema"])


def fill(document, base, key, value):
    record = document["values"][key]
    record.update(value=value, source="SYNTHETIC-TEST-DATA-NOT-SURVEY", date="2026-11-06")
    field = base[2][key]
    if model := field.get("candidate_model_field"):
        record["model_ref"] = document["values"][model]["value"]


def comparison(base, document):
    cfg, parent, fields = base
    records = normalize(document, parent, fields, cfg)
    checks, alternatives, impact = evaluate(parent, cfg, fields, records)
    return {c["id"]: c for c in checks}, alternatives, impact


def filled_zone(base):
    doc = empty(base)
    entries = {"common.duct.inner_mm": 125, "common.duct.insulation_each_mm": 25,
        "common.duct.gap_mm": 50, "common.duct.edge_mm": 50, "common.duct.extra_hanging_mm": 50,
        "C2.model": "SYNTHETIC-NOT-REAL-UNIT:REV1", "C2.installed_box_mm": [1500, 950, 450],
        "C2.available_box_mm": [1600, 1000, 500], "C2.beam_bottom_z_mm": 2800,
        "C2.ceiling_target_z_mm": 2200, "C2.duct_available_wh_mm": [500, 500],
        "C2.pull_required_mm": 600, "C2.pull_available_mm": 650,
        "C2.removal_required_wh_mm": [1330, 737], "C2.removal_available_wh_mm": [1550, 950],
        "C2.design_flow_m3_h": 30, "C2.fan_min_flow_m3_h": 20, "C2.fan_max_flow_m3_h": 70,
        "C2.required_pressure_pa": 70, "C2.curve_flow_m3_h": 30, "C2.curve_available_pressure_pa": 90}
    for key, value in entries.items():
        fill(doc, base, key, value)
    return doc


def fill_external(doc, base, group, permission):
    fill(doc, base, group+".opening_permitted", permission)
    for role in ["OA", "EA"]:
        fill(doc, base, group+"."+role+".solid_z_interval_mm", [2300, 2800])
        fill(doc, base, group+"."+role+".required_opening_height_mm", 300)


def test_empty_planning_stays_pending_without_fabricating_real_conditions(report):
    assert report["conditions_total"] == 184 and report["conditions_received"] == 0
    assert report["summary"] == {"pending": 101}
    assert all(v["value"] is None for v in report["input_records"].values())
    assert report["adopted"] is report["actual_integration_performed"] is report["primary_or_3d_written"] is False
    assert report["selected_product"] is None and report["professional_approval"] == "unknown"
    assert not report["planning_assumptions_only"]["actual_installed"]
    assert all(c["next_comparison"] == "retain-both-await-conditions" for c in report["comparison_choices"])


def test_all_frozen_sources_and_control_hashes_current(report):
    assert report["protected_controls_unchanged"] == 149
    assert [v["id"] for v in report["retained_b_entries"]] == ["b-rear-split", "b-front-split"]
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest
    assert any("單台洗衣機留2F" in v for v in report["fixed_requirements"])


def test_parent_pin_and_scope_cannot_be_bypassed(monkeypatch):
    cfg = copy.deepcopy(read_json(ROOT/CONFIG))
    original = planning.read_json
    monkeypatch.setattr(planning, "read_json", lambda path: cfg if Path(path) == ROOT/CONFIG else original(path))
    cfg["parent_file_sha256"] = "0"*64
    with pytest.raises(ContractError, match="parent file changed"):
        context(ROOT)
    cfg["automatic_primary_3d_write"] = True
    with pytest.raises(ContractError, match="cannot adopt"):
        context(ROOT)


def test_partial_data_only_updates_dependent_comparisons(base):
    doc = empty(base)
    fill(doc, base, "C2.beam_bottom_z_mm", 2800)
    checks, _, impacts = comparison(base, doc)
    assert checks["C2:ceiling"]["status"] == "pending"
    assert "C2.beam_bottom_z_mm" not in checks["C2:ceiling"]["missing"]
    assert all(v["status"] == "pending" for v in checks.values())
    changed = next(v for v in impacts if v["id"] == "C2.beam_bottom_z_mm")
    assert changed["value_received"] and changed["affected_checks"] == ["C2:ceiling"]


@pytest.mark.parametrize("key,value", [("C2.beam_bottom_z_mm", -1), ("C2.beam_bottom_z_mm", True),
    ("C2.available_box_mm", [1600, 0, 500]), ("C2.available_box_mm", [1600, 1000]),
    ("C2.fan_min_flow_m3_h", float("nan")), ("C2.curve_available_pressure_pa", float("inf")),
    ("B.rear_alley_exists", 1), ("B.rear_alley_exists", "false"),
    ("B2-front.OA.solid_z_interval_mm", [2800, 2300]), ("C2.model", "")])
def test_invalid_types_and_units_not_coerced(base, key, value):
    doc = empty(base)
    fill(doc, base, key, value)
    with pytest.raises(ContractError, match="Invalid condition"):
        comparison(base, doc)


@pytest.mark.parametrize("mutation", ["source", "date", "unit", "unknown-id", "root", "baseline", "registry"])
def test_invalid_metadata_and_stale_inputs_rejected(base, mutation):
    doc = empty(base)
    fill(doc, base, "C2.beam_bottom_z_mm", 2800)
    if mutation == "source":
        doc["values"]["C2.beam_bottom_z_mm"]["source"] = ""
    elif mutation == "date":
        doc["values"]["C2.beam_bottom_z_mm"]["date"] = "2026/11/06"
    elif mutation == "unit":
        doc["values"]["C2.beam_bottom_z_mm"]["unit"] = "cm"
    elif mutation == "unknown-id":
        doc["values"]["primary.adopted"] = {"value": True}
    elif mutation == "root":
        doc["adopted"] = True
    elif mutation == "baseline":
        doc["baseline_report_hash"] = "0"*64
    else:
        doc["registry_hash"] = "0"*64
    with pytest.raises(ContractError):
        comparison(base, doc)


def test_model_revision_binding_prevents_mixing_old_product_numbers(base):
    doc = filled_zone(base)
    doc["values"]["C2.model"]["value"] = "SYNTHETIC-DIFFERENT-REVISION"
    with pytest.raises(ContractError, match="same candidate model/revision"):
        comparison(base, doc)


def test_product_data_requires_a_model_even_if_other_fields_missing(base):
    doc = empty(base)
    fill(doc, base, "C2.installed_box_mm", [1600, 1000, 450])
    with pytest.raises(ContractError, match="same candidate model/revision"):
        comparison(base, doc)


def test_zero_and_false_are_received_conditions_not_missing_values(base):
    doc = filled_zone(base)
    fill(doc, base, "C2.fan_min_flow_m3_h", 0)
    fill(doc, base, "B.rear_alley_exists", False)
    checks, choices, _ = comparison(base, doc)
    assert checks["C2:flow"]["status"] == "numeric-fit"
    assert checks["B:rear-alley"]["suggested_comparison"] == "front-entry-fallback-priority"
    assert not checks["B:rear-alley"]["transport_or_opening_approval"]
    assert all(v["next_comparison"] == "retain-both-await-conditions" for v in choices)


def test_box_rotation_does_not_flip_unit_or_approve_whole_transport():
    assert box_comparison([1500, 900, 400], [1000, 1600, 450])["status"] == "numeric-fit"
    assert box_comparison([1500, 900, 400], [1600, 1000, 350])["status"] == "conflict"


def test_synthetic_conditions_recalculate_only_the_requested_zone(base):
    doc = filled_zone(base)
    checks, _, _ = comparison(base, doc)
    assert checks["C2:machine"]["status"] == "numeric-fit"
    assert checks["C2:ducts"]["eligible"] == ["four-stacked"]
    assert checks["C2:ceiling"]["margin_mm"] == 50
    assert checks["C2:pressure"]["margin_pa"] == 20
    assert checks["C2:removal"]["margin_mm"] == [220, 213]
    assert all(c["status"] == "pending" for key, c in checks.items() if key.startswith("A"))
    assert all(c["status"] == "pending" for key, c in checks.items() if key.startswith("manual:"))
    assert all(c["professional_approval"] == "unknown" for c in checks.values())


def test_narrow_four_ducts_and_too_low_ceiling_conflicts_do_not_shrink_design(base):
    doc = filled_zone(base)
    assert sections([125, 25, 50, 50]) == {"four-flat": [950, 275], "four-stacked": [500, 500]}
    fill(doc, base, "C2.duct_available_wh_mm", [500, 300])
    checks, _, _ = comparison(base, doc)
    assert checks["C2:ducts"]["status"] == checks["C2:ceiling"]["status"] == "conflict"
    fill(doc, base, "C2.duct_available_wh_mm", [500, 500])
    fill(doc, base, "C2.ceiling_target_z_mm", 2300)
    checks, _, _ = comparison(base, doc)
    assert checks["C2:ceiling"]["status"] == "conflict" and checks["C2:ceiling"]["margin_mm"] == -50
    assert doc["values"]["C2.ceiling_target_z_mm"]["value"] == 2300


def test_mismatched_curve_flow_is_pending_not_a_false_pressure_pass(base):
    doc = filled_zone(base)
    fill(doc, base, "C2.curve_flow_m3_h", 150)
    checks, _, _ = comparison(base, doc)
    assert checks["C2:pressure"]["status"] == "pending" and not checks["C2:pressure"]["missing"]
    assert "不同" in checks["C2:pressure"]["reason"]


def test_contradictory_fan_range_is_conflict(base):
    doc = filled_zone(base)
    fill(doc, base, "C2.fan_min_flow_m3_h", 100)
    checks, _, _ = comparison(base, doc)
    assert checks["C2:flow"]["status"] == "conflict" and checks["C2:flow"]["data_contradiction"]


def test_b_no_alley_and_opening_permission_are_independent_and_per_floor(base):
    doc = empty(base)
    fill(doc, base, "B.rear_alley_exists", False)
    fill_external(doc, base, "B2-rear", True)
    checks, choices, _ = comparison(base, doc)
    assert choices[0]["next_comparison"] == "compare-rear-default-first"
    assert choices[1]["next_comparison"] == "retain-both-await-conditions"
    assert checks["B:rear-alley"]["suggested_comparison"] == "front-entry-fallback-priority"
    assert checks["B3-rear:wall"]["status"] == "pending"


def test_b_front_fallback_needs_all_conditions_not_just_false_rear(base):
    doc = empty(base)
    fill(doc, base, "B2-rear.opening_permitted", False)
    _, choices, _ = comparison(base, doc)
    assert choices[0]["next_comparison"] == "retain-both-await-conditions"
    fill_external(doc, base, "B2-front", True)
    checks, choices, _ = comparison(base, doc)
    assert choices[0]["next_comparison"] == "compare-front-fallback-first"
    assert checks["B2-front:OA"]["center_z_range_mm"] == [2450, 2650]
    assert not checks["B2-front:OA"]["actual_hole_z_selected"]
    fill(doc, base, "B2-front.opening_permitted", False)
    _, choices, _ = comparison(base, doc)
    assert choices[0]["next_comparison"] == "reroute-required-no-party-wall-assumption"
    assert choices[0]["rear_and_front_retained"] and choices[0]["entry_layout_selected"] is None


def test_impact_map_uses_exact_network_and_outlet_group_not_all_floors(base):
    _, _, impacts = comparison(base, empty(base))
    mapping = {v["id"]: v for v in impacts}
    assert mapping["B2-rear.opening_permitted"]["affected_checks"] == ["B2-rear:wall"]
    assert mapping["B2-front.OA.solid_z_interval_mm"]["affected_checks"] == ["B2-front:OA"]
    assert all(c.startswith("C2:") for c in mapping["C2.installed_box_mm"]["affected_checks"])


@pytest.mark.parametrize("text", ['{"values":{},"values":{}}', '{"value":NaN}', '{"value":Infinity}'])
def test_duplicate_or_nonfinite_json_is_not_silently_loaded(text):
    with pytest.raises(ContractError):
        parse_json(text)


def test_json_and_csv_templates_roundtrip_and_bound_versions(tmp_path, base, report):
    cfg, parent, fields = base
    files = exporter.render(report, cfg["input_schema"])
    for suffix in ["json", "csv"]:
        path = tmp_path/("conditions."+suffix)
        path.write_text(files["conditions-template."+suffix], encoding="utf-8")
        doc, digest = load_input(path, fields, cfg)
        assert digest == sha256_file(path)
        records = normalize(doc, parent, fields, cfg)
        assert len(records) == 184 and all(v["value"] is None for v in records.values())


def test_csv_partial_values_and_duplicate_rows(tmp_path, base, report):
    cfg, parent, fields = base
    stream = io.StringIO(exporter.template_csv(report))
    rows = list(csv.DictReader(stream))
    row = next(v for v in rows if v["id"] == "B.rear_alley_exists")
    row.update(value="false", source="SYNTHETIC TEST", date="2026-11-06")
    path = tmp_path/"partial.csv"
    def save(rows):
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    save([row])
    doc, _ = load_input(path, fields, cfg)
    assert normalize(doc, parent, fields, cfg)["B.rear_alley_exists"]["value"] is False
    save([row, row])
    with pytest.raises(ContractError, match="duplicate CSV"):
        load_input(path, fields, cfg)


def test_private_output_rejects_broad_paths_sources_existing_and_symlink_escape(tmp_path):
    for path in [".", "inputs/private", "Docs/new", "structured/candidates/new", "inputs/private/../../../escape"]:
        with pytest.raises(ContractError):
            exporter.private_target(tmp_path, path)
    private = tmp_path/"inputs/private"
    private.mkdir(parents=True)
    saved = private/"existing.json"
    saved.write_text("OWNER-DATA", encoding="utf-8")
    with pytest.raises(ContractError, match="overwrite"):
        exporter.private_target(tmp_path, str(saved))
    (private/"escape").symlink_to(tmp_path/"Docs", target_is_directory=True)
    with pytest.raises(ContractError):
        exporter.private_target(tmp_path, "inputs/private/escape/new")
    assert saved.read_text() == "OWNER-DATA"


def test_private_root_itself_cannot_be_aliased_to_source_directory(tmp_path):
    (tmp_path/"Docs").mkdir()
    (tmp_path/"inputs").mkdir()
    (tmp_path/"inputs/private").symlink_to(tmp_path/"Docs", target_is_directory=True)
    with pytest.raises(ContractError):
        exporter.private_target(tmp_path, "inputs/private/new-result")


def test_cli_summary_does_not_write_primary_or_publish_actual_data(tmp_path, monkeypatch, capsys, base, report):
    cfg, parent, fields = base
    path = tmp_path/"conditions.json"
    doc = empty(base)
    fill(doc, base, "B.rear_alley_exists", False)
    path.write_text(json.dumps(doc), encoding="utf-8")
    fake = copy.deepcopy(report)
    fake.update(conditions_received=1)
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    monkeypatch.setattr(exporter, "context", lambda root: (cfg, parent, fields))
    monkeypatch.setattr(exporter, "build", lambda *args: fake)
    assert exporter.main(["--inputs", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["output_written"] is None and not output["primary_or_3d_written"]
    assert list(tmp_path.iterdir()) == [path]


def test_cli_explicit_new_private_output_and_init_refuse_overwrite(tmp_path, monkeypatch, capsys, base, report):
    cfg, parent, fields = base
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    monkeypatch.setattr(exporter, "context", lambda root: (cfg, parent, fields))
    monkeypatch.setattr(exporter, "build", lambda *args: report)
    name = "inputs/private/conditions.json"
    assert exporter.main(["--init-input", name]) == 0
    first = (tmp_path/name).read_bytes()
    assert exporter.main(["--init-input", name]) == 1
    assert (tmp_path/name).read_bytes() == first
    out = "inputs/private/run01"
    assert exporter.main(["--inputs", name, "--out", out]) == 0
    assert (tmp_path/out/"artifact-manifest.json").is_file()
    assert exporter.main(["--inputs", name, "--out", out]) == 1
    assert "Refusing" in capsys.readouterr().err


def test_cannot_write_actual_inputs_into_default_frozen_report(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as error:
        exporter.main(["--check", "--inputs", "whatever.json"])
    assert error.value.code == 2
    with pytest.raises(ContractError):
        exporter.write_new_result(tmp_path, OUT, {"review.json": "{}"})


def test_output_artifacts_links_hashes_and_no_script_execution(report, base):
    files = exporter.render(report, base[0]["input_schema"])
    assert len(files) == 9
    manifest = json.loads(files["artifact-manifest.json"])
    assert manifest["report_hash"] == report["report_hash"]
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest
        assert (ROOT/OUT/name).read_bytes() == files[name].encode()
    text = files["index.html"]
    assert "收到 0／184" in text and "未整合施工資料" in text
    assert "<script" not in text and "三維" in text
    for link in re.findall(r'href="([^"]+)"', text):
        if not link.startswith("#"):
            assert (ROOT/OUT/link).is_file()
    assert len(list(csv.DictReader(io.StringIO(files["conditions-template.csv"])))) == 184


def test_input_html_is_escaped_not_executable(base):
    doc = empty(base)
    fill(doc, base, "C2.model", '<img src=x onerror="alert(1)">')
    report = build(ROOT, doc)
    text = exporter.index_html(report)
    assert '<img src=x onerror="alert(1)">' not in text
    assert "&lt;img" in text
