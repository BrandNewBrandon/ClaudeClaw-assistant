"""Hooks — lightweight event-driven scripts for the assistant runtime.

Hooks allow users to run custom Python scripts when specific events occur
in the runtime, without modifying core code.

## Hook discovery

Hooks are Python files in a ``hooks/`` directory (inside the project root
or at ``~/.assistant/hooks/``).  Each file should define one or more
functions decorated with ``@hook(event_name)``.

## Supported events

- ``startup``         — runtime is starting up (after config loaded)
- ``shutdown``        — runtime is shutting down
- ``message_in``      — a user message was received
- ``message_out``     — the assistant sent a reply
- ``session_reset``   — a session was reset (/new, /reset, daily, idle)
- ``command``         — a slash command was executed
- ``compaction``      — session compaction occurred
- ``error``           — an error occurred during message handling
- ``tool_call``       — a tool was invoked (exec, web search, etc.)

## Hook file format

.. code-block:: python

    # hooks/my_hook.py
    from app.hooks import hook

    @hook("message_in")
    def on_message(event):
        print(f"Got message from {event['chat_id']}: {event['text'][:50]}")

    @hook("error")
    def on_error(event):
        # Send alert, log to file, etc.
        pass

## Event data

Each event is a plain dict with at least ``{"event": "event_name", "timestamp": "..."}``.
Additional keys depend on the event type (chat_id, agent, text, error, etc.).
"""
from __future__ import annotations

import importlib.util
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)

# Type alias for hook handlers
HookHandler = Callable[[dict[str, Any]], None]

# Module-level registry used by the @hook decorator
_decorator_registry: dict[str, list[HookHandler]] = defaultdict(list)


def hook(event: str) -> Callable[[HookHandler], HookHandler]:
    """Decorator to register a function as a hook handler.

    Usage::

        @hook("message_in")
        def on_message(event):
            print(event["text"])
    """
    def decorator(fn: HookHandler) -> HookHandler:
        _decorator_registry[event].append(fn)
        return fn
    return decorator


class HookRegistry:
    """Central registry and dispatcher for hook handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = defaultdict(list)
        self._lock = threading.Lock()

    def register(self, event: str, handler: HookHandler) -> None:
        """Register a handler for an event."""
        with self._lock:
            self._handlers[event].append(handler)

    def load_from_directory(self, hooks_dir: Path) -> int:
        """Discover and load hook files from a directory.

        Returns the number of handlers registered.
        """
        if not hooks_dir.exists():
            return 0

        count_before = sum(len(v) for v in self._handlers.values())

        for path in sorted(hooks_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                self._load_hook_file(path)
            except Exception:
                LOGGER.exception("Failed to load hook file: %s", path)

        count_after = sum(len(v) for v in self._handlers.values())
        loaded = count_after - count_before
        if loaded:
            LOGGER.info("Loaded %d hook handler(s) from %s", loaded, hooks_dir)
        return loaded

    def _load_hook_file(self, path: Path) -> None:
        """Import a single hook file and collect decorated handlers."""
        global _decorator_registry

        # Clear the decorator registry so we only capture this file's hooks
        old_registry = dict(_decorator_registry)
        _decorator_registry.clear()

        try:
            spec = importlib.util.spec_from_file_location(
                f"assistant_hook_{path.stem}", str(path)
            )
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Transfer decorated hooks to our registry
            with self._lock:
                for event, handlers in _decorator_registry.items():
                    self._handlers[event].extend(handlers)
                    LOGGER.debug(
                        "Registered %d handler(s) for '%s' from %s",
                        len(handlers), event, path.name,
                    )
        finally:
            # Restore the decorator registry
            _decorator_registry.clear()
            _decorator_registry.update(old_registry)

    def emit(self, event: str, **data: Any) -> None:
        """Fire an event, calling all registered handlers.

        Handlers run synchronously in the calling thread. Exceptions
        are caught and logged — a bad hook never crashes the runtime.
        """
        with self._lock:
            handlers = list(self._handlers.get(event, []))

        if not handlers:
            return

        event_data: dict[str, Any] = {
            "event": event,
            "timestamp": datetime.now().astimezone().isoformat(),
            **data,
        }

        for handler in handlers:
            try:
                handler(event_data)
            except Exception:
                LOGGER.exception(
                    "Hook handler %s.%s failed for event '%s'",
                    getattr(handler, "__module__", "?"),
                    getattr(handler, "__name__", "?"),
                    event,
                )

    def emit_async(self, event: str, **data: Any) -> None:
        """Fire an event in a background thread (non-blocking).

        Use for events where you don't want hook execution to slow
        down the main message handling path.
        """
        thread = threading.Thread(
            target=self.emit,
            args=(event,),
            kwargs=data,
            name=f"hook-{event}",
            daemon=True,
        )
        thread.start()

    @property
    def handler_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._handlers.values())

    def registered_events(self) -> list[str]:
        with self._lock:
            return sorted(self._handlers.keys())
