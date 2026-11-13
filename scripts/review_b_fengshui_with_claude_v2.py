#!/usr/bin/env python3
"""Explicit-model, tool-free Claude discussion; no fallback, retry or global setting edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def model_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise argparse.ArgumentTypeError("Use the exact supported model ID, without spaces or shell syntax")
    return value


def command(cli, model):
    return [cli, "--print", "--output-format", "json", "--model", model,
        "--tools", "", "--permission-mode", "plan", "--disable-slash-commands",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--settings", '{"disableAllHooks":true}', "--no-session-persistence"]


def inspect_response(raw, exit_code):
    """Summarize errors without echoing raw CLI/session/credential metadata."""
    try:
        response = json.loads(raw)
    except (ValueError, UnicodeError):
        return {"status": "no-valid-structured-response", "failure_category": "invalid-json"}, None
    if not isinstance(response, dict):
        return {"status": "no-valid-structured-response", "failure_category": "invalid-response-shape"}, None
    text = response.get("result")
    complete = exit_code == 0 and response.get("is_error") is not True and isinstance(text, str) and bool(text.strip())
    status = "response-awaiting-codex-crosscheck" if complete else "cli-error-or-incomplete"
    detail = text if isinstance(text, str) else ""
    unsupported = re.search(r"invalid model name|unknown model|model[^\n]{0,120}(?:not found|not supported|unavailable)", detail, re.I)
    category = None if complete else "unsupported-model" if unsupported else "cli-or-api-error-or-empty-response"
    http = response.get("api_error_status")
    if not isinstance(http, int) or not 400 <= http <= 599:
        http = None
    return {"status": status, "failure_category": category, "api_error_http_status": http,
        "cli_model": response.get("model") if isinstance(response.get("model"), str) else None,
        "cli_subtype": response.get("subtype") if isinstance(response.get("subtype"), str) else None,
        "cli_is_error": response.get("is_error") is True}, text if complete else None


def stop_own_process(proc):
    # This invocation starts its own group; never stop unrelated Claude/browser sessions.
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--model", type=model_name, required=True, help="Exact ID supported by your current API; no automatic substitute")
    parser.add_argument("--timeout", type=float, default=17, help="1..900 seconds; long work is owner-run in another terminal")
    parser.add_argument("--output", type=Path, help="New or empty local directory; existing results are never overwritten")
    parser.add_argument("--dry-run", action="store_true", help="Validate prompt/arguments without inference or file writes")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 900:
        parser.error("timeout must be 1..900 seconds")
    brief_path = args.brief.resolve()
    brief = brief_path.read_bytes()
    cli = shutil.which("claude")
    if not cli:
        print("Claude Code CLI unavailable; no installation, login or substitute attempted.")
        return 2
    if args.output and args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("output directory must be new or empty; never overwrite a previous attempt")
    if args.dry_run:
        print(json.dumps({"status": "prepared-without-inference", "requested_model": args.model,
            "prompt_sha256": hashlib.sha256(brief).hexdigest(), "model_availability_verified": False,
            "tools_enabled": False, "mcp_enabled": False, "hooks_enabled": False,
            "inference_requests": 0, "files_written": 0}, ensure_ascii=False))
        return 0
    out = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="house-b-claude-"))
    out.mkdir(parents=True, exist_ok=True)
    (out/"prompt.md").write_bytes(brief)
    record = {"schema": "house-b-claude-discussion-result-v2", "prompt_sha256": hashlib.sha256(brief).hexdigest(),
        "prompt_file": str(args.brief), "requested_model": args.model, "cli": "Claude Code",
        "status": "not-started", "tools_enabled": False, "mcp_enabled": False, "hooks_enabled": False,
        "drawings_changed": False, "consensus": False, "professional_approval": "unknown",
        "timeout_seconds": args.timeout, "automatic_retry": False, "automatic_model_fallback": False}
    started = time.monotonic()
    print(f"Research output: {out}\nRequested model: {args.model}\nTool-free B discussion; no drawings changed.", flush=True)
    with (out/"stdout.json").open("wb") as stdout, (out/"stderr.log").open("wb") as stderr:
        proc = subprocess.Popen(command(cli, args.model), cwd=ROOT, stdin=subprocess.PIPE,
            stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            proc.communicate(brief, timeout=args.timeout)
            record["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            stop_own_process(proc)
            record.update(status="timeout-no-completed-discussion", failure_category="timeout",
                exit_code=proc.returncode, own_process_group_closed=proc.poll() is not None)
    if record["status"] != "timeout-no-completed-discussion":
        details, text = inspect_response((out/"stdout.json").read_bytes(), record["exit_code"])
        record.update(details)
        if text is not None:
            (out/"response.md").write_text(text+"\n", encoding="utf-8")
    record.update(elapsed_seconds=round(time.monotonic()-started, 3),
        stdout_sha256=hashlib.sha256((out/"stdout.json").read_bytes()).hexdigest())
    (out/"result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Status: {record['status']}\nResult: {out/'result.json'}")
    if record.get("failure_category") == "unsupported-model":
        print("API rejected the selected model. Confirm the exact available model ID; keep this attempt and use a new output directory.")
    elif record.get("failure_category"):
        print(f"Failure category: {record['failure_category']}; private stdout/stderr retained. No automatic retry or model fallback.")
    return 0 if record["status"] == "response-awaiting-codex-crosscheck" else 1


if __name__ == "__main__":
    raise SystemExit(main())
