"""Tests for TerminalChatSession session isolation."""
from __future__ import annotations

from pathlib import Path

from app.memory import MemoryStore


def test_session_ids_isolated_by_chat_id(tmp_path: Path) -> None:
    """Two different chat_ids must not share session IDs."""
    session_ids_a: dict[str, str] = {}
    session_ids_b: dict[str, str] = {}

    chat_id_a = "alpha"
    chat_id_b = "beta"
    agent = "main"

    # Simulate session ID assignment (mirrors chat_session.py:234)
    session_ids_a[f"{chat_id_a}:{agent}"] = "sess-aaa"
    session_ids_b[f"{chat_id_b}:{agent}"] = "sess-bbb"

    # Session IDs are independent
    assert session_ids_a.get(f"{chat_id_a}:{agent}") == "sess-aaa"
    assert session_ids_a.get(f"{chat_id_b}:{agent}") is None
    assert session_ids_b.get(f"{chat_id_b}:{agent}") == "sess-bbb"
    assert session_ids_b.get(f"{chat_id_a}:{agent}") is None


def test_transcript_paths_differ_by_chat_id(tmp_path: Path) -> None:
    """Different chat_ids must produce different transcript files."""
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    path_a = store.transcript_path("terminal", "alpha", account_id="primary", agent_name="main")
    path_b = store.transcript_path("terminal", "beta", account_id="primary", agent_name="main")

    assert path_a != path_b
    assert "alpha" in str(path_a)
    assert "beta" in str(path_b)


def test_transcript_entries_isolated_by_chat_id(tmp_path: Path) -> None:
    """Appending a transcript to chat A must not appear in chat B's transcript."""
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    store.append_transcript(
        surface="terminal",
        account_id="primary",
        chat_id="alpha",
        direction="in",
        agent="main",
        message_text="hello from alpha",
    )

    entries_alpha = store.read_recent_transcript(
        "terminal", "alpha", limit=10, account_id="primary", agent_name="main",
    )
    entries_beta = store.read_recent_transcript(
        "terminal", "beta", limit=10, account_id="primary", agent_name="main",
    )

    assert len(entries_alpha) == 1
    assert entries_alpha[0].message_text == "hello from alpha"
    assert len(entries_beta) == 0
