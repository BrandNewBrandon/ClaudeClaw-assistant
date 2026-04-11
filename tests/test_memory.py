from __future__ import annotations

from pathlib import Path

from app.memory import MemoryStore


def test_memory_store_reads_long_term_memory_file(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agent_dir = agents_dir / "main"
    agent_dir.mkdir(parents=True)
    (agent_dir / "MEMORY.md").write_text("Knows Brandon likes local-first tools.", encoding="utf-8")

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    assert store.read_long_term_memory("main") == "Knows Brandon likes local-first tools."


def test_memory_store_returns_relevant_memory_snippets(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agent_dir = agents_dir / "main"
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True)
    (agent_dir / "MEMORY.md").write_text(
        "Brandon likes OpenClaw-style assistants.\nHe prefers concise updates.",
        encoding="utf-8",
    )
    (memory_dir / "2026-04-04.md").write_text(
        "Tested Telegram runtime on Mac and fixed packaging issues.",
        encoding="utf-8",
    )
    (memory_dir / "2026-04-05.md").write_text(
        "Worked on multi-account routing and latency instrumentation.",
        encoding="utf-8",
    )

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    snippets = store.find_relevant_memory("main", "What did we do for multi-account routing on Telegram?", limit=3)

    assert snippets
    joined = "\n".join(snippets)
    assert "multi-account routing" in joined


def test_memory_store_returns_empty_when_no_relevant_snippets(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")

    assert store.find_relevant_memory("main", "browser automation", limit=3) == []


def test_find_relevant_memory_keyword_fallback_when_semantic_disabled(tmp_path: Path) -> None:
    """When semantic=False, keyword search is used even if fastembed is installed."""
    agents_dir = tmp_path / "agents"
    agent_dir = agents_dir / "main"
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True)
    (agent_dir / "MEMORY.md").write_text(
        "Set up multi-account routing for Telegram bots.",
        encoding="utf-8",
    )

    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=agents_dir)

    snippets = store.find_relevant_memory("main", "routing", limit=3, semantic=False)

    assert snippets
    assert "routing" in "\n".join(snippets).lower()


def test_transcript_path_includes_agent_name(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    path = store.transcript_path("telegram", "123", account_id="primary", agent_name="main")
    assert path.name == "telegram-primary-123-main.jsonl"


def test_append_transcript_scopes_by_agent(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    store.append_transcript(
        surface="telegram", account_id="primary", chat_id="123",
        direction="in", agent="main", message_text="Hello from main",
    )
    store.append_transcript(
        surface="telegram", account_id="primary", chat_id="123",
        direction="in", agent="builder", message_text="Hello from builder",
    )
    main_path = store.transcript_path("telegram", "123", account_id="primary", agent_name="main")
    builder_path = store.transcript_path("telegram", "123", account_id="primary", agent_name="builder")
    assert main_path != builder_path
    assert main_path.exists()
    assert builder_path.exists()
    assert "Hello from main" in main_path.read_text(encoding="utf-8")
    assert "Hello from builder" not in main_path.read_text(encoding="utf-8")


def test_read_recent_transcript_scoped_by_agent(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    store.append_transcript(
        surface="telegram", account_id="primary", chat_id="123",
        direction="in", agent="main", message_text="main message",
    )
    store.append_transcript(
        surface="telegram", account_id="primary", chat_id="123",
        direction="in", agent="builder", message_text="builder message",
    )
    main_entries = store.read_recent_transcript(
        "telegram", "123", account_id="primary", agent_name="main"
    )
    builder_entries = store.read_recent_transcript(
        "telegram", "123", account_id="primary", agent_name="builder"
    )
    assert any("main message" in e.message_text for e in main_entries)
    assert not any("builder message" in e.message_text for e in main_entries)
    assert any("builder message" in e.message_text for e in builder_entries)
    assert not any("main message" in e.message_text for e in builder_entries)


def test_read_transcript_with_compaction_scoped_by_agent(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    store.append_transcript(
        surface="telegram", account_id="primary", chat_id="123",
        direction="in", agent="main", message_text="only main sees this",
    )
    summary, entries = store.read_transcript_with_compaction(
        "telegram", "123", account_id="primary", agent_name="builder"
    )
    assert summary is None


def test_search_transcript_returns_matching_entries(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello world")
    store.append_transcript(surface="telegram", chat_id="c1", direction="out", agent="main", message_text="hi there")
    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="goodbye world")

    results = store.search_transcript("telegram", "c1", "world", agent_name="main")
    assert len(results) == 2
    assert results[0].message_text == "hello world"
    assert results[1].message_text == "goodbye world"


def test_search_transcript_no_matches(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text="hello")
    results = store.search_transcript("telegram", "c1", "xyz", agent_name="main")
    assert len(results) == 0


def test_search_transcript_respects_limit(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    for i in range(20):
        store.append_transcript(surface="telegram", chat_id="c1", direction="in", agent="main", message_text=f"match {i}")
    results = store.search_transcript("telegram", "c1", "match", agent_name="main", limit=5)
    assert len(results) == 5


def test_concurrent_transcript_writes(tmp_path: Path) -> None:
    """Concurrent writes should not corrupt the transcript file."""
    import threading
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(20):
                store.append_transcript(
                    surface="telegram", chat_id="c1", direction="in",
                    agent="main", message_text=f"thread-{n}-msg-{i}",
                )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    entries = store.read_recent_transcript("telegram", "c1", limit=200, agent_name="main")
    assert len(entries) == 80  # 4 threads × 20 messages
