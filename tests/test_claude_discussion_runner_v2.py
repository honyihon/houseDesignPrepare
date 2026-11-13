import json

import pytest

from scripts import review_b_fengshui_with_claude_v2 as runner


def test_explicit_model_preserves_tool_free_flags_without_fallback():
    argv = runner.command("/usr/bin/claude", "provider/claude-exact-id")
    assert argv[argv.index("--model")+1] == "provider/claude-exact-id"
    assert argv[argv.index("--tools")+1] == ""
    assert argv[argv.index("--mcp-config")+1] == '{"mcpServers":{}}'
    assert argv[argv.index("--settings")+1] == '{"disableAllHooks":true}'
    assert {"--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"} <= set(argv)
    assert "--fallback-model" not in argv and "--dangerously-skip-permissions" not in argv


def test_error_true_overrides_misleading_success_subtype_and_retains_only_safe_diagnostics():
    raw = json.dumps({"subtype": "success", "is_error": True, "api_error_status": 400,
        "result": "API Error: 400 Invalid model name passed in model=claude-fable-5-2; private-secret",
        "credential_expires_at": "private-metadata", "session_id": "private-session"})
    record, text = runner.inspect_response(raw, 1)
    assert record["status"] == "cli-error-or-incomplete" and record["failure_category"] == "unsupported-model"
    assert record["api_error_http_status"] == 400 and record["cli_subtype"] == "success"
    assert text is None and "private-" not in json.dumps(record)


def test_success_does_not_guess_answering_model_from_usage_labels():
    record, text = runner.inspect_response(json.dumps({"is_error": False, "result": "研究回覆", "modelUsage": {"some-model": {}}}), 0)
    assert record["status"] == "response-awaiting-codex-crosscheck" and text == "研究回覆"
    assert record["cli_model"] is None


@pytest.mark.parametrize("raw,exit_code", [('not json', 0), ('[]', 0), ('{}', 0), ('{"result":"   "}', 0), ('{"result":"partial"}', 1)])
def test_invalid_empty_or_failed_output_cannot_create_a_completed_discussion(raw, exit_code):
    record, text = runner.inspect_response(raw, exit_code)
    assert record["status"] != "response-awaiting-codex-crosscheck" and text is None


def test_dry_run_does_not_start_cli_or_create_output(monkeypatch, tmp_path, capsys):
    brief = tmp_path/"brief.md"
    brief.write_text("研究資料", encoding="utf-8")
    output = tmp_path/"attempt"
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("No inference during dry run"))
    assert runner.main(["--brief", str(brief), "--model", "claude-exact-id", "--output", str(output), "--dry-run"]) == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["model_availability_verified"] is False


def test_existing_attempt_cannot_be_overwritten(monkeypatch, tmp_path):
    brief = tmp_path/"brief.md"
    brief.write_text("study")
    output = tmp_path/"attempt"
    output.mkdir()
    (output/"result.json").write_text("owner result")
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("Must not start CLI"))
    with pytest.raises(SystemExit) as exc:
        runner.main(["--brief", str(brief), "--model", "claude-exact-id", "--output", str(output)])
    assert exc.value.code == 2 and (output/"result.json").read_text() == "owner result"


def test_failed_cli_writes_no_response_or_secret_diagnostic(monkeypatch, tmp_path, capsys):
    brief = tmp_path/"brief.md"
    brief.write_text("study")
    output = tmp_path/"attempt"
    calls = []

    class FakeProcess:
        returncode = 1

        def __init__(self, argv, **kw):
            calls.append(argv)
            assert kw["start_new_session"]
            kw["stdout"].write(json.dumps({"is_error": True, "subtype": "success", "result": "Invalid model name; private-secret"}).encode())

        def communicate(self, body, timeout):
            assert body == b"study" and timeout == 17

    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    assert runner.main(["--brief", str(brief), "--model", "claude-exact-id", "--output", str(output)]) == 1
    record = json.loads((output/"result.json").read_text())
    assert record["failure_category"] == "unsupported-model" and record["requested_model"] == "claude-exact-id"
    assert not record["consensus"] and record["professional_approval"] == "unknown"
    assert len(calls) == 1 and not (output/"response.md").exists()
    assert "private-secret" not in capsys.readouterr().out and "private-secret" not in json.dumps(record)


def test_timeout_stops_only_own_process_group_without_retry(monkeypatch, tmp_path):
    brief = tmp_path/"brief.md"
    brief.write_text("study")
    output = tmp_path/"attempt"
    groups, calls = [], []

    class FakeProcess:
        pid = 987654
        returncode = None

        def __init__(self, argv, **kw):
            calls.append(argv)
            assert kw["start_new_session"]

        def communicate(self, body, timeout):
            raise runner.subprocess.TimeoutExpired("claude", timeout)

        def wait(self, timeout):
            self.returncode = -15
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    # This fake-process harness exercises the WSL/POSIX group API on Windows CI too.
    monkeypatch.setattr(runner.os, "killpg", lambda pid, sig: groups.append((pid, sig)), raising=False)
    assert runner.main(["--brief", str(brief), "--model", "claude-exact-id", "--output", str(output)]) == 1
    record = json.loads((output/"result.json").read_text())
    assert record["status"] == "timeout-no-completed-discussion" and record["own_process_group_closed"]
    assert groups == [(987654, runner.signal.SIGTERM)] and len(calls) == 1
    assert not record["automatic_retry"] and not record["automatic_model_fallback"]
