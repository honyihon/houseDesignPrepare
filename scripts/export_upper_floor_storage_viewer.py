#!/usr/bin/env python3
"""Create a bounded, offline storage-height viewer and an independently unpackable ZIP."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from house_design.upper_floor_storage_viewer import ARCHIVE, OUT, build  # noqa: E402


def render(root,report):
    root=Path(root)
    payload=json.dumps(report,ensure_ascii=False,separators=(",",":"))
    payload=payload.replace("&","\\u0026").replace("<","\\u003c").replace(">","\\u003e").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    text=(root/"scripts/templates/upper-floor-storage-viewer.html").read_text()
    if text.count("__STORAGE_DATA__") != 1:
        raise ValueError("Storage viewer needs exactly one data placeholder")
    files={"index.html":text.replace("__STORAGE_DATA__",payload).encode(),
        "viewer.js":(root/"scripts/templates/upper-floor-storage-viewer.js").read_bytes(),
        "vendor/three.min.js":(root/"assets/vendor/three/three.min.js").read_bytes(),
        "vendor/LICENSE":(root/"assets/vendor/three/LICENSE").read_bytes(),
        "review.json":(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode()}
    for case in report["cases"]:
        data=(root/case["plan_source"]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=case["plan_sha256"]:
            raise ValueError("Storage plan changed while packaging")
        files[case["plan_file"]]=data
    files["README.md"]=("# ABC逐層儲藏立體檢視\n\n解壓整包，開[index.html](index.html)。不需WSL、Node、伺服器或網路。\n\n"
        "只有橙色儲藏櫃按指定高度建模；周邊房間、家具及設備為同版平面投影，不補造牆高、樓梯或家具高度。尚未併入原主3D。\n\n"
        "十版本涵蓋九個棟層，B兩屋頂方案分開；各版可連同版平面。原家規、衣櫃容量與需求保留，產品、結構及真人操作仍待核。\n\n"
        "顯示第3版：保留上方樓層與尺寸、品名避讓及完整中文清單；清單與返回圖面留頂部間距。配置與尺寸不變，本版畫面待另驗。\n\n"
        "本批來源與檔案雜湊見review.json及artifact-manifest.json；這不是專業核可或新的畫面驗收通過紀錄。\n").encode()
    files["artifact-manifest.json"]=(json.dumps({"schema":"house-upper-floor-storage-viewer-artifacts-v1",
        "report_hash":report["report_hash"],"source_hashes":report["source_hashes"],"rendered_qa":"not-run",
        "artifacts":{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n").encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,11,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,value)
    archive_contents=sorted(files)
    files[ARCHIVE]=stream.getvalue()
    files["archive-manifest.json"]=(json.dumps({"schema":"house-upper-floor-storage-viewer-archive-v1",
        "archive":ARCHIVE,"sha256":hashlib.sha256(files[ARCHIVE]).hexdigest(),"archive_contains":archive_contents},indent=2)+"\n").encode()
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    try:
        report=build(ROOT)
        files=render(ROOT,report)
        target=ROOT/OUT
        if args.check:
            if any(not (target/n).is_file() or (target/n).read_bytes()!=v for n,v in files.items()):
                raise ValueError("Storage viewer is stale")
        else:
            target.mkdir(parents=True,exist_ok=True)
            for name,value in files.items():
                dest=target/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(value)
        print(json.dumps({"status":"checked" if args.check else "exported","cases":10,"floors":9,"files":len(files),
            "original_main_3d_changed":False,"surroundings":"source-footprints-only","browser":"not-run","zip_bytes":len(files[ARCHIVE])}))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
