from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / ".house-design-cache.json"


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]


def _paths(*values: str) -> tuple[Path, ...]:
    return tuple(ROOT / value for value in values)


def build_steps(selection: str, style: str, paper: str, output: str, mode: str) -> list[Step]:
    structured_sources = _paths(
        "structured/AbuildingView.structured.json",
        "structured/BbuildingView.structured.json",
        "structured/CbuildingView.structured.json",
        "structured/storage.structured.json",
    )
    steps = [
        Step(
            "extract",
            ("scripts/extract_layout_data.py",),
            _paths(
                "AbuildingView.html",
                "BbuildingView.html",
                "CbuildingView.html",
                "storage.html",
                "scripts/extract_layout_data.py",
            ),
            (*structured_sources, ROOT / "structured/index.json"),
        ),
        Step(
            "program",
            ("scripts/build_room_program.py",),
            (
                *structured_sources,
                # inputs/dimensions.json is where real measurements land, so a
                # measuring session must invalidate this step even though the
                # HTML has not changed. _hash_paths tolerates it being absent.
                *_paths(
                    "scripts/build_room_program.py",
                    "scripts/config/residential_defaults_tw.json",
                    "scripts/lib/dimension_overrides.py",
                    "inputs/dimensions.json",
                ),
            ),
            _paths("structured/room_program.json"),
        ),
        Step(
            "metrics",
            ("scripts/evaluate_architect_metrics.py",),
            _paths(
                "structured/room_program.json",
                "scripts/evaluate_architect_metrics.py",
                "scripts/lib/architect_metrics.py",
            ),
            _paths("structured/architect_metrics/metrics.json", "structured/architect_metrics/report.md"),
        ),
        Step(
            "candidates",
            ("scripts/generate_layout_candidates.py",),
            _paths(
                "structured/room_program.json",
                "structured/architect_metrics/metrics.json",
                "scripts/generate_layout_candidates.py",
                "scripts/lib/standards.py",
            ),
            _paths("structured/candidates/layout_candidates.json", "structured/candidates/summary.md"),
        ),
        Step(
            "viewer",
            ("scripts/render_candidate_viewer.py",),
            _paths(
                "structured/room_program.json",
                "structured/candidates/layout_candidates.json",
                "scripts/render_candidate_viewer.py",
            ),
            _paths("structured/candidates/viewer.html"),
        ),
        # model3d reads this plan for the historical comparison. Generate it
        # first so one pipeline run cannot pair a fresh viewer with an old plan.
        Step(
            "parametric",
            ("scripts/generate_parametric_plan.py",),
            _paths(
                "inputs/site.json",
                "inputs/brief/A.json",
                "inputs/brief/B.json",
                "inputs/brief/C.json",
                "inputs/dimensions.json",
                "scripts/generate_parametric_plan.py",
                "scripts/lib/plan_geometry.py",
                "scripts/lib/plan_rules.py",
                "scripts/lib/standards.py",
                "scripts/config/residential_defaults_tw.json",
            ),
            _paths("structured/parametric/plan.json", "structured/parametric/capacity.md"),
        ),
        Step(
            "model3d",
            ("scripts/export_model_3d.py",),
            _paths(
                "structured/room_program.json",
                "inputs/dimensions.json",
                "inputs/furniture-layout.json",
                "inputs/concept-layout-review.json",
                "inputs/facade-concept.json",
                "inputs/requirements.json",
                "inputs/physical-items.json",
                "inputs/a-mdf-under-stair.json",
                "inputs/references/abc-before-space-efficiency-20261014.json",
                "inputs/references/abc-before-a-storage-20261014.json",
                "structured/parametric/plan.json",
                "scripts/export_model_3d.py",
                "scripts/templates/model3d.html",
                "scripts/templates/model3d_facade.js",
                "scripts/export_top1_svgs.py",
                "scripts/lib/__init__.py",
                "scripts/lib/dimension_overrides.py",
                "scripts/lib/furniture_layout.py",
                "scripts/lib/model3d_bc_flow.py",
                "scripts/lib/model3d_fengshui.py",
                "scripts/lib/model3d_mdf.py",
                "scripts/lib/model3d_openings.py",
                "scripts/lib/model3d_space_efficiency.py",
                "scripts/lib/model3d_tour.py",
                "scripts/lib/model3d_review.py",
                "scripts/lib/model3d_functions.py",
                "scripts/lib/model3d_placement.py",
                "scripts/lib/model3d_plan.py",
                "scripts/lib/model3d_facade.py",
                "assets/references/facade-photo-v1.jpg",
                "house_design/__init__.py",
                "house_design/contracts.py",
                "house_design/physical_items.py",
                "house_design/rendering/__init__.py",
                "house_design/rendering/html_payload.py",
                "house_design/rendering/naming.py",
                "scripts/config/residential_defaults_tw.json",
                "scripts/lib/html_parametric_compare.py",
                "scripts/lib/standards.py",
                "assets/vendor/three/three.min.js",
            ),
            _paths(
                "structured/candidates/model3d.html",
                "structured/candidates/furniture-plans/layout.js",
                *(f"structured/candidates/furniture-plans/{building}_facade-front.svg" for building in "ABC"),
                *(
                    f"structured/candidates/furniture-plans/{building}_floor-{floor}.svg"
                    for building in "ABC"
                    for floor in range(1, 5)
                ),
            ),
        ),
        Step(
            "walkthrough",
            ("scripts/export_walkthrough_3d.py",),
            _paths(
                "structured/parametric/plan.json",
                # The geometry is parametric, but room_program supplies the
                # traceable link back to the original HTML rooms. Any HTML or
                # dimension change must therefore invalidate this viewer too.
                "structured/room_program.json",
                "scripts/export_walkthrough_3d.py",
                "scripts/templates/walkthrough.html",
                "scripts/lib/html_parametric_compare.py",
                "scripts/lib/standards.py",
                "scripts/lib/viewer_shell.py",
                "scripts/config/residential_defaults_tw.json",
                "assets/vendor/three/three.min.js",
            ),
            _paths("structured/parametric/walkthrough.html"),
        ),
        Step(
            "svg",
            ("scripts/export_top1_svgs.py", "--selection", selection, "--style", style),
            _paths(
                "structured/room_program.json",
                "structured/candidates/layout_candidates.json",
                "scripts/export_top1_svgs.py",
                "scripts/config/residential_defaults_tw.json",
                "scripts/lib/dimension_overrides.py",
            ),
            _paths("structured/candidates/svg/manifest.json", "structured/candidates/svg/index.html"),
        ),
    ]
    if mode != "concept":
        steps.append(
            Step(
                "pdf",
                ("scripts/export_print_bundle_pdf.py", "--paper", paper, "--output", output),
                _paths("structured/candidates/svg/manifest.json", "scripts/export_print_bundle_pdf.py"),
                (ROOT / output,),
            )
        )
    if mode in {"ifc", "release"}:
        steps.append(
            Step(
                "validate",
                ("scripts/validate_layout_bundle.py", "--strict"),
                _paths(
                    "structured/room_program.json",
                    "structured/candidates/svg/manifest.json",
                    "scripts/validate_layout_bundle.py",
                ),
                (),
            )
        )
    return steps


def _manifest_svg_paths(manifest_path: Path) -> tuple[Path, ...]:
    if not manifest_path.exists():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    exports = manifest.get("exports", []) if isinstance(manifest, dict) else []
    return tuple(manifest_path.parent / str(item.get("file", "")) for item in exports if item.get("file"))


def _model3d_optional_outputs() -> tuple[Path, ...]:
    """Read the generated data assignment, never import or run the renderer.

    Missing base outputs already invalidate the cache. An unreadable manifest
    must also invalidate it, rather than silently forgetting its conditional
    outputs. Invalid output contracts after generation must not be cached.
    """
    directory = ROOT / "structured/candidates/furniture-plans"
    manifest = directory / "layout.js"
    if not manifest.exists():
        return ()
    source = manifest.read_text(encoding="utf-8").strip()
    prefix = "window.HOUSE_CONCEPT_LAYOUT = "
    if not source.startswith(prefix) or not source.endswith(";"):
        raise ValueError("Invalid model3d plan data assignment")
    data = json.loads(source[len(prefix):-1])
    if not isinstance(data, dict) or data.get("schema") != "house-concept-furniture-plan-v1":
        raise ValueError("Invalid model3d plan manifest schema")
    review, buildings = data.get("layout_review", {}), data.get("buildings")
    if not isinstance(review, dict) or not isinstance(buildings, list):
        raise ValueError("Invalid model3d plan manifest structure")
    mdf = review.get("mdf_study")
    paths: list[Path] = []

    def include(name: object) -> None:
        if (not isinstance(name, str) or not name.endswith(".svg")
                or Path(name).name != name or "\\" in name):
            raise ValueError("Conditional model3d outputs must be SVG filenames in furniture-plans")
        paths.append(directory / name)

    for building in buildings:
        if not isinstance(building, dict) or not isinstance(building.get("floors"), list):
            raise ValueError("Invalid model3d building in plan manifest")
        for floor in building["floors"]:
            if not isinstance(floor, dict):
                raise ValueError("Invalid model3d floor in plan manifest")
            if mdf and building.get("id") == "A" and floor.get("id") == "floor-1":
                if not isinstance(mdf, dict):
                    raise ValueError("Invalid model3d MDF study in plan manifest")
                include(mdf.get("plan_file"))
                include(mdf.get("section_file"))
            if floor.get("frontage_study_file"):
                include(floor["frontage_study_file"])
    return tuple(dict.fromkeys(paths))


def _effective_inputs(step: Step) -> tuple[Path, ...]:
    if step.name == "pdf":
        manifest = ROOT / "structured/candidates/svg/manifest.json"
        return (*step.inputs, *_manifest_svg_paths(manifest))
    return step.inputs


def _effective_outputs(step: Step) -> tuple[Path, ...]:
    if step.name == "model3d":
        return tuple(dict.fromkeys((*step.outputs, *_model3d_optional_outputs())))
    if step.name == "svg":
        manifest = ROOT / "structured/candidates/svg/manifest.json"
        return (*step.outputs, *_manifest_svg_paths(manifest))
    return step.outputs


def _hash_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        try:
            display_path = path.relative_to(ROOT)
        except ValueError:
            display_path = path
        digest.update(str(display_path).encode())
        if not path.exists():
            digest.update(b"<missing>")
        else:
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _fingerprint(step: Step) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(step.command).encode())
    digest.update(_hash_paths(_effective_inputs(step)).encode())
    return digest.hexdigest()


def _load_cache() -> dict[str, dict[str, str]]:
    if not CACHE_FILE.exists():
        return {}
    try:
        value = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, dict)}


def _save_cache(cache: dict[str, dict[str, str]]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _outputs_exist(outputs: Iterable[Path]) -> bool:
    values = tuple(outputs)
    return bool(values) and all(path.exists() for path in values)


def run_pipeline(
    *,
    mode: str,
    selection: str,
    style: str,
    paper: str,
    output: str,
    force: bool = False,
    from_step: str | None = None,
    to_step: str | None = None,
    python_exe: str = sys.executable,
) -> None:
    resolved_selection = "baseline" if selection == "auto" else selection
    steps = build_steps(resolved_selection, style, paper, output, mode)
    names = [step.name for step in steps]
    start = names.index(from_step) if from_step else 0
    end = names.index(to_step) if to_step else len(steps) - 1
    if start > end:
        raise ValueError("--from-step must not come after --to-step")

    cache = _load_cache()
    for step in steps[start : end + 1]:
        fingerprint = _fingerprint(step)
        cache_key = f"{mode}:{step.name}"
        try:
            outputs = _effective_outputs(step)
        except (OSError, ValueError):
            # A damaged generated manifest needs rebuilding, not a cache hit.
            outputs = ()
        cached = cache.get(cache_key, {})
        cache_hit = (
            not force
            and _outputs_exist(outputs)
            and cached.get("fingerprint") == fingerprint
            and cached.get("output_hash") == _hash_paths(outputs)
        )
        if cache_hit:
            print(f"[cached] {step.name}")
            continue
        print(f"[run] {step.name}")
        subprocess.run([python_exe, *step.command], cwd=ROOT, check=True)
        outputs = _effective_outputs(step)
        cache[cache_key] = {
            "fingerprint": _fingerprint(step),
            "output_hash": _hash_paths(outputs) if outputs else "",
        }
        _save_cache(cache)
