#!/usr/bin/env python3
"""Package B source-height 3D code and offline plans without executing a scene."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT/"scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from lib.model3d_plan import render_plan  # noqa: E402

from house_design.b_upper_storage_viewer import ARCHIVE, HTML, OUT, RUNTIME, build  # noqa: E402
from house_design.plan_readability import readable_svg  # noqa: E402


def label_helper(root):
    source = (root/"scripts/templates/upper-floor-storage-viewer.js").read_text()
    start = source.index("  function rectsOverlap(")
    end = source.index("  if(typeof module!", start)
    return ("(function(global){'use strict';\n"+source[start:end]+
        "\nglobal.B_UPPER_LABELS={rectsOverlap:rectsOverlap,placeLabels:placeLabels};})(globalThis);\n").encode()


def render(root, report):
    root = Path(root)
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    template = (root/HTML).read_text()
    if template.count("__B_UPPER_DATA__") != 1:
        raise ValueError("B viewer needs exactly one data placeholder")
    files = {"index.html": template.replace("__B_UPPER_DATA__", payload).encode(),
        "viewer.js": (root/RUNTIME).read_bytes(), "label-layout.js": label_helper(root),
        "vendor/three.min.js": (root/"assets/vendor/three/three.min.js").read_bytes(),
        "vendor/LICENSE": (root/"assets/vendor/three/LICENSE").read_bytes(),
        "review.json": (json.dumps(report, ensure_ascii=False, indent=2)+"\n").encode()}
    for plan in report["plans"]:
        raw = (root/plan["source"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != plan["sha256"]:
            raise ValueError("B matched plan changed")
        files[plan["file"]] = raw
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ground_names = []
    for entry in report["entry_options"]:
        for state in entry["states"]:
            name = entry["id"]+"_"+state["id"]+"_floor-1.svg"
            svg = ET.fromstring(render_plan("B", state["floor"], viewer_url="index.html"))
            for node in svg.iter():
                for key in list(node.attrib):
                    if key.lower().startswith("on"):
                        del node.attrib[key]
                    elif key.endswith("href"):
                        node.set(key, "index.html")
            files[name] = readable_svg(ET.tostring(svg, encoding="utf-8"))[0]
            ground_names.append(name)
    plans = [p["file"] for p in report["plans"]]+ground_names
    links = "".join('<li><a href="'+n+'">'+n+'</a></li>' for n in plans)
    files["plans.html"] = ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>B同版平面目錄</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:auto;padding:20px}li{margin:12px 0}a{color:#075e79}</style>'
        '<h1>B同版平面目錄</h1><p>上層P4／Q3與兩個RF，各比原配置／收納；一樓後門預案／無後巷前門備案各三態維持原來源。尚未採用，RF24㎡及專業缺口保留。</p>'
        '<p><a href="index.html">回B上層3D比較</a></p><ul>'+links+'</ul></html>').encode()
    files["README.md"] = ("# B同版上層與收納3D比較\n\n解壓整包開[index.html](index.html)，或[同版平面](plans.html)。不需WSL、Node、網路或伺服器。\n\n"
        "四樓層版本各有原配置／加櫃，保多邊形房界、二樓L形到達、Q3上下層梯及RF開口；可看收納、整層、樓梯、俯視及完整品名。\n\n"
        "只有新增櫃與尺寸相符的來源概念家具用指定高度；其餘只畫原平面投影。房界線框是辨識標示，不是真實牆高／厚度。樓梯沒有補造梁板或扶手，也不代表淨高與結構核可。\n\n"
        "顯示第2版把二樓梯標籤改為「一樓原梯接Q3上層改梯」，不改來源幾何；原P4房間名稱留在來源JSON作追溯，不直接當成改梯後的畫面說明。\n\n"
        "一樓兩入口各三態另有原同版平面，本3D不合併一樓。RF24㎡原目標仍缺，P4排水與聲學／結構／新風／產品待核。新畫面待屋主另驗，不沿用TQX7gQ第1版、A／C或其他已驗收檢視的passed。\n").encode()
    files["artifact-manifest.json"] = (json.dumps({"schema": "house-b-upper-storage-viewer-artifacts-v1",
        "report_hash": report["report_hash"], "source_hashes": report["source_hashes"], "rendered_qa": "not-run",
        "artifacts": {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()}}, ensure_ascii=False, indent=2)+"\n").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    contents = sorted(files)
    files[ARCHIVE] = stream.getvalue()
    files["archive-manifest.json"] = (json.dumps({"schema": "house-b-upper-storage-viewer-archive-v1",
        "archive": ARCHIVE, "sha256": hashlib.sha256(files[ARCHIVE]).hexdigest(), "archive_contains": contents}, indent=2)+"\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files = render(ROOT, report)
        target = ROOT/OUT
        if args.check:
            if any(not (target/n).is_file() or (target/n).read_bytes() != b for n, b in files.items()):
                raise ValueError("B upper storage viewer is stale")
        else:
            target.mkdir(parents=True, exist_ok=True)
            for n, raw in files.items():
                (target/n).parent.mkdir(parents=True, exist_ok=True)
                (target/n).write_bytes(raw)
        print(json.dumps({"status": "checked" if args.check else "exported", **report["summary"],
            "files": len(files), "zip_bytes": len(files[ARCHIVE]), "main_3d_changed": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
