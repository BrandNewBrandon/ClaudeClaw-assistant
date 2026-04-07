"""Approval gate for potentially dangerous tool calls (e.g. run_command).

When Claude wants to run a shell command the request is held here and the
user is asked to confirm (YES / NO) before anything executes.  On channels
that support inline keyboards (Telegram), Approve/Deny buttons are shown
instead.
"""
from __future__ import annotations

import secrets
import threading
from typing import NamedTuple


class _Key(NamedTuple):
    surface: str
    account_id: str
    chat_id: str


class _PendingApproval(NamedTuple):
    command: str
    approval_id: str


class ApprovalStore:
    """Thread-safe store for pending command approvals."""

    def __init__(self) -> None:
        self._pending: dict[_Key, _PendingApproval] = {}
        self._by_id: dict[str, _Key] = {}  # approval_id -> key (reverse lookup)
        self._lock = threading.Lock()

    def request(self, surface: str, account_id: str, chat_id: str, command: str) -> tuple[str, str]:
        """Record a pending approval.

        Returns ``(message_text, approval_id)`` — the caller decides whether
        to show inline keyboard buttons or plain text.
        """
        approval_id = secrets.token_hex(4)  # 8-char hex string
        key = _Key(surface, account_id, chat_id)
        with self._lock:
            # Clear any previous pending approval for the same key
            old = self._pending.pop(key, None)
            if old is not None:
                self._by_id.pop(old.approval_id, None)
            self._pending[key] = _PendingApproval(command, approval_id)
            self._by_id[approval_id] = key
        preview = command if len(command) <= 400 else command[:400] + "..."
        message = (
            "Approval required before running this command:\n\n"
            f"{preview}\n\n"
            "Reply YES to execute or NO to cancel."
        )
        return message, approval_id

    def has_pending(self, surface: str, account_id: str, chat_id: str) -> bool:
        with self._lock:
            return _Key(surface, account_id, chat_id) in self._pending

    def pop(self, surface: str, account_id: str, chat_id: str) -> str | None:
        """Return and remove the pending command, or None if none exists."""
        with self._lock:
            entry = self._pending.pop(_Key(surface, account_id, chat_id), None)
            if entry is None:
                return None
            self._by_id.pop(entry.approval_id, None)
            return entry.command

    def resolve_by_id(self, approval_id: str, *, approved: bool) -> tuple[_Key, str] | None:
        """Look up a pending approval by its short ID.

        Returns ``(key, command)`` if found, else ``None``.  The entry is
        removed from the store regardless of whether it was approved or denied.
        """
        with self._lock:
            key = self._by_id.pop(approval_id, None)
            if key is None:
                return None
            entry = self._pending.pop(key, None)
            if entry is None:
                return None
            return key, entry.command
