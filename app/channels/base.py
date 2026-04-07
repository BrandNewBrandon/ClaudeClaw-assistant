from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ChannelError(Exception):
    pass


@dataclass(frozen=True)
class ChannelMessage:
    """Surface-agnostic inbound message."""

    # Monotonically increasing ID used for dedup; managed per-channel.
    update_id: int
    # Surface-specific identifier for the conversation (channel, DM, group).
    chat_id: str
    # Per-chat message ID used for dedup within a chat.
    message_id: int
    # Plain-text body.
    text: str
    # Raw payload from the underlying platform (for debugging).
    raw: dict[str, Any] = field(default_factory=dict)
    # Local temp file path for an attached image, if any (cleaned up by the router after use).
    image_path: str | None = None


@dataclass(frozen=True)
class ChannelCallback:
    """Surface-agnostic inline-button callback (e.g. Telegram callback_query)."""

    update_id: int
    chat_id: str
    callback_id: str       # platform-specific callback ID for answering
    data: str              # callback_data payload (e.g. "a:3f1c0a9e")
    message_id: int = 0    # the message the button was on


class BaseChannel(ABC):
    """Common interface all channel adapters must implement."""

    # ── Receiving ────────────────────────────────────────────────────────────

    @abstractmethod
    def get_updates(self) -> list[ChannelMessage | ChannelCallback]:
        """Block until at least one message arrives (or a short timeout elapses)
        and return all buffered messages and callbacks.

        Polling channels (Telegram) do one HTTP round-trip per call.
        Event-driven channels (Discord, Slack) drain an internal queue.
        """

    # ── Sending ──────────────────────────────────────────────────────────────

    @abstractmethod
    def send_message(self, chat_id: str, text: str) -> None:
        """Send a text message to the given chat."""

    def send_and_get_message_id(self, chat_id: str, text: str) -> int | None:
        """Send a message and return the platform message_id for later in-place editing.

        Returns ``None`` if the channel does not support message editing
        (Discord, Slack default).  Telegram overrides this.
        """
        return None

    def edit_message(self, chat_id: str, message_id: int, text: str) -> None:
        """Edit a previously sent message in-place.

        No-op on channels that do not support editing.
        """

    def send_message_with_buttons(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]]
    ) -> int | None:
        """Send a message with inline action buttons (e.g. Approve / Deny).

        Returns the message_id if supported, or ``None`` if the channel
        does not support inline keyboards.
        """
        return None

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        """Acknowledge an inline-button callback. No-op if unsupported."""

    def send_typing(self, chat_id: str) -> None:
        """Indicate the bot is typing. No-op if unsupported."""

    def start_typing_loop(
        self, chat_id: str, interval_seconds: int
    ) -> tuple[threading.Event, threading.Thread]:
        """Start a background typing indicator loop.

        Returns ``(stop_event, thread)``; set ``stop_event`` to stop it.
        Default implementation calls ``send_typing`` repeatedly.
        """
        stop_event = threading.Event()

        def _worker() -> None:
            while not stop_event.is_set():
                try:
                    self.send_typing(chat_id)
                except Exception:
                    pass
                stop_event.wait(interval_seconds)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return stop_event, thread

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Called once when the runtime initialises.

        Event-driven channels (Discord, Slack) use this to connect their
        gateway/socket before ``get_updates`` is ever called.
        Polling channels (Telegram) can leave this as a no-op.
        """

    def stop(self) -> None:
        """Called on runtime shutdown to release resources."""
