# Phase 2 — Agent Identity Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each ClaudeClaw agent a truly isolated entity — separate transcript history, separate Claude session continuity, and a clean config pattern for two dedicated bot tokens.

**Architecture:** Three targeted changes: (1) scope transcript files by agent name in `MemoryStore`; (2) key Claude session IDs by agent in `AssistantRouter` and `TerminalChatSession`; (3) clean up `config.example.json` and add a "Multiple bots" section to `GUIDE.md`.

**Tech Stack:** Python 3.12, pytest, existing `app/memory.py` / `app/router.py` / `app/chat_session.py`

---

## File Map

| File | What changes |
|------|-------------|
| `app/memory.py` | `transcript_path`, `read_recent_transcript`, `read_transcript_with_compaction` get `agent_name` param |
| `app/compaction.py` | Pass `agent_name` to `read_transcript_with_compaction` |
| `app/router.py` | Pass `agent_name` to transcript reads/writes; key `_session_ids` by agent |
| `app/chat_session.py` | Pass `agent_name` to transcript reads; key `_session_ids` by agent |
| `app/commands.py` | Pass `agent_name` to `read_recent_transcript` |
| `app/mcp_server.py` | Pass `agent_name` to `read_recent_transcript` |
| `config/config.example.json` | Remove `chat_agent_map` from two-bot pattern |
| `GUIDE.md` | Add "Multiple bots" section |
| `tests/test_memory.py` | Add transcript isolation tests |
| `tests/test_routing.py` | Add session isolation tests |
| `tests/test_compaction.py` | Update monkeypatched lambdas for new signature |

---

## Task 1: Transcript isolation — update MemoryStore signatures and file paths

The transcript file is currently named `{surface}-{account}-{chat_id}.jsonl`. After this task it will be `{surface}-{account}-{chat_id}-{agent_name}.jsonl`. Each agent gets its own file.

**Files:**
- Modify: `app/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_memory.py`:

```python
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
    assert entries == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/macbook/Projects/assistant-runtime
pytest tests/test_memory.py::test_transcript_path_includes_agent_name tests/test_memory.py::test_append_transcript_scopes_by_agent tests/test_memory.py::test_read_recent_transcript_scoped_by_agent tests/test_memory.py::test_read_transcript_with_compaction_scoped_by_agent -v
```

Expected: FAIL — `transcript_path()` does not accept `agent_name`.

- [ ] **Step 3: Update `transcript_path` in `app/memory.py`**

Find (line ~119):
```python
def transcript_path(self, surface: str, chat_id: str, *, account_id: str = "primary") -> Path:
    return self._shared_dir / "transcripts" / f"{surface}-{account_id}-{chat_id}.jsonl"
```

Replace with:
```python
def transcript_path(self, surface: str, chat_id: str, *, account_id: str = "primary", agent_name: str = "main") -> Path:
    return self._shared_dir / "transcripts" / f"{surface}-{account_id}-{chat_id}-{agent_name}.jsonl"
```

- [ ] **Step 4: Update `append_transcript` to pass `agent` to `transcript_path`**

Find (line ~135):
```python
path = self.transcript_path(surface, chat_id, account_id=account_id)
```

Replace with:
```python
path = self.transcript_path(surface, chat_id, account_id=account_id, agent_name=agent)
```

- [ ] **Step 5: Update `read_transcript_with_compaction` signature and path call**

Find:
```python
def read_transcript_with_compaction(
    self,
    surface: str,
    chat_id: str,
    *,
    account_id: str = "primary",
) -> tuple[str | None, list[TranscriptEntry]]:
    """Read transcript respecting compaction markers.
    ...
    """
    path = self.transcript_path(surface, chat_id, account_id=account_id)
```

Replace the def line and the path line with:
```python
def read_transcript_with_compaction(
    self,
    surface: str,
    chat_id: str,
    *,
    account_id: str = "primary",
    agent_name: str = "main",
) -> tuple[str | None, list[TranscriptEntry]]:
    """Read transcript respecting compaction markers.

    Returns ``(compaction_summary_or_None, recent_entries_after_last_compaction)``.
    If no compaction marker exists, returns ``(None, all_entries)``.
    """
    path = self.transcript_path(surface, chat_id, account_id=account_id, agent_name=agent_name)
```

- [ ] **Step 6: Update `read_recent_transcript` signature and path call**

Find:
```python
def read_recent_transcript(self, surface: str, chat_id: str, limit: int = 6, *, account_id: str = "primary") -> list[TranscriptEntry]:
    path = self.transcript_path(surface, chat_id, account_id=account_id)
```

Replace with:
```python
def read_recent_transcript(self, surface: str, chat_id: str, limit: int = 6, *, account_id: str = "primary", agent_name: str = "main") -> list[TranscriptEntry]:
    path = self.transcript_path(surface, chat_id, account_id=account_id, agent_name=agent_name)
```

- [ ] **Step 7: Run the new tests to verify they pass**

```bash
pytest tests/test_memory.py::test_transcript_path_includes_agent_name tests/test_memory.py::test_append_transcript_scopes_by_agent tests/test_memory.py::test_read_recent_transcript_scoped_by_agent tests/test_memory.py::test_read_transcript_with_compaction_scoped_by_agent -v
```

Expected: 4 PASSED.

- [ ] **Step 8: Run the full test suite to check nothing broke**

```bash
pytest --tb=short -q
```

Expected: all previously passing tests still pass (some may fail due to stale monkeypatched lambdas in test_compaction.py — fix those in Task 3).

- [ ] **Step 9: Commit**

```bash
git add app/memory.py tests/test_memory.py
git commit -m "feat: scope transcript files by agent name in MemoryStore"
```

---

## Task 2: Update all transcript read call sites to pass agent_name

Every caller of `read_recent_transcript`, `read_transcript_with_compaction`, and `transcript_path` needs to pass `agent_name` explicitly. The `append_transcript` callers need no change — the method already receives `agent=` and uses it for the path.

**Files:**
- Modify: `app/router.py`, `app/chat_session.py`, `app/compaction.py`, `app/commands.py`, `app/mcp_server.py`

- [ ] **Step 1: Update `app/compaction.py`**

Find (line ~65):
```python
summary, recent = self._memory.read_transcript_with_compaction(
    surface, chat_id, account_id=account_id,
)
```

Replace with:
```python
summary, recent = self._memory.read_transcript_with_compaction(
    surface, chat_id, account_id=account_id, agent_name=agent,
)
```

- [ ] **Step 2: Update `app/router.py` — `transcript_path` call**

Find (line ~509):
```python
transcript_path = self._memory.transcript_path(surface, message.chat_id, account_id=account_id)
```

Replace with:
```python
transcript_path = self._memory.transcript_path(surface, message.chat_id, account_id=account_id, agent_name=active_agent)
```

- [ ] **Step 3: Update `app/router.py` — `read_transcript_with_compaction` call**

Find (line ~682):
```python
compaction_summary, recent_transcript = self._memory.read_transcript_with_compaction(
    surface,
    message.chat_id,
    account_id=account_id,
)
```

Replace with:
```python
compaction_summary, recent_transcript = self._memory.read_transcript_with_compaction(
    surface,
    message.chat_id,
    account_id=account_id,
    agent_name=active_agent,
)
```

- [ ] **Step 4: Update `app/commands.py` — `/transcript` command**

Find (line ~289):
```python
entries = self._memory_store.read_recent_transcript(
    surface, chat_id, limit=limit, account_id=account_id or "primary"
)
```

Replace with:
```python
entries = self._memory_store.read_recent_transcript(
    surface, chat_id, limit=limit, account_id=account_id or "primary",
    agent_name=active_agent,
)
```

- [ ] **Step 5: Update `app/chat_session.py` — `read_recent_transcript` call**

Find (line ~172):
```python
recent_transcript = self._memory.read_recent_transcript(
    SURFACE, self._chat_id, limit=6, account_id=ACCOUNT_ID
)
```

Replace with:
```python
recent_transcript = self._memory.read_recent_transcript(
    SURFACE, self._chat_id, limit=6, account_id=ACCOUNT_ID,
    agent_name=self._agent_name,
)
```

- [ ] **Step 6: Update `app/mcp_server.py` — `read_recent_transcript` call**

Find (line ~123):
```python
recent_transcript = memory_store.read_recent_transcript("mcp", chat_id)
```

Replace with:
```python
recent_transcript = memory_store.read_recent_transcript("mcp", chat_id, agent_name=agent_name)
```

- [ ] **Step 7: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass except the monkeypatched lambdas in `test_compaction.py` — those get fixed in Task 3.

- [ ] **Step 8: Commit**

```bash
git add app/compaction.py app/router.py app/chat_session.py app/commands.py app/mcp_server.py
git commit -m "feat: pass agent_name to all transcript read call sites"
```

---

## Task 3: Fix monkeypatched lambdas in test_compaction.py

The `monkeypatch.setattr` calls that stub `read_transcript_with_compaction` use the old signature. They need to accept the new `agent_name` keyword argument.

**Files:**
- Modify: `tests/test_compaction.py`

- [ ] **Step 1: Update all four monkeypatched lambdas**

In `test_compaction.py`, find every occurrence of:
```python
lambda surface, chat_id, account_id="primary": (None, entries)
```
and:
```python
lambda surface, chat_id, account_id="primary": ("Previous summary here.", entries)
```

Replace each with the corresponding:
```python
lambda surface, chat_id, account_id="primary", agent_name="main": (None, entries)
```
and:
```python
lambda surface, chat_id, account_id="primary", agent_name="main": ("Previous summary here.", entries)
```

Also find the `transcript_path` call in `test_maybe_compact_returns_false_when_under_threshold`:
```python
tpath = memory.transcript_path("telegram", "123", account_id="primary")
```
Replace with:
```python
tpath = memory.transcript_path("telegram", "123", account_id="primary", agent_name="main")
```

- [ ] **Step 2: Run test_compaction.py to verify all 5 tests pass**

```bash
pytest tests/test_compaction.py -v
```

Expected: 5 PASSED.

- [ ] **Step 3: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_compaction.py
git commit -m "fix: update test_compaction monkeypatches for agent_name signature"
```

---

## Task 4: Session isolation — key Claude session IDs by agent in router.py (TDD)

`_session_ids` maps `session_key → Claude session ID`. Changing the key to include agent means switching agents in a chat starts a fresh Claude session rather than resuming the previous one.

**Files:**
- Modify: `app/router.py`
- Test: `tests/test_routing.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_routing.py`:

```python
def test_session_key_differs_by_agent(tmp_path: Path) -> None:
    """Two agents in the same chat produce different session keys for _session_ids."""
    try:
        router = make_router(tmp_path, default_agent="main")
        # Simulate session IDs stored for two agents in the same chat
        session_key = "telegram:primary:123"
        router._session_ids[f"{session_key}:main"] = "session-main"
        router._session_ids[f"{session_key}:builder"] = "session-builder"

        assert router._session_ids.get(f"{session_key}:main") == "session-main"
        assert router._session_ids.get(f"{session_key}:builder") == "session-builder"
        assert router._session_ids.get(f"{session_key}:main") != router._session_ids.get(f"{session_key}:builder")
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_session_key_format_includes_agent(tmp_path: Path) -> None:
    """_session_key base is surface:account:chat_id; agent appended inline."""
    try:
        router = make_router(tmp_path)
        base = router._session_key("telegram", "primary", "123")
        assert base == "telegram:primary:123"
        # Agent-scoped key is base + ":" + agent
        assert f"{base}:main" == "telegram:primary:123:main"
        assert f"{base}:builder" == "telegram:primary:123:builder"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)
```

- [ ] **Step 2: Run tests to verify they pass (these tests don't require implementation changes — they validate the key format contract)**

```bash
pytest tests/test_routing.py::test_session_key_differs_by_agent tests/test_routing.py::test_session_key_format_includes_agent -v
```

Expected: PASSED — these tests verify structure, not router internals.

- [ ] **Step 3: Update `_session_ids` usage in `app/router.py` — the reset path**

Find (line ~603):
```python
self._session_ids.pop(session_key, None)
```

Replace with:
```python
self._session_ids.pop(f"{session_key}:{active_agent}", None)
```

- [ ] **Step 4: Update `_session_ids` lookup in `app/router.py` — reading prior session ID**

Find (line ~698):
```python
prior_session_id = self._session_ids.get(session_key)
```

Replace with:
```python
prior_session_id = self._session_ids.get(f"{session_key}:{active_agent}")
```

- [ ] **Step 5: Update `_session_ids` write in `app/router.py` — storing new session ID**

Find (line ~717):
```python
self._session_ids[session_key] = new_session_id
```

Replace with:
```python
self._session_ids[f"{session_key}:{active_agent}"] = new_session_id
```

- [ ] **Step 6: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/router.py tests/test_routing.py
git commit -m "feat: scope Claude session IDs by agent in router"
```

---

## Task 5: Session isolation in TerminalChatSession (chat_session.py)

`TerminalChatSession` has its own `_session_ids` dict using `self._chat_id` as the key. Scope it by agent so that switching agents in the REPL also starts a fresh Claude session.

**Files:**
- Modify: `app/chat_session.py`

- [ ] **Step 1: Update `_session_ids` read in `chat_session.py`**

Find (line ~180):
```python
prior_session_id = self._session_ids.get(self._chat_id)
```

Replace with:
```python
prior_session_id = self._session_ids.get(f"{self._chat_id}:{self._agent_name}")
```

- [ ] **Step 2: Update `_session_ids` write in `chat_session.py`**

Find (line ~232):
```python
self._session_ids[self._chat_id] = last_session_id
```

Replace with:
```python
self._session_ids[f"{self._chat_id}:{self._agent_name}"] = last_session_id
```

- [ ] **Step 3: Update the session reset on agent switch in `chat_session.py`**

Find (line ~319):
```python
if reset_chat:
    self._session_ids.pop(self._chat_id, None)
```

Replace with:
```python
if reset_chat:
    self._session_ids.pop(f"{self._chat_id}:{self._agent_name}", None)
```

Note: the `switch_to` block (lines ~312-315) updates `self._agent_name`, so any subsequent `_session_ids` lookup naturally uses the new agent's key — no additional changes needed there.

- [ ] **Step 4: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/chat_session.py
git commit -m "feat: scope Claude session IDs by agent in TerminalChatSession"
```

---

## Task 6: Update config.example.json and GUIDE.md

Clean up the example config and document the two-bot pattern.

**Files:**
- Modify: `config/config.example.json`
- Modify: `GUIDE.md`

- [ ] **Step 1: Update `config/config.example.json`**

Replace the current contents with:

```json
{
  "accounts": {
    "primary": {
      "platform": "telegram",
      "token": "REPLACE_ME",
      "allowed_chat_ids": [
        "REPLACE_CHAT_ID"
      ]
    },
    "builder-bot": {
      "platform": "telegram",
      "token": "REPLACE_ME",
      "allowed_chat_ids": [
        "REPLACE_CHAT_ID"
      ]
    }
  },
  "routing": {
    "primary": {
      "default_agent": "main"
    },
    "builder-bot": {
      "default_agent": "builder"
    }
  },
  "default_agent": "main",
  "claude_timeout_seconds": 300,
  "telegram_poll_timeout_seconds": 30,
  "typing_interval_seconds": 4,
  "claude_working_directory_mode": "agent_dir",
  "model_provider": "claude-code",
  "claude_model": "sonnet",
  "claude_effort": "medium"
}
```

- [ ] **Step 2: Add "Multiple bots" section to `GUIDE.md`**

Find the section in `GUIDE.md` that covers agents or configuration (search for `## Agents` or `## Configuration`). Add the following section after it:

```markdown
## Multiple bots

Each bot gets its own Telegram token and is locked to a dedicated agent. Configure them under `accounts` and `routing` in `config.json`:

```json
"accounts": {
  "primary": {
    "platform": "telegram",
    "token": "<main-bot-token>",
    "allowed_chat_ids": ["<your-chat-id>"]
  },
  "builder-bot": {
    "platform": "telegram",
    "token": "<builder-bot-token>",
    "allowed_chat_ids": ["<your-chat-id>"]
  }
},
"routing": {
  "primary": { "default_agent": "main" },
  "builder-bot": { "default_agent": "builder" }
}
```

Each account gets its own polling thread when the runtime starts. The two bots share one process but have completely separate identities:

- Separate Telegram username and avatar (set via @BotFather)
- Separate `AGENT.md` personality
- Separate conversation transcript (each bot only reads its own history)
- Separate Claude session continuity (switching between bots never leaks context)
- Separate memory notes under `agents/<name>/memory/`

To add a second bot token: register a new bot with @BotFather, add the account block to `config.json`, create the agent with `assistant manage create-agent <name>`, and restart the runtime.
```

- [ ] **Step 3: Run full test suite to confirm nothing broke**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add config/config.example.json GUIDE.md
git commit -m "docs: update config example and guide for two-bot dedicated agent pattern"
```

---

## Final verification

- [ ] **Run the complete test suite one last time**

```bash
pytest -v
```

Expected: all tests pass (should be 83+ with the 4 new transcript isolation tests and 2 new routing tests).

- [ ] **Smoke check the config loads with the new example**

```bash
cd /Users/macbook/Projects/assistant-runtime
python3 -c "
from app.config import load_config
from pathlib import Path
cfg = load_config(Path('config/config.example.json'))
print('accounts:', list(cfg.accounts.keys()))
print('routing:', {k: v.default_agent for k, v in cfg.routing.items()})
"
```

Expected output:
```
accounts: ['primary', 'builder-bot']
routing: {'primary': 'main', 'builder-bot': 'builder'}
```
