# Phase 3D — Context Assembly Caching Design

**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Add mtime-based file-content caching to `ContextBuilder` so `load_agent_context` stops re-reading unchanged agent files on every message.

---

## Problem

`ContextBuilder.load_agent_context` reads up to 8 files on every inbound message:

- `AGENT.md`, `USER.md`, `MEMORY.md`, `TOOLS.md`, `BOOTSTRAP.md` — static persona files
- Up to 2 recent daily notes from `memory/*.md`

These files change rarely (only when the agent writes to them via `write_file`, or the user edits them manually). Re-reading them on every message is unnecessary disk I/O on every single request.

---

## Goal

Cache file contents in `ContextBuilder` using mtime as the invalidation key. If a file's mtime is unchanged since the last read, return the cached content. If mtime changed (file was edited), re-read and update the cache. This means:

- Zero stale-data risk — edits are detected immediately on the next message
- No configuration required — fully automatic
- No behavioral change for callers — `load_agent_context` signature and return type are unchanged

---

## Design

### Cache structure

Add to `ContextBuilder.__init__`:

```python
self._file_cache: dict[Path, tuple[float, str]] = {}
# path -> (mtime, content)
```

### New instance method: `_read_cached`

Replace the `@staticmethod _read_optional` with an instance method `_read_cached`:

```python
def _read_cached(self, path: Path) -> str:
    if not path.exists():
        self._file_cache.pop(path, None)
        return ""
    mtime = path.stat().st_mtime
    cached = self._file_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    content = path.read_text(encoding="utf-8").strip()
    self._file_cache[path] = (mtime, content)
    return content
```

Behaviour:
- **Missing file** — evicts any cached entry, returns `""`
- **Cache hit** — mtime matches → return cached content, no disk read
- **Cache miss** — first access or mtime changed → read from disk, store `(mtime, content)`

### Call site changes

In `load_agent_context`, replace all `self._read_optional(...)` calls with `self._read_cached(...)`:

```python
agent_md=self._read_cached(agent_dir / "AGENT.md"),
user_md=self._read_cached(agent_dir / "USER.md"),
memory_md=self._read_cached(agent_dir / "MEMORY.md"),
tools_md=self._read_cached(agent_dir / "TOOLS.md"),
recent_daily_notes=self._load_recent_daily_notes(agent_dir / "memory"),
bootstrap_md=self._read_cached(agent_dir / "BOOTSTRAP.md"),
```

In `_load_recent_daily_notes`, replace `self._read_optional(path)` with `self._read_cached(path)`.

### Remove `_read_optional`

The static method is no longer needed. Delete it.

---

## What Is Not Changing

- `AgentContext` dataclass — unchanged
- `build_prompt` — unchanged
- Daily notes glob logic — unchanged (the `glob("*.md")` directory scan stays; only the individual file reads are cached)
- All callers of `load_agent_context` in `router.py`, `compaction.py`, `chat_session.py`, `mcp_server.py` — unchanged signatures

---

## Thread Safety

CPython's GIL makes simple dict reads and assignments safe under concurrent access. This is a personal assistant with low message concurrency; no explicit lock is needed.

---

## Testing

| Test | File |
|------|------|
| Cache hit: second call with unchanged mtime skips disk read | `tests/test_context_builder.py` |
| Cache miss: call after mtime change re-reads file | `tests/test_context_builder.py` |
| Missing file: returns `""` and evicts cache entry | `tests/test_context_builder.py` |
| File created after first call: detected on next call | `tests/test_context_builder.py` |
| `load_agent_context` returns correct content from cache | `tests/test_context_builder.py` |

---

## Files Touched

| File | Change |
|------|--------|
| `app/context_builder.py` | Add `_file_cache` dict, add `_read_cached` instance method, update call sites, remove `_read_optional` |
| `tests/test_context_builder.py` | New or extended tests for caching behaviour |
