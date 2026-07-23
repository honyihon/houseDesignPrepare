from __future__ import annotations

from pathlib import Path

from validate_layout_bundle import inspect_svg


def test_svg_metadata_does_not_count_as_rendered_marker(tmp_path: Path) -> None:
    svg = tmp_path / "sample.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><metadata>ELEV: ENT</metadata>'
        '<g data-marker="entrance"><path d="M 0 0"/></g><text>DIM:W</text></svg>',
        encoding="utf-8",
    )

    markers, visible_text = inspect_svg(svg)

    assert markers == {"entrance"}
    assert "DIM:W" in visible_text
    assert "ELEV:" not in visible_text
