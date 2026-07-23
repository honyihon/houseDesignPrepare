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
            _paths("AbuildingView.html", "BbuildingView.html", "CbuildingView.html", "storage.html", "scripts/extract_layout_data.py"),
            (*structured_sources, ROOT / "structured/index.json"),
        ),
        Step(
            "program",
            ("scripts/build_room_program.py",),
            (*structured_sources, *_paths("scripts/build_room_program.py", "scripts/config/residential_defaults_tw.json")),
            _paths("structured/room_program.json"),
        ),
        Step(
            "metrics",
            ("scripts/evaluate_architect_metrics.py",),
            _paths("structured/room_program.json", "scripts/evaluate_architect_metrics.py", "scripts/lib/architect_metrics.py"),
            _paths("structured/architect_metrics/metrics.json", "structured/architect_metrics/report.md"),
        ),
        Step(
            "candidates",
            ("scripts/generate_layout_candidates.py",),
            _paths("structured/room_program.json", "structured/architect_metrics/metrics.json", "scripts/generate_layout_candidates.py"),
            _paths("structured/candidates/layout_candidates.json", "structured/candidates/summary.md"),
        ),
        Step(
            "viewer",
            ("scripts/render_candidate_viewer.py",),
            _paths("structured/room_program.json", "structured/candidates/layout_candidates.json", "scripts/render_candidate_viewer.py"),
            _paths("structured/candidates/viewer.html"),
        ),
        Step(
            "svg",
            ("scripts/export_top1_svgs.py", "--selection", selection, "--style", style),
            _paths(
                "structured/room_program.json",
                "structured/candidates/layout_candidates.json",
                "scripts/export_top1_svgs.py",
                "scripts/config/residential_defaults_tw.json",
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
    if mode == "ifc":
        steps.append(
            Step(
                "validate",
                ("scripts/validate_layout_bundle.py", "--strict"),
                _paths("structured/room_program.json", "structured/candidates/svg/manifest.json", "scripts/validate_layout_bundle.py"),
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


def _effective_inputs(step: Step) -> tuple[Path, ...]:
    if step.name == "pdf":
        manifest = ROOT / "structured/candidates/svg/manifest.json"
        return (*step.inputs, *_manifest_svg_paths(manifest))
    return step.inputs


def _effective_outputs(step: Step) -> tuple[Path, ...]:
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
        outputs = _effective_outputs(step)
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
