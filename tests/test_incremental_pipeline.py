from __future__ import annotations

from pathlib import Path

from house_design.pipeline import Step, _effective_outputs, _fingerprint, _outputs_exist, build_steps
from house_design.rendering import encode_html_json, stable_svg_filename


def test_rendering_boundary_preserves_filename_contract() -> None:
    assert stable_svg_filename("A", "floor-1") == "a_floor-1.svg"
    assert stable_svg_filename("", "") == "unknown_unknown.svg"


def test_html_payload_escapes_script_closing_tag() -> None:
    encoded = encode_html_json({"value": "</script>"})

    assert "</script>" not in encoded
    assert "<\\/script>" in encoded


def test_step_fingerprint_changes_with_input(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    source.write_text("before", encoding="utf-8")
    step = Step("example", ("tool.py",), (source,), (output,))
    before = _fingerprint(step)
    source.write_text("after", encoding="utf-8")

    assert _fingerprint(step) != before
    assert _outputs_exist(step.outputs) is False
    output.write_text("done", encoding="utf-8")
    assert _outputs_exist(step.outputs) is True


def test_pipeline_exposes_ifc_validation_and_concept_skips_pdf() -> None:
    concept = build_steps("best", "presentation", "a3", "bundle.pdf", "concept")
    ifc = build_steps("baseline", "technical", "a4", "bundle.pdf", "ifc")

    assert [step.name for step in concept][-1] == "svg"
    assert [step.name for step in ifc][-2:] == ["pdf", "validate"]
    assert "--strict" in ifc[-1].command


def test_release_mode_is_the_named_alias_for_the_old_ifc_gate() -> None:
    release = build_steps("baseline", "technical", "a4", "bundle.pdf", "release")

    assert [step.name for step in release][-2:] == ["pdf", "validate"]


def test_svg_effective_outputs_include_manifest_exports(tmp_path: Path, monkeypatch) -> None:
    import house_design.pipeline as pipeline

    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    manifest = tmp_path / "structured/candidates/svg/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"exports": [{"file": "a.svg"}]}', encoding="utf-8")
    step = Step("svg", ("export.py",), (), (manifest, manifest.parent / "index.html"))

    assert manifest.parent / "a.svg" in _effective_outputs(step)


def test_concept_step_range_does_not_offer_ifc_only_validation() -> None:
    names = [step.name for step in build_steps("best", "presentation", "a3", "bundle.pdf", "concept")]

    assert "pdf" not in names
    assert "validate" not in names


def test_legacy_render_steps_track_authority_warning_sources() -> None:
    steps = {step.name: step for step in build_steps("baseline", "presentation", "a3", "bundle.pdf", "concept")}

    standards = Path("scripts/lib/standards.py")
    compare = Path("scripts/lib/html_parametric_compare.py")
    program = Path("structured/room_program.json")
    furniture = Path("inputs/furniture-layout.json")
    dimensions = Path("inputs/dimensions.json")
    physical_items = Path("inputs/physical-items.json")
    furniture_loader = Path("scripts/lib/furniture_layout.py")
    physical_items_loader = Path("house_design/physical_items.py")
    model3d_template = Path("scripts/templates/model3d.html")
    walkthrough_template = Path("scripts/templates/walkthrough.html")
    assert any(path.as_posix().endswith(standards.as_posix()) for path in steps["parametric"].inputs)
    assert any(path.as_posix().endswith(dimensions.as_posix()) for path in steps["parametric"].inputs)
    assert any(path.as_posix().endswith(standards.as_posix()) for path in steps["walkthrough"].inputs)
    assert any(path.as_posix().endswith(compare.as_posix()) for path in steps["walkthrough"].inputs)
    assert any(path.as_posix().endswith(program.as_posix()) for path in steps["walkthrough"].inputs)
    assert any(path.as_posix().endswith(compare.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(furniture.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(physical_items.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(furniture_loader.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(physical_items_loader.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(model3d_template.as_posix()) for path in steps["model3d"].inputs)
    assert any(path.as_posix().endswith(walkthrough_template.as_posix()) for path in steps["walkthrough"].inputs)


def test_model3d_step_tracks_the_entire_shared_html_furniture_bundle() -> None:
    step = next(
        s for s in build_steps("baseline", "presentation", "a3", "bundle.pdf", "concept") if s.name == "model3d"
    )
    for module in ("model3d_tour", "model3d_placement", "model3d_plan", "model3d_review", "model3d_facade"):
        assert any(p.as_posix().endswith(f"scripts/lib/{module}.py") for p in step.inputs)
    assert any(p.as_posix().endswith("inputs/concept-layout-review.json") for p in step.inputs)
    assert len(step.outputs) == 17  # viewer, shared data, 12 plans, 3 facade elevations
    for source in ("inputs/facade-concept.json", "scripts/templates/model3d_facade.js", "assets/references/facade-photo-v1.jpg"):
        assert any(p.as_posix().endswith(source) for p in step.inputs)
    assert any(p.as_posix().endswith("furniture-plans/layout.js") for p in step.outputs)
    for building in "ABC":
        assert any(p.as_posix().endswith(f"furniture-plans/{building}_facade-front.svg") for p in step.outputs)
        for floor in range(1, 5):
            assert any(p.as_posix().endswith(f"furniture-plans/{building}_floor-{floor}.svg") for p in step.outputs)
