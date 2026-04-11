"""iMessage adapter — macOS only.

Reads incoming messages from the local Messages database
(``~/Library/Messages/chat.db``) and sends replies via AppleScript.

No external dependencies required — uses sqlite3 and subprocess from stdlib.

Config example
--------------
.. code-block:: json

    {
      "platform": "imessage",
      "token": "",
      "allowed_chat_ids": ["+15551234567", "user@icloud.com"]
    }

Requirements
------------
- macOS with Messages app signed in to iMessage
- Full Disk Access granted to the process (needed to read chat.db)
"""
from __future__ import annotations

import logging
import platform
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from .base import BaseChannel, ChannelError, ChannelMessage

LOGGER = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"


class IMessageChannel(BaseChannel):
    """iMessage adapter using local Messages database + AppleScript."""

    def __init__(
        self,
        allowed_chat_ids: list[str],
        poll_timeout_seconds: int = 30,
        *,
        db_path: Path | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        if platform.system() != "Darwin":
            raise ChannelError(
                "iMessage adapter is only available on macOS."
            )

        self._allowed = set(allowed_chat_ids)
        self._poll_timeout = poll_timeout_seconds
        self._poll_interval = poll_interval
        self._db_path = db_path or _DEFAULT_DB_PATH

        self._queue: Queue[ChannelMessage] = Queue()
        self._update_counter = 0
        self._counter_lock = threading.Lock()
        self._last_rowid = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── BaseChannel ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._db_path.exists():
            raise ChannelError(
                f"Messages database not found at {self._db_path}. "
                "Ensure Messages app is configured and Full Disk Access is granted."
            )
        # Initialize last_rowid to current max so we don't replay history
        self._last_rowid = self._get_max_rowid()
        LOGGER.info("IMessageChannel started, last_rowid=%d", self._last_rowid)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, name="imessage-poll", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get_updates(self) -> list[ChannelMessage]:
        messages: list[ChannelMessage] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except Empty:
                break
        if not messages:
            try:
                messages.append(self._queue.get(timeout=self._poll_timeout))
            except Empty:
                return []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except Empty:
                break
        return messages

    def send_message(self, chat_id: str, text: str) -> None:
        if not text or not text.strip():
            return
        for chunk in _split(text, 10000):
            self._send_imessage(chat_id, chunk)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Background thread: poll the Messages database for new messages."""
        while not self._stop_event.is_set():
            try:
                self._check_new_messages()
            except Exception:
                LOGGER.exception("iMessage poll error")
            self._stop_event.wait(self._poll_interval)

    def _get_max_rowid(self) -> int:
        """Get the highest ROWID in the message table."""
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            cursor = conn.execute("SELECT MAX(ROWID) FROM message")
            row = cursor.fetchone()
            conn.close()
            return int(row[0] or 0)
        except Exception:
            LOGGER.exception("Failed to read max ROWID from Messages DB")
            return 0

    def _check_new_messages(self) -> None:
        """Query for messages newer than last_rowid."""
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except Exception:
            LOGGER.exception("Failed to connect to Messages DB")
            return

        try:
            rows = conn.execute("""
                SELECT
                    m.ROWID,
                    m.text,
                    m.is_from_me,
                    m.date,
                    h.id AS handle_id
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.ROWID > ?
                  AND m.is_from_me = 0
                  AND m.text IS NOT NULL
                  AND m.text != ''
                ORDER BY m.ROWID ASC
            """, (self._last_rowid,)).fetchall()
        except Exception:
            LOGGER.exception("Failed to query Messages DB")
            conn.close()
            return

        for row in rows:
            rowid = int(row["ROWID"])
            text = str(row["text"] or "").strip()
            handle_id = str(row["handle_id"] or "")

            if not text or not handle_id:
                self._last_rowid = max(self._last_rowid, rowid)
                continue

            # Filter by allowed chat IDs (phone numbers or email addresses)
            if handle_id not in self._allowed:
                self._last_rowid = max(self._last_rowid, rowid)
                continue

            with self._counter_lock:
                self._update_counter += 1
                uid = self._update_counter

            self._queue.put(
                ChannelMessage(
                    update_id=uid,
                    chat_id=handle_id,
                    message_id=rowid,
                    text=text,
                    raw={"handle": handle_id, "rowid": rowid},
                )
            )
            self._last_rowid = max(self._last_rowid, rowid)

        conn.close()

    def _send_imessage(self, recipient: str, text: str) -> None:
        """Send an iMessage via AppleScript."""
        # Escape for AppleScript string
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
        escaped_recipient = recipient.replace("\\", "\\\\").replace('"', '\\"')

        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st account whose service type = iMessage\n'
            f'  set targetBuddy to participant "{escaped_recipient}" of targetService\n'
            f'  send "{escaped_text}" to targetBuddy\n'
            f'end tell'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                LOGGER.warning(
                    "osascript failed (rc=%d): %s", result.returncode,
                    result.stderr.strip()[:200],
                )
        except subprocess.TimeoutExpired:
            LOGGER.warning("osascript timed out sending to %s", recipient)
        except FileNotFoundError:
            raise ChannelError("osascript not found — iMessage requires macOS.")


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
