"""Tests for `assistant watchdog` supervisor loop.

We don't spawn a real runtime. Instead, monkeypatch the helpers the
watchdog leans on (_read_pid, _is_process_running, _start_runtime,
time.sleep) and observe the loop behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app import assistant_cli


class _FakeClock:
    """Monotonic clock that advances only when the watchdog calls time.sleep()."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pids: list[int | None],
    alive: dict[int, bool],
    starts: list[float],
    clock: _FakeClock,
) -> None:
    """Plug fakes into the assistant_cli module for one watchdog test."""
    pid_iter = iter(pids)

    def fake_read_pid(_path: Path) -> int | None:
        try:
            return next(pid_iter)
        except StopIteration:
            raise KeyboardInterrupt  # terminate the loop deterministically

    monkeypatch.setattr(assistant_cli, "_read_pid", fake_read_pid)
    monkeypatch.setattr(
        assistant_cli, "_is_process_running", lambda pid: alive.get(pid, False)
    )
    monkeypatch.setattr(assistant_cli, "ensure_runtime_dirs", lambda: None)

    def fake_start(_project_root: Path, **_kwargs: Any) -> int:
        starts.append(clock.now)
        # After a start, assume the next _read_pid returns an alive pid
        # unless the test queued something else.
        return 0

    monkeypatch.setattr(assistant_cli, "_start_runtime", fake_start)
    monkeypatch.setattr(assistant_cli.time, "sleep", clock.sleep)
    monkeypatch.setattr(assistant_cli.time, "monotonic", clock.monotonic)


def test_watchdog_restarts_when_pid_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First poll: pid file missing → restart. Second poll: pid alive → idle."""
    clock = _FakeClock()
    starts: list[float] = []
    _install_fakes(
        monkeypatch,
        pids=[None, 12345, 12345],  # missing → alive → alive → KeyboardInterrupt
        alive={12345: True},
        starts=starts,
        clock=clock,
    )

    rc = assistant_cli._cmd_watchdog(tmp_path, interval=5.0, max_restarts=3, window=60.0)
    assert rc == 0
    assert len(starts) == 1


def test_watchdog_restarts_when_pid_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pid file exists but PID is dead → restart."""
    clock = _FakeClock()
    starts: list[float] = []
    _install_fakes(
        monkeypatch,
        pids=[111, 222],  # dead → alive → KeyboardInterrupt
        alive={111: False, 222: True},
        starts=starts,
        clock=clock,
    )

    rc = assistant_cli._cmd_watchdog(tmp_path, interval=5.0, max_restarts=3, window=60.0)
    assert rc == 0
    assert len(starts) == 1


def test_watchdog_bails_after_max_restarts_in_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime flaps faster than window allows → watchdog gives up with rc=1."""
    clock = _FakeClock()
    starts: list[float] = []
    # pid always None → runtime is always dead → watchdog keeps restarting.
    # After max_restarts restarts within the window, it should return 1.
    _install_fakes(
        monkeypatch,
        pids=[None] * 50,
        alive={},
        starts=starts,
        clock=clock,
    )

    rc = assistant_cli._cmd_watchdog(tmp_path, interval=5.0, max_restarts=3, window=60.0)
    assert rc == 1
    assert len(starts) == 3  # bailed out on the 4th iteration


def test_watchdog_forgets_restarts_outside_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restarts that drop out of the rolling window don't count toward the cap."""
    clock = _FakeClock()
    starts: list[float] = []
    # Big interval: each restart ages out of the window before the next check.
    _install_fakes(
        monkeypatch,
        pids=[None, None, None, None],  # always dead, four polls then KI
        alive={},
        starts=starts,
        clock=clock,
    )

    rc = assistant_cli._cmd_watchdog(
        tmp_path, interval=120.0, max_restarts=3, window=60.0
    )
    # interval=120s, window=60s → every prior restart falls out before next check,
    # so the loop never hits the cap. It runs out of queued pids and exits via KI.
    assert rc == 0
    assert len(starts) == 4
