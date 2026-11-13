#!/usr/bin/env python3
"""Bounded read-only repository inventory, public JSON and Markdown links; no runtime work."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 5000
MAX_FILE_BYTES = 20*1024*1024
MAX_DUPLICATE_BYTES = 200*1024*1024
LOCAL_PARTS = {"private", "node_modules", "__pycache__", ".venv", ".git", ".pytest_cache", ".worktrees"}


def local_only(name):
    path = Path(name)
    return (bool(LOCAL_PARTS.intersection(path.parts)) or path.name == "settings.local.json"
        or (path.name.startswith(".env") and not path.name.endswith(".example")))


def markdown_links(text):
    lines, fence = [], None
    for line in text.splitlines():
        token = re.match(r"^\s*(`{3,}|~{3,})", line)
        if token:
            char = token.group(1)[0]
            fence = None if fence == char else char if fence is None else fence
        elif fence is None:
            lines.append(line)
    for match in re.finditer(r"\]\(<?([^\s)>]+)>?(?:\s+\"[^\"]*\")?\)", "\n".join(lines)):
        raw = match.group(1)
        if raw.startswith("#") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw):
            continue
        path = unquote(re.split(r"[?#]", raw, maxsplit=1)[0])
        if path:
            yield raw, path


def repository_files(root):
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True, timeout=10)
    return list(dict.fromkeys(p for p in result.stdout.decode("utf-8").split("\0") if p))


def inspect(root, files=None):
    root = Path(root).resolve()
    files = repository_files(root) if files is None else list(files)
    if len(files) > MAX_FILES:
        raise ValueError("Repository inventory exceeds bounded file count; manual inspection needed")
    issues, infos, sizes = [], [], defaultdict(list)
    extensions, top = Counter(), Counter()
    total_bytes, json_count, markdown_count, link_count = 0, 0, 0, 0
    for name in files:
        path = root/name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(root) or ".." in Path(name).parts:
            issues.append({"path": name, "kind": "outside-project-path"})
            continue
        if local_only(name):
            issues.append({"path": name, "kind": "local-only-file-in-public-index"})
            continue  # Never read local credentials, private conditions or permissions.
        if not path.is_file() or path.is_symlink():
            issues.append({"path": name, "kind": "missing-or-symlink-file"})
            continue
        size = path.stat().st_size
        extensions[path.suffix or "[no-extension]"] += 1
        top[Path(name).parts[0]] += 1
        total_bytes += size
        if size > MAX_FILE_BYTES:
            infos.append({"path": name, "kind": "too-large-for-content-check", "bytes": size})
            continue
        if size > 1000:
            sizes[size].append(name)
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8-sig"))
                json_count += 1
            if path.suffix == ".md":
                markdown_count += 1
                for raw, target in markdown_links(path.read_text(encoding="utf-8-sig")):
                    link_count += 1
                    destination = (path.parent/target).resolve()
                    if not destination.is_relative_to(root):
                        issues.append({"path": name, "kind": "document-link-outside-project", "link": raw})
                    elif local_only(destination.relative_to(root).as_posix()):
                        issues.append({"path": name, "kind": "document-links-private-data", "link": raw})
                    elif not destination.exists():
                        issues.append({"path": name, "kind": "missing-local-document-link", "link": raw})
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append({"path": name, "kind": "invalid-public-text-or-json", "detail": type(exc).__name__})
    duplicate_budget = 0
    duplicates = []
    for size, candidates in sorted(sizes.items()):
        if len(candidates) < 2:
            continue
        if duplicate_budget+size*len(candidates) > MAX_DUPLICATE_BYTES:
            infos.append({"kind": "duplicate-scan-budget-reached"})
            break
        hashes = defaultdict(list)
        for name in candidates:
            hashes[hashlib.sha256((root/name).read_bytes()).hexdigest()].append(name)
        duplicate_budget += size*len(candidates)
        duplicates.extend({"bytes_each": size, "paths": names, "action": "keep-until-generator-and-evidence-references-reviewed"}
            for names in hashes.values() if len(names) > 1)
    return {"schema": "house-repository-health-v1", "files_considered": len(files), "public_bytes": total_bytes,
        "top_directories": dict(top), "extensions": dict(extensions), "public_json_checked": json_count,
        "markdown_checked": markdown_count, "local_links_checked": link_count, "issues": issues,
        "informational": infos, "duplicate_groups": duplicates, "writes_performed": False,
        "browser_started": False, "scope": "Files/JSON syntax/local Markdown targets only; no code, schema, source-seal, rendered or design approval"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--json", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        result = inspect(args.root)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Repository inventory incomplete: "+str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"files": result["files_considered"], "JSON_syntax_checked": result["public_json_checked"],
            "markdown_checked": result["markdown_checked"], "local_links_checked": result["local_links_checked"],
            "issues": result["issues"], "duplicate_groups_kept": len(result["duplicate_groups"]),
            "informational": result["informational"], "writes_performed": False, "browser_started": False}, ensure_ascii=False))
    return 1 if args.check and result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
