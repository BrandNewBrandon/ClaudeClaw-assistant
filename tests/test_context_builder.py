from __future__ import annotations

import os
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


def test_read_cached_returns_content(tmp_path: Path) -> None:
    """_read_cached reads and returns file content."""
    p = tmp_path / "AGENT.md"
    p.write_text("hello", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    assert builder._read_cached(p) == "hello"


def test_read_cached_cache_hit_skips_disk_read(tmp_path: Path) -> None:
    """Same (mtime_ns, size) returns cached content without re-reading."""
    p = tmp_path / "AGENT.md"
    p.write_text("original", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    builder._read_cached(p)  # prime the cache

    # Overwrite with same-length content and restore mtime at nanosecond
    # precision so the (mtime_ns, size) cache key is byte-identical.
    st = p.stat()
    p.write_text("modified", encoding="utf-8")  # also 8 bytes
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))

    result = builder._read_cached(p)
    assert result == "original"  # cache hit — stale disk content ignored


def test_read_cached_cache_miss_re_reads_on_size_change(tmp_path: Path) -> None:
    """When file size changes, _read_cached re-reads even if mtime is identical."""
    p = tmp_path / "AGENT.md"
    p.write_text("v1", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    assert builder._read_cached(p) == "v1"  # prime cache

    # Different-length content. Even if the filesystem mtime resolution is coarse
    # and happens to match, the size guard forces a re-read.
    st = p.stat()
    p.write_text("v2-longer", encoding="utf-8")
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # pin mtime; size alone triggers miss

    result = builder._read_cached(p)
    assert result == "v2-longer"


def test_read_cached_cache_miss_re_reads_on_mtime_change(tmp_path: Path) -> None:
    """When mtime_ns changes, _read_cached re-reads the file."""
    p = tmp_path / "AGENT.md"
    p.write_text("aa", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    assert builder._read_cached(p) == "aa"  # prime cache

    # Same-size different content. Bump mtime forward by 2 seconds so it's
    # unambiguous regardless of filesystem timestamp resolution.
    p.write_text("bb", encoding="utf-8")
    future = p.stat().st_mtime + 2
    os.utime(p, (future, future))

    result = builder._read_cached(p)
    assert result == "bb"


def test_read_cached_missing_file_returns_empty_string(tmp_path: Path) -> None:
    """Missing file returns '' and does not store a cache entry."""
    builder = ContextBuilder(tmp_path)
    p = tmp_path / "NONEXISTENT.md"
    assert builder._read_cached(p) == ""
    assert p not in builder._file_cache


def test_read_cached_evicts_entry_when_file_deleted(tmp_path: Path) -> None:
    """If a file is deleted after being cached, _read_cached returns '' and evicts entry."""
    p = tmp_path / "AGENT.md"
    p.write_text("hello", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    builder._read_cached(p)  # prime cache
    assert p in builder._file_cache

    p.unlink()  # delete the file
    result = builder._read_cached(p)
    assert result == ""
    assert p not in builder._file_cache


def test_load_agent_context_uses_cache_on_second_call(tmp_path: Path) -> None:
    """Second load_agent_context call for same agent reuses cached file content."""
    agent_dir = tmp_path / "main"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text("agent persona", encoding="utf-8")
    (agent_dir / "USER.md").write_text("user profile", encoding="utf-8")

    builder = ContextBuilder(tmp_path)
    ctx1 = builder.load_agent_context("main")
    assert ctx1.agent_md == "agent persona"

    # Overwrite on disk with same-length content and freeze mtime at ns
    # precision so the (mtime_ns, size) cache key is byte-identical.
    p = agent_dir / "AGENT.md"
    st = p.stat()
    p.write_text("AGENT_PERSONA", encoding="utf-8")  # same 13 bytes as "agent persona"
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))

    ctx2 = builder.load_agent_context("main")
    assert ctx2.agent_md == "agent persona"  # served from cache


def test_format_relevant_memory_respects_content(tmp_path: Path) -> None:
    """Relevant memory block renders all provided snippets."""
    builder = ContextBuilder(tmp_path)
    snippets = [
        "**decision**: Use flat files\nKeep it simple.",
        "**discovery**: User prefers terse output\nNo essays.",
    ]
    result = builder._format_relevant_memory(snippets)
    assert "flat files" in result
    assert "terse output" in result


def test_daily_notes_tail_cap_truncates_large_files(tmp_path: Path) -> None:
    """Daily notes larger than DAILY_NOTE_TAIL_CHARS are truncated from the head."""
    mem = tmp_path / "memory"
    mem.mkdir()
    large_note = "HEADER\n" + "stale-line\n" * 2000 + "RECENT-ANCHOR\n"
    (mem / "2026-04-12.md").write_text(large_note, encoding="utf-8")

    builder = ContextBuilder(tmp_path)
    result = builder._load_recent_daily_notes(mem)

    assert "RECENT-ANCHOR" in result  # tail kept
    assert "HEADER" not in result  # head dropped
    assert "truncated" in result  # marker present
    assert len(result) < len(large_note)
    # Final block stays near the cap plus header + marker overhead.
    assert len(result) < builder.DAILY_NOTE_TAIL_CHARS + 500


def test_daily_notes_small_files_untouched(tmp_path: Path) -> None:
    """Notes under the cap pass through verbatim with no truncation marker."""
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "2026-04-13.md").write_text("just a small note", encoding="utf-8")

    builder = ContextBuilder(tmp_path)
    result = builder._load_recent_daily_notes(mem)

    assert "just a small note" in result
    assert "truncated" not in result
