from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AgentConfigError(Exception):
    pass


@dataclass(frozen=True)
class AgentConfig:
    display_name: str | None = None
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    effort: str | None = None


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AgentConfigError(f"Invalid agent config field: {key}")
    cleaned = value.strip()
    return cleaned or None


def load_agent_config(agent_dir: Path) -> AgentConfig:
    config_path = agent_dir / "agent.json"
    if not config_path.exists():
        return AgentConfig()

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentConfigError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise AgentConfigError(f"Agent config must be an object: {config_path}")

    return AgentConfig(
        display_name=_optional_string(raw, "display_name"),
        description=_optional_string(raw, "description"),
        provider=_optional_string(raw, "provider"),
        model=_optional_string(raw, "model"),
        effort=_optional_string(raw, "effort"),
    )
