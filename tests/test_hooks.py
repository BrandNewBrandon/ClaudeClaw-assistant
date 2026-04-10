from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from app.hooks import HookRegistry


def test_register_and_emit() -> None:
    """Registered handler is called with correct event data."""
    registry = HookRegistry()
    calls: list[dict[str, Any]] = []

    registry.register("test_event", lambda e: calls.append(e))
    registry.emit("test_event", key="value")

    assert len(calls) == 1
    assert calls[0]["event"] == "test_event"
    assert calls[0]["key"] == "value"
    assert "timestamp" in calls[0]


def test_emit_unknown_event_is_noop() -> None:
    """Emitting an event with no handlers doesn't crash."""
    registry = HookRegistry()
    registry.emit("nonexistent_event", data="ignored")


def test_handler_exception_does_not_crash_emit() -> None:
    """A failing handler doesn't prevent other handlers from running."""
    registry = HookRegistry()
    calls: list[str] = []

    def bad_handler(e: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    def good_handler(e: dict[str, Any]) -> None:
        calls.append("ok")

    registry.register("test", bad_handler)
    registry.register("test", good_handler)
    registry.emit("test")

    assert calls == ["ok"]


def test_handler_count_and_registered_events() -> None:
    registry = HookRegistry()

    registry.register("alpha", lambda e: None)
    registry.register("alpha", lambda e: None)
    registry.register("beta", lambda e: None)

    assert registry.handler_count == 3
    assert registry.registered_events() == ["alpha", "beta"]


def test_load_from_directory(tmp_path: Path) -> None:
    """Hook files in a directory are discovered and loaded."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "my_hook.py").write_text(
        "from app.hooks import hook\n\n"
        "@hook('test_load')\n"
        "def on_test(event):\n"
        "    pass\n",
        encoding="utf-8",
    )

    registry = HookRegistry()
    count = registry.load_from_directory(hooks_dir)

    assert count == 1
    assert "test_load" in registry.registered_events()


def test_load_from_directory_skips_underscore_files(tmp_path: Path) -> None:
    """Files starting with _ are not loaded."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "_private.py").write_text(
        "from app.hooks import hook\n\n"
        "@hook('should_not_load')\n"
        "def secret(event):\n"
        "    pass\n",
        encoding="utf-8",
    )

    registry = HookRegistry()
    count = registry.load_from_directory(hooks_dir)

    assert count == 0
    assert registry.handler_count == 0


def test_load_from_nonexistent_directory(tmp_path: Path) -> None:
    """Loading from a missing directory returns 0 and doesn't crash."""
    registry = HookRegistry()
    count = registry.load_from_directory(tmp_path / "no_such_dir")

    assert count == 0


def test_emit_async_fires_handler() -> None:
    """emit_async runs handler in a background thread."""
    registry = HookRegistry()
    received = threading.Event()

    def handler(e: dict[str, Any]) -> None:
        received.set()

    registry.register("async_test", handler)
    registry.emit_async("async_test")

    assert received.wait(timeout=2.0), "Handler was not called within timeout"
