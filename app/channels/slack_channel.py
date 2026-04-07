from __future__ import annotations

import logging
import threading
from queue import Empty, Queue
from typing import Any

from .base import BaseChannel, ChannelError, ChannelMessage

LOGGER = logging.getLogger(__name__)

# slack-sdk is an optional dependency.
try:
    from slack_sdk import WebClient as _WebClient
    from slack_sdk.socket_mode import SocketModeClient as _SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest as _SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse as _SocketModeResponse

    _SLACK_AVAILABLE = True
except ImportError:
    _WebClient = None  # type: ignore[assignment,misc]
    _SocketModeClient = None  # type: ignore[assignment,misc]
    _SocketModeRequest = None  # type: ignore[assignment,misc]
    _SocketModeResponse = None  # type: ignore[assignment,misc]
    _SLACK_AVAILABLE = False


class SlackChannel(BaseChannel):
    """Slack adapter using Socket Mode (``slack-sdk``).

    Socket Mode lets the bot receive events via a persistent WebSocket without
    exposing a public HTTP endpoint.  Requires two tokens:

    ``token`` (top-level config field)
        A *Bot Token* (``xoxb-…``) for sending messages via the Web API.
    ``app_token`` (inside ``channel_config``)
        An *App-Level Token* (``xapp-…``) with the ``connections:write`` scope
        for Socket Mode.

    Config example
    --------------
    .. code-block:: json

        {
          "platform": "slack",
          "token": "xoxb-...",
          "allowed_chat_ids": ["C01234567"],
          "channel_config": {
            "app_token": "xapp-..."
          }
        }

    Requirements
    ------------
    ``slack-sdk`` >= 3.0: ``pip install 'slack-sdk>=3.0'``
    """

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        allowed_chat_ids: list[str],
        poll_timeout_seconds: int = 30,
    ) -> None:
        if not _SLACK_AVAILABLE:
            raise ChannelError(
                "slack-sdk is not installed. "
                "Install it with: pip install 'slack-sdk>=3.0'"
            )

        self._bot_token = bot_token
        self._app_token = app_token
        self._allowed = set(allowed_chat_ids)
        self._poll_timeout = poll_timeout_seconds

        self._queue: Queue[ChannelMessage] = Queue()
        self._web_client: Any = None
        self._socket_client: Any = None
        self._update_counter = 0
        self._counter_lock = threading.Lock()

    # ── BaseChannel ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._web_client = _WebClient(token=self._bot_token)
        self._socket_client = _SocketModeClient(
            app_token=self._app_token,
            web_client=self._web_client,
        )
        self._socket_client.socket_mode_request_listeners.append(self._on_event)
        self._socket_client.connect()
        LOGGER.info("SlackChannel socket mode connected")

    def stop(self) -> None:
        if self._socket_client is not None:
            try:
                self._socket_client.disconnect()
            except Exception:
                pass

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
        if self._web_client is None:
            raise ChannelError("SlackChannel not started")
        # Slack has a ~4000-char limit per message block; split conservatively
        for chunk in _split(text, 3800):
            try:
                self._web_client.chat_postMessage(channel=chat_id, text=chunk)
            except Exception as exc:
                raise ChannelError(f"Slack send failed: {exc}") from exc

    def send_typing(self, chat_id: str) -> None:
        # Slack doesn't support a "bot is typing" indicator via the API.
        pass

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_event(self, client: Any, req: Any) -> None:
        """Socket Mode event listener — called on the socket thread."""
        # Acknowledge immediately to avoid retries
        client.send_socket_mode_response(_SocketModeResponse(envelope_id=req.envelope_id))

        if req.type != "events_api":
            return

        payload = req.payload or {}
        event = payload.get("event", {})

        if event.get("type") != "message":
            return
        if event.get("subtype"):
            # Skip edits, bot messages, etc.
            return

        channel = event.get("channel", "")
        if channel not in self._allowed:
            return

        text = event.get("text", "") or ""
        ts = event.get("ts", "0")
        # Convert Slack timestamp ("1234567890.123456") to a stable int ID
        try:
            ts_int = int(ts.replace(".", ""))
        except (ValueError, AttributeError):
            ts_int = 0

        with self._counter_lock:
            self._update_counter += 1
            uid = self._update_counter

        self._queue.put(
            ChannelMessage(
                update_id=uid,
                chat_id=channel,
                message_id=ts_int,
                text=text,
                raw={"user": event.get("user", ""), "ts": ts},
            )
        )


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
