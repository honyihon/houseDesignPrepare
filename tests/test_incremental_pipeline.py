from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import house_design.pipeline as pipeline
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


def test_model3d_inputs_cover_transitive_local_python_imports_without_importing_renderers() -> None:
    root = Path(__file__).resolve().parents[1]
    pending = [root / "scripts/export_model_3d.py"]
    visited: set[Path] = set()

    def resolve(module: str) -> Path | None:
        for base in (root / "scripts", root):
            stem = base.joinpath(*module.split("."))
            for path in (stem.with_suffix(".py"), stem / "__init__.py"):
                if path.is_file():
                    return path
        return None

    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        modules = []
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules.extend([node.module, *(node.module + "." + alias.name for alias in node.names)])
        for module in modules:
            path = resolve(module)
            if path:
                pending.append(path)
            parts = module.split(".")
            for index in range(1, len(parts)):
                package = resolve(".".join(parts[:index]))
                if package and package.name == "__init__.py":
                    pending.append(package)

    step = next(s for s in build_steps("baseline", "presentation", "a3", "bundle.pdf", "concept")
                if s.name == "model3d")
    assert visited <= set(step.inputs), sorted(str(p.relative_to(root)) for p in visited - set(step.inputs))


def test_model3d_tracks_data_dependencies_and_runs_after_its_parametric_input() -> None:
    steps = build_steps("baseline", "presentation", "a3", "bundle.pdf", "concept")
    step = next(s for s in steps if s.name == "model3d")
    for relative in (
        "inputs/a-mdf-under-stair.json",
        "inputs/references/abc-before-space-efficiency-20261014.json",
        "inputs/references/abc-before-a-storage-20261014.json",
        "structured/parametric/plan.json",
    ):
        assert pipeline.ROOT / relative in step.inputs
    names = [s.name for s in steps]
    assert names.index("parametric") < names.index("model3d")


@pytest.mark.parametrize("relative", [
    "scripts/lib/model3d_openings.py", "scripts/lib/model3d_bc_flow.py",
    "scripts/lib/model3d_fengshui.py", "scripts/lib/model3d_mdf.py",
    "scripts/lib/model3d_space_efficiency.py", "scripts/lib/dimension_overrides.py",
    "house_design/rendering/html_payload.py", "inputs/a-mdf-under-stair.json",
    "inputs/references/abc-before-a-storage-20261014.json", "structured/parametric/plan.json",
])
def test_model3d_fingerprint_changes_for_its_previously_missing_dependency(relative, monkeypatch) -> None:
    step = next(s for s in build_steps("baseline", "presentation", "a3", "bundle.pdf", "concept")
                if s.name == "model3d")
    original = Path.read_bytes
    before = _fingerprint(step)
    target = pipeline.ROOT / relative
    monkeypatch.setattr(Path, "read_bytes", lambda p: original(p) + b"test-only-change" if p == target else original(p))
    assert _fingerprint(step) != before


def model3d_fixture(tmp_path, monkeypatch, *, mdf=True, frontage=True):
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    directory = tmp_path / "structured/candidates/furniture-plans"
    directory.mkdir(parents=True)
    manifest = directory / "layout.js"
    study = {"plan_file": "A_floor-1_mdf-study.svg", "section_file": "A_floor-1_mdf-section.svg"}
    data = {
        "schema": "house-concept-furniture-plan-v1",
        "layout_review": {"mdf_study": study} if mdf else {},
        "buildings": [
            {"id": "A", "floors": [{"id": "floor-1"}]},
            {"id": "C", "floors": [{"id": "floor-1", **(
                {"frontage_study_file": "C_floor-1_frontage-study.svg"} if frontage else {})}]},
        ],
    }
    manifest.write_text("window.HOUSE_CONCEPT_LAYOUT = " + json.dumps(data) + ";\n", encoding="utf-8")
    viewer = directory.parent / "model3d.html"
    viewer.write_text("test-only-viewer", encoding="utf-8")
    source = tmp_path / "source.json"
    source.write_text("test-only-source", encoding="utf-8")
    names = [*study.values()] if mdf else []
    if frontage:
        names.append("C_floor-1_frontage-study.svg")
    for name in names:
        (directory / name).write_text("test-only-svg", encoding="utf-8")
    return Step("model3d", ("test-only-export.py",), (source,), (viewer, manifest)), data, names


@pytest.mark.parametrize("mdf,frontage", [(False, False), (True, False), (False, True), (True, True)])
def test_model3d_tracks_only_manifest_declared_conditional_outputs(tmp_path, monkeypatch, mdf, frontage) -> None:
    step, _, names = model3d_fixture(tmp_path, monkeypatch, mdf=mdf, frontage=frontage)
    assert set(_effective_outputs(step)) == {*step.outputs, *(step.outputs[1].parent / n for n in names)}
    assert _outputs_exist(_effective_outputs(step))


@pytest.mark.parametrize("name", [
    "A_floor-1_mdf-study.svg", "A_floor-1_mdf-section.svg", "C_floor-1_frontage-study.svg",
])
@pytest.mark.parametrize("change", ["missing", "changed"])
def test_conditional_output_change_invalidates_pipeline_cache_without_running_renderer(
    tmp_path, monkeypatch, name, change,
) -> None:
    step, _, _ = model3d_fixture(tmp_path, monkeypatch)
    cache = {"concept:model3d": {
        "fingerprint": _fingerprint(step), "output_hash": pipeline._hash_paths(_effective_outputs(step)),
    }}
    target = step.outputs[1].parent / name
    if change == "missing":
        target.unlink()  # This is only the pytest temporary fixture, never a project drawing.
    else:
        target.write_text("test-only-edited-svg", encoding="utf-8")
    calls = []

    def regenerate(*args, **kwargs):
        calls.append(args)
        target.write_text("test-only-regenerated-svg", encoding="utf-8")

    monkeypatch.setattr(pipeline, "build_steps", lambda *args: [step])
    monkeypatch.setattr(pipeline, "_load_cache", lambda: cache)
    monkeypatch.setattr(pipeline, "_save_cache", lambda value: None)
    monkeypatch.setattr(pipeline.subprocess, "run", regenerate)
    kwargs = {"mode": "concept", "selection": "baseline", "style": "presentation", "paper": "a3", "output": "x"}
    pipeline.run_pipeline(**kwargs)
    assert len(calls) == 1
    pipeline.run_pipeline(**kwargs)
    assert len(calls) == 1  # An unchanged second run really can use the cache.


def test_model3d_fingerprint_ignores_unrelated_files(tmp_path, monkeypatch) -> None:
    step, _, _ = model3d_fixture(tmp_path, monkeypatch)
    before = _fingerprint(step)
    (tmp_path / "unrelated.txt").write_text("noise", encoding="utf-8")
    assert _fingerprint(step) == before


@pytest.mark.parametrize("bad_manifest", [
    "window.HOUSE_CONCEPT_LAYOUT = {};\n",
    "window.HOUSE_CONCEPT_LAYOUT = invalid;\n",
    "alert('not a data manifest');\n",
])
def test_invalid_model3d_manifest_is_not_silently_treated_as_no_optional_outputs(
    tmp_path, monkeypatch, bad_manifest,
) -> None:
    step, _, _ = model3d_fixture(tmp_path, monkeypatch)
    step.outputs[1].write_text(bad_manifest, encoding="utf-8")
    with pytest.raises(ValueError):
        _effective_outputs(step)


def test_mdf_source_presence_does_not_claim_a_study_was_generated(tmp_path, monkeypatch) -> None:
    step, _, _ = model3d_fixture(tmp_path, monkeypatch, mdf=False, frontage=False)
    source = tmp_path / "inputs/a-mdf-under-stair.json"
    source.parent.mkdir()
    source.write_text('{"test_only": true}', encoding="utf-8")
    assert _effective_outputs(step) == step.outputs


@pytest.mark.parametrize("name", ["../outside.svg", "/outside.svg", "subdir\\outside.svg"])
def test_conditional_outputs_cannot_escape_the_plan_directory(tmp_path, monkeypatch, name) -> None:
    step, data, _ = model3d_fixture(tmp_path, monkeypatch)
    data["layout_review"]["mdf_study"]["plan_file"] = name
    step.outputs[1].write_text("window.HOUSE_CONCEPT_LAYOUT = " + json.dumps(data) + ";\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SVG filenames"):
        _effective_outputs(step)


@pytest.mark.parametrize("repair", [True, False])
def test_corrupt_manifest_rebuilds_and_invalid_regeneration_never_saves_cache(
    tmp_path, monkeypatch, repair,
) -> None:
    step, _, _ = model3d_fixture(tmp_path, monkeypatch)
    original = step.outputs[1].read_text(encoding="utf-8")
    cache = {"concept:model3d": {
        "fingerprint": _fingerprint(step), "output_hash": pipeline._hash_paths(_effective_outputs(step)),
    }}
    step.outputs[1].write_text("not a manifest", encoding="utf-8")
    calls, saves = [], []

    def regenerate(*args, **kwargs):
        calls.append(args)
        if repair:
            step.outputs[1].write_text(original, encoding="utf-8")

    monkeypatch.setattr(pipeline, "build_steps", lambda *args: [step])
    monkeypatch.setattr(pipeline, "_load_cache", lambda: cache)
    monkeypatch.setattr(pipeline, "_save_cache", lambda value: saves.append(value))
    monkeypatch.setattr(pipeline.subprocess, "run", regenerate)
    kwargs = {"mode": "concept", "selection": "baseline", "style": "presentation", "paper": "a3", "output": "x"}
    if repair:
        pipeline.run_pipeline(**kwargs)
        assert len(saves) == 1
    else:
        with pytest.raises(ValueError, match="data assignment"):
            pipeline.run_pipeline(**kwargs)
        assert not saves
    assert len(calls) == 1
