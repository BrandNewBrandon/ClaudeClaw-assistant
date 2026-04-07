from __future__ import annotations

import subprocess
from pathlib import Path

from app import app_paths
from app.assistant_cli import _is_process_running, _read_pid, _status_runtime


def test_read_pid_returns_none_for_missing_or_invalid_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pid"
    invalid = tmp_path / "invalid.pid"
    invalid.write_text("not-a-pid", encoding="utf-8")

    assert _read_pid(missing) is None
    assert _read_pid(invalid) is None


def test_status_runtime_reports_not_running_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv(app_paths.APP_ROOT_ENV, str(tmp_path / "app-root"))

    exit_code = _status_runtime()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "assistant-runtime is not running." in output
    assert "PID file:" in output
    assert "Log file:" in output


def test_status_runtime_reports_stale_runtime_state(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv(app_paths.APP_ROOT_ENV, str(tmp_path / "app-root"))
    app_paths.ensure_runtime_dirs()
    pid_path = app_paths.get_runtime_pid_file()
    pid_path.write_text("999999\n", encoding="utf-8")

    exit_code = _status_runtime()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "stale runtime state" in output.lower()


def test_is_process_running_uses_tasklist_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("app.assistant_cli.os.name", "nt")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='"python.exe","1234","Console","1","10,000 K"\n', stderr='')

    monkeypatch.setattr("app.assistant_cli.subprocess.run", fake_run)

    assert _is_process_running(1234) is True


def test_is_process_running_handles_missing_windows_pid(monkeypatch) -> None:
    monkeypatch.setattr("app.assistant_cli.os.name", "nt")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='INFO: No tasks are running which match the specified criteria.\n', stderr='')

    monkeypatch.setattr("app.assistant_cli.subprocess.run", fake_run)

    assert _is_process_running(999999) is False
