"""Read-only compact diagnostics for native Windows export drift in CI."""
from __future__ import annotations

import importlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]


def difference(a, b, path=""):
    if type(a) is not type(b):
        return (path, repr(a)[:120], repr(b)[:120])
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return (path, "keys", repr(set(a) ^ set(b))[:120])
        for k in a:
            if a[k] != b[k]:
                return difference(a[k], b[k], path+"/"+k)
    elif isinstance(a, list):
        if len(a) != len(b):
            return (path, len(a), len(b))
        for n, (x, y) in enumerate(zip(a, b, strict=True)):
            if x != y:
                return difference(x, y, path+"/"+str(n))
    elif a != b:
        return (path, repr(a)[:120], repr(b)[:120])
    return None


def main():
    for name in ("abc_laundry_access", "b_roof_daily_use", "b_third_entertainment", "c_ground_coordination",
                 "upper_floor_storage_viewer", "b_upper_storage_sync"):
        try:
            model = importlib.import_module("house_design."+name)
            exporter = importlib.import_module("scripts.export_"+name)
            report = model.build(ROOT)
            saved = json.loads((ROOT / model.OUT / "review.json").read_text(encoding="utf-8"))
            print(name, "report difference", difference(saved, json.loads(json.dumps(report))), flush=True)
            files = exporter.render(ROOT, report) if name == "upper_floor_storage_viewer" else exporter.render(report)
            for path, value in files.items():
                current = value.encode() if isinstance(value, str) else value
                stored = (ROOT / model.OUT / path).read_bytes()
                if current == stored:
                    continue
                if path.endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(stored)) as old, zipfile.ZipFile(io.BytesIO(current)) as new:
                        print(name, path, "zip metadata", [(i.create_system, j.create_system) for i, j in
                            zip(old.infolist(), new.infolist(), strict=True)][:1],
                            "content differences", [n for n in old.namelist() if old.read(n) != new.read(n)][:3], flush=True)
                else:
                    offset = next((i for i, (x, y) in enumerate(zip(stored, current, strict=False)) if x != y), min(len(stored), len(current)))
                    print(name, path, "byte offset", offset, "stored", repr(stored[max(0,offset-35):offset+90]),
                          "current", repr(current[max(0,offset-35):offset+90]), flush=True)
                break
        except Exception as error:
            print(name, type(error).__name__, str(error)[:250], flush=True)


if __name__ == "__main__":
    main()
