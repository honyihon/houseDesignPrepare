"""Bounded, read-only navigation/source index; never a QA/adoption authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

INDEX = "inputs/project-status.json"
MAX_BYTES = 20 * 1024 * 1024
PUBLIC_DIRS = {"Docs", "assets", "house_design", "inputs", "rules", "schemas", "scripts", "structured", "tests"}
ROOT_FILES = {"AbuildingView.html", "BbuildingView.html", "CbuildingView.html", "README.md", "AGENTS.md"}


def public_path(root: Path, relative: str) -> Path:
    """Reject traversal, private/hidden paths and symlinks into those paths."""
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Expected a public project-relative POSIX path")
    name = PurePosixPath(relative)
    if (not relative or not name.parts or name.is_absolute()
            or any(p in {".", ".."} or p.startswith(".") for p in name.parts)
            or "private" in name.parts or (name.parts[0] not in PUBLIC_DIRS and relative not in ROOT_FILES)):
        raise ValueError("Outside public project paths")
    target = (root / relative).resolve()
    try:
        resolved = target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Source leaves the project") from exc
    if (not resolved.parts or any(p.startswith(".") or p == "private" for p in resolved.parts)
            or (resolved.parts[0] not in PUBLIC_DIRS and resolved.as_posix() not in ROOT_FILES)):
        raise ValueError("Source resolves outside public project paths")
    return target


def digest(root: Path, relative: str, cache: dict[str, str]) -> str:
    if relative not in cache:
        target = public_path(root, relative)
        if not target.is_file():
            raise ValueError("Source is missing or not a file")
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("Source exceeds 20MB; manual verification required")
        result = hashlib.sha256()
        size = 0
        with target.open("rb") as source:
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > MAX_BYTES:
                    raise ValueError("Source grew beyond 20MB")
                result.update(block)
        cache[relative] = result.hexdigest()
    return cache[relative]


def read_public_json(root: Path, relative: str) -> dict:
    target = public_path(root, relative)
    if target.stat().st_size > MAX_BYTES:
        raise ValueError("JSON exceeds 20MB")
    with target.open("rb") as source:
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("JSON grew beyond 20MB")
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def inspect_project(root: Path) -> dict[str, Any]:
    """Compare declared source/optional artifact hashes; do not execute package validators."""
    index = read_public_json(root, INDEX)
    if index.get("schema") != "house-project-status-index-v1":
        raise ValueError("Unsupported project status index")
    packages = index.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Missing package index")
    ids = [p.get("id") for p in packages if isinstance(p, dict)]
    if len(ids) != len(packages) or any(not isinstance(p, str) or not p for p in ids) or len(set(ids)) != len(ids):
        raise ValueError("Package IDs must be unique nonempty strings")
    if index.get("default_package") not in ids:
        raise ValueError("Default package is not indexed")
    if any(p.get("check_scope", "current") not in {"current", "history"} for p in packages):
        raise ValueError("Package check_scope must be current or history")
    default = next(p for p in packages if p["id"] == index["default_package"])
    if default.get("check_scope", "current") != "current":
        raise ValueError("Default package cannot point to archived history")
    cache: dict[str, str] = {}
    results = []
    for package in packages:
        failures, changed, artifacts = [], [], {}
        for key in ("document", "entry", "viewer", "report", "manifest"):
            if package.get(key) is not None:
                try:
                    artifacts[key] = {"path": package[key], "sha256": digest(root, package[key], cache)}
                except (OSError, ValueError) as exc:
                    failures.append({"field": key, "issue": str(exc)})
        report, source_count = {}, 0
        source_state = "snapshot-only-no-source-manifest"
        if package.get("report") is not None:
            try:
                report = read_public_json(root, package["report"])
                sources = report.get("source_hashes")
                if not isinstance(sources, dict) or not sources:
                    raise ValueError("Missing declared source hashes")
                source_count = len(sources)
                for name, expected in sources.items():
                    if (not isinstance(expected, str) or len(expected) != 64
                            or any(c not in "0123456789abcdef" for c in expected)):
                        failures.append({"field": "source_hashes", "path": name, "issue": "Invalid SHA-256"})
                        continue
                    try:
                        actual = digest(root, name, cache)
                        if actual != expected:
                            changed.append({"path": name, "expected_sha256": expected, "actual_sha256": actual})
                    except (OSError, ValueError) as exc:
                        failures.append({"field": "source_hashes", "path": name, "issue": str(exc)})
                source_state = "source-changed-rebuild-required" if changed else "declared-source-hashes-match"
            except (OSError, ValueError) as exc:
                failures.append({"field": "report", "issue": str(exc)})
        if failures:
            source_state = "source-check-incomplete"
        artifact_state, artifact_count = "not-declared", 0
        if package.get("manifest") is not None:
            try:
                manifest = read_public_json(root, package["manifest"])
                if manifest.get("report_hash") != report.get("report_hash") or not manifest.get("report_hash"):
                    raise ValueError("Artifact manifest/report identity mismatch")
                declared = manifest.get("artifacts")
                if not isinstance(declared, dict) or not declared:
                    raise ValueError("Missing declared artifact hashes")
                for name, expected in declared.items():
                    if (not isinstance(name, str) or not name or "/" in name or "\\" in name
                            or name in {".", ".."} or name.startswith(".")
                            or not isinstance(expected, str) or len(expected) != 64
                            or any(c not in "0123456789abcdef" for c in expected)):
                        raise ValueError("Invalid same-package artifact path or SHA-256")
                    relative = (PurePosixPath(package["manifest"]).parent/name).as_posix()
                    actual = digest(root, relative, cache)
                    artifact_count += 1
                    if actual != expected:
                        failures.append({"field": "manifest", "path": relative, "issue": "Declared artifact hash changed"})
                artifact_state = "artifact-changed" if any(f["field"] == "manifest" for f in failures) else "declared-artifact-hashes-match"
            except (OSError, ValueError) as exc:
                artifact_state = "artifact-check-incomplete"
                failures.append({"field": "manifest", "issue": str(exc)})
        raw_result = None
        raw_state = ("not-required-no-new-viewer" if package.get("role") == "data-only-no-new-viewer"
                     and package.get("viewer") is None else "not-imported")
        if package.get("raw_result") is not None:
            try:
                raw_result = {"path": package["raw_result"], "sha256": digest(root, package["raw_result"], cache)}
                raw_state = "present-unverified"
            except (OSError, ValueError) as exc:
                raw_state = "unavailable"
                failures.append({"field": "raw_result", "issue": str(exc)})
        results.append({
            "id": package["id"], "label": package.get("label", package["id"]), "role": package.get("role"),
            "check_scope": package.get("check_scope", "current"),
            "source_state": source_state, "declared_sources": source_count, "changed_sources": changed,
            "artifact_state": artifact_state, "declared_artifacts": artifact_count,
            "issues": failures, "artifacts": artifacts, "design_adopted": report.get("adopted", "unknown"),
            "owner_reported_run": package.get("owner_reported_run"),
            "owner_reported_status": package.get("owner_reported_status"),
            "raw_result_state": raw_state, "raw_result": raw_result,
            "rendered_qa_acceptance": "not-verified-by-this-index",
            "professional_approval": "unknown",
        })
    return {"schema": "house-project-status-check-v1", "index_updated_at": index.get("updated_at"),
        "default_package": index["default_package"], "packages": results, "work_items": index.get("work_items", []),
        "sources_hashed": len(cache), "writes_performed": False, "browser_started": False,
        "scope": "Declared source/optional artifact hashes and file presence only; no report seal, render, product or design approval"}


def source_checks_current(result: dict, *, include_history: bool = False) -> bool:
    return all(not p["issues"] and not p["changed_sources"]
               and (p["role"] == "history-reference" or p["source_state"] == "declared-source-hashes-match")
               for p in result["packages"] if include_history or p.get("check_scope", "current") == "current")


def render_status(result: dict) -> str:
    lines = ["# 專案來源與驗收索引（唯讀）", "",
        "只查宣告來源／有提供的產物雜湊與檔案存在；不驗報告封印、不生成圖、不啟動瀏覽器、不接受QA或採用方案。", "",
        "--check預設只要求現行規劃來源相符；歷史差異照列，--include-history才一併作為退出碼條件。", "",
        "| 入口 | 範圍 | 來源狀態 | 已宣告來源數 | 產物狀態 | 原始QA |", "| --- | --- | --- | ---: | --- | --- |"]
    for package in result["packages"]:
        label = package["label"].replace("|", "／")
        lines.append(f"| {label} | {package.get('check_scope', 'current')} | {package['source_state']} | {package['declared_sources']} | {package.get('artifact_state', 'not-declared')} | {package['raw_result_state']} |")
    if any(p["changed_sources"] or p["issues"] for p in result["packages"]):
        lines += ["", "## 來源差異／待補檔案", ""]
    for package in result["packages"]:
        for changed in package["changed_sources"]:
            lines.append(f"- {package['id']}：來源已改 `{changed['path']}`，舊結果不沿用。")
        for issue in package["issues"]:
            location = " `"+issue["path"]+"`" if issue.get("path") else ""
            lines.append(f"- {package['id']}：{issue['field']}{location}：{issue['issue']}")
    lines += ["", "屋主回報passed與文件歷史紀錄不等於本次來源驗證；有原始result也仍需專用驗證器與截圖目視。",
        "來源更動先釐清上游重建與鎖定快照，不自動重產、不只更新預期雜湊、不盲跑瀏覽器。"]
    return "\n".join(lines) + "\n"
