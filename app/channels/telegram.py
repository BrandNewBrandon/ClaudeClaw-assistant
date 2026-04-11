from __future__ import annotations

import threading
from typing import Any

from .base import BaseChannel, ChannelCallback, ChannelError, ChannelMessage
from ..telegram_client import TelegramCallback, TelegramClient, TelegramError, TelegramMessage


class TelegramChannel(BaseChannel):
    """Telegram adapter — wraps the existing TelegramClient with long-polling."""

    def __init__(
        self,
        bot_token: str,
        allowed_chat_ids: list[str],
        poll_timeout_seconds: int = 30,
        typing_interval_seconds: int = 4,
    ) -> None:
        self._client = TelegramClient(
            bot_token=bot_token,
            poll_timeout_seconds=poll_timeout_seconds,
        )
        self._allowed = set(allowed_chat_ids)
        self._typing_interval = typing_interval_seconds
        self._offset: int | None = None

    # ── BaseChannel ──────────────────────────────────────────────────────────

    def get_updates(self) -> list[ChannelMessage | ChannelCallback]:
        try:
            raw_updates = self._client.get_updates(offset=self._offset)
        except TelegramError as exc:
            raise ChannelError(str(exc)) from exc

        results: list[ChannelMessage | ChannelCallback] = []
        for update in raw_updates:
            self._offset = max(self._offset or 0, update.update_id + 1)
            if isinstance(update, TelegramCallback):
                results.append(
                    ChannelCallback(
                        update_id=update.update_id,
                        chat_id=update.chat_id,
                        callback_id=update.callback_query_id,
                        data=update.data,
                        message_id=update.message_id,
                    )
                )
            elif isinstance(update, TelegramMessage):
                results.append(
                    ChannelMessage(
                        update_id=update.update_id,
                        chat_id=update.chat_id,
                        message_id=update.message_id,
                        text=update.text,
                        raw=update.raw,
                        image_path=update.image_path,
                        document_path=update.document_path,
                        document_name=update.document_name,
                        voice_path=update.voice_path,
                    )
                )
        return results

    def send_message(self, chat_id: str, text: str) -> None:
        try:
            self._client.send_message(chat_id, text)
        except TelegramError as exc:
            raise ChannelError(str(exc)) from exc

    def send_and_get_message_id(self, chat_id: str, text: str) -> int | None:
        try:
            return self._client.send_message_return_id(chat_id, text)
        except TelegramError as exc:
            raise ChannelError(str(exc)) from exc

    def edit_message(self, chat_id: str, message_id: int, text: str) -> None:
        try:
            self._client.edit_message(chat_id, message_id, text)
        except TelegramError as exc:
            raise ChannelError(str(exc)) from exc

    def send_message_with_buttons(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]]
    ) -> int | None:
        try:
            return self._client.send_message_with_buttons(chat_id, text, buttons)
        except TelegramError as exc:
            raise ChannelError(str(exc)) from exc

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._client.answer_callback_query(callback_id, text)
        except TelegramError:
            pass

    def send_typing(self, chat_id: str) -> None:
        try:
            self._client.send_typing(chat_id)
        except TelegramError:
            pass

    def start_typing_loop(
        self, chat_id: str, interval_seconds: int
    ) -> tuple[threading.Event, threading.Thread]:
        return self._client.start_typing_loop(chat_id, interval_seconds)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def allowed_chat_ids(self) -> set[str]:
        return self._allowed
