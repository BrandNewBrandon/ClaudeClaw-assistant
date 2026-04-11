"""DM pairing — approve new chat IDs without editing config manually.

Flow:
1. Unknown chat_id messages the bot → bot sends a 6-digit pairing code.
2. Owner sees the code in logs or runs `assistant pair --list`.
3. Owner runs `assistant pair <code>` → chat_id is added to allowed list.
4. Bot can now respond to the new user.

Pairing requests are persisted to a JSON file so the CLI and runtime
can communicate without shared memory.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_CODE_EXPIRY_SECONDS = 600  # 10 minutes
_RATE_LIMIT_SECONDS = 300   # 1 code per chat_id per 5 minutes


class PairingStore:
    """Thread-safe store for pairing requests, backed by a JSON file."""

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "pairing_requests.json"
        self._approved_path = state_dir / "pairing_approved.json"
        self._lock = threading.Lock()
        self._rate_limits: dict[str, float] = {}  # chat_id -> last request time

    def request(self, account_id: str, chat_id: str) -> tuple[str, int] | None:
        """Generate a pairing code for a new chat_id.

        Returns (message_to_send, code) or None if rate-limited.
        """
        now = time.time()

        # Rate limit check
        rate_key = f"{account_id}:{chat_id}"
        with self._lock:
            last = self._rate_limits.get(rate_key, 0.0)
            if now - last < _RATE_LIMIT_SECONDS:
                return None
            self._rate_limits[rate_key] = now

        code = random.randint(100_000, 999_999)
        entry = {
            "account_id": account_id,
            "chat_id": chat_id,
            "code": code,
            "created_at": now,
        }

        self._append(entry)
        LOGGER.warning(
            "PAIRING REQUEST: code=%d account=%s chat_id=%s — "
            "approve with 'assistant pair %d'",
            code, account_id, chat_id, code,
        )
        msg = (
            f"This bot requires pairing. Your code is: **{code}**\n"
            "Ask the bot owner to approve it."
        )
        return msg, code

    def pending(self) -> list[dict[str, Any]]:
        """Return all non-expired pending requests."""
        now = time.time()
        entries = self._read_all()
        return [e for e in entries if now - e.get("created_at", 0) < _CODE_EXPIRY_SECONDS]

    def approve(self, code: int) -> tuple[str, str] | None:
        """Approve a pairing code. Returns (account_id, chat_id) or None.

        Also writes to the approved-pairs file so the running runtime
        can pick up the new chat_id without a restart.
        """
        now = time.time()
        with self._lock:
            entries = self._read_all()
            remaining: list[dict[str, Any]] = []
            result: tuple[str, str] | None = None

            for entry in entries:
                if entry.get("code") == code and now - entry.get("created_at", 0) < _CODE_EXPIRY_SECONDS:
                    result = (entry["account_id"], entry["chat_id"])
                    # Don't keep this entry
                    continue
                remaining.append(entry)

            self._write_all(remaining)

        if result is not None:
            self._write_approved(result[0], result[1])

        return result

    def poll_approved(self) -> list[tuple[str, str]]:
        """Read and clear newly approved pairs. Returns list of (account_id, chat_id).

        Called by the router to pick up approvals made via the CLI.
        """
        with self._lock:
            if not self._approved_path.exists():
                return []
            try:
                data = json.loads(self._approved_path.read_text(encoding="utf-8"))
                pairs = [(e["account_id"], e["chat_id"]) for e in data if isinstance(e, dict)]
            except (json.JSONDecodeError, OSError, KeyError):
                pairs = []
            # Clear the file after reading
            if pairs:
                self._approved_path.write_text("[]\n", encoding="utf-8")
            return pairs

    def _write_approved(self, account_id: str, chat_id: str) -> None:
        """Append an approved pair to the approved file for the runtime to pick up."""
        with self._lock:
            existing: list[dict[str, Any]] = []
            if self._approved_path.exists():
                try:
                    existing = json.loads(self._approved_path.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []
            existing.append({"account_id": account_id, "chat_id": chat_id})
            self._approved_path.parent.mkdir(parents=True, exist_ok=True)
            self._approved_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    def _append(self, entry: dict[str, Any]) -> None:
        with self._lock:
            entries = self._read_all()
            # Evict expired
            now = time.time()
            entries = [e for e in entries if now - e.get("created_at", 0) < _CODE_EXPIRY_SECONDS]
            entries.append(entry)
            self._write_all(entries)

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_all(self, entries: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
