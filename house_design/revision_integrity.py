from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from house_design.contracts import (
    ROOT,
    ContractError,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
)

REVISION_ROOT = ROOT / "inputs/revisions"
REVISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def revision_manifest_content_hash(manifest: dict[str, Any]) -> str:
    """Seal every persisted manifest field except the seal itself."""

    return stable_hash({key: value for key, value in manifest.items() if key != "content_hash"})


def revision_dir(revision_id: str, root: Path = REVISION_ROOT) -> Path:
    if not REVISION_ID_RE.fullmatch(revision_id):
        raise ContractError("revision id may contain only letters, digits, dot, underscore and dash")
    return root / revision_id


def reference_path(reference: Any) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    path = Path(reference)
    return path if path.is_absolute() else ROOT / path


def _source_recovery(directory: Path, manifest: dict[str, Any]) -> tuple[dict[int, Path], list[str]]:
    """Resolve audited historical copies without changing any manifest digest.

    A recovery is not a waiver: the archived bytes must match the original
    source digest, and live-source success must not hide damaged recovery data.
    Paths are relative to this revision's source directory, never external.
    """
    record_path = directory / "source-recovery.json"
    if not record_path.exists():
        return {}, []
    errors: list[str] = []
    try:
        record = read_json(record_path)
        if record.get("schema") != "house-revision-source-recovery-v1":
            errors.append("invalid recovery schema")
        if record.get("revision_id") != manifest.get("revision_id"):
            errors.append("recovery revision id differs")
        if record.get("original_manifest_sha256") != sha256_file(directory / "manifest.json"):
            errors.append("recovery is not bound to the original manifest bytes")
        if record.get("content_hash") != stable_hash({k: v for k, v in record.items() if k != "content_hash"}):
            errors.append("recovery seal differs")
        for key in ("recovered_at", "reason"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                errors.append(f"recovery {key} is required")
        entries = record.get("sources")
        if not isinstance(entries, list) or not entries:
            return {}, [*errors, "recovery sources must be a non-empty array"]
        paths: dict[int, Path] = {}
        sources = manifest.get("sources")
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append("recovery source must be an object")
                continue
            index = entry.get("source_index")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not isinstance(sources, list)
                or index < 0
                or index >= len(sources)
                or index in paths
            ):
                errors.append("invalid or duplicate recovery source index")
                continue
            source = sources[index]
            if not isinstance(source, dict):
                errors.append("original source must be an object")
                continue
            if entry.get("original_file") != source.get("file") or entry.get("sha256") != source.get("sha256"):
                errors.append(f"source[{index}] recovery does not match original reference and digest")
            origin = entry.get("origin")
            if (
                not isinstance(origin, dict)
                or origin.get("type") != "git_commit"
                or not re.fullmatch(r"[0-9a-f]{40}", str(origin.get("commit") or ""))
                or origin.get("path") != source.get("file")
            ):
                errors.append(f"source[{index}] recovery needs exact Git commit and original path")
            archive = entry.get("archived_file")
            if not isinstance(archive, str) or not archive.strip() or Path(archive).is_absolute():
                errors.append(f"source[{index}] archive must be a relative source path")
                continue
            path = (directory / archive).resolve()
            source_root = (directory / "source").resolve()
            if not path.is_relative_to(source_root) or not source_root.is_relative_to(directory.resolve()):
                errors.append(f"source[{index}] archive escapes revision source directory")
                continue
            paths[index] = path
            if not path.is_file() or sha256_file(path) != source.get("sha256"):
                errors.append(f"source[{index}] archived bytes differ from original digest")
        return paths, errors
    except (ContractError, OSError, ValueError, TypeError, AttributeError) as exc:
        return {}, [f"invalid source recovery: {exc}"]


def verify_revision_integrity(revision_id: str, root: Path = REVISION_ROOT) -> dict[str, Any]:
    """Verify that an immutable revision still matches every stored digest."""

    directory = revision_dir(revision_id, root)
    manifest = read_json(directory / "manifest.json")
    checks: list[dict[str, Any]] = []

    def check(name: str, valid: bool, message: str, **details: Any) -> None:
        item: dict[str, Any] = {"name": name, "valid": valid, "message": message}
        if details:
            item["details"] = details
        checks.append(item)

    manifest_revision = manifest.get("revision_id")
    check(
        "manifest_revision_id",
        manifest_revision == revision_id,
        "manifest revision_id matches the requested immutable directory"
        if manifest_revision == revision_id
        else f"manifest revision_id is {manifest_revision!r}; expected {revision_id!r}",
    )

    recovered, recovery_errors = _source_recovery(directory, manifest)
    if (directory / "source-recovery.json").exists():
        check(
            "source_recovery",
            not recovery_errors,
            "audited historical sources match the original manifest"
            if not recovery_errors
            else "; ".join(recovery_errors),
        )

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        check("sources", False, "manifest sources must be an array")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                check(f"source[{index}]", False, "source record must be an object")
                continue
            path = reference_path(source.get("file"))
            expected = source.get("sha256")
            exists = path is not None and path.is_file()
            actual = sha256_file(path) if exists and path is not None else None
            original_actual = actual
            recovered_path = recovered.get(index) if not recovery_errors else None
            if recovered_path is not None:
                path = recovered_path
                exists = path.is_file()
                actual = sha256_file(path) if exists else None
            valid = bool(exists and isinstance(expected, str) and expected == actual)
            check(
                f"source[{index}]",
                valid,
                "source digest matches" if valid else "source file is missing or its SHA-256 does not match",
                file=source.get("file"),
                expected_sha256=expected,
                actual_sha256=actual,
                verification_source="audited_historical_copy" if recovered_path else "manifest_reference",
                verified_file=str(path) if path is not None else None,
                live_reference_sha256=original_actual,
            )

    mapping = manifest.get("mapping")
    if mapping is not None:
        if not isinstance(mapping, dict):
            check("mapping", False, "mapping record must be an object or null")
        else:
            path = reference_path(mapping.get("file"))
            expected = mapping.get("sha256")
            exists = path is not None and path.is_file()
            actual = sha256_file(path) if exists and path is not None else None
            valid = bool(exists and isinstance(expected, str) and expected == actual)
            check(
                "mapping",
                valid,
                "mapping digest matches" if valid else "mapping file is missing or its SHA-256 does not match",
                file=mapping.get("file"),
                expected_sha256=expected,
                actual_sha256=actual,
            )

    model_path = reference_path(manifest.get("normalized_model"))
    expected_model_hash = manifest.get("normalized_model_sha256")
    model_exists = model_path is not None and model_path.is_file()
    actual_model_hash = sha256_file(model_path) if model_exists and model_path is not None else None
    model_hash_valid = bool(
        model_exists and isinstance(expected_model_hash, str) and expected_model_hash == actual_model_hash
    )
    check(
        "normalized_model_sha256",
        model_hash_valid,
        "normalized model digest matches"
        if model_hash_valid
        else "normalized model is missing, unsealed or its SHA-256 does not match",
        file=manifest.get("normalized_model"),
        expected_sha256=expected_model_hash,
        actual_sha256=actual_model_hash,
    )
    if model_exists and model_path is not None:
        try:
            model = read_json(model_path)
            model_revision = model.get("revision_id")
            check(
                "model_revision_id",
                model_revision == revision_id,
                "normalized model revision_id matches"
                if model_revision == revision_id
                else f"normalized model revision_id is {model_revision!r}; expected {revision_id!r}",
            )
        except ContractError as exc:
            check("model_revision_id", False, str(exc))
    else:
        check("model_revision_id", False, "normalized model is unavailable")

    expected_content_hash = manifest.get("content_hash")
    actual_content_hash = revision_manifest_content_hash(manifest)
    content_hash_valid = isinstance(expected_content_hash, str) and expected_content_hash == actual_content_hash
    check(
        "content_hash",
        content_hash_valid,
        "manifest seal matches" if content_hash_valid else "manifest content hash is missing or does not match",
        expected_sha256=expected_content_hash,
        actual_sha256=actual_content_hash,
    )
    errors = [item for item in checks if not item["valid"]]
    return {
        "schema": "house-revision-integrity-v1",
        "revision_id": revision_id,
        "checked_at": utc_now(),
        "valid": not errors,
        "checks": checks,
        "errors": errors,
    }
