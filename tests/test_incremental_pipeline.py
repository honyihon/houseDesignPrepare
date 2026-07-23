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
