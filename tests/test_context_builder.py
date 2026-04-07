from __future__ import annotations

from pathlib import Path

from app.context_builder import AgentContext, ContextBuilder
from app.memory import TranscriptEntry


def test_build_prompt_includes_relevant_memory_block(tmp_path: Path) -> None:
    builder = ContextBuilder(tmp_path)
    context = AgentContext(
        agent_name="main",
        agent_dir=tmp_path / "main",
        agent_md="agent",
        user_md="user",
        memory_md="long-term",
        tools_md="tools",
        recent_daily_notes="daily",
    )
    transcript = [
        TranscriptEntry(
            timestamp="2026-04-05T22:00:00-06:00",
            surface="telegram",
            account_id="primary",
            chat_id="123",
            direction="in",
            agent="main",
            message_text="hello",
            metadata={},
        )
    ]

    prompt = builder.build_prompt(
        context,
        "What next?",
        recent_transcript=transcript,
        relevant_memory=["Brandon prefers concise updates.", "Multi-account runtime is live."],
        tool_instructions="Use TOOL {...} when web lookup is needed.",
        tool_results=["TOOL_RESULT {\"name\": \"web_search\", \"status\": \"ok\", \"output\": \"result\"}"],
    )

    assert "=== RELEVANT MEMORY ===" in prompt
    assert "Brandon prefers concise updates." in prompt
    assert "Multi-account runtime is live." in prompt
    assert "=== TOOL INSTRUCTIONS ===" in prompt
    assert "Use TOOL {...} when web lookup is needed." in prompt
    assert "=== TOOL RESULTS ===" in prompt
    assert "TOOL_RESULT {\"name\": \"web_search\"" in prompt
    assert "=== RECENT TRANSCRIPT ===" in prompt
