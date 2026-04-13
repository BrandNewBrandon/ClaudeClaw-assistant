from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .secret_store import SecretStore

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_RESERVED_NAMES = {"_template"}


class ProvisioningError(Exception):
    pass


def validate_agent_name(name: str) -> str:
    name = name.strip().lower()
    if not _NAME_RE.match(name):
        raise ProvisioningError(
            f"Invalid agent name {name!r}. Use lowercase letters, digits, dashes; 1-32 chars, "
            "must start with a letter or digit."
        )
    if name in _RESERVED_NAMES:
        raise ProvisioningError(f"Agent name {name!r} is reserved")
    return name


def scaffold_agent(
    agents_dir: Path,
    name: str,
    display_name: str,
    persona: str,
    description: str = "",
) -> Path:
    """Copy agents/_template/ to agents/<name>/ with placeholders rendered."""
    name = validate_agent_name(name)
    agents_dir = Path(agents_dir)
    target = agents_dir / name
    if target.exists():
        raise ProvisioningError(f"Agent {name!r} already exists at {target}")
    template = agents_dir / "_template"
    if not template.exists():
        raise ProvisioningError(
            f"Template not found at {template}. Create agents/_template/ first."
        )
    shutil.copytree(template, target)
    replacements = {
        "{{display_name}}": display_name,
        "{{description}}": description,
        "{{persona}}": persona,
    }
    for file_name in ("agent.json", "AGENT.md", "TOOLS.md"):
        path = target / file_name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for key, value in replacements.items():
            content = content.replace(key, value)
        path.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Channel credential validators
# ---------------------------------------------------------------------------

def _telegram_get_me(token: str) -> dict[str, Any]:
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise ProvisioningError(f"Telegram getMe failed: {body.get('description', body)}")
    return body["result"]


def _discord_get_me(token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "id" not in body:
        raise ProvisioningError(f"Discord /users/@me failed: {body}")
    return body


def _slack_auth_test(token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise ProvisioningError(f"Slack auth.test failed: {body.get('error')}")
    return body


# ---------------------------------------------------------------------------
# bind_channel: atomically validate → keyring → config → return account_id
# ---------------------------------------------------------------------------

def bind_channel_impl(
    config_path: Path,
    agent: str,
    channel: str,
    *,
    token: str | None = None,
    app_token: str | None = None,
    chat_identifier: str | None = None,
    allowed_chat_ids: list[str] | None = None,
    secret_store: SecretStore | None = None,
) -> dict[str, Any]:
    """Validate credentials, store in keyring, append to config.json.

    Returns dict: {"account_id", "channel", "display", "info"}.
    Caller should then call router.add_account(result["account_id"]) to hot-load.
    """
    channel = channel.lower().strip()
    agent = agent.strip()
    if not agent:
        raise ProvisioningError("bind_channel requires 'agent' name")
    if channel not in {"telegram", "discord", "slack", "imessage"}:
        raise ProvisioningError(
            f"Unsupported channel: {channel}. Use telegram/discord/slack/imessage."
        )
    store = secret_store if secret_store is not None else SecretStore()

    display = "?"
    info: dict[str, Any] = {}

    if channel == "telegram":
        if not token:
            raise ProvisioningError("Telegram bind requires 'token'")
        try:
            info = _telegram_get_me(token)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ProvisioningError(f"Telegram token validation failed: {exc}") from exc
        display = f"@{info.get('username', '?')}"
    elif channel == "discord":
        if not token:
            raise ProvisioningError("Discord bind requires 'token'")
        try:
            info = _discord_get_me(token)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ProvisioningError(f"Discord token validation failed: {exc}") from exc
        display = info.get("username", "?")
    elif channel == "slack":
        if not token or not app_token:
            raise ProvisioningError("Slack bind requires both 'token' (bot) and 'app_token' (app-level)")
        try:
            info = _slack_auth_test(token)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ProvisioningError(f"Slack token validation failed: {exc}") from exc
        display = info.get("user", "?")
    elif channel == "imessage":
        if not chat_identifier:
            raise ProvisioningError(
                "iMessage bind requires 'chat_identifier'. Call list_imessage_chats() first."
            )
        display = chat_identifier
        info = {"chat_identifier": chat_identifier}

    # Store secrets
    if channel in {"telegram", "discord", "slack"}:
        store.set(agent, channel, token or "")
    if channel == "slack":
        store.set(agent, "slack-app", app_token or "")

    # Update config.json
    config_path = Path(config_path)
    cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    accounts = cfg.setdefault("accounts", {})
    routing = cfg.setdefault("routing", {})
    account_id = f"{agent}-{channel}"

    entry: dict[str, Any] = {"platform": channel, "agent": agent}
    if channel in {"telegram", "discord", "slack"}:
        entry["token_ref"] = f"{agent}:{channel}"
        entry["allowed_chat_ids"] = list(allowed_chat_ids or [])
    if channel == "slack":
        entry["channel_config"] = {"app_token_ref": f"{agent}:slack-app"}
    if channel == "imessage":
        entry["chat_identifier"] = chat_identifier
        entry["allowed_chat_ids"] = [chat_identifier]

    accounts[account_id] = entry
    routing[account_id] = {"default_agent": agent, "chat_agent_map": {}}
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    return {"account_id": account_id, "channel": channel, "display": display, "info": info}


# ---------------------------------------------------------------------------
# iMessage chat listing (macOS only, read-only sqlite access)
# ---------------------------------------------------------------------------

def list_imessage_chats_impl(limit: int = 20) -> list[dict[str, str]]:
    if os.name == "nt":
        raise ProvisioningError(
            "iMessage listing requires macOS (Messages.app). Run this from your Mac."
        )
    db = Path.home() / "Library" / "Messages" / "chat.db"
    if not db.exists():
        raise ProvisioningError(
            f"Messages database not found at {db}. Is Messages.app configured on this Mac?"
        )
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        raise ProvisioningError(
            f"Cannot open Messages database: {exc}. Grant Full Disk Access to your terminal in System Settings."
        ) from exc
    try:
        rows = conn.execute(
            "SELECT chat_identifier, display_name FROM chat ORDER BY ROWID DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    finally:
        conn.close()
    return [{"chat_identifier": cid, "display_name": name or ""} for cid, name in rows]
