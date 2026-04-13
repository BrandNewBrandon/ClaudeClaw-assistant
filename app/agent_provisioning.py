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


def is_real_agent_dir(path: Path) -> bool:
    """True if `path` is a directory that represents a real user agent.

    Excludes hidden dirs (`.`-prefixed), template/reserved dirs (`_`-prefixed),
    and non-directories. Use at every `agents_dir.iterdir()` call site so the
    template folder never gets treated as an agent by consolidation, listings,
    dashboards, or the MCP server.
    """
    if not path.is_dir():
        return False
    if path.name.startswith((".", "_")):
        return False
    return True


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
    commit_hook: "Any" = None,
) -> dict[str, Any]:
    """Validate credentials, store in keyring, append to config.json.

    If ``commit_hook`` is provided, it is called with the new account_id
    AFTER the config has been written. If the hook raises, the config file
    is restored to its prior bytes AND the keyring entries just written are
    deleted, so the operation is atomic: either the account is live OR
    nothing changed. Without a hook, the caller is responsible for any
    post-commit work and accepts the rollback gap.

    Returns dict: {"account_id", "channel", "display", "info"}.
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

    # Snapshot config.json bytes before any mutation so we can rollback if
    # commit_hook fails. None means "no prior file — rollback by deleting".
    config_path = Path(config_path)
    prior_bytes: bytes | None = None
    if config_path.exists():
        prior_bytes = config_path.read_bytes()

    # Store secrets — track what we set so we can un-set on rollback.
    secrets_written: list[tuple[str, str]] = []
    if channel in {"telegram", "discord", "slack"}:
        store.set(agent, channel, token or "")
        secrets_written.append((agent, channel))
    if channel == "slack":
        store.set(agent, "slack-app", app_token or "")
        secrets_written.append((agent, "slack-app"))

    # Build the new config dict from the (possibly just-read) prior state.
    cfg = json.loads(prior_bytes.decode("utf-8")) if prior_bytes else {}
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

    # Run the caller's commit hook (typically router.add_account). If it
    # raises, undo everything and re-raise as ProvisioningError so the tool
    # layer reports a clean failure instead of a half-applied state.
    if commit_hook is not None:
        try:
            commit_hook(account_id)
        except Exception as exc:  # noqa: BLE001
            # Rollback config.json
            if prior_bytes is not None:
                config_path.write_bytes(prior_bytes)
            else:
                try:
                    config_path.unlink()
                except FileNotFoundError:
                    pass
            # Rollback keyring
            for ag, ch in secrets_written:
                try:
                    store.delete(ag, ch)
                except Exception:  # noqa: BLE001
                    pass
            raise ProvisioningError(
                f"bind_channel commit failed; rolled back config and secrets: {exc}"
            ) from exc

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
