"""Regression test: approved commands run off the channel polling thread.

Previously _handle_callback called execute_shell_command synchronously on
the Telegram poll loop, so a slow command froze every incoming message
and every other approval until it returned. Fix threads the command, and
this test pins that by monkeypatching execute_shell_command to sleep for
longer than the test's tolerance and asserting _handle_callback still
returns immediately.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import router as router_mod
from app.channels.base import ChannelCallback


class _FakeChannel:
    def __init__(self) -> None:
        self.callbacks_answered: list[tuple[str, str]] = []
        self.edits: list[tuple[str, int, str]] = []
        self.sends: list[tuple[str, str]] = []

    def answer_callback(self, callback_id: str, text: str) -> None:
        self.callbacks_answered.append((callback_id, text))

    def edit_message(self, chat_id: str, message_id: int, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    def send_message(self, chat_id: str, text: str) -> None:
        self.sends.append((chat_id, text))


class _FakeApprovalStore:
    def __init__(self, command: str) -> None:
        self._command = command

    def resolve_by_id(self, approval_id: str, *, approved: bool):
        return ("some-key", self._command)


class _FakeMemory:
    def __init__(self) -> None:
        self.appended: list[dict] = []

    def append_transcript(self, **kwargs) -> None:
        self.appended.append(kwargs)


def _make_router_stub(tmp_path: Path, *, command: str) -> router_mod.AssistantRouter:
    r = router_mod.AssistantRouter()
    r._config = SimpleNamespace(
        default_agent="main", chat_agent_map={}, routing={}, agents_dir=tmp_path,
        project_root=tmp_path, claude_working_directory_mode="project_root",
    )
    r._approval_store = _FakeApprovalStore(command)
    r._memory = _FakeMemory()
    # Stub out agent resolution / working dir — we don't exercise them here.
    r._resolve_agent_for_chat = lambda chat_id, account_id=None: ("main", "default")  # type: ignore[method-assign]
    r._resolve_working_directory = lambda agent_name: tmp_path  # type: ignore[method-assign]
    return r


def test_handle_callback_returns_before_slow_command_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Channel poll thread must NOT block on execute_shell_command."""
    slow_command_ran = threading_event()

    def slow_shell(cmd: str, *, cwd: str | None = None) -> str:
        # Simulate a slow shell command (what Get-ChildItem -Recurse was doing).
        time.sleep(2.0)
        slow_command_ran.set()
        return "done"

    monkeypatch.setattr(router_mod, "execute_shell_command", slow_shell)

    router = _make_router_stub(tmp_path, command="slow-cmd")
    channel = _FakeChannel()
    callback = ChannelCallback(
        update_id=1,
        chat_id="42",
        callback_id="cb-1",
        data="a:abc123",
        message_id=99,
    )

    t0 = time.monotonic()
    router._handle_callback("primary", callback, channel)
    elapsed = time.monotonic() - t0

    # Must return nearly instantly — definitely before the 2s sleep completes.
    assert elapsed < 0.5, f"_handle_callback blocked for {elapsed:.2f}s"
    # The ack fired immediately.
    assert channel.callbacks_answered == [("cb-1", "Command approved!")]
    # The "Running..." placeholder edit happened immediately.
    assert any("Running" in edit[2] for edit in channel.edits)
    # The command has not finished yet.
    assert not slow_command_ran.is_set()

    # Let the worker thread finish so the test doesn't leak it.
    assert slow_command_ran.wait(timeout=5.0)
    # Give the worker a moment to edit with the final result.
    for _ in range(20):
        if any("Output:" in edit[2] for edit in channel.edits):
            break
        time.sleep(0.05)
    assert any("Output:" in edit[2] and "done" in edit[2] for edit in channel.edits)


def threading_event():
    import threading
    return threading.Event()
