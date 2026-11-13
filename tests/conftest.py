from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

_XML_NAMESPACES = ET._namespace_map.copy()

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

for path in (ROOT, SCRIPTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


@pytest.fixture(scope="session", autouse=True)
def canonical_export_process():
    """Exercise the supported canonical ZIP export context on every CI host."""
    from house_design.reproducible_export import canonical_zip_metadata

    with canonical_zip_metadata():
        yield


@pytest.fixture(autouse=True)
def isolate_xml_namespace_registry(monkeypatch, request):
    """SVG prefixes must not depend on which other exporter a test imported or ran."""
    monkeypatch.setattr(ET, "_namespace_map", _XML_NAMESPACES.copy())
    if getattr(request.module, "SVG_DEFAULT_NAMESPACE", False):
        ET.register_namespace("", "http://www.w3.org/2000/svg")
