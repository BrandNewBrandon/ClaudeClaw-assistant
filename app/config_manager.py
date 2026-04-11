from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigManagerError(Exception):
    pass


PLACEHOLDER_VALUES = {"REPLACE_ME", "REPLACE_CHAT_ID"}


def _sanitize_config_data(data: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(data)

    token = sanitized.get("telegram_bot_token")
    if token in PLACEHOLDER_VALUES:
        sanitized["telegram_bot_token"] = ""

    allowed_chat_ids = sanitized.get("allowed_chat_ids")
    if isinstance(allowed_chat_ids, list):
        sanitized["allowed_chat_ids"] = [
            chat_id for chat_id in allowed_chat_ids if isinstance(chat_id, str) and chat_id.strip() and chat_id not in PLACEHOLDER_VALUES
        ]

    chat_agent_map = sanitized.get("chat_agent_map")
    if isinstance(chat_agent_map, dict):
        sanitized["chat_agent_map"] = {
            str(chat_id): str(agent_name)
            for chat_id, agent_name in chat_agent_map.items()
            if isinstance(chat_id, str)
            and chat_id.strip()
            and chat_id not in PLACEHOLDER_VALUES
            and isinstance(agent_name, str)
            and agent_name.strip()
            and agent_name not in PLACEHOLDER_VALUES
        }

    accounts = sanitized.get("accounts")
    if isinstance(accounts, dict):
        cleaned_accounts: dict[str, Any] = {}
        for account_id, account in accounts.items():
            if not isinstance(account_id, str) or not account_id.strip() or not isinstance(account, dict):
                continue
            cleaned = dict(account)
            token = cleaned.get("token")
            if token in PLACEHOLDER_VALUES:
                cleaned["token"] = ""
            allowed_chat_ids = cleaned.get("allowed_chat_ids")
            if isinstance(allowed_chat_ids, list):
                cleaned["allowed_chat_ids"] = [
                    chat_id
                    for chat_id in allowed_chat_ids
                    if isinstance(chat_id, str) and chat_id.strip() and chat_id not in PLACEHOLDER_VALUES
                ]
            cleaned_accounts[account_id.strip()] = cleaned
        sanitized["accounts"] = cleaned_accounts

    routing = sanitized.get("routing")
    if isinstance(routing, dict):
        cleaned_routing: dict[str, Any] = {}
        for account_id, account_routing in routing.items():
            if not isinstance(account_id, str) or not account_id.strip() or not isinstance(account_routing, dict):
                continue
            cleaned = dict(account_routing)
            chat_agent_map = cleaned.get("chat_agent_map")
            if isinstance(chat_agent_map, dict):
                cleaned["chat_agent_map"] = {
                    str(chat_id): str(agent_name)
                    for chat_id, agent_name in chat_agent_map.items()
                    if isinstance(chat_id, str)
                    and chat_id.strip()
                    and chat_id not in PLACEHOLDER_VALUES
                    and isinstance(agent_name, str)
                    and agent_name.strip()
                    and agent_name not in PLACEHOLDER_VALUES
                }
            cleaned_routing[account_id.strip()] = cleaned
        sanitized["routing"] = cleaned_routing

    return sanitized


def load_raw_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigManagerError(f"Config file not found: {config_path}")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigManagerError(f"Invalid JSON in config file: {config_path}") from exc


def load_example_config(path: str | Path) -> dict[str, Any]:
    return load_raw_config(path)


def write_config(path: str | Path, data: dict[str, Any]) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_config_data(data)
    config_path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    # Restrict permissions — config contains tokens
    try:
        import os
        if os.name != "nt":  # chmod not meaningful on Windows
            config_path.chmod(0o600)
    except OSError:
        pass  # Non-fatal — best effort


def ensure_config_exists(config_path: str | Path, example_path: str | Path) -> Path:
    config_file = Path(config_path)
    if config_file.exists():
        return config_file
    example = load_example_config(example_path)
    write_config(config_file, example)
    return config_file


def update_config_values(config_path: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    config = load_raw_config(config_path)
    config.update(updates)
    write_config(config_path, config)
    return config
