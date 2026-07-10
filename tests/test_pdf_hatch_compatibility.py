from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO

from export_print_bundle_pdf import load_svg_drawing
import export_top1_svgs as svg_export


PROFILE = {
    "presentation_version": 2,
    "colors": {"hatch": "#94a3b8"},
    "room_fills": {
        "bath": "#f3fdff",
        "service": "#f7f9fc",
        "outdoor": "#f2fbf5",
        "other": "#ffffff",
    },
}


def test_presentation_hatch_uses_concrete_fill_and_explicit_paths() -> None:
    fill = svg_export.room_fill_color(PROFILE, "bath", "presentation")
    hatch = svg_export.room_hatch_paths(
        x=0,
        y=0,
        width=36,
        height=27,
        kind="bath",
        profile=PROFILE,
        drawing_style="presentation",
    )

    assert fill == "#f3fdff"
    assert "url(#p2-" not in fill
    assert 'data-hatch-kind="bath"' in hatch
    assert "<path" in hatch


def test_explicit_hatch_svg_loads_without_unsupported_color_warning(tmp_path) -> None:
    fill = svg_export.room_fill_color(PROFILE, "bath", "presentation")
    hatch = svg_export.room_hatch_paths(
        x=0,
        y=0,
        width=36,
        height=27,
        kind="bath",
        profile=PROFILE,
        drawing_style="presentation",
    )
    svg_path = tmp_path / "hatch.svg"
    svg_path.write_text(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="27">'
            f'<rect x="0" y="0" width="36" height="27" fill="{fill}"/>'
            f"{hatch}</svg>"
        ),
        encoding="utf-8",
    )
    stderr = StringIO()

    with redirect_stderr(stderr):
        drawing = load_svg_drawing(svg_path, "")

    assert drawing is not None
    assert "Can't handle color" not in stderr.getvalue()


def test_bottom_legend_uses_pdf_compatible_hatch_samples() -> None:
    parts: list[str] = []

    svg_export.draw_bottom_legend(
        parts=parts,
        x=0,
        y=20,
        width=1000,
        interior_wall_px=2,
        exterior_wall_px=4,
        profile=PROFILE,
        drawing_style="presentation",
    )
    markup = "".join(parts)

    assert "url(#p2-" not in markup
    assert markup.count("data-hatch-kind=") == 3


def test_manifest_records_selection_fields_without_strategy_filename() -> None:
    name = svg_export.stable_svg_filename("A", "floor-1")

    assert name == "a_floor-1.svg"
    assert "_baseline" not in name
    assert "_mep" not in name
    assert "_circulation" not in name
    assert "_daylight" not in name
