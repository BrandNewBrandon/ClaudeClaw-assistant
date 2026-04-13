"""Proactive system health monitors."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Callable

_NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # type: ignore[attr-defined]

LOGGER = logging.getLogger(__name__)

MonitorFn = Callable[[], str | None]
SendCallback = Callable[[str, str, str], None]


class MonitorRunner:
    """Runs registered monitors periodically and alerts on triggers."""

    def __init__(
        self,
        *,
        poll_interval: int = 300,
        cooldown_seconds: int = 3600,
    ) -> None:
        self._poll_interval = poll_interval
        self._cooldown_seconds = cooldown_seconds
        self._monitors: dict[str, MonitorFn] = {}
        self._send_callbacks: dict[str, SendCallback] = {}
        self._targets: dict[str, list[str]] = {}
        self._last_fired: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_monitor(self, name: str, fn: MonitorFn) -> None:
        self._monitors[name] = fn

    def register_sender(self, surface: str, callback: SendCallback) -> None:
        self._send_callbacks[surface] = callback

    def register_target(self, surface: str, chat_id: str) -> None:
        self._targets.setdefault(surface, [])
        if chat_id not in self._targets[surface]:
            self._targets[surface].append(chat_id)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="monitor-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                LOGGER.exception("MonitorRunner tick error")
            self._stop_event.wait(self._poll_interval)

    def tick(self) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        for name, fn in self._monitors.items():
            last = self._last_fired.get(name, 0.0)
            if now - last < self._cooldown_seconds:
                continue
            try:
                alert = fn()
            except Exception:
                LOGGER.exception("Monitor %s raised", name)
                continue
            if alert is None:
                continue
            self._last_fired[name] = now
            self._broadcast(f"[Monitor: {name}] {alert}")

    def _broadcast(self, text: str) -> None:
        for surface, chat_ids in self._targets.items():
            callback = self._send_callbacks.get(surface)
            if callback is None:
                continue
            for chat_id in chat_ids:
                try:
                    callback(surface, chat_id, text)
                except Exception:
                    LOGGER.exception("Failed to send monitor alert to %s:%s", surface, chat_id)

    def monitor_names(self) -> list[str]:
        return list(self._monitors.keys())


def disk_usage_monitor(*, threshold_percent: float = 90.0, path: str = "/") -> MonitorFn:
    """Factory: returns a monitor that alerts if disk usage exceeds threshold."""
    def check() -> str | None:
        usage = shutil.disk_usage(path)
        percent = (usage.used / usage.total) * 100
        if percent >= threshold_percent:
            free_gb = usage.free / (1024 ** 3)
            return f"Disk usage at {percent:.1f}% — {free_gb:.1f} GB free on {path}"
        return None
    return check


def process_count_monitor(*, threshold: int = 500) -> MonitorFn:
    """Factory: returns a monitor that alerts if process count is high."""
    def check() -> str | None:
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW_FLAGS,
            )
            count = len(result.stdout.strip().splitlines()) - 1
            if count >= threshold:
                return f"High process count: {count} processes running (threshold: {threshold})"
        except Exception as exc:
            logging.getLogger(__name__).debug("Process count check failed: %s", exc)
            return None
        return None
    return check
