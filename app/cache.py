"""Response cache and per-chat cooldown tracker.

ResponseCache — avoids redundant Claude calls for identical repeated messages.
CooldownTracker — enforces a minimum interval between calls per chat.

Both are in-memory only (no persistence); they reset on restart, which is fine
since the goal is preventing rapid-fire duplicates within a session, not across
restarts.
"""
from __future__ import annotations

import time
from typing import Tuple


class ResponseCache:
    """TTL-keyed response cache keyed by (chat_id, normalised message text)."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        # key -> (reply_text, expiry_timestamp)
        self._store: dict[Tuple[str, str], tuple[str, float]] = {}

    @staticmethod
    def _make_key(chat_id: str, message: str) -> Tuple[str, str]:
        return (chat_id, message.lower().strip())

    def get(self, chat_id: str, message: str) -> str | None:
        """Return cached reply, or None on miss/expiry."""
        key = self._make_key(chat_id, message)
        entry = self._store.get(key)
        if entry is None:
            return None
        reply, expiry = entry
        if time.monotonic() >= expiry:
            del self._store[key]
            return None
        return reply

    def set(self, chat_id: str, message: str, reply: str) -> None:
        """Store a reply. Overwrites any existing entry."""
        key = self._make_key(chat_id, message)
        self._store[key] = (reply, time.monotonic() + self._ttl)

    def invalidate(self, chat_id: str, message: str) -> None:
        """Remove a specific entry (e.g. after a slash command that changes state)."""
        self._store.pop(self._make_key(chat_id, message), None)


class CooldownTracker:
    """Enforces a minimum elapsed time between Claude calls per chat."""

    def __init__(self, cooldown_seconds: float = 1.0) -> None:
        self._cooldown = cooldown_seconds
        self._last_call: dict[str, float] = {}

    def is_ready(self, chat_id: str) -> bool:
        """Return True if enough time has passed since the last call."""
        last = self._last_call.get(chat_id)
        if last is None:
            return True
        return time.monotonic() - last >= self._cooldown

    def seconds_remaining(self, chat_id: str) -> float:
        """Seconds until the cooldown expires (0.0 if already ready)."""
        last = self._last_call.get(chat_id)
        if last is None:
            return 0.0
        remaining = self._cooldown - (time.monotonic() - last)
        return max(0.0, remaining)

    def record(self, chat_id: str) -> None:
        """Mark that a Claude call was just made for this chat."""
        self._last_call[chat_id] = time.monotonic()
