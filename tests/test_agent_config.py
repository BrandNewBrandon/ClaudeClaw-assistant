from __future__ import annotations

from pathlib import Path

from app.agent_config import AgentConfigError, load_agent_config


def test_load_agent_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    config = load_agent_config(tmp_path)
    assert config.display_name is None
    assert config.description is None
    assert config.provider is None
    assert config.model is None
    assert config.effort is None


def test_load_agent_config_reads_fields(tmp_path: Path) -> None:
    (tmp_path / "agent.json").write_text(
        """
        {
          "display_name": "Builder",
          "description": "Focused assistant",
          "provider": "claude-code",
          "model": "opus",
          "effort": "high"
        }
        """,
        encoding="utf-8",
    )

    config = load_agent_config(tmp_path)

    assert config.display_name == "Builder"
    assert config.description == "Focused assistant"
    assert config.provider == "claude-code"
    assert config.model == "opus"
    assert config.effort == "high"


def test_load_agent_config_rejects_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "agent.json").write_text("{not-json}", encoding="utf-8")

    try:
        load_agent_config(tmp_path)
    except AgentConfigError as exc:
        assert "Invalid JSON" in str(exc)
    else:
        raise AssertionError("Expected AgentConfigError for invalid JSON")
