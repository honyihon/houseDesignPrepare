"""Stable rendering boundaries shared by script entrypoints."""

from house_design.rendering.html_payload import encode_html_json
from house_design.rendering.naming import stable_svg_filename

__all__ = ["encode_html_json", "stable_svg_filename"]
