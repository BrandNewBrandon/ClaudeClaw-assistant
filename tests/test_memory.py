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
