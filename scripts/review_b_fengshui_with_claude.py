#!/usr/bin/env python3
"""Owner-authorized, tool-free Claude Code discussion; bounded and never a consensus stamp."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEF = ROOT/"Docs/claude-b-fengshui-brief-v1.md"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--timeout", type=float, default=17, help="Default17s; longer runs are for owner in a separate terminal")
    parser.add_argument("--output", type=Path, help="New or empty local output directory")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error("timeout must be 1..900 seconds")
    brief = args.brief.resolve().read_bytes()
    cli = shutil.which("claude")
    if not cli:
        print("Claude Code CLI unavailable; no installation, login or substitute attempted.")
        return 2
    out = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="house-b-claude-"))
    if args.output:
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            parser.error("output directory must be empty; never overwrite a previous response")
    (out/"prompt.md").write_bytes(brief)
    argv = [cli, "--print", "--output-format", "json", "--tools", "", "--permission-mode", "plan",
        "--disable-slash-commands", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--settings", '{"disableAllHooks":true}', "--no-session-persistence"]
    record = {"schema": "house-b-claude-discussion-result-v1", "prompt_sha256": hashlib.sha256(brief).hexdigest(),
        "prompt_file": str(args.brief), "status": "not-started", "cli": "Claude Code",
        "tools_enabled": False, "mcp_enabled": False, "hooks_enabled": False,
        "drawings_changed": False, "consensus": False, "professional_approval": "unknown", "timeout_seconds": args.timeout}
    started = time.monotonic()
    print(f"Research output: {out}\nTool-free B design discussion; no drawings changed.", flush=True)
    with (out/"stdout.json").open("wb") as stdout, (out/"stderr.log").open("wb") as stderr:
        proc = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            start_new_session=True)
        try:
            proc.communicate(brief, timeout=args.timeout)
            record["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            # Only this invocation's process group; never kill the owner's browsers or other Claude sessions.
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=.5)
            record.update(status="timeout-no-completed-discussion", exit_code=proc.returncode,
                retry="not-attempted", own_process_group_closed=proc.poll() is not None)
    if record["status"] != "timeout-no-completed-discussion":
        try:
            response = json.loads((out/"stdout.json").read_text())
            text = response.get("result", "")
            complete = proc.returncode == 0 and response.get("is_error") is not True and isinstance(text, str) and bool(text.strip())
            record.update(status="response-awaiting-codex-crosscheck" if complete else "cli-error-or-incomplete",
                cli_model=response.get("model"), cli_subtype=response.get("subtype"))
            if complete:
                (out/"response.md").write_text(text+"\n")
        except (ValueError, OSError):
            record["status"] = "no-valid-structured-response"
    record.update(elapsed_seconds=round(time.monotonic()-started, 3),
        stdout_sha256=hashlib.sha256((out/"stdout.json").read_bytes()).hexdigest())
    (out/"result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n")
    print(f"Status: {record['status']}\nResult: {out/'result.json'}")
    if record["status"] == "timeout-no-completed-discussion":
        print("Stopped this invocation; no automatic retry. Owner may run a longer discussion in another terminal.")
    return 0 if record["status"] == "response-awaiting-codex-crosscheck" else 1


if __name__ == "__main__":
    raise SystemExit(main())
