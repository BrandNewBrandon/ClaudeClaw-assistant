"""Response cache and per-chat cooldown tracker.

ResponseCache — avoids redundant Claude calls for identical repeated messages.
CooldownTracker — enforces a minimum interval between calls per chat.

Both are in-memory only (no persistence); they reset on restart, which is fine
since the goal is preventing rapid-fire duplicates within a session, not across
restarts.
"""
from __future__ import annotations

import logging
import time
from typing import Tuple

LOGGER = logging.getLogger(__name__)

# Maximum number of entries the cache will hold before evicting oldest
_DEFAULT_MAX_ENTRIES = 500


class ResponseCache:
    """TTL-keyed response cache keyed by (chat_id, agent, normalised message text)."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        # key -> (reply_text, expiry_timestamp)
        self._store: dict[Tuple[str, str, str], tuple[str, float]] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(chat_id: str, agent: str, message: str) -> Tuple[str, str, str]:
        return (chat_id, agent, message.lower().strip())

    def get(self, chat_id: str, agent: str, message: str) -> str | None:
        """Return cached reply, or None on miss/expiry."""
        key = self._make_key(chat_id, agent, message)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        reply, expiry = entry
        if time.monotonic() >= expiry:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return reply

    def set(self, chat_id: str, agent: str, message: str, reply: str) -> None:
        """Store a reply. Overwrites any existing entry. Evicts oldest if full."""
        self._evict_expired()
        if len(self._store) >= self._max_entries:
            self._evict_oldest()
        key = self._make_key(chat_id, agent, message)
        self._store[key] = (reply, time.monotonic() + self._ttl)

    def invalidate(self, chat_id: str, agent: str, message: str) -> None:
        """Remove a specific entry (e.g. after a slash command that changes state)."""
        self._store.pop(self._make_key(chat_id, agent, message), None)

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]

    def _evict_oldest(self) -> None:
        """Remove the oldest entry by expiry time."""
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k][1])
        del self._store[oldest_key]

    @property
    def stats(self) -> dict[str, int]:
        """Return cache hit/miss statistics."""
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}


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
