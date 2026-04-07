from __future__ import annotations

import asyncio
import logging
import threading
from queue import Empty, Queue
from typing import Any

from .base import BaseChannel, ChannelError, ChannelMessage

LOGGER = logging.getLogger(__name__)

# discord.py is an optional dependency; the runtime works without it as long as
# no account is configured with platform = "discord".
try:
    import discord as _discord

    _DISCORD_AVAILABLE = True
except ImportError:
    _discord = None  # type: ignore[assignment]
    _DISCORD_AVAILABLE = False


class DiscordChannel(BaseChannel):
    """Discord adapter using discord.py gateway (websocket).

    Each DiscordChannel runs a dedicated asyncio event loop in a daemon thread.
    Incoming messages are pushed to a thread-safe queue; ``get_updates()``
    drains that queue (blocking up to ``poll_timeout_seconds`` for the first
    message so the worker thread doesn't spin).

    Sending is done via ``asyncio.run_coroutine_threadsafe`` so the sync
    router can call ``send_message`` directly.

    Requirements
    ------------
    ``discord.py`` >= 2.0 with ``message_content`` intent enabled for the bot
    in the Discord developer portal.

    Config fields (``channel_config`` section)
    -------------------------------------------
    ``token`` — bot token (same as the top-level ``token`` field).
    ``allowed_chat_ids`` — list of Discord channel IDs (strings) the bot
    should respond in.
    """

    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: list[str],
        poll_timeout_seconds: int = 30,
    ) -> None:
        if not _DISCORD_AVAILABLE:
            raise ChannelError(
                "discord.py is not installed. "
                "Install it with: pip install 'discord.py>=2.0'"
            )

        self._token = bot_token
        self._allowed = set(allowed_chat_ids)
        self._poll_timeout = poll_timeout_seconds

        self._queue: Queue[ChannelMessage] = Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None
        self._thread: threading.Thread | None = None
        self._update_counter = 0
        self._counter_lock = threading.Lock()

        # Map of channel_id (str) -> discord channel object for send_message
        self._channel_cache: dict[str, Any] = {}

    # ── BaseChannel ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._client = self._build_client()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="discord-gateway",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("DiscordChannel started")

    def stop(self) -> None:
        if self._client is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def get_updates(self) -> list[ChannelMessage]:
        messages: list[ChannelMessage] = []

        # Drain anything already in the queue
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except Empty:
                break

        # If nothing was queued, block until one arrives or timeout
        if not messages:
            try:
                messages.append(self._queue.get(timeout=self._poll_timeout))
            except Empty:
                return []

        # Drain any additional messages that arrived during the wait
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except Empty:
                break

        return messages

    def send_message(self, chat_id: str, text: str) -> None:
        if self._loop is None or self._client is None:
            raise ChannelError("DiscordChannel not started")
        future = asyncio.run_coroutine_threadsafe(
            self._async_send(chat_id, text), self._loop
        )
        try:
            future.result(timeout=30)
        except Exception as exc:
            raise ChannelError(f"Discord send failed: {exc}") from exc

    def send_typing(self, chat_id: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._async_typing(chat_id), self._loop
        )

    # ── Internal ─────────────────────────────────────────────────────────────

    def _build_client(self) -> Any:
        intents = _discord.Intents.default()
        intents.message_content = True
        client = _discord.Client(intents=intents, loop=self._loop)

        @client.event
        async def on_ready() -> None:
            LOGGER.info("Discord bot logged in as %s", client.user)

        @client.event
        async def on_message(message: Any) -> None:
            if message.author.bot:
                return
            chat_id = str(message.channel.id)
            if chat_id not in self._allowed:
                return
            # Cache channel object for later sends
            self._channel_cache[chat_id] = message.channel
            with self._counter_lock:
                self._update_counter += 1
                uid = self._update_counter
            self._queue.put(
                ChannelMessage(
                    update_id=uid,
                    chat_id=chat_id,
                    message_id=message.id,
                    text=message.content or "",
                    raw={"author": str(message.author), "guild": str(message.guild)},
                )
            )

        return client

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._client.start(self._token))  # type: ignore[union-attr]
        except Exception:
            LOGGER.exception("Discord event loop exited with error")

    async def _async_send(self, chat_id: str, text: str) -> None:
        channel = self._channel_cache.get(chat_id)
        if channel is None and self._client is not None:
            channel = self._client.get_channel(int(chat_id))
        if channel is None:
            raise ChannelError(f"Discord channel {chat_id!r} not found")
        # Split at 2000 chars (Discord limit)
        for chunk in _split(text, 2000):
            await channel.send(chunk)

    async def _async_typing(self, chat_id: str) -> None:
        channel = self._channel_cache.get(chat_id)
        if channel is not None:
            async with channel.typing():
                pass


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
