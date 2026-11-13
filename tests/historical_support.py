"""Read sealed historical geometry and report its drift; never bypass production source guards."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEALS = Path(__file__).parent/"fixtures/historical-study-seals.json"


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_drift(report):
    """Return exact changed bytes, not a pretend successful freshness check."""
    return {name: {"recorded": expected, "current": checksum(ROOT/name) if (ROOT/name).is_file() else None}
        for name, expected in report.get("source_hashes", {}).items()
        if not (ROOT/name).is_file() or checksum(ROOT/name) != expected}


def assert_historical_sources(name, report):
    record = json.loads(SEALS.read_text())["studies"][name]
    assert source_drift(report) == record["observed_source_drift"], "Unreviewed historical source drift: "+name
    return record


def saved_payload(path):
    """Decode the literal only. Do not execute a viewer or a full scene generator."""
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)
    assert match, "Missing saved viewer data: "+str(path)
    return json.loads(match[1])


def historical_study(name):
    """Geometry tests use recorded input data; live rebuilds must still reject stale sources."""
    record = json.loads(SEALS.read_text())["studies"][name]
    path = ROOT/record["report"]
    assert checksum(path) == record["report_sha256"], "Historical report changed: "+name
    for relative, expected in record["artifacts"].items():
        assert checksum(ROOT/relative) == expected, "Historical artifact changed: "+relative
    text = path.read_text(encoding="utf-8")
    report = json.loads(text.split(" = ", 1)[1].rstrip(";\n")) if path.suffix == ".js" else json.loads(text)
    assert_historical_sources(name, report)
    viewer = ROOT/"structured/candidates"/(name+"-3d.html")
    if viewer.is_file() and "options" in report:
        data = saved_payload(viewer)
        key = "bc_options" if name in {"preparation-review", "interior-improvements"} else name.replace("-", "_")
        key = record.get("viewer_key", key)
        options = {o["id"]: o for o in data[key]["options"]}
        for option in report["options"]:
            frozen = options[option["id"]]
            if "states" in option:
                models = {s["id"]: s["model"] for s in frozen["states"]}
                for state in option["states"]:
                    state["model"] = copy.deepcopy(models[state["id"]])
            else:
                option["model"] = copy.deepcopy(frozen["model"])
    return report


def historical_option(name, option):
    report = historical_study(name)
    return report, next(o for o in report["options"] if o["id"] == option)


def historical_state(name, option, state):
    report, selected = historical_option(name, option)
    return report, next(s for s in selected["states"] if s["id"] == state)


def recorded_source_precondition(monkeypatch, module, name):
    """Isolate a later tamper guard in a negative unit test, never a live rebuild.

    Seal and audit the actual archive first. Only its original source-hash
    precondition is substituted; report/viewer integrity checks stay real.
    Separate tests must exercise the real stale-source rejection.
    """
    report = historical_study(name)
    recorded = {ROOT / p: h for p, h in report["source_hashes"].items()}
    original = module.sha256_file
    monkeypatch.setattr(module, "sha256_file", lambda p: recorded[p] if p in recorded else original(p))
