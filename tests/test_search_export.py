from __future__ import annotations

from pathlib import Path
from app.commands import CommandHandler
from app.memory import MemoryStore
from app.runtime_state import RuntimeState


def _make_handler_with_memory(tmp_path):
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)
    handler = CommandHandler(agents_dir=agents_dir, memory_store=store)
    return handler, store


def test_search_chat_returns_matches(tmp_path):
    handler, store = _make_handler_with_memory(tmp_path)
    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello world")
    store.append_transcript(surface="telegram", chat_id="c1", direction="out", agent="main", message_text="hi there")
    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello again")

    reply, _, _, _ = handler.handle(
        "/search-chat hello",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram", chat_id="c1", account_id="primary",
    )
    assert "hello world" in reply
    assert "hello again" in reply
    assert "hi there" not in reply


def test_search_chat_no_matches(tmp_path):
    handler, store = _make_handler_with_memory(tmp_path)
    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello")

    reply, _, _, _ = handler.handle(
        "/search-chat xyz",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram", chat_id="c1", account_id="primary",
    )
    assert "No matches" in reply


def test_search_chat_no_query(tmp_path):
    handler, _ = _make_handler_with_memory(tmp_path)
    reply, _, _, _ = handler.handle(
        "/search-chat",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "Usage" in reply


def test_export_returns_formatted_transcript(tmp_path):
    handler, store = _make_handler_with_memory(tmp_path)
    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello")
    store.append_transcript(surface="telegram", chat_id="c1", direction="out", agent="main", message_text="hi back")

    reply, _, _, _ = handler.handle(
        "/export",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram", chat_id="c1", account_id="primary",
    )
    assert "You:" in reply
    assert "Assistant:" in reply
    assert "hello" in reply
    assert "hi back" in reply


def test_export_empty_transcript(tmp_path):
    handler, _ = _make_handler_with_memory(tmp_path)
    reply, _, _, _ = handler.handle(
        "/export",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram", chat_id="c1", account_id="primary",
    )
    assert "No transcript" in reply
