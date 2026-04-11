from __future__ import annotations

import json
from pathlib import Path

from app.config_manager import ensure_config_exists, load_raw_config, update_config_values, write_config


def test_ensure_config_exists_copies_example_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    example_path = tmp_path / "config" / "config.example.json"
    example_path.parent.mkdir(parents=True, exist_ok=True)
    example_path.write_text(json.dumps({"default_agent": "main"}, indent=2), encoding="utf-8")

    created = ensure_config_exists(config_path, example_path)

    assert created == config_path
    assert load_raw_config(config_path)["default_agent"] == "main"


def test_update_config_values_preserves_unrelated_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "default_agent": "main",
                "claude_model": "sonnet",
                "extra": "keep-me",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    updated = update_config_values(config_path, {"claude_model": "opus"})

    assert updated["claude_model"] == "opus"
    assert updated["extra"] == "keep-me"
    assert load_raw_config(config_path)["claude_model"] == "opus"


def test_ensure_config_exists_sanitizes_placeholder_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    example_path = tmp_path / "config" / "config.example.json"
    example_path.parent.mkdir(parents=True, exist_ok=True)
    example_path.write_text(
        json.dumps(
            {
                "telegram_bot_token": "REPLACE_ME",
                "allowed_chat_ids": ["REPLACE_ME", "123"],
                "chat_agent_map": {"REPLACE_CHAT_ID": "main", "123": "main"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ensure_config_exists(config_path, example_path)
    config = load_raw_config(config_path)

    assert config["telegram_bot_token"] == ""
    assert config["allowed_chat_ids"] == ["123"]
    assert config["chat_agent_map"] == {"123": "main"}


def test_write_config_sets_permissions(tmp_path: Path) -> None:
    """Config file should be owner-only readable (0o600) on Unix."""
    import os
    import stat
    config_path = tmp_path / "config.json"
    write_config(config_path, {"test": True})
    if os.name != "nt":
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_ensure_config_exists_sanitizes_placeholder_values_in_accounts(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    example_path = tmp_path / "config" / "config.example.json"
    example_path.parent.mkdir(parents=True, exist_ok=True)
    example_path.write_text(
        json.dumps(
            {
                "accounts": {
                    "telegram-main": {
                        "platform": "telegram",
                        "token": "REPLACE_ME",
                        "allowed_chat_ids": ["REPLACE_ME", "123"]
                    }
                },
                "routing": {
                    "telegram-main": {
                        "default_agent": "main",
                        "chat_agent_map": {"REPLACE_CHAT_ID": "main", "123": "main"}
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ensure_config_exists(config_path, example_path)
    config = load_raw_config(config_path)

    assert config["accounts"]["telegram-main"]["token"] == ""
    assert config["accounts"]["telegram-main"]["allowed_chat_ids"] == ["123"]
    assert config["routing"]["telegram-main"]["chat_agent_map"] == {"123": "main"}
