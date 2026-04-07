from __future__ import annotations

import json
import ssl
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import certifi


class TelegramError(Exception):
    pass


@dataclass(frozen=True)
class TelegramMessage:
    update_id: int
    chat_id: str
    message_id: int
    text: str
    raw: dict[str, Any]
    image_path: str | None = None  # temp file path if a photo was attached


class TelegramClient:
    def __init__(self, bot_token: str, poll_timeout_seconds: int = 30) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{bot_token}"
        self._poll_timeout_seconds = poll_timeout_seconds
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def get_updates(self, offset: int | None = None) -> list[TelegramMessage]:
        payload: dict[str, Any] = {
            "timeout": self._poll_timeout_seconds,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset

        data = self._post_json("getUpdates", payload)
        results: list[TelegramMessage] = []

        for item in data:
            message = item.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", "")).strip()
            if not chat_id:
                continue

            text = message.get("text")
            photo_sizes = message.get("photo")  # present when a photo is sent
            caption = message.get("caption", "")  # text on photo messages

            # Skip messages that have neither text nor a photo
            if not isinstance(text, str) and not photo_sizes:
                continue

            # For photo messages use the caption as the user's text
            effective_text: str = text if isinstance(text, str) else (caption or "")

            # Download the photo (largest size) if one is present
            image_path: str | None = None
            if photo_sizes:
                try:
                    file_id = photo_sizes[-1]["file_id"]  # last = highest resolution
                    image_path = self._download_photo(file_id)
                except Exception as exc:
                    # Log but don't drop the message — fall back to caption-only
                    import logging
                    logging.getLogger(__name__).warning("Failed to download Telegram photo: %s", exc)

            results.append(
                TelegramMessage(
                    update_id=int(item["update_id"]),
                    chat_id=chat_id,
                    message_id=int(message["message_id"]),
                    text=effective_text,
                    raw=item,
                    image_path=image_path,
                )
            )

        return results

    def _download_photo(self, file_id: str) -> str:
        """Download a Telegram photo to a temp file. Returns the file path."""
        # Step 1: resolve the file path on Telegram's servers
        file_info = self._post_json("getFile", {"file_id": file_id})
        file_path = file_info.get("file_path", "")
        if not file_path:
            raise TelegramError(f"getFile returned no file_path for file_id={file_id!r}")

        # Step 2: download the raw bytes
        download_url = f"{self._file_base_url}/{file_path}"
        request = urllib.request.Request(download_url)
        try:
            with urllib.request.urlopen(request, timeout=30, context=self._ssl_context) as resp:
                data = resp.read()
        except urllib.error.URLError as exc:
            raise TelegramError(f"Photo download failed: {exc}") from exc

        # Step 3: write to a temp file and return its path
        suffix = ".jpg"
        if "." in file_path:
            suffix = "." + file_path.rsplit(".", 1)[-1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="assistant_img_")
        try:
            import os
            os.write(fd, data)
        finally:
            import os
            os.close(fd)
        return tmp_path

    def send_message_return_id(self, chat_id: str, text: str) -> int:
        """Send a message and return Telegram's message_id (for later editing)."""
        result = self._post_json(
            "sendMessage",
            {"chat_id": chat_id, "text": text or "▌"},
        )
        return int(result["message_id"])

    def edit_message(self, chat_id: str, message_id: int, text: str) -> None:
        """Edit an existing message in-place.

        Silently swallows rate-limit errors (420) and "message is not modified"
        errors (400) — both are harmless during streaming.
        """
        try:
            self._post_json(
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text or "(empty)",
                },
            )
        except TelegramError as exc:
            msg = str(exc)
            if "Too Many Requests" in msg or "message is not modified" in msg:
                return
            raise

    def send_message(self, chat_id: str, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            cleaned = "(No reply text was produced.)"

        for chunk in self._split_message(cleaned):
            self._post_json(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                },
            )

    def send_typing(self, chat_id: str) -> None:
        self._post_json(
            "sendChatAction",
            {
                "chat_id": chat_id,
                "action": "typing",
            },
        )

    def start_typing_loop(self, chat_id: str, interval_seconds: int) -> tuple[threading.Event, threading.Thread]:
        stop_event = threading.Event()

        def worker() -> None:
            while not stop_event.is_set():
                try:
                    self.send_typing(chat_id)
                except Exception:
                    pass
                stop_event.wait(interval_seconds)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return stop_event, thread

    def _post_json(self, method: str, payload: dict[str, Any]) -> Any:
        encoded = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/{method}",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._poll_timeout_seconds + 10,
                context=self._ssl_context,
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram HTTP error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram request failed: {exc}") from exc

        parsed = json.loads(body)
        if not parsed.get("ok"):
            raise TelegramError(f"Telegram API returned error: {parsed}")
        return parsed.get("result")

    @staticmethod
    def _split_message(text: str, limit: int = 4096) -> list[str]:
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        remaining = text
        while len(remaining) > limit:
            split_at = remaining.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = limit
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")
        if remaining:
            chunks.append(remaining)
        return chunks
