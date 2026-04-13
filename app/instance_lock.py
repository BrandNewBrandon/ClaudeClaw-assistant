from __future__ import annotations

import os
import subprocess
from pathlib import Path


class InstanceLockError(Exception):
    pass


class InstanceLock:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd: int | None = None

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_stale_lock_if_needed()
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        try:
            self._fd = os.open(str(self._lock_path), flags)
        except FileExistsError as exc:
            raise InstanceLockError(
                f"Another assistant-runtime instance appears to be running. Lock file exists: {self._lock_path}"
            ) from exc

        os.write(self._fd, str(os.getpid()).encode("utf-8"))

    def release(self) -> None:
        try:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    def _clear_stale_lock_if_needed(self) -> None:
        if not self._lock_path.exists():
            return

        lock_pid = self._read_lock_pid()
        if lock_pid is None:
            self._lock_path.unlink(missing_ok=True)
            return

        if not _is_process_running(lock_pid):
            self._lock_path.unlink(missing_ok=True)

    def _read_lock_pid(self) -> int | None:
        try:
            raw = self._lock_path.read_text(encoding="utf-8").strip()
            return int(raw) if raw else None
        except (OSError, ValueError):
            return None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # Use OpenProcess via ctypes — no subprocess, no flashing console.
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            exit_code = ctypes.c_ulong(0)
            still_running = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) != 0 and exit_code.value == 259  # STILL_ACTIVE
            kernel32.CloseHandle(handle)
            return bool(still_running)
        except Exception:  # noqa: BLE001
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = (result.stdout or "").strip().lower()
            if result.returncode != 0 or not output:
                return False
            return "no tasks are running" not in output and "info:" not in output
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
