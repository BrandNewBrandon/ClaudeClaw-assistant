from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import BaseChannel, ChannelError

if TYPE_CHECKING:
    from ..config import AccountConfig


def build_channel(account: AccountConfig, *, poll_timeout_seconds: int = 30) -> BaseChannel:
    """Instantiate the correct BaseChannel subclass for the given account config."""
    platform = (account.platform or "telegram").lower()
    extra: dict[str, Any] = account.channel_config or {}

    if platform == "telegram":
        from .telegram import TelegramChannel
        return TelegramChannel(
            bot_token=account.token,
            allowed_chat_ids=account.allowed_chat_ids,
            poll_timeout_seconds=poll_timeout_seconds,
        )

    if platform == "discord":
        from .discord_channel import DiscordChannel
        return DiscordChannel(
            bot_token=account.token,
            allowed_chat_ids=account.allowed_chat_ids,
            poll_timeout_seconds=poll_timeout_seconds,
        )

    if platform == "slack":
        app_token = extra.get("app_token", "")
        if not app_token:
            raise ChannelError(
                "Slack account requires 'app_token' (xapp-…) in 'channel_config'."
            )
        from .slack_channel import SlackChannel
        return SlackChannel(
            bot_token=account.token,
            app_token=app_token,
            allowed_chat_ids=account.allowed_chat_ids,
            poll_timeout_seconds=poll_timeout_seconds,
        )

    if platform == "imessage":
        from .imessage import IMessageChannel
        db_path_str = extra.get("db_path")
        return IMessageChannel(
            allowed_chat_ids=account.allowed_chat_ids,
            poll_timeout_seconds=poll_timeout_seconds,
            db_path=__import__("pathlib").Path(db_path_str) if db_path_str else None,
        )

    if platform == "whatsapp":
        bridge_url = extra.get("bridge_url", "http://localhost:3000")
        from .whatsapp_channel import WhatsAppChannel
        return WhatsAppChannel(
            bot_token=account.token,
            allowed_chat_ids=account.allowed_chat_ids,
            poll_timeout_seconds=poll_timeout_seconds,
            bridge_url=bridge_url,
        )

    raise ChannelError(f"Unsupported platform: {platform!r}")
