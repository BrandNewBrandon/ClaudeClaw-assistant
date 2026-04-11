from __future__ import annotations

from pathlib import Path

from app.commands import CommandHandler
from app.runtime_state import RuntimeState


def test_diagnostics_command(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    handler = CommandHandler(agents_dir=agents_dir)

    state = RuntimeState()
    state.messages_processed = 42
    state.tool_calls_executed = 10
    state.errors_count = 2
    state.register_thread("job-runner", "running")

    reply, _, _, _ = handler.handle(
        "/diagnostics",
        active_agent="main", default_agent="main", runtime_state=state,
    )
    assert "42" in reply
    assert "10" in reply
    assert "job-runner" in reply
    assert "running" in reply


def test_runtime_state_diagnostics() -> None:
    state = RuntimeState()
    state.increment_messages()
    state.increment_messages()
    state.increment_tool_calls()
    state.increment_errors()
    state.register_thread("test-thread", "active")

    diag = state.get_diagnostics()
    assert diag["messages_processed"] == 2
    assert diag["tool_calls_executed"] == 1
    assert diag["errors_count"] == 1
    assert diag["active_threads"] == {"test-thread": "active"}

    state.unregister_thread("test-thread")
    diag2 = state.get_diagnostics()
    assert diag2["active_threads"] == {}
