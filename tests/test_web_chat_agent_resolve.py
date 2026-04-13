"""Tests for dashboard chat agent-name resolution.

Regression coverage for the case where the browser POSTs an empty
``agent_name`` (frontend race: dropdown not populated yet) and the server
used to fall back to a hardcoded ``"main"`` that didn't exist on installs
where the default agent has a different name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.web.server import ChatAgentError, resolve_chat_agent


def _make_agents_dir(tmp_path: Path, *names: str) -> Path:
    agents = tmp_path / "agents"
    agents.mkdir()
    for name in names:
        (agents / name).mkdir()
    return agents


def test_explicit_agent_returned_when_exists(tmp_path: Path) -> None:
    agents = _make_agents_dir(tmp_path, "Avi Nuge", "main")
    result = resolve_chat_agent(
        requested="Avi Nuge",
        default_agent="main",
        agents_dir=agents,
    )
    assert result == "Avi Nuge"


def test_empty_request_falls_back_to_config_default(tmp_path: Path) -> None:
    agents = _make_agents_dir(tmp_path, "Avi Nuge")
    result = resolve_chat_agent(
        requested="",
        default_agent="Avi Nuge",
        agents_dir=agents,
    )
    assert result == "Avi Nuge"


def test_whitespace_request_falls_back_to_config_default(tmp_path: Path) -> None:
    agents = _make_agents_dir(tmp_path, "finance")
    result = resolve_chat_agent(
        requested="   ",
        default_agent="finance",
        agents_dir=agents,
    )
    assert result == "finance"


def test_none_request_falls_back_to_config_default(tmp_path: Path) -> None:
    agents = _make_agents_dir(tmp_path, "main")
    result = resolve_chat_agent(
        requested=None,
        default_agent="main",
        agents_dir=agents,
    )
    assert result == "main"


def test_nonexistent_agent_raises_clean_error(tmp_path: Path) -> None:
    agents = _make_agents_dir(tmp_path, "main")
    with pytest.raises(ChatAgentError, match="Avi Nuge"):
        resolve_chat_agent(
            requested="Avi Nuge",
            default_agent="main",
            agents_dir=agents,
        )


def test_nonexistent_default_agent_raises_clean_error(tmp_path: Path) -> None:
    # Empty request + default_agent doesn't exist on disk — hard-fail rather
    # than masking the config mismatch.
    agents = _make_agents_dir(tmp_path, "finance")
    with pytest.raises(ChatAgentError, match="main"):
        resolve_chat_agent(
            requested="",
            default_agent="main",
            agents_dir=agents,
        )


def test_hardcoded_main_fallback_not_used(tmp_path: Path) -> None:
    """Regression: server used to fall back to 'main' which didn't exist on
    installs with a differently-named default agent."""
    agents = _make_agents_dir(tmp_path, "Avi Nuge")
    # Empty request + config default 'Avi Nuge'. If the old hardcoded
    # fallback were still in place, this would try 'main' and fail.
    result = resolve_chat_agent(
        requested="",
        default_agent="Avi Nuge",
        agents_dir=agents,
    )
    assert result == "Avi Nuge"
