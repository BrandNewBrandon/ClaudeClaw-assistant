"""WhatsApp adapter via HTTP bridge.

Connects to a local WhatsApp bridge server that handles the actual
WhatsApp protocol.  The bridge can be any implementation (whatsapp-web.js,
Baileys, whatsmeow, etc.) as long as it exposes:

    GET  /messages?since=<timestamp>  → JSON array of messages
    POST /send                        → Send a message

The adapter is protocol-agnostic — it only speaks HTTP to the bridge.

Config example
--------------
.. code-block:: json

    {
      "platform": "whatsapp",
      "token": "bridge-api-key",
      "allowed_chat_ids": ["+15551234567"],
      "channel_config": {
        "bridge_url": "http://localhost:3000"
      }
    }

Bridge API contract
-------------------
**GET /messages?since=<iso-timestamp>**

Headers: ``Authorization: Bearer <token>``

Response (200):

.. code-block:: json

    {
      "messages": [
        {
          "id": "msg-id-string",
          "from": "+15551234567",
          "text": "Hello",
          "timestamp": "2026-04-11T14:30:00Z"
        }
      ]
    }

**POST /send**

Headers: ``Authorization: Bearer <token>``, ``Content-Type: application/json``

Body:

.. code-block:: json

    {
      "to": "+15551234567",
      "text": "Reply text"
    }

Response (200): ``{"ok": true}``

Requirements
------------
No external dependencies — uses urllib from stdlib.
A running WhatsApp bridge server is required.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

from .base import BaseChannel, ChannelError, ChannelMessage

LOGGER = logging.getLogger(__name__)

_DEFAULT_BRIDGE_URL = "http://localhost:3000"


class WhatsAppChannel(BaseChannel):
    """WhatsApp adapter via HTTP bridge server."""

    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: list[str],
        poll_timeout_seconds: int = 30,
        *,
        bridge_url: str = _DEFAULT_BRIDGE_URL,
        poll_interval: float = 3.0,
    ) -> None:
        self._token = bot_token
        self._allowed = set(allowed_chat_ids)
        self._poll_timeout = poll_timeout_seconds
        self._poll_interval = poll_interval
        self._bridge_url = bridge_url.rstrip("/")

        self._queue: Queue[ChannelMessage] = Queue()
        self._update_counter = 0
        self._counter_lock = threading.Lock()
        self._last_timestamp = datetime.now(tz=timezone.utc).isoformat()
        self._seen_ids: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── BaseChannel ──────────────────────────────────────────────────────────

    def start(self) -> None:
        # Verify bridge is reachable
        try:
            self._bridge_request("GET", "/messages", params={"since": self._last_timestamp})
        except Exception as exc:
            raise ChannelError(
                f"WhatsApp bridge not reachable at {self._bridge_url}: {exc}\n"
                "Ensure your WhatsApp bridge server is running."
            ) from exc

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, name="whatsapp-poll", daemon=True,
        )
        self._thread.start()
        LOGGER.info("WhatsAppChannel started, bridge=%s", self._bridge_url)

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
        for chunk in _split(text, 4096):
            try:
                self._bridge_request("POST", "/send", body={
                    "to": chat_id,
                    "text": chunk,
                })
            except Exception as exc:
                raise ChannelError(f"WhatsApp send failed: {exc}") from exc

    # ── Internal ─────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Background thread: poll bridge for new messages."""
        while not self._stop_event.is_set():
            try:
                self._check_new_messages()
            except Exception:
                LOGGER.exception("WhatsApp poll error")
            self._stop_event.wait(self._poll_interval)

    def _check_new_messages(self) -> None:
        """Fetch new messages from bridge."""
        try:
            data = self._bridge_request("GET", "/messages", params={
                "since": self._last_timestamp,
            })
        except Exception:
            LOGGER.debug("WhatsApp bridge poll failed", exc_info=True)
            return

        if not isinstance(data, dict) or "messages" not in data:
            LOGGER.debug("WhatsApp bridge returned unexpected response format: %s", type(data).__name__)
            return

        messages = data["messages"]
        if not isinstance(messages, list):
            LOGGER.debug("WhatsApp bridge 'messages' field is not a list")
            return

        for msg in messages:
            msg_id = str(msg.get("id", ""))
            if not msg_id or msg_id in self._seen_ids:
                continue

            sender = str(msg.get("from", ""))
            text = str(msg.get("text", "")).strip()
            timestamp = str(msg.get("timestamp", ""))

            if not text or not sender:
                self._seen_ids.add(msg_id)
                continue

            if sender not in self._allowed:
                self._seen_ids.add(msg_id)
                continue

            with self._counter_lock:
                self._update_counter += 1
                uid = self._update_counter

            self._queue.put(
                ChannelMessage(
                    update_id=uid,
                    chat_id=sender,
                    message_id=uid,
                    text=text,
                    raw={"id": msg_id, "from": sender, "timestamp": timestamp},
                )
            )
            self._seen_ids.add(msg_id)
            if timestamp:
                self._last_timestamp = timestamp

        # Prevent seen_ids from growing unbounded
        if len(self._seen_ids) > 10000:
            self._seen_ids = set(list(self._seen_ids)[-5000:])

    def _bridge_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the bridge server."""
        url = f"{self._bridge_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        data_bytes: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ChannelError(f"Bridge HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ChannelError(f"Bridge request failed: {exc}") from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return {"raw": response_body}


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
