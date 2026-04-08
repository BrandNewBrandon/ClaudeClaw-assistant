"""Automatic session reset triggers — daily and idle timeouts.

Modeled after :class:`ConsolidationThread`: a daemon thread that wakes
periodically and checks whether any session should be auto-reset.

Resets work by appending a compaction marker to the transcript, which
causes :meth:`MemoryStore.read_transcript_with_compaction` to start fresh
without deleting any raw history.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryStore
    from .sessions import SessionStore

LOGGER = logging.getLogger(__name__)


class SessionResetThread:
    """Daemon thread that fires daily and idle session resets."""

    def __init__(
        self,
        memory_store: MemoryStore,
        sessions: SessionStore,
        *,
        daily_hour: int | None = None,
        idle_minutes: int | None = None,
        last_activity: dict[str, float],
        active_agents: dict[str, str],
    ) -> None:
        self._memory = memory_store
        self._sessions = sessions
        self._daily_hour = daily_hour
        self._idle_minutes = idle_minutes
        self._last_activity = last_activity      # shared ref from router
        self._active_agents = active_agents      # session_key -> agent name
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_daily_date: str | None = None  # "YYYY-MM-DD"

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="session-reset",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "SessionResetThread started (daily_hour=%s, idle_minutes=%s)",
            self._daily_hour, self._idle_minutes,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_daily_reset()
                self._check_idle_reset()
            except Exception:
                LOGGER.exception("SessionResetThread unexpected error")
            # Check every 60 seconds
            self._stop_event.wait(60)

    def _check_daily_reset(self) -> None:
        if self._daily_hour is None:
            return

        now = datetime.now().astimezone()
        today = now.strftime("%Y-%m-%d")

        if self._last_daily_date == today:
            return
        if now.hour < self._daily_hour:
            return

        self._last_daily_date = today
        LOGGER.info("Daily session reset triggered for date=%s", today)

        # Reset all known sessions
        for session_key, agent in list(self._active_agents.items()):
            try:
                # Parse session key: "surface:account_id:chat_id"
                parts = session_key.split(":", 2)
                if len(parts) != 3:
                    continue
                surface, account_id, chat_id = parts

                self._memory.append_compaction_summary(
                    surface=surface,
                    account_id=account_id,
                    chat_id=chat_id,
                    agent=agent,
                    summary_text="[Session automatically reset — new day.]",
                    compacted_count=0,
                )
                LOGGER.info("Daily reset: session_key=%s agent=%s", session_key, agent)
            except Exception:
                LOGGER.exception("Daily reset failed for session_key=%s", session_key)

    def _check_idle_reset(self) -> None:
        if self._idle_minutes is None:
            return

        now = time.monotonic()
        idle_threshold = self._idle_minutes * 60

        for session_key, last_time in list(self._last_activity.items()):
            if now - last_time < idle_threshold:
                continue

            agent = self._active_agents.get(session_key)
            if not agent:
                continue

            try:
                parts = session_key.split(":", 2)
                if len(parts) != 3:
                    continue
                surface, account_id, chat_id = parts

                self._memory.append_compaction_summary(
                    surface=surface,
                    account_id=account_id,
                    chat_id=chat_id,
                    agent=agent,
                    summary_text="[Session automatically reset after idle timeout.]",
                    compacted_count=0,
                )
                # Remove from activity tracking so we don't reset again
                self._last_activity.pop(session_key, None)
                LOGGER.info(
                    "Idle reset: session_key=%s agent=%s (idle %d min)",
                    session_key, agent, self._idle_minutes,
                )
            except Exception:
                LOGGER.exception("Idle reset failed for session_key=%s", session_key)
