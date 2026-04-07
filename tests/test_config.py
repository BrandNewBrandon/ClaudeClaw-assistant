from __future__ import annotations

import json
from pathlib import Path

from app.config import ConfigError, load_config


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_load_config_uses_portable_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "assistant-runtime"
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"

    write_json(
        config_path,
        {
            "telegram_bot_token": "token",
            "allowed_chat_ids": ["123"],
            "default_agent": "main",
            "claude_timeout_seconds": 300,
            "telegram_poll_timeout_seconds": 30,
            "typing_interval_seconds": 4,
            "claude_working_directory_mode": "agent_dir",
            "model_provider": "claude-code",
        },
    )

    config = load_config(config_path)

    assert config.project_root == project_root.resolve()
    assert config.agents_dir == (project_root / "agents").resolve()
    assert config.shared_dir == (project_root / "shared").resolve()
    assert config.model_provider == "claude-code"
    assert config.accounts["primary"].token == "token"
    assert config.routing["primary"].default_agent == "main"


def test_load_config_parses_chat_agent_map(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"

    write_json(
        config_path,
        {
            "telegram_bot_token": "token",
            "allowed_chat_ids": ["123"],
            "default_agent": "main",
            "claude_timeout_seconds": 300,
            "telegram_poll_timeout_seconds": 30,
            "typing_interval_seconds": 4,
            "claude_working_directory_mode": "agent_dir",
            "model_provider": "claude-code",
            "chat_agent_map": {"123": "main", "456": "builder"},
        },
    )

    config = load_config(config_path)

    assert config.chat_agent_map == {"123": "main", "456": "builder"}
    assert config.routing["primary"].chat_agent_map == {"123": "main", "456": "builder"}


def test_load_config_parses_accounts_and_routing(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"

    write_json(
        config_path,
        {
            "default_agent": "main",
            "claude_timeout_seconds": 300,
            "telegram_poll_timeout_seconds": 30,
            "typing_interval_seconds": 4,
            "claude_working_directory_mode": "agent_dir",
            "model_provider": "claude-code",
            "accounts": {
                "telegram-main": {
                    "platform": "telegram",
                    "token": "token-a",
                    "allowed_chat_ids": ["123"]
                },
                "telegram-builder": {
                    "platform": "telegram",
                    "token": "token-b",
                    "allowed_chat_ids": ["456"]
                }
            },
            "routing": {
                "telegram-main": {
                    "default_agent": "main",
                    "chat_agent_map": {"123": "main"}
                },
                "telegram-builder": {
                    "default_agent": "builder",
                    "chat_agent_map": {"456": "builder"}
                }
            }
        },
    )

    config = load_config(config_path)

    assert config.accounts["telegram-main"].token == "token-a"
    assert config.accounts["telegram-builder"].allowed_chat_ids == ["456"]
    assert config.routing["telegram-main"].default_agent == "main"
    assert config.routing["telegram-builder"].chat_agent_map == {"456": "builder"}
    assert config.telegram_bot_token == "token-a"
    assert config.default_agent == "main"


def test_load_config_rejects_unsupported_provider(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"

    write_json(
        config_path,
        {
            "telegram_bot_token": "token",
            "allowed_chat_ids": ["123"],
            "default_agent": "main",
            "claude_timeout_seconds": 300,
            "telegram_poll_timeout_seconds": 30,
            "typing_interval_seconds": 4,
            "claude_working_directory_mode": "agent_dir",
            "model_provider": "openai",
        },
    )

    try:
        load_config(config_path)
    except ConfigError as exc:
        assert "Unsupported model_provider" in str(exc)
    else:
        raise AssertionError("Expected ConfigError for unsupported provider")
