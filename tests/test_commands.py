from __future__ import annotations

import json
from pathlib import Path

from app.commands import CommandHandler
from app.runtime_state import RuntimeState


def make_agent(agents_dir: Path, name: str, *, provider: str = "claude-code", model: str = "sonnet", effort: str = "medium") -> None:
    agent_dir = agents_dir / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "agent.json").write_text(
        json.dumps(
            {
                "display_name": name.title(),
                "description": f"{name} description",
                "provider": provider,
                "model": model,
                "effort": effort,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_agent_command_includes_provider_model_and_effort(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "main")

    handler = CommandHandler(
        agents_dir=agents_dir,
        default_provider="claude-code",
        default_model="sonnet",
        default_effort="medium",
    )
    runtime_state = RuntimeState()

    reply, switch_to, reset, remember_text = handler.handle(
        "/agent",
        active_agent="main",
        default_agent="main",
        runtime_state=runtime_state,
        routing_source="default",
    )

    assert "Provider: claude-code" in reply
    assert "Model: sonnet" in reply
    assert "Effort: medium" in reply
    assert "Account: primary" in reply
    assert "Routing: default" in reply
    assert switch_to is None
    assert reset is False
    assert remember_text is None


def test_agent_switch_is_blocked_for_pinned_chat(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "main")
    make_agent(agents_dir, "builder", model="opus", effort="high")

    handler = CommandHandler(agents_dir=agents_dir)
    runtime_state = RuntimeState()

    reply, switch_to, reset, remember_text = handler.handle(
        "/agent switch builder",
        active_agent="main",
        default_agent="main",
        runtime_state=runtime_state,
        routing_source="config",
        pinned_agent="main",
    )

    assert "pinned to main by config" in reply
    assert switch_to is None
    assert reset is False
    assert remember_text is None


def test_status_includes_timing_fields(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "main")

    handler = CommandHandler(
        agents_dir=agents_dir,
        default_provider="claude-code",
        default_model="sonnet",
        default_effort="medium",
    )
    runtime_state = RuntimeState(
        current_message_id=123,
        typing_started_at="2026-04-05T22:00:01-06:00",
        model_started_at="2026-04-05T22:00:02-06:00",
        model_finished_at="2026-04-05T22:00:05-06:00",
        last_reply_at="2026-04-05T22:00:06-06:00",
        last_model_duration_ms=3000,
        last_message_duration_ms=5000,
    )

    reply, switch_to, reset, remember_text = handler.handle(
        "/status",
        active_agent="main",
        default_agent="main",
        runtime_state=runtime_state,
        routing_source="default",
    )

    assert "Current/last message ID: 123" in reply
    assert "Typing started at: 2026-04-05T22:00:01-06:00" in reply
    assert "Model started at: 2026-04-05T22:00:02-06:00" in reply
    assert "Model finished at: 2026-04-05T22:00:05-06:00" in reply
    assert "Last reply at: 2026-04-05T22:00:06-06:00" in reply
    assert "Last model duration ms: 3000" in reply
    assert "Last message duration ms: 5000" in reply
    assert switch_to is None
    assert reset is False
    assert remember_text is None


def test_agent_info_returns_requested_agent_details(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "builder", model="opus", effort="high")

    handler = CommandHandler(agents_dir=agents_dir)
    runtime_state = RuntimeState()

    reply, switch_to, reset, remember_text = handler.handle(
        "/agent info builder",
        active_agent="builder",
        default_agent="main",
        runtime_state=runtime_state,
        routing_source="session",
    )

    assert "Agent: builder" in reply
    assert "Provider: claude-code" in reply
    assert "Model: opus" in reply
    assert "Effort: high" in reply
    assert switch_to is None
    assert reset is False
    assert remember_text is None


def test_remember_command_returns_memory_text(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "main")

    handler = CommandHandler(agents_dir=agents_dir)
    runtime_state = RuntimeState()

    reply, switch_to, reset, remember_text = handler.handle(
        "/remember Brandon prefers concise updates",
        active_agent="main",
        default_agent="main",
        runtime_state=runtime_state,
    )

    assert "I'll remember that for main" in reply
    assert switch_to is None
    assert reset is False
    assert remember_text == "Brandon prefers concise updates"


def test_memory_command_returns_preview(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    make_agent(agents_dir, "main")

    handler = CommandHandler(agents_dir=agents_dir)
    runtime_state = RuntimeState()

    reply, switch_to, reset, remember_text = handler.handle(
        "/memory",
        active_agent="main",
        default_agent="main",
        runtime_state=runtime_state,
        memory_preview=["Brandon prefers concise updates.", "ClaudeClaw is the target architecture."],
    )

    assert "Relevant memory:" in reply
    assert "Brandon prefers concise updates." in reply
    assert "ClaudeClaw is the target architecture." in reply
    assert switch_to is None
    assert reset is False
    assert remember_text is None
