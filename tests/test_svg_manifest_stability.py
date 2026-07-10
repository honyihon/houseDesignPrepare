from __future__ import annotations

from export_top1_svgs import stable_svg_filename


def test_stable_svg_filename_ignores_candidate_strategy() -> None:
    assert stable_svg_filename("A", "floor-1") == "a_floor-1.svg"
    assert stable_svg_filename("B", "floor-4") == "b_floor-4.svg"
