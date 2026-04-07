"""Approval gate for potentially dangerous tool calls (e.g. run_command).

When Claude wants to run a shell command the request is held here and the
user is asked to confirm (YES / NO) before anything executes.
"""
from __future__ import annotations

import threading
from typing import NamedTuple


class _Key(NamedTuple):
    surface: str
    account_id: str
    chat_id: str


class ApprovalStore:
    """Thread-safe store for pending command approvals."""

    def __init__(self) -> None:
        self._pending: dict[_Key, str] = {}
        self._lock = threading.Lock()

    def request(self, surface: str, account_id: str, chat_id: str, command: str) -> str:
        """Record a pending approval and return the message to show the user."""
        with self._lock:
            self._pending[_Key(surface, account_id, chat_id)] = command
        preview = command if len(command) <= 400 else command[:400] + "…"
        return (
            "⚠️ Approval required before running this command:\n\n"
            f"{preview}\n\n"
            "Reply YES to execute or NO to cancel."
        )

    def has_pending(self, surface: str, account_id: str, chat_id: str) -> bool:
        with self._lock:
            return _Key(surface, account_id, chat_id) in self._pending

    def pop(self, surface: str, account_id: str, chat_id: str) -> str | None:
        """Return and remove the pending command, or None if none exists."""
        with self._lock:
            return self._pending.pop(_Key(surface, account_id, chat_id), None)
