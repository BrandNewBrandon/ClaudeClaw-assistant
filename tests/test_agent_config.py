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


def test_safe_commands_parses_as_tuple(tmp_path: Path) -> None:
    (tmp_path / "agent.json").write_text(
        '{"safe_commands": ["git status", "pytest"]}',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert config.safe_commands == ("git status", "pytest")
    assert isinstance(config.safe_commands, tuple)


def test_missing_safe_commands_defaults_to_empty_tuple(tmp_path: Path) -> None:
    config = load_agent_config(tmp_path)
    assert config.safe_commands == ()


def test_working_dir_parses_from_agent_json(tmp_path: Path) -> None:
    (tmp_path / "agent.json").write_text(
        '{"working_dir": "~/Projects"}',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    assert config.working_dir == "~/Projects"


def test_missing_working_dir_defaults_to_none(tmp_path: Path) -> None:
    config = load_agent_config(tmp_path)
    assert config.working_dir is None


def test_safe_command_prefix_matches(tmp_path: Path) -> None:
    """'git status --short' is whitelisted when 'git status' is in safe_commands."""
    (tmp_path / "agent.json").write_text(
        '{"safe_commands": ["git status", "pytest"]}',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    cmd = "git status --short"
    assert any(cmd == p or cmd.startswith(p + " ") for p in config.safe_commands)


def test_safe_command_prefix_does_not_match_different_subcommand(tmp_path: Path) -> None:
    """'git push' is NOT whitelisted when only 'git status' is in safe_commands."""
    (tmp_path / "agent.json").write_text(
        '{"safe_commands": ["git status"]}',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    cmd = "git push"
    assert not any(cmd == p or cmd.startswith(p + " ") for p in config.safe_commands)


def test_safe_command_prefix_does_not_match_longer_command_name(tmp_path: Path) -> None:
    """'lsblk' must NOT be whitelisted when only 'ls' is in safe_commands."""
    (tmp_path / "agent.json").write_text(
        '{"safe_commands": ["ls"]}',
        encoding="utf-8",
    )
    config = load_agent_config(tmp_path)
    cmd = "lsblk"
    assert not any(cmd == p or cmd.startswith(p + " ") for p in config.safe_commands)
