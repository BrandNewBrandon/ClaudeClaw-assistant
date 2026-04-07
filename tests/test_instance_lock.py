from __future__ import annotations

import subprocess
from pathlib import Path

from app.instance_lock import InstanceLock, InstanceLockError


def test_instance_lock_acquires_and_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "runtime.lock"
    lock = InstanceLock(lock_path)

    lock.acquire()
    assert lock_path.exists()

    lock.release()
    assert not lock_path.exists()


def test_instance_lock_clears_stale_lock_with_dead_pid(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "runtime.lock"
    lock_path.write_text("999999\n", encoding="utf-8")

    monkeypatch.setattr("app.instance_lock._is_process_running", lambda pid: False)

    lock = InstanceLock(lock_path)
    lock.acquire()

    assert lock_path.exists()
    assert lock_path.read_text(encoding="utf-8").strip().isdigit()

    lock.release()


def test_instance_lock_raises_when_live_lock_exists(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "runtime.lock"
    lock_path.write_text("1234\n", encoding="utf-8")

    monkeypatch.setattr("app.instance_lock._is_process_running", lambda pid: True)

    lock = InstanceLock(lock_path)

    try:
        lock.acquire()
    except InstanceLockError as exc:
        assert "Lock file exists" in str(exc)
    else:
        raise AssertionError("Expected InstanceLockError")


def test_instance_lock_windows_process_check_handles_missing_pid(monkeypatch) -> None:
    monkeypatch.setattr("app.instance_lock.os.name", "nt")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout='INFO: No tasks are running which match the specified criteria.\n', stderr='')

    monkeypatch.setattr("app.instance_lock.subprocess.run", fake_run)

    from app.instance_lock import _is_process_running

    assert _is_process_running(999999) is False
