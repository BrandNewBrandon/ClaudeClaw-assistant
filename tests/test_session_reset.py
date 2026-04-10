from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from app.session_reset import SessionResetThread


def _make_memory_mock() -> Any:
    mock = MagicMock()
    mock.append_compaction_summary.return_value = None
    return mock


def _make_sessions_mock() -> Any:
    return MagicMock()


def test_daily_reset_clears_session_id(tmp_path: Path) -> None:
    """Daily reset pops the compound session key from session_ids."""
    session_ids: dict[str, str] = {
        "telegram:primary:123:main": "claude-session-abc",
    }
    last_activity: dict[str, float] = {"telegram:primary:123": time.monotonic()}
    active_agents: dict[str, str] = {"telegram:primary:123": "main"}

    thread = SessionResetThread(
        memory_store=_make_memory_mock(),
        sessions=_make_sessions_mock(),
        daily_hour=0,
        last_activity=last_activity,
        active_agents=active_agents,
        session_ids=session_ids,
    )
    # Force daily reset to fire by backdating _last_daily_date
    thread._last_daily_date = "1970-01-01"

    thread._check_daily_reset()

    assert "telegram:primary:123:main" not in session_ids


def test_idle_reset_clears_session_id(tmp_path: Path) -> None:
    """Idle reset pops the compound session key from session_ids."""
    session_ids: dict[str, str] = {
        "telegram:primary:123:builder": "claude-session-xyz",
    }
    # Simulate last activity 2 hours ago
    last_activity: dict[str, float] = {"telegram:primary:123": time.monotonic() - 7200}
    active_agents: dict[str, str] = {"telegram:primary:123": "builder"}

    thread = SessionResetThread(
        memory_store=_make_memory_mock(),
        sessions=_make_sessions_mock(),
        idle_minutes=30,
        last_activity=last_activity,
        active_agents=active_agents,
        session_ids=session_ids,
    )

    thread._check_idle_reset()

    assert "telegram:primary:123:builder" not in session_ids


def test_reset_without_session_ids_does_not_crash() -> None:
    """SessionResetThread works when session_ids is not provided (backward compat)."""
    last_activity: dict[str, float] = {"telegram:primary:123": time.monotonic() - 7200}
    active_agents: dict[str, str] = {"telegram:primary:123": "main"}

    thread = SessionResetThread(
        memory_store=_make_memory_mock(),
        sessions=_make_sessions_mock(),
        idle_minutes=30,
        last_activity=last_activity,
        active_agents=active_agents,
        # session_ids omitted — default None
    )

    # Should not raise
    thread._check_idle_reset()


def test_daily_reset_only_clears_matching_agent_session(tmp_path: Path) -> None:
    """Daily reset clears the agent that was active, not other agents."""
    session_ids: dict[str, str] = {
        "telegram:primary:123:main": "session-main",
        "telegram:primary:456:builder": "session-builder",
    }
    last_activity: dict[str, float] = {
        "telegram:primary:123": time.monotonic(),
        "telegram:primary:456": time.monotonic(),
    }
    active_agents: dict[str, str] = {
        "telegram:primary:123": "main",
        "telegram:primary:456": "builder",
    }

    thread = SessionResetThread(
        memory_store=_make_memory_mock(),
        sessions=_make_sessions_mock(),
        daily_hour=0,
        last_activity=last_activity,
        active_agents=active_agents,
        session_ids=session_ids,
    )
    thread._last_daily_date = "1970-01-01"

    thread._check_daily_reset()

    assert "telegram:primary:123:main" not in session_ids
    assert "telegram:primary:456:builder" not in session_ids
