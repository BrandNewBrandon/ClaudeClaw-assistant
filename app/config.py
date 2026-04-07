from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AccountConfig:
    id: str
    platform: str
    token: str
    allowed_chat_ids: list[str]
    # Platform-specific extras (e.g. Slack's app_token for Socket Mode)
    channel_config: dict[str, Any] | None = None


@dataclass(frozen=True)
class RoutingConfig:
    account_id: str
    default_agent: str
    chat_agent_map: dict[str, str]


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    allowed_chat_ids: list[str]
    default_agent: str
    claude_timeout_seconds: int
    telegram_poll_timeout_seconds: int
    typing_interval_seconds: int
    project_root: Path
    agents_dir: Path
    shared_dir: Path
    claude_working_directory_mode: str
    model_provider: str
    claude_model: str | None
    claude_effort: str | None
    chat_agent_map: dict[str, str]
    accounts: dict[str, AccountConfig]
    routing: dict[str, RoutingConfig]
    # Rate-limit / caching knobs (all optional with safe defaults)
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    cooldown_seconds_per_chat: float = 0.0
    max_prompt_chars: int = 24_000
    # Memory consolidation
    consolidation_enabled: bool = True
    consolidation_keep_days: int = 3
    consolidation_hour: int = 2
    # Semantic memory search (requires: pip install assistant-runtime[semantic])
    semantic_search_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Quiet hours (HH:MM 24-hour format, e.g. "22:00". Both None = disabled)
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    # Morning briefing / heartbeat
    briefing_enabled: bool = False
    briefing_times: list[int] = field(default_factory=lambda: [9])


class ConfigError(Exception):
    pass


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid string config value: {key}")
    return value


def _require_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ConfigError(f"Missing or invalid integer config value: {key}")
    return value


def _require_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"Missing or invalid string list config value: {key}")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Invalid optional string config value: {key}")
    cleaned = value.strip()
    return cleaned or None


def _resolve_path(raw_value: str | None, *, base_dir: Path, default: Path) -> Path:
    if raw_value is None or not raw_value.strip():
        return default.resolve()
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate)
    return candidate.resolve()


def _optional_string_map(data: dict[str, Any], key: str) -> dict[str, str]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Invalid optional map config value: {key}")
    result: dict[str, str] = {}
    for map_key, map_value in value.items():
        if not isinstance(map_key, str) or not map_key.strip():
            raise ConfigError(f"Invalid map key in config value: {key}")
        if not isinstance(map_value, str) or not map_value.strip():
            raise ConfigError(f"Invalid map value in config value: {key}.{map_key}")
        result[map_key.strip()] = map_value.strip()
    return result


def _parse_accounts(raw: dict[str, Any]) -> tuple[dict[str, AccountConfig], dict[str, RoutingConfig]]:
    accounts_value = raw.get("accounts")
    routing_value = raw.get("routing")

    if accounts_value is None:
        default_account = AccountConfig(
            id="primary",
            platform="telegram",
            token=_require_string(raw, "telegram_bot_token"),
            allowed_chat_ids=_require_string_list(raw, "allowed_chat_ids"),
        )
        default_routing = RoutingConfig(
            account_id="primary",
            default_agent=_require_string(raw, "default_agent"),
            chat_agent_map=_optional_string_map(raw, "chat_agent_map"),
        )
        return {default_account.id: default_account}, {default_account.id: default_routing}

    if not isinstance(accounts_value, dict) or not accounts_value:
        raise ConfigError("Missing or invalid accounts config value: accounts")
    if routing_value is not None and not isinstance(routing_value, dict):
        raise ConfigError("Invalid routing config value: routing")

    accounts: dict[str, AccountConfig] = {}
    routing: dict[str, RoutingConfig] = {}

    for account_id, account_raw in accounts_value.items():
        if not isinstance(account_id, str) or not account_id.strip():
            raise ConfigError("Invalid account id in accounts config")
        if not isinstance(account_raw, dict):
            raise ConfigError(f"Invalid account config for: {account_id}")

        cleaned_account_id = account_id.strip()
        platform = account_raw.get("platform", "telegram")
        if not isinstance(platform, str) or not platform.strip():
            raise ConfigError(f"Invalid platform for account: {cleaned_account_id}")
        supported = {"telegram", "discord", "slack"}
        if platform.lower() not in supported:
            raise ConfigError(f"Unsupported account platform {platform!r}. Supported: {sorted(supported)}")

        channel_config_raw = account_raw.get("channel_config")
        channel_config: dict[str, Any] | None = None
        if isinstance(channel_config_raw, dict):
            channel_config = channel_config_raw

        account = AccountConfig(
            id=cleaned_account_id,
            platform=platform.lower(),
            token=_require_string(account_raw, "token"),
            allowed_chat_ids=_require_string_list(account_raw, "allowed_chat_ids"),
            channel_config=channel_config,
        )
        accounts[cleaned_account_id] = account

        routing_raw = routing_value.get(cleaned_account_id, {}) if isinstance(routing_value, dict) else {}
        if routing_value is not None and not isinstance(routing_raw, dict):
            raise ConfigError(f"Invalid routing config for account: {cleaned_account_id}")

        default_agent = _require_string(routing_raw, "default_agent") if routing_raw else _require_string(raw, "default_agent")
        chat_agent_map = _optional_string_map(routing_raw, "chat_agent_map") if routing_raw else {}
        routing[cleaned_account_id] = RoutingConfig(
            account_id=cleaned_account_id,
            default_agent=default_agent,
            chat_agent_map=chat_agent_map,
        )

    return accounts, routing


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    config_dir = path.resolve().parent
    default_project_root = config_dir.parent
    project_root = _resolve_path(raw.get("project_root"), base_dir=config_dir, default=default_project_root)
    agents_dir = _resolve_path(raw.get("agents_dir"), base_dir=project_root, default=project_root / "agents")
    shared_dir = _resolve_path(raw.get("shared_dir"), base_dir=project_root, default=project_root / "shared")

    model_provider = _require_string(raw, "model_provider") if raw.get("model_provider") is not None else "claude-code"
    if model_provider != "claude-code":
        raise ConfigError(f"Unsupported model_provider: {model_provider}")

    accounts, routing = _parse_accounts(raw)
    primary_account = accounts["primary"] if "primary" in accounts else next(iter(accounts.values()))
    primary_routing = routing[primary_account.id]

    return AppConfig(
        telegram_bot_token=primary_account.token,
        allowed_chat_ids=primary_account.allowed_chat_ids,
        default_agent=primary_routing.default_agent,
        claude_timeout_seconds=_require_int(raw, "claude_timeout_seconds"),
        telegram_poll_timeout_seconds=_require_int(raw, "telegram_poll_timeout_seconds"),
        typing_interval_seconds=_require_int(raw, "typing_interval_seconds"),
        project_root=project_root,
        agents_dir=agents_dir,
        shared_dir=shared_dir,
        claude_working_directory_mode=_require_string(raw, "claude_working_directory_mode"),
        model_provider=model_provider,
        claude_model=_optional_string(raw, "claude_model"),
        claude_effort=_optional_string(raw, "claude_effort"),
        chat_agent_map=primary_routing.chat_agent_map,
        accounts=accounts,
        routing=routing,
        cache_enabled=bool(raw.get("cache_enabled", True)),
        cache_ttl_seconds=int(raw.get("cache_ttl_seconds", 300)),
        cooldown_seconds_per_chat=float(raw.get("cooldown_seconds_per_chat", 0.0)),
        max_prompt_chars=int(raw.get("max_prompt_chars", 24_000)),
        consolidation_enabled=bool(raw.get("consolidation_enabled", True)),
        consolidation_keep_days=int(raw.get("consolidation_keep_days", 3)),
        consolidation_hour=int(raw.get("consolidation_hour", 2)),
        semantic_search_enabled=bool(raw.get("semantic_search_enabled", True)),
        embedding_model=str(raw.get("embedding_model", "BAAI/bge-small-en-v1.5")),
        quiet_hours_start=_optional_string(raw, "quiet_hours_start"),
        quiet_hours_end=_optional_string(raw, "quiet_hours_end"),
        briefing_enabled=bool(raw.get("briefing_enabled", False)),
        briefing_times=[int(h) for h in raw.get("briefing_times", [9])],
    )
