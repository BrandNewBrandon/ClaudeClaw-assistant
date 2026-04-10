# Phase 3D — Context Assembly Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add mtime-based file-content caching to `ContextBuilder` so agent context files are only re-read from disk when they actually change.

**Architecture:** A `_file_cache: dict[Path, tuple[float, str]]` dict on `ContextBuilder` stores `(mtime, content)` per file. A new instance method `_read_cached` checks mtime before reading; it replaces the existing `_read_optional` static method at all call sites. No change to `AgentContext`, `build_prompt`, or any caller outside `context_builder.py`.

**Tech Stack:** Python 3.11+, pathlib, pytest

---

## File Map

| File | Change |
|------|--------|
| `app/context_builder.py` | Add `_file_cache` to `__init__`, add `_read_cached` instance method, update 6 call sites in `load_agent_context` + 1 in `_load_recent_daily_notes`, remove `_read_optional` |
| `tests/test_context_builder.py` | Add 5 new tests for caching behaviour (cache hit, cache miss, missing file, file created after first call, integration through `load_agent_context`) |

---

## Task 1: `_read_cached` method and cache tests

**Files:**
- Modify: `app/context_builder.py`
- Modify: `tests/test_context_builder.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_context_builder.py`:

```python
def test_read_cached_returns_content(tmp_path: Path) -> None:
    """_read_cached reads and returns file content."""
    p = tmp_path / "AGENT.md"
    p.write_text("hello", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    assert builder._read_cached(p) == "hello"


def test_read_cached_cache_hit_skips_disk_read(tmp_path: Path) -> None:
    """Second call with unchanged mtime returns cached content without re-reading."""
    p = tmp_path / "AGENT.md"
    p.write_text("original", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    builder._read_cached(p)  # prime the cache

    # Overwrite content on disk but preserve mtime so cache thinks nothing changed
    mtime = p.stat().st_mtime
    p.write_text("changed", encoding="utf-8")
    import os
    os.utime(p, (mtime, mtime))  # restore original mtime

    result = builder._read_cached(p)
    assert result == "original"  # cache hit — stale disk content ignored


def test_read_cached_cache_miss_re_reads_on_mtime_change(tmp_path: Path) -> None:
    """When mtime changes, _read_cached re-reads the file."""
    p = tmp_path / "AGENT.md"
    p.write_text("v1", encoding="utf-8")
    builder = ContextBuilder(tmp_path)
    assert builder._read_cached(p) == "v1"  # prime cache

    # Write new content — filesystem will update mtime
    p.write_text("v2", encoding="utf-8")

    result = builder._read_cached(p)
    assert result == "v2"  # cache miss — new content returned


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_context_builder.py::test_read_cached_returns_content \
       tests/test_context_builder.py::test_read_cached_cache_hit_skips_disk_read \
       tests/test_context_builder.py::test_read_cached_cache_miss_re_reads_on_mtime_change \
       tests/test_context_builder.py::test_read_cached_missing_file_returns_empty_string \
       tests/test_context_builder.py::test_read_cached_evicts_entry_when_file_deleted \
       -v
```

Expected: FAIL — `AttributeError: 'ContextBuilder' object has no attribute '_read_cached'`

- [ ] **Step 3: Add `_file_cache` and `_read_cached` to `app/context_builder.py`**

In `ContextBuilder.__init__`, add the cache dict:

```python
    def __init__(self, agents_dir: Path) -> None:
        self._agents_dir = agents_dir
        self._file_cache: dict[Path, tuple[float, str]] = {}
```

Add `_read_cached` as an instance method (add it just before `_load_recent_daily_notes`):

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

Do NOT yet remove `_read_optional` or change any call sites — that's Task 2.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_context_builder.py::test_read_cached_returns_content \
       tests/test_context_builder.py::test_read_cached_cache_hit_skips_disk_read \
       tests/test_context_builder.py::test_read_cached_cache_miss_re_reads_on_mtime_change \
       tests/test_context_builder.py::test_read_cached_missing_file_returns_empty_string \
       tests/test_context_builder.py::test_read_cached_evicts_entry_when_file_deleted \
       -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/context_builder.py tests/test_context_builder.py
git commit -m "feat: add _read_cached with mtime-based invalidation to ContextBuilder"
```

---

## Task 2: Wire `_read_cached` into call sites, remove `_read_optional`

**Files:**
- Modify: `app/context_builder.py`
- Modify: `tests/test_context_builder.py`

- [ ] **Step 1: Write the integration test**

Add to `tests/test_context_builder.py`:

```python
def test_load_agent_context_uses_cache_on_second_call(tmp_path: Path) -> None:
    """Second load_agent_context call for same agent reuses cached file content."""
    agent_dir = tmp_path / "main"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text("agent persona", encoding="utf-8")
    (agent_dir / "USER.md").write_text("user profile", encoding="utf-8")

    builder = ContextBuilder(tmp_path)
    ctx1 = builder.load_agent_context("main")
    assert ctx1.agent_md == "agent persona"

    # Overwrite on disk but freeze mtime so cache hit fires
    import os
    p = agent_dir / "AGENT.md"
    mtime = p.stat().st_mtime
    p.write_text("new persona", encoding="utf-8")
    os.utime(p, (mtime, mtime))

    ctx2 = builder.load_agent_context("main")
    assert ctx2.agent_md == "agent persona"  # served from cache
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_context_builder.py::test_load_agent_context_uses_cache_on_second_call -v
```

Expected: FAIL — `AssertionError: assert 'new persona' == 'agent persona'` (call sites still use `_read_optional`)

- [ ] **Step 3: Update `load_agent_context` to use `_read_cached`**

In `app/context_builder.py`, update `load_agent_context` (lines 25–39). Replace all `self._read_optional(...)` calls:

```python
    def load_agent_context(self, agent_name: str) -> AgentContext:
        agent_dir = self._agents_dir / agent_name
        if not agent_dir.exists():
            raise FileNotFoundError(f"Agent directory not found: {agent_dir}")

        return AgentContext(
            agent_name=agent_name,
            agent_dir=agent_dir,
            agent_md=self._read_cached(agent_dir / "AGENT.md"),
            user_md=self._read_cached(agent_dir / "USER.md"),
            memory_md=self._read_cached(agent_dir / "MEMORY.md"),
            tools_md=self._read_cached(agent_dir / "TOOLS.md"),
            recent_daily_notes=self._load_recent_daily_notes(agent_dir / "memory"),
            bootstrap_md=self._read_cached(agent_dir / "BOOTSTRAP.md"),
        )
```

- [ ] **Step 4: Update `_load_recent_daily_notes` to use `_read_cached`**

In `_load_recent_daily_notes` (lines 173–185), change the line that reads each note file:

```python
    def _load_recent_daily_notes(self, memory_dir: Path) -> str:
        if not memory_dir.exists():
            return ""

        files = sorted(memory_dir.glob("*.md"), reverse=True)
        recent = []
        for path in files:
            if path.name.upper() == "README.MD":
                continue
            recent.append(f"# {path.name}\n{self._read_cached(path)}")
            if len(recent) >= 2:
                break
        return "\n\n".join(recent)
```

- [ ] **Step 5: Remove `_read_optional`**

Delete the entire `_read_optional` static method (lines 187–207 in original file, now at the bottom):

```python
    # DELETE THIS ENTIRE METHOD:
    @staticmethod
    def _read_optional(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()
```

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```

Expected: ALL PASS — 99 total (98 existing + 1 new integration test)

- [ ] **Step 7: Commit**

```bash
git add app/context_builder.py tests/test_context_builder.py
git commit -m "feat: wire _read_cached into load_agent_context and daily notes, remove _read_optional"
```
